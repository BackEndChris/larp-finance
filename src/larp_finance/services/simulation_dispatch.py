import logging
from datetime import timedelta

from kombu.exceptions import OperationalError
from redis.exceptions import RedisError
from sqlalchemy import and_, func, or_, select

from larp_finance.models import Simulation
from larp_finance.services.simulation_processing import clear_claim, MAX_PROCESSING_ATTEMPTS


logger = logging.getLogger(__name__)
MAX_DISPATCH_ATTEMPTS = 12
RECOVERY_BATCH_SIZE = 50


def dispatch_simulations(db, simulation_id=None):
    """Simulation rows are the durable queue; publish only committed rows."""
    from larp_finance.tasks import process_simulation_task

    due = or_(
        and_(Simulation.status == "pending", Simulation.next_dispatch_at <= func.clock_timestamp()),
        and_(Simulation.status == "running", or_(
            Simulation.lease_expires_at.is_(None),
            Simulation.lease_expires_at <= func.clock_timestamp(),
        )),
    )
    seen = []
    for _ in range(RECOVERY_BATCH_SIZE):
        query = select(Simulation).where(due)
        if simulation_id is not None:
            query = query.where(Simulation.id == simulation_id)
        if seen:
            query = query.where(Simulation.id.not_in(seen))
        simulation = db.scalar(
            query.order_by(Simulation.next_dispatch_at, Simulation.id).limit(1)
            .with_for_update(skip_locked=True).execution_options(populate_existing=True)
        )
        if simulation is None:
            db.rollback()
            break
        seen.append(simulation.id)
        if (simulation.dispatch_attempts >= MAX_DISPATCH_ATTEMPTS
                or simulation.processing_attempts >= MAX_PROCESSING_ATTEMPTS):
            simulation.status = "failed"
            simulation.error_message = "Simulation recovery attempts exhausted"
            clear_claim(simulation)
            db.commit()
            continue
        simulation.status = "pending"
        clear_claim(simulation)
        simulation.dispatch_attempts += 1
        now = db.scalar(select(func.clock_timestamp()))
        simulation.next_dispatch_at = now + timedelta(
            seconds=min(60 * simulation.dispatch_attempts, 300)
        )
        try:
            process_simulation_task.apply_async(args=[simulation.id], retry=False)
        except (OperationalError, RedisError, OSError):
            logger.warning("Simulation %s publication failed; recovery scheduled", simulation.id)
        db.commit()
    return len(seen)
