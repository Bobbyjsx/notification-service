from fastapi import APIRouter, Depends, status

from app.dependencies import get_delivery_worker_service, verify_cloud_tasks_caller
from app.schemas.task import EmailDeliveryTaskPayload, TaskExecutionResponse
from app.services.delivery_worker import DeliveryWorkerService

router = APIRouter(prefix="/tasks", tags=["Tasks Worker"])


@router.post(
    "/deliver-email",
    response_model=TaskExecutionResponse,
    status_code=status.HTTP_200_OK,
    summary="Cloud Tasks asynchronous email delivery worker",
)
async def deliver_email_task(
    payload: EmailDeliveryTaskPayload,
    is_authorized: bool = Depends(verify_cloud_tasks_caller),
    worker: DeliveryWorkerService = Depends(get_delivery_worker_service),
) -> TaskExecutionResponse:
    """
    Asynchronously delivers an email notification scheduled by Cloud Tasks.
    Idempotent and safe to execute multiple times.
    """
    return await worker.execute_task(payload)
