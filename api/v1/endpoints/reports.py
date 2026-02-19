
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

        return events

    except Exception as e:
        logger.error(f"Error fetching events for organization {organization_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching events: {str(e)}"
        )
   
 