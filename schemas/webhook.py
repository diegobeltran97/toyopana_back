from pydantic import BaseModel, Field,  EmailStr, HttpUrl
from typing import Optional, Dict, Any, List
from datetime import datetime


class PipefyCard(BaseModel):
    """Pipefy card object in webhook payload"""
    id: str
    title: Optional[str] = None
    due_date: Optional[str] = None
    assignees: Optional[List[Dict[str, Any]]] = []
    comments: Optional[List[Dict[str, Any]]] = []
    comments_count: Optional[int] = 0
    current_phase: Optional[Dict[str, Any]] = None
    done: Optional[bool] = False
    fields: Optional[List[Dict[str, Any]]] = []
    labels: Optional[List[Dict[str, Any]]] = []
    phases_history: Optional[List[Dict[str, Any]]] = []
    pipe: Optional[Dict[str, Any]] = None
    url: Optional[str] = None


class PipefyPhase(BaseModel):
    """Pipefy phase object in webhook payload"""
    id: Optional[str] = None
    name: Optional[str] = None


class PipefyWebhookData(BaseModel):
    """Data object inside Pipefy webhook payload"""
    action: str = Field(..., description="Action type (e.g., card.create, card.move, card.done)")
    card: Optional[PipefyCard] = None
    from_phase: Optional[PipefyPhase] = None
    on_phase: Optional[PipefyPhase] = None
    field: Optional[Dict[str, Any]] = None
    field_value: Optional[Any] = None


class PipefyWebhookPayload(BaseModel):
    """Complete Pipefy webhook payload"""
    data: PipefyWebhookData


""" from here is my own code"""

class PhaseRef(BaseModel):
    id: int
    name: str


class MovedBy(BaseModel):
    id: int
    name: str
    username: str
    email: EmailStr
    avatar_url: HttpUrl


class CardRef(BaseModel):
    id: int
    title: str
    pipe_id: str


class PipefyWebhookData(BaseModel):
    action: str
    from_: PhaseRef = Field(..., alias="from")  # "from" is reserved in Python
    to: PhaseRef
    moved_by: MovedBy
    card: CardRef

    class Config:
        populate_by_name = True


class PipefyReceivingWebhookData(BaseModel):
    data: PipefyWebhookData

    
class PhaseData(BaseModel):
    """Phase information from Pipefy card"""
    id: str
    name: str


class FieldData(BaseModel):
    """Field data from Pipefy card"""
    name: str
    value: Optional[Any] = None
    field: Optional[Dict[str, Any]] = None
    array_value: Optional[List[Any]] = None
    filled_at: Optional[str] = None
    updated_at: Optional[str] = None
    report_value: Optional[Any] = None


class NestedCardData(BaseModel):
    """Nested card data fetched from connected card ID"""
    id: str
    title: str
    current_phase: Optional[PhaseData] = None
    fields: Optional[List[FieldData]] = None
    url: Optional[str] = None


class CardData(BaseModel):
    """Main card data to be saved in database"""
    id: str
    title: str
    current_phase: Optional[PhaseData] = None
    pipe: Optional[str] = None
    fields: Optional[List[FieldData]] = None
    user_data: Optional[NestedCardData] = None
    user_car_information: Optional[NestedCardData] = None
    assignees: Optional[List[Dict[str, Any]]] = None
    labels: Optional[List[Dict[str, Any]]] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    due_date: Optional[str] = None
    url: Optional[str] = None
