import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict


class CustomerSearch(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    national_id: Optional[str] = None


class CustomerCreate(BaseModel):
    name: str
    phone: str
    national_id: Optional[str] = None


class CustomerUpdate(BaseModel):
    """Partial update of a customer. Only the fields sent are applied."""

    name: Optional[str] = None
    phone: Optional[str] = None
    national_id: Optional[str] = None


class CustomerOut(BaseModel):
    id: uuid.UUID
    name: str
    phone: str
    national_id: Optional[str] = None
    type: Optional[str] = None
    source: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CustomerListItem(BaseModel):
    """A single row in the client directory list, with visit count."""

    id: uuid.UUID
    name: str
    phone: str
    national_id: Optional[str] = None
    type: Optional[str] = None
    source: Optional[str] = None
    created_at: datetime
    visitas: int

    model_config = ConfigDict(from_attributes=True)


class CustomerOrderVehicle(BaseModel):
    """Vehicle snapshot embedded within a customer's order summary."""

    plate: Optional[str] = None
    make: Optional[str] = None
    model: Optional[str] = None
    year: Optional[int] = None
    km_last_service: Optional[int] = None


class CustomerOrderSummary(BaseModel):
    """One of a customer's orders, as embedded in the profile detail."""

    id: uuid.UUID
    date_order: Optional[datetime] = None
    received_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    order_status: Optional[str] = None
    order_reason: Optional[str] = None
    service_type: Optional[str] = None
    total_amount: Optional[float] = None
    priority: Optional[str] = None
    km_in: Optional[int] = None
    vehicle: Optional[CustomerOrderVehicle] = None
    technician: Optional[str] = None


class CustomerDetail(BaseModel):
    """Full customer profile: identity, aggregate stats, and order history."""

    id: uuid.UUID
    name: str
    phone: str
    national_id: Optional[str] = None
    type: Optional[str] = None
    source: Optional[str] = None
    created_at: datetime
    visitas: int
    ticket_promedio: Optional[float] = None
    is_frequent: bool
    orders: List[CustomerOrderSummary] = []
