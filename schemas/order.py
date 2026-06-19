import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Literal, Optional
from fastapi import File, Form, Path, UploadFile
from pydantic import BaseModel, ConfigDict

from schemas.customer import CustomerCreate
from schemas.vehicle import VehicleCreate


# Allowed values mirror the DB check constraints (orders_status_check /
# orders_priority_check). Keep them here so both create and update validate
# against the same set and reject bad input with a 422 before hitting Postgres.
OrderStatus = Literal[
    "recibido",
    "en_proceso",
    "pendiente",
    "contactado",
    "aprobado",
    "listo",
    "entregado",
    "cancelado",
]
OrderPriority = Literal["alta", "media", "baja"]


class OrderCreate(BaseModel):
    organization_id: uuid.UUID
    customer_id: uuid.UUID
    vehicle_id: uuid.UUID
    created_by: uuid.UUID  # app_users.id of the logged-in user
    received_at: datetime
    order_reason: str
    service_type: str
    km_in: Optional[int] = None
    priority: OrderPriority = "media"
    status: OrderStatus = "recibido"


class OrderFullCreate(OrderCreate):
    customer_id: Optional[uuid.UUID]
    vehicle_id: Optional[uuid.UUID]
    customerData: CustomerCreate
    vehicleData: VehicleCreate
    
    
 
class OrderUpdate(BaseModel):
    """Partial update of an order. Every field is optional; only the fields
    actually sent are applied (so nulls aren't written over existing values).
    `status`/`priority` are constrained to the DB's allowed values so the API
    rejects bad input before it reaches Postgres.
    """

    customer_id: Optional[uuid.UUID] = None
    vehicle_id: Optional[uuid.UUID] = None
    assigned_to: Optional[uuid.UUID] = None  # técnico (app_users.id)
    service_type: Optional[str] = None
    status: Optional[OrderStatus] = None
    priority: Optional[OrderPriority] = None
    order_reason: Optional[str] = None
    total_amount: Optional[Decimal] = None
    received_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    km_in: Optional[int] = None


class OrderOut(OrderCreate):
    id: uuid.UUID
    # These columns are NOT NULL-constrained in the DB, so relax the stricter
    # create-time requirements when reading rows back.
    vehicle_id: Optional[uuid.UUID] = None
    created_by: Optional[uuid.UUID] = None
    assigned_to: Optional[uuid.UUID] = None  # técnico
    received_at: Optional[datetime] = None
    order_reason: Optional[str] = None
    total_amount: Decimal
    date_order: datetime
    completed_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class OrderFullUpdate(BaseModel):
    """Partial update for order, customer, and/or vehicle in one call."""

    order: Optional[OrderUpdate] = None
    customer: Optional[Dict[str, Any]] = None
    vehicle: Optional[Dict[str, Any]] = None
