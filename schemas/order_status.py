"""
Pydantic schemas for Order Statuses.

Order statuses represent the different states an order can be in during its lifecycle.
There are two types of statuses:
- workshop: Physical work stages (recibido, en_proceso, aprobado, pagado, etc.)
- followup: Customer communication stages (requiere_de_contacto, contactado, agendado, finalizada)
"""

from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class StatusType(str, Enum):
    """Type of status classification."""

    WORKSHOP = "workshop"
    FOLLOWUP = "followup"


class OrderStatusBase(BaseModel):
    """Base schema for order status with common fields."""

    status_type: StatusType = Field(..., description="Type of status (workshop or followup)")
    code: str = Field(
        ...,
        min_length=1,
        max_length=50,
        description="Unique code for the status (e.g., 'recibido', 'en_proceso')",
    )
    label: str = Field(
        ..., min_length=1, max_length=100, description="Human-readable label"
    )
    sort_order: int = Field(
        ..., ge=0, description="Order for displaying statuses (lower = earlier)"
    )
    is_terminal: bool = Field(
        default=False, description="Whether this is a final/terminal status"
    )


class OrderStatusCreate(OrderStatusBase):
    """Schema for creating a new order status."""

    pass


class OrderStatusUpdate(BaseModel):
    """Schema for updating an order status (all fields optional)."""

    status_type: Optional[StatusType] = None
    code: Optional[str] = Field(None, min_length=1, max_length=50)
    label: Optional[str] = Field(None, min_length=1, max_length=100)
    sort_order: Optional[int] = Field(None, ge=0)
    is_terminal: Optional[bool] = None


class OrderStatusOut(OrderStatusBase):
    """Schema for order status response."""

    id: UUID
    created_at: datetime

    class Config:
        from_attributes = True


class OrderStatusList(BaseModel):
    """Schema for paginated list of order statuses."""

    statuses: list[OrderStatusOut]
    total: int
    workshop_count: int
    followup_count: int
