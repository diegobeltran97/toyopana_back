from fastapi import APIRouter, HTTPException, status, Request
from schemas.webhook import (
    PipefyReceivingWebhookData,
    PipefyWebhookPayload,
    PipefyEventResponse
)
from repositories.pipefy_events import PipefyEventsRepository
from services.pipefy_service import process_card_details

from typing import Dict, Any
import logging

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post(
    "/webhook/pipefy",
    response_model=Dict[str, Any],
    status_code=status.HTTP_200_OK,
    summary="Pipefy Webhook Receiver",
    tags=["webhook"]
)
async def receive_pipefy_webhook(
    payload: PipefyWebhookPayload,
    request: Request
):
    """
    Receive and process Pipefy webhook events.

    This endpoint receives webhooks from Pipefy when card events occur
    (card.create, card.move, card.done, card.field_update, etc.)

    The webhook must be configured in Pipefy to point to this endpoint:
    POST /api/webhook/pipefy

    Expected payload structure:
    ```json
    {
        "data": {
            "action": "card.create",
            "card": {
                "id": "123456",
                "title": "Card Title",
                "pipe": {"id": "pipe_123"},
                ...
            },
            ...
        }
    }
    ```

    Args:
        payload: The Pipefy webhook payload
        request: FastAPI request object for logging

    Returns:
        Success confirmation with event ID
    """
    try:
        # Log the incoming webhook
        logger.info(f"Received Pipefy webhook: action={payload.data.action}")

        # Extract relevant data from payload
        event_type = payload.data.action
        pipefy_card_id = None
        pipe_id = None

        if payload.data.card:
            pipefy_card_id = payload.data.card.id
            if payload.data.card.pipe:
                pipe_id = payload.data.card.pipe.get("id")

        # Convert payload to dict for storage
        raw_payload = payload.model_dump()

        # TODO: Extract organization_id from the payload or use a default
        # For now, we'll need to determine how to map Pipefy pipes to organizations
        # This could be done via a mapping table or configuration
        organization_id = "00000000-0000-0000-0000-000000000000"  # Placeholder

        # You might want to add logic here to map pipe_id to organization_id
        # For example:
        # organization_id = await get_organization_id_by_pipe_id(pipe_id)

        # Save the event to database
        repo = PipefyEventsRepository()
        event = await repo.create_event(
            organization_id=organization_id,
            event_type=event_type,
            raw_payload=raw_payload,
            pipefy_card_id=pipefy_card_id,
            pipe_id=pipe_id
        )

        logger.info(f"Saved Pipefy event: id={event.get('id')}, type={event_type}")

        return {
            "success": True,
            "message": "Webhook received and processed",
            "event_id": event.get("id"),
            "event_type": event_type
        }

    except Exception as e:
        logger.error(f"Error processing Pipefy webhook: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error processing webhook: {str(e)}"
        )

@router.get(
    "/webhook/pipefy/events/{organization_id}",
    response_model=list[Dict[str, Any]],
    summary="Get Pipefy Events by Organization",
    tags=["webhook"]
)
async def get_organization_events(
    organization_id: str,
    limit: int = 100
):
    """
    Retrieve all Pipefy events for a specific organization.

    Args:
        organization_id: The organization UUID
        limit: Maximum number of events to return (default: 100)

    Returns:
        List of Pipefy events
    """
    try:
        repo = PipefyEventsRepository()
        events = await repo.get_events_by_organization(
            organization_id=organization_id,
            limit=limit
        )

        return events

    except Exception as e:
        logger.error(f"Error fetching events for organization {organization_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching events: {str(e)}"
        )


@router.get(
    "/webhook/pipefy/events/card/{pipefy_card_id}",
    response_model=list[Dict[str, Any]],
    summary="Get Pipefy Events by Card ID",
    tags=["webhook"]
)
async def get_card_events(
    pipefy_card_id: str,
    limit: int = 100
):
    """
    Retrieve all Pipefy events for a specific card.

    Args:
        pipefy_card_id: The Pipefy card ID
        limit: Maximum number of events to return (default: 100)

    Returns:
        List of Pipefy events
    """
    try:
        repo = PipefyEventsRepository()
        events = await repo.get_events_by_card(
            pipefy_card_id=pipefy_card_id,
            limit=limit
        )

        return events

    except Exception as e:
        logger.error(f"Error fetching events for card {pipefy_card_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching events: {str(e)}"
        )


@router.post("/webhook/pipefy/receive",
             response_model=Dict[str, Any],
             status_code=status.HTTP_200_OK,
             summary="Receive Pipefy Webhook",
             tags=["webhook"])
async def receive_pipefy_webhook(payload: PipefyReceivingWebhookData):
    phase_from = payload.data.from_.name
    phase_to = payload.data.to.name
    card_id = payload.data.card.id
    
    
    try:        # Process the card details using the service function
        result = await process_card_details(card_id)
        
        return {
            "success": True,
            "message": "Webhook received and processed",
            "data": result
        }   
    except Exception as e:
        logger.error(f"Error processing card details: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error processing card details: {str(e)}"
        )
    