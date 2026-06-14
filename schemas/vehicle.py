import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class VehicleSearch(BaseModel):
    plate: Optional[str] = None
    make: Optional[str] = None
    model: Optional[str] = None


class VehicleCreate(BaseModel):
    organization_id: uuid.UUID
    plate: str
    make: str
    model: str
    year: int
    km_last_service: Optional[int] = None


class VehicleOut(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    plate: str
    make: str
    model: str
    year: int
    km_last_service: Optional[int] = None
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
