import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal, Optional
from pydantic import BaseModel, ConfigDict


class OrderCreate(BaseModel):
    organization_id: uuid.UUID
    customer_id: uuid.UUID
    vehicle_id: uuid.UUID
    created_by: uuid.UUID  # app_users.id of the logged-in user
    received_at: datetime
    order_reason: str
    service_type: str
    km_in: Optional[int] = None
    priority: Literal["alta", "media", "baja"] = "media"
    status: str = "recibido"


class OrderOut(OrderCreate):
    id: uuid.UUID
    total_amount: Decimal
    date_order: datetime
    completed_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)
