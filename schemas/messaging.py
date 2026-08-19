"""Provider-neutral domain DTOs for messaging.

These are the shapes the rest of the app speaks. They are intentionally
independent of any specific provider (Whapi, Twilio, ...). Provider-specific
wire formats live under integrations/<provider>/wire.py and are translated to
and from these by the provider's mapper.
"""

from typing import Dict, Optional

from pydantic import BaseModel, Field


class OutboundMessage(BaseModel):
    """A message the application wants to send, in domain terms.

    Free-form text. Note that official providers (Meta, Twilio) only accept
    free text inside the 24h customer-service window; outside it they require
    OutboundTemplate instead.
    """

    phone: str = Field(..., description="Recipient phone number (any human format)")
    body: str = Field(..., min_length=1, description="Text content to send")
    typing_time: Optional[int] = Field(
        None, ge=0, le=60, description="Optional simulated typing seconds (0-60)"
    )


class OutboundTemplate(BaseModel):
    """A resolved templated message, ready for any provider to dispatch.

    Carries both representations so each provider can use the one its vendor
    requires -- ``body`` for providers that render locally (Whapi), or
    ``provider_template_name`` for those that reference pre-approved copy
    (Meta/Twilio). Resolution and parameter validation happen upstream in
    MessagingService, so providers never touch the template store: they have
    no organization context and no business rules.
    """

    phone: str = Field(..., description="Recipient phone number (any human format)")
    name: str = Field(..., description="Logical template name, for logs and errors")
    params: Dict[str, str] = Field(
        default_factory=dict, description="Template parameter values by name"
    )
    body: str = Field(..., description="Resolved copy with {param} placeholders")
    language: str = Field("es", description="Template language code")
    provider_template_name: Optional[str] = Field(
        None, description="Approved template name on the provider's side (Meta/Twilio)"
    )
    typing_time: Optional[int] = Field(
        None, ge=0, le=60, description="Optional simulated typing seconds (0-60)"
    )


class SentMessage(BaseModel):
    """The outcome of a successfully accepted outbound message."""

    id: Optional[str] = Field(None, description="Provider message id")
    to: Optional[str] = Field(None, description="Normalized recipient id")
    status: str = Field(..., description="'sent' or 'failed'")
