from larp_finance.celery_app import celery_app


@celery_app.task
def add_numbers(a: int, b: int) -> int:
    return a + b
