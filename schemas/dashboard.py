"""Pydantic schemas for the dashboard metrics endpoint."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class DashboardMetricsOut(BaseModel):
    """Aggregate order metrics for the dashboard KPI cards.

    All counts are scoped to a single organization. Time-based counts use
    America/Panama day/week/month boundaries.
    """

    created_today: int = Field(..., description="Orders received today (received_at)")
    created_this_week: int = Field(..., description="Orders received since Monday")
    created_this_month: int = Field(
        ..., description="Orders received this calendar month"
    )
    active_orders: int = Field(
        ..., description="Orders currently in an in-progress workshop status"
    )
    completed_today: int = Field(
        ..., description="Orders that reached 'pagado' today (from status history)"
    )
    cancelled_today: int = Field(
        ..., description="Orders that reached 'cancelado' today (from status history)"
    )
    new_vs_cancelled_ratio: Optional[float] = Field(
        None,
        description="created_today / cancelled_today; null when no cancellations today",
    )
    period: str = Field(
        "today", description="Period used for the completed/ratio metrics"
    )
    timezone: str = Field(
        "America/Panama", description="Timezone used for the date boundaries"
    )
    generated_at: datetime = Field(..., description="When the metrics were computed")
