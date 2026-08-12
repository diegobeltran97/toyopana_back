"""Pydantic models for citas (appointments).

A cita is an intention to visit, booked before the vehicle arrives. It is NOT
an order: the order is created separately at reception. `converted_order_id` is
the one-way bridge to the order that eventually fulfilled the cita — the column
exists, but nothing writes it in this iteration.
"""

import uuid
from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict


class CitaStatus(str, Enum):
    """Lifecycle of a cita. Mirrors the citas_status_check DB constraint."""

    agendada = "agendada"
    confirmada = "confirmada"
    cumplida = "cumplida"
    no_show = "no_show"
    cancelada = "cancelada"


class CitaCreate(BaseModel):
    """Booking payload. The org comes from the JWT, never from the body."""

    customer_id: uuid.UUID
    scheduled_at: datetime
    service_type: Optional[str] = None


class CitaUpdate(BaseModel):
    """Partial update: status change and/or reschedule. Only sent fields apply."""

    status: Optional[CitaStatus] = None
    scheduled_at: Optional[datetime] = None
    service_type: Optional[str] = None
    vehicle_id: Optional[uuid.UUID] = None


class CitaCustomer(BaseModel):
    """Customer snapshot embedded in a cita, for calendar display."""

    id: uuid.UUID
    name: str
    phone: Optional[str] = None


class CitaRead(BaseModel):
    """A cita as returned by the API."""

    id: uuid.UUID
    organization_id: uuid.UUID
    customer_id: uuid.UUID
    vehicle_id: Optional[uuid.UUID] = None
    scheduled_at: datetime
    service_type: Optional[str] = None
    status: CitaStatus
    converted_order_id: Optional[uuid.UUID] = None
    created_at: datetime
    updated_at: datetime
    customer: Optional[CitaCustomer] = None

    model_config = ConfigDict(from_attributes=True)
