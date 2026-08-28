"""Provider-neutral domain DTOs for inbound messages.

The mirror of schemas/messaging.py on the way in. Services and the decision
engine speak these shapes; every Whapi-specific detail is translated away by
integrations/whapi/parser.py before anything here is constructed.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class InboundMessage(BaseModel):
    """A message a customer sent us, in domain terms."""

    provider: str = Field(..., description="Which integration produced this, e.g. 'whapi'")
    provider_event_id: str = Field(
        ..., description="The provider's message id; the idempotency key"
    )
    chat_id: str = Field(
        ...,
        description="The provider's own conversation id, kept for the "
        "wa_conversations upsert (organization_id, wa_chat_id)",
    )
    from_phone: str = Field(..., description="Sender in E.164, e.g. +50761234567")
    from_name: Optional[str] = Field(None, description="Display name, when the provider sends one")
    body: Optional[str] = Field(None, description="Text content; None for a pure interactive reply")
    reply_id: Optional[str] = Field(
        None,
        description="Id of the tapped menu option, when the message is an "
        "interactive reply. Its presence is what routes a message away from "
        "the LLM and into deterministic handling.",
    )
    received_at: datetime = Field(..., description="When the provider says it arrived (UTC)")
