"""Provider-neutral domain DTOs for messaging.

These are the shapes the rest of the app speaks. They are intentionally
independent of any specific provider (Whapi, Twilio, ...). Provider-specific
wire formats live under integrations/<provider>/wire.py and are translated to
and from these by the provider's mapper.
"""

from typing import Optional

from pydantic import BaseModel, Field


class OutboundMessage(BaseModel):
    """A message the application wants to send, in domain terms."""

    phone: str = Field(..., description="Recipient phone number (any human format)")
    body: str = Field(..., min_length=1, description="Text content to send")
    typing_time: Optional[int] = Field(
        None, ge=0, le=60, description="Optional simulated typing seconds (0-60)"
    )


class SentMessage(BaseModel):
    """The outcome of a successfully accepted outbound message."""

    id: Optional[str] = Field(None, description="Provider message id")
    to: Optional[str] = Field(None, description="Normalized recipient id")
    status: str = Field(..., description="'sent' or 'failed'")
