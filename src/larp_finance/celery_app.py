import os

from celery import Celery


REDIS_URL = os.getenv(
    "REDIS_URL",
    "redis://localhost:6379/0",
)


celery_app = Celery(
    "larp_finance",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["larp_finance.tasks"],
)

celery_app.conf.update(
    broker_connection_timeout=3,
    broker_transport_options={"socket_connect_timeout": 3, "socket_timeout": 3},
    worker_prefetch_multiplier=1,
)
