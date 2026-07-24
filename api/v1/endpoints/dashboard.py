"""API endpoint for dashboard order metrics."""

from fastapi import APIRouter, Query

from schemas.dashboard import DashboardMetricsOut
from services import dashboard_service

router = APIRouter()


@router.get(
    "/metrics",
    response_model=DashboardMetricsOut,
    summary="Dashboard order metrics",
    tags=["dashboard"],
)
async def get_dashboard_metrics(
    organization_id: str = Query(
        ..., description="Organization to compute metrics for"
    ),
):
    """
    Aggregate order KPIs for the dashboard cards.

    - **created_today / this_week / this_month**: orders by `received_at`
      (America/Panama day/week/month boundaries).
    - **active_orders**: orders currently in an in-progress workshop status.
    - **completed_today / cancelled_today**: orders that reached
      'pagado' / 'cancelado' today (derived from order_status_history).
    - **new_vs_cancelled_ratio**: created_today / cancelled_today (null when
      there are no cancellations today).
    """
    return await dashboard_service.get_dashboard_metrics(organization_id)
