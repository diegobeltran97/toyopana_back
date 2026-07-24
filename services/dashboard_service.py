"""Business logic for dashboard order metrics.

Computes KPI aggregates over orders and order_status_history. Time windows use
America/Panama day/week/month boundaries (week starts Monday). "completed" and
"cancelled" are derived from status-history transitions because orders.completed_at
is not reliably populated and an order's order_status is overwritten as it moves
through the workshop and follow-up pipelines.
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Tuple
from zoneinfo import ZoneInfo

from repositories.dashboard import DashboardRepository
from schemas.dashboard import DashboardMetricsOut

logger = logging.getLogger(__name__)

# In-progress workshop statuses. Excludes follow-up statuses
# (requiere_de_contacto, contactado, agendado, finalizada) and the terminal
# states (pagado, cancelado). Mirrors the codes in schemas/order.OrderStatus.
ACTIVE_ORDER_STATUSES = [
    "recibido",
    "en_proceso",
    "pendiente_aprobacion",
    "aprobado",
]

PANAMA_TZ = ZoneInfo("America/Panama")


def _period_boundaries() -> Tuple[str, str, str]:
    """
    Return (today_start, week_start, month_start) as UTC ISO strings.

    Boundaries are the local midnight in America/Panama for the current day,
    the current week (Monday) and the current month, converted to UTC so they
    can be compared against timestamptz columns via PostgREST.
    """
    now_local = datetime.now(PANAMA_TZ)
    day_start = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = day_start - timedelta(days=day_start.weekday())  # Monday
    month_start = day_start.replace(day=1)

    def to_utc_iso(dt: datetime) -> str:
        return dt.astimezone(timezone.utc).isoformat()

    return to_utc_iso(day_start), to_utc_iso(week_start), to_utc_iso(month_start)


async def get_dashboard_metrics(organization_id: str) -> DashboardMetricsOut:
    """
    Compute the dashboard KPI metrics for an organization.

    Args:
        organization_id: The organization UUID to compute metrics for

    Returns:
        DashboardMetricsOut with created/active/completed/cancelled counts.
    """
    today_start, week_start, month_start = _period_boundaries()
    repo = DashboardRepository()

    (
        created_today,
        created_this_week,
        created_this_month,
        active_orders,
        completed_today,
        cancelled_today,
    ) = await asyncio.gather(
        repo.count_orders(organization_id, received_after=today_start),
        repo.count_orders(organization_id, received_after=week_start),
        repo.count_orders(organization_id, received_after=month_start),
        repo.count_orders(organization_id, statuses=ACTIVE_ORDER_STATUSES),
        repo.count_orders_reached_status(organization_id, "pagado", today_start),
        repo.count_orders_reached_status(organization_id, "cancelado", today_start),
    )

    ratio = round(created_today / cancelled_today, 2) if cancelled_today else None

    logger.info(
        "Dashboard metrics for org %s: created_today=%d active=%d completed=%d",
        organization_id,
        created_today,
        active_orders,
        completed_today,
    )

    return DashboardMetricsOut(
        created_today=created_today,
        created_this_week=created_this_week,
        created_this_month=created_this_month,
        active_orders=active_orders,
        completed_today=completed_today,
        cancelled_today=cancelled_today,
        new_vs_cancelled_ratio=ratio,
        generated_at=datetime.now(timezone.utc),
    )
