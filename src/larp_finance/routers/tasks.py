from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from kombu.exceptions import OperationalError
from redis.exceptions import RedisError
from pydantic import BaseModel

from larp_finance.auth import get_current_user
from larp_finance.celery_app import celery_app
from larp_finance.models import User
from larp_finance.tasks import add_numbers


router = APIRouter(
    prefix="/tasks",
    tags=["Tasks"],
)


class AddNumbersRequest(BaseModel):
    a: int
    b: int


@router.post("/add", status_code=status.HTTP_202_ACCEPTED)
def submit_addition(
    data: AddNumbersRequest,
    current_user: User = Depends(get_current_user),
):
    try:
        task = add_numbers.delay(data.a, data.b)
    except OperationalError:
        raise HTTPException(
            status_code=503,
            detail="Task queue temporarily unavailable",
        )

    return {
        "task_id": task.id,
        "status": "submitted",
    }


@router.get("/{task_id}")
def get_task_status(
    task_id: UUID,
    current_user: User = Depends(get_current_user),
):
    try:
        task = celery_app.AsyncResult(str(task_id))
        return {
            "task_id": str(task_id),
            "status": task.state,
            "result": task.result if task.successful() else None,
        }
    except (RedisError, OperationalError):
        raise HTTPException(status_code=503, detail="Task results temporarily unavailable") from None
