"""Run alongside the API and worker: python -m larp_finance.simulation_recovery."""
import logging
from time import sleep

from sqlalchemy.exc import SQLAlchemyError

from larp_finance.database import SessionLocal
from larp_finance.services.simulation_dispatch import dispatch_simulations

logger = logging.getLogger(__name__)


def main():
    logging.basicConfig(level=logging.INFO)
    while True:
        try:
            with SessionLocal() as db:
                dispatch_simulations(db)
        except SQLAlchemyError:
            logger.exception("Simulation recovery database failure; retrying next scan")
        sleep(15)


if __name__ == "__main__":
    main()
