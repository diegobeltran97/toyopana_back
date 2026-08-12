"""Pydantic schemas for the marketing metrics endpoint."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class FunnelOut(BaseModel):
    """Current count of orders in each follow-up (marketing) status."""

    requiere_de_contacto: int = Field(..., description="Orders awaiting first contact")
    contactado: int = Field(..., description="Orders already contacted")
    agendado: int = Field(..., description="Orders with an appointment scheduled")
    finalizada: int = Field(..., description="Orders whose follow-up is finished")


class MarketingMetricsOut(BaseModel):
    """Aggregate marketing KPIs for the Resumen tab.

    All counts are scoped to a single organization. Message counts use
    America/Panama day boundaries; the response rate uses a rolling 7-day window.
    """

    messages_sent_today: int = Field(..., description="Outbound wa_messages sent today")
    messages_sent_yesterday: int = Field(
        ..., description="Outbound wa_messages sent yesterday (drives the vs-ayer delta)"
    )
    response_rate: Optional[float] = Field(
        None,
        description="Messaged conversations (7d) that got an inbound reply, 0-1; null when none messaged",
    )
    appointments_scheduled: int = Field(
        ..., description="Orders currently in 'agendado' status"
    )
    conversion_to_appointment: Optional[float] = Field(
        None,
        description="agendado / (contactado + agendado + finalizada), 0-1; null when denominator 0",
    )
    funnel: FunnelOut = Field(..., description="Current order counts per follow-up status")
    timezone: str = Field("America/Panama", description="Timezone used for day boundaries")
    generated_at: datetime = Field(..., description="When the metrics were computed")
