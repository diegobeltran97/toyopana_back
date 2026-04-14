
import logging
from typing import Dict, Any
from fastapi import APIRouter, HTTPException, status
from repositories.pipefy_events import PipefyEventsRepository




router = APIRouter()
logger = logging.getLogger(__name__)

@router.get("/main/reports/{organization_id}", response_model=list[Dict[str, Any]], summary="Get Reports by organization", tags=["reports"])
async def get_reports(organization_id: str, limit: int = 100):
    """
    Endpoint to retrieve reports data.
    """
    try:
        repo = PipefyEventsRepository()
        events = await repo.get_events_by_organization(
            organization_id=organization_id,
            limit=limit
        )
        #this is a temporary solution
        data_response = []

        logger.info(f"Fetched {len(events)} events for organization {organization_id}")

        for event in events:
            raw_payload = event.get("raw_payload", {})
            fields = raw_payload.get("fields", [])

            # Debug: Log the number of fields and card ID
            card_id = raw_payload.get("id", "unknown")
            logger.info(f"Processing event {event} for card {card_id} with {len(fields)} fields")
            logger.info(f"Card {card_id} (Event ID: {event.get('id')}): {len(fields)} fields in raw_payload")
            
            #.fields = event.get("raw_payload", {}).get("fields", [])

            event_data = {
                "events": event,
                "data_user": raw_payload.get("user_data"),
                "data_car": raw_payload.get("user_car_information"),
            }
            data_response.append(event_data)


        return data_response

    except Exception as e:
        logger.error(f"Error fetching events for organization {organization_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching events: {str(e)}"
        )


@router.get("/main/reports/debug/card/{card_id}", response_model=Dict[str, Any], summary="Debug: Get event by card ID", tags=["reports"])
async def debug_get_event_by_card(card_id: str):
    """
    Debug endpoint to retrieve raw event data for a specific card ID to verify data integrity.
    """
    try:
        repo = PipefyEventsRepository()
        events = await repo.get_events_by_card(pipefy_card_id=card_id, limit=1)

        if not events:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No events found for card {card_id}"
            )

        event = events[0]
        raw_payload = event.get("raw_payload", {})
        fields = raw_payload.get("fields", [])

        return {
            "event_id": event.get("id"),
            "card_id": card_id,
            "field_count": len(fields),
            "field_names": [f.get("name") for f in fields],
            "full_event": event
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching event for card {card_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching event: {str(e)}"
        )
   
 