"""API endpoint for marketing metrics (Resumen tab)."""

from fastapi import APIRouter, Query

from schemas.marketing import MarketingMetricsOut
from services import marketing_service

router = APIRouter()


@router.get(
    "/metrics",
    response_model=MarketingMetricsOut,
    summary="Marketing metrics",
    tags=["marketing"],
)
async def get_marketing_metrics(
    organization_id: str = Query(
        ..., description="Organization to compute metrics for"
    ),
):
    """
    Aggregate marketing KPIs and the follow-up funnel for the marketing page.

    - **messages_sent_today / _yesterday**: outbound wa_messages (America/Panama day).
    - **response_rate**: messaged conversations (last 7d) that got an inbound reply.
    - **appointments_scheduled**: orders currently in 'agendado'.
    - **conversion_to_appointment**: agendado / (contactado + agendado + finalizada).
    - **funnel**: current order counts per follow-up status.
    """
    return await marketing_service.get_marketing_metrics(organization_id)
