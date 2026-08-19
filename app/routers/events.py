from fastapi import APIRouter, Depends, status

from app.core.security import ServiceIdentity
from app.dependencies import get_current_service, get_event_processor_service
from app.schemas.event import (
    EventIngestResponse,
    PlatformEvent,
    PubSubPushEnvelope,
)
from app.services.event_processor import EventProcessorService

router = APIRouter(prefix="/events", tags=["Events"])


@router.post(
    "",
    response_model=EventIngestResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Ingest a platform event directly",
)
async def ingest_event(
    event: PlatformEvent,
    service: ServiceIdentity = Depends(get_current_service),
    event_processor: EventProcessorService = Depends(get_event_processor_service),
) -> EventIngestResponse:
    """
    Ingests a platform event directly from an authenticated service.
    """
    return await event_processor.process_event(event)


@router.post(
    "/pubsub",
    response_model=EventIngestResponse,
    status_code=status.HTTP_200_OK,
    summary="Pub/Sub push subscription receiver",
)
async def ingest_pubsub_event(
    envelope: PubSubPushEnvelope,
    event_processor: EventProcessorService = Depends(get_event_processor_service),
) -> EventIngestResponse:
    """
    Receives and decodes push events from Google Cloud Pub/Sub.
    Returns HTTP 200 to acknowledge the message.
    """
    event = event_processor.parse_pubsub_message(envelope)
    return await event_processor.process_event(event)
