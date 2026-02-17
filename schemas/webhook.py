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


class PipefyEventCreate(BaseModel):
    """Schema for creating a pipefy_events record - matches database schema"""
    organization_id: str
    pipefy_card_id: Optional[str] = None
    pipe_id: Optional[str] = None
    event_type: str
    raw_payload: Dict[str, Any]


class PipefyEventResponse(BaseModel):
    """Response schema for pipefy_events"""
    id: str
    organization_id: str
    pipefy_card_id: Optional[str]
    pipe_id: Optional[str]
    event_type: str
    raw_payload: Dict[str, Any]
    created_at: datetime

    class Config:
        from_attributes = True

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
