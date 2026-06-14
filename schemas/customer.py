import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class CustomerSearch(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    national_id: Optional[str] = None


class CustomerCreate(BaseModel):
    name: str
    phone: str
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
