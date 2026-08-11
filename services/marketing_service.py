"""Business logic for marketing metrics (Resumen tab).

Aggregates order follow-up statuses and WhatsApp message activity into the KPIs
and funnel on the marketing page. Time windows use America/Panama day
boundaries; the response rate uses a rolling 7-day window.
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple
from zoneinfo import ZoneInfo

from repositories.dashboard import DashboardRepository
from repositories.marketing import MarketingRepository
from schemas.marketing import FunnelOut, MarketingMetricsOut

logger = logging.getLogger(__name__)

PANAMA_TZ = ZoneInfo("America/Panama")


def _boundaries() -> Tuple[str, str, str]:
    """Return (today_start, yesterday_start, seven_days_ago) as UTC ISO strings.

    Each is a local America/Panama midnight converted to UTC, so they compare
    correctly against timestamptz columns via PostgREST.
    """
    now_local = datetime.now(PANAMA_TZ)
    day_start = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday_start = day_start - timedelta(days=1)
    seven_days_ago = day_start - timedelta(days=7)

    def to_utc_iso(dt: datetime) -> str:
        return dt.astimezone(timezone.utc).isoformat()

    return (
        to_utc_iso(day_start),
        to_utc_iso(yesterday_start),
        to_utc_iso(seven_days_ago),
    )


def _safe_ratio(numerator: int, denominator: int) -> Optional[float]:
    """numerator / denominator rounded to 4 dp, or None when denominator is 0."""
    if denominator <= 0:
        return None
    return round(numerator / denominator, 4)


async def get_marketing_metrics(
    organization_id: str,
    *,
    marketing_repo: Optional[MarketingRepository] = None,
    dashboard_repo: Optional[DashboardRepository] = None,
) -> MarketingMetricsOut:
    """
    Compute the marketing KPIs and follow-up funnel for an organization.

    Repositories are injectable for testing; by default the real Supabase-backed
    repositories are used.
    """
    marketing_repo = marketing_repo or MarketingRepository()
    dashboard_repo = dashboard_repo or DashboardRepository()

    today_start, yesterday_start, seven_days_ago = _boundaries()

    (
        n_requiere,
        n_contactado,
        n_agendado,
        n_finalizada,
        messages_today,
        messages_yesterday,
        messaged_convs,
        replied_convs,
    ) = await asyncio.gather(
        dashboard_repo.count_orders(organization_id, statuses=["requiere_de_contacto"]),
        dashboard_repo.count_orders(organization_id, statuses=["contactado"]),
        dashboard_repo.count_orders(organization_id, statuses=["agendado"]),
        dashboard_repo.count_orders(organization_id, statuses=["finalizada"]),
        marketing_repo.count_outbound_messages(organization_id, sent_after=today_start),
        marketing_repo.count_outbound_messages(
            organization_id, sent_after=yesterday_start, sent_before=today_start
        ),
        marketing_repo.conversation_ids_with_message(
            organization_id, "outbound", seven_days_ago
        ),
        marketing_repo.conversation_ids_with_message(
            organization_id, "inbound", seven_days_ago
        ),
    )

    funnel = FunnelOut(
        requiere_de_contacto=n_requiere,
        contactado=n_contactado,
        agendado=n_agendado,
        finalizada=n_finalizada,
    )

    conversion = _safe_ratio(n_agendado, n_contactado + n_agendado + n_finalizada)
    response_rate = _safe_ratio(
        len(messaged_convs & replied_convs), len(messaged_convs)
    )

    logger.info(
        "Marketing metrics for org %s: msgs_today=%d agendado=%d conversion=%s response_rate=%s",
        organization_id,
        messages_today,
        n_agendado,
        conversion,
        response_rate,
    )

    return MarketingMetricsOut(
        messages_sent_today=messages_today,
        messages_sent_yesterday=messages_yesterday,
        response_rate=response_rate,
        appointments_scheduled=n_agendado,
        conversion_to_appointment=conversion,
        funnel=funnel,
        generated_at=datetime.now(timezone.utc),
    )
