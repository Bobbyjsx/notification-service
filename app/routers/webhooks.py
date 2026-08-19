import json

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status

from app.core.security import verify_resend_webhook_signature
from app.dependencies import get_webhook_processor_service
from app.schemas.webhook import ResendWebhookEvent, WebhookProcessResponse
from app.services.webhook_processor import WebhookProcessorService

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])


@router.post(
    "/resend",
    response_model=WebhookProcessResponse,
    status_code=status.HTTP_200_OK,
    summary="Resend delivery status webhook receiver",
)
async def receive_resend_webhook(
    request: Request,
    svix_id: str | None = Header(None, alias="svix-id"),
    svix_timestamp: str | None = Header(None, alias="svix-timestamp"),
    svix_signature: str | None = Header(None, alias="svix-signature"),
    processor: WebhookProcessorService = Depends(get_webhook_processor_service),
) -> WebhookProcessResponse:
    """
    Receives and processes delivery webhooks (sent, delivered, bounced, complained) from Resend.
    Verifies Svix signature headers.
    """
    body_bytes = await request.body()

    # 1. Verify Svix signature
    try:
        verify_resend_webhook_signature(
            payload_body=body_bytes,
            svix_id=svix_id,
            svix_timestamp=svix_timestamp,
            svix_signature=svix_signature,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Webhook signature verification failed: {exc}",
        ) from exc

    # 2. Parse payload into event schema
    try:
        raw_json = json.loads(body_bytes.decode("utf-8"))
        event = ResendWebhookEvent(**raw_json)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid webhook JSON structure: {exc}",
        ) from exc

    # 3. Process event idempotently
    return await processor.process_webhook_event(event)
