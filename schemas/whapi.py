# app/schemas/whapi.py
"""Pydantic schemas for Whapi.cloud API requests and responses"""

from typing import Optional, List, Literal
from pydantic import BaseModel, Field


# ============================================================================
# Label Color Enum
# ============================================================================

LabelColor = Literal[
    "salmon",
    "gold",
    "violet",
    "blue",
    "pink",
    "green",
    "brown",
    "orange",
    "purple",
    "teal",
    "red",
    "yellow",
    "indigo",
    "cyan",
    "magenta",
    "lime",
    "navy",
    "olive",
    "maroon",
    "gray"
]


# ============================================================================
# Message Schemas
# ============================================================================

class SendTextMessageRequest(BaseModel):
    """Request schema for sending a text message"""
    to: str = Field(..., description="Phone number or Chat ID where message will be sent")
    body: str = Field(..., description="Message text content")
    typing_time: Optional[int] = Field(None, ge=0, le=60, description="Simulated typing duration in seconds (0-60)")
    no_link_preview: Optional[bool] = Field(None, description="Disable link previews")
    mentions: Optional[List[str]] = Field(None, description="Array of contact IDs to mention")

    class Config:
        json_schema_extra = {
            "example": {
                "to": "5215512345678@s.whatsapp.net",
                "body": "Hello! This is a test message.",
                "typing_time": 2,
                "no_link_preview": False
            }
        }


class MessageObject(BaseModel):
    """WhatsApp message object"""
    id: Optional[str] = None
    from_: Optional[str] = Field(None, alias="from")
    to: Optional[str] = None
    body: Optional[str] = None
    timestamp: Optional[int] = None
    type: Optional[str] = None

    class Config:
        populate_by_name = True


class SendMessageResponse(BaseModel):
    """Response from sending a message"""
    sent: bool = Field(..., description="Whether the message was sent successfully")
    message: Optional[MessageObject] = Field(None, description="Message details")


# ============================================================================
# Label Schemas
# ============================================================================

class LabelBase(BaseModel):
    """Base label information"""
    id: str = Field(..., description="Label identifier")
    name: str = Field(..., description="Label name")
    color: LabelColor = Field(..., description="Label color from predefined set")


class Label(LabelBase):
    """Complete label object with count"""
    count: Optional[int] = Field(None, description="Number of items with this label")

    class Config:
        json_schema_extra = {
            "example": {
                "id": "1",
                "name": "Important",
                "color": "red",
                "count": 5
            }
        }


class CreateLabelRequest(BaseModel):
    """Request to create a new label"""
    id: str = Field(..., description="Unique label identifier")
    name: str = Field(..., description="Label display name")
    color: LabelColor = Field(..., description="Label color")

    class Config:
        json_schema_extra = {
            "example": {
                "id": "urgent",
                "name": "Urgent",
                "color": "red"
            }
        }


class ChatAssociation(BaseModel):
    """Chat associated with a label"""
    id: str = Field(..., description="Chat ID")
    name: Optional[str] = Field(None, description="Chat name")


class MessageAssociation(BaseModel):
    """Message associated with a label"""
    id: str = Field(..., description="Message ID")
    chat_id: Optional[str] = Field(None, description="ID of chat containing this message")


class LabelAssociations(BaseModel):
    """Objects associated with a specific label"""
    chats: List[ChatAssociation] = Field(default_factory=list, description="Chats with this label")
    messages: List[MessageAssociation] = Field(default_factory=list, description="Messages with this label")

    class Config:
        json_schema_extra = {
            "example": {
                "chats": [
                    {"id": "5215512345678@s.whatsapp.net", "name": "John Doe"}
                ],
                "messages": []
            }
        }


class LabelsResponse(BaseModel):
    """Response containing list of labels"""
    labels: List[Label] = Field(..., description="Array of label objects")


class EnrichedLabel(BaseModel):
    """Label with associated chats and messages included"""
    id: str = Field(..., description="Label identifier")
    name: str = Field(..., description="Label name")
    color: LabelColor = Field(..., description="Label color from predefined set")
    count: Optional[int] = Field(None, description="Number of items with this label")
    chats: List[ChatAssociation] = Field(default_factory=list, description="Chats with this label")
    messages: List[MessageAssociation] = Field(default_factory=list, description="Messages with this label")

    class Config:
        json_schema_extra = {
            "example": {
                "id": "10",
                "name": "Cita de Taller",
                "color": "deepskyblue",
                "count": 3,
                "chats": [
                    {"id": "5075512345678@s.whatsapp.net", "name": "Juan Pérez"},
                    {"id": "5075587654321@s.whatsapp.net", "name": "María González"}
                ],
                "messages": [
                    {"id": "msg123", "chat_id": "5075512345678@s.whatsapp.net"}
                ]
            }
        }


class LabelStats(BaseModel):
    """Label with count statistics for chats and messages"""
    id: str = Field(..., description="Label identifier")
    name: str = Field(..., description="Label name")
    color: LabelColor = Field(..., description="Label color from predefined set")
    count: Optional[int] = Field(None, description="Original count from API (may be null)")
    chats: int = Field(..., description="Number of chats associated with this label")
    messages: int = Field(..., description="Number of messages associated with this label")

    class Config:
        json_schema_extra = {
            "example": {
                "id": "10",
                "name": "Cita de Taller",
                "color": "deepskyblue",
                "count": None,
                "chats": 23,
                "messages": 5
            }
        }


# ============================================================================
# Common Response Schemas
# ============================================================================

class WhapifySuccessResponse(BaseModel):
    """Generic success response"""
    success: bool = True
    message: Optional[str] = None


class WhapifyErrorResponse(BaseModel):
    """Generic error response"""
    success: bool = False
    error: str = Field(..., description="Error type")
    status_code: Optional[int] = None
    details: Optional[str] = None
