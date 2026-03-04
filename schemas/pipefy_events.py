from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from datetime import datetime


class PipefyEventCreate(BaseModel):
    """
    Schema for creating a pipefy_events record

    Matches the database insert requirements for the pipefy_events table.
    """
    organization_id: str = Field(..., description="UUID of the organization")
    pipefy_card_id: Optional[str] = Field(None, description="Pipefy card ID")
    pipe_id: Optional[str] = Field(None, description="Pipefy pipe ID")
    event_type: str = Field(..., description="Type of event (e.g., card.create, card.move)")
    raw_payload: Dict[str, Any] = Field(..., description="Complete webhook payload as JSON")
    actions_taken: Optional[Dict[str, Any]] = Field(None, description="Actions taken in response to the event")


class PipefyEventUpdateActions(BaseModel):
    """
    Schema for updating actions taken on a pipefy event

    Used when updating the actions_taken field after processing an event.
    """
    actions_taken: Dict[str, Any] = Field(
        ...,
        description="Actions taken in response to the event (e.g., WhatsApp message sent, notification delivered)",
        examples=[
            {
                "whatsapp_sent": True,
                "message_id": "msg_123",
                "sent_at": "2024-01-15T10:30:00Z"
            }
        ]
    )


class PipefyEventResponse(BaseModel):
    """
    Response schema for pipefy_events

    Represents a complete record from the pipefy_events table.
    Matches the database table structure exactly.
    """
    id: str = Field(..., description="UUID primary key (auto-generated)")
    organization_id: str = Field(..., description="UUID of the organization")
    pipefy_card_id: Optional[str] = Field(None, description="Pipefy card ID")
    pipe_id: Optional[str] = Field(None, description="Pipefy pipe ID")
    event_type: str = Field(..., description="Type of event")
    raw_payload: Dict[str, Any] = Field(..., description="Complete webhook payload as JSON")
    actions_taken: Optional[Dict[str, Any]] = Field(None, description="Actions taken in response to the event")
    created_at: datetime = Field(..., description="Timestamp when record was created")

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "organization_id": "7ace5443-06c0-4ba2-b495-88262238466a",
                "pipefy_card_id": "123456",
                "pipe_id": "pipe_789",
                "event_type": "card.move",
                "raw_payload": {
                    "data": {
                        "action": "card.move",
                        "card": {"id": "123456", "title": "Test Card"}
                    }
                },
                "actions_taken": {
                    "whatsapp_sent": True,
                    "message_id": "msg_abc123",
                    "sent_at": "2024-01-15T10:30:00Z"
                },
                "created_at": "2024-01-15T10:25:00Z"
            }
        }


class PipefyEventDB(BaseModel):
    """
    Complete database schema for pipefy_events table

    Represents the exact structure of the Supabase pipefy_events table:

    CREATE TABLE public.pipefy_events (
        id uuid NOT NULL DEFAULT gen_random_uuid(),
        organization_id uuid NOT NULL,
        pipefy_card_id text NULL,
        pipe_id text NULL,
        event_type text NULL,
        raw_payload jsonb NOT NULL,
        created_at timestamp with time zone NULL DEFAULT now(),
        actions_taken json NULL,
        CONSTRAINT pipefy_events_pkey PRIMARY KEY (id),
        CONSTRAINT pipefy_events_organization_id_fkey
            FOREIGN KEY (organization_id) REFERENCES organization(id) ON DELETE CASCADE
    );
    """
    id: str
    organization_id: str
    pipefy_card_id: Optional[str] = None
    pipe_id: Optional[str] = None
    event_type: Optional[str] = None
    raw_payload: Dict[str, Any]
    actions_taken: Optional[Dict[str, Any]] = None
    created_at: datetime

    class Config:
        from_attributes = True
