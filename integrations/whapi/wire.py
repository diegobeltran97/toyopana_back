"""Whapi.cloud wire-format DTOs.

These mirror the exact request/response JSON shapes of the Whapi REST API
(https://panel.whapi.cloud/rest). They are internal to the whapi integration
package and should never leak into services or endpoints -- the mapper
translates them to/from the provider-neutral schemas.messaging DTOs.
"""

from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class SendTextWire(BaseModel):
    """Request body for POST /messages/text."""

    to: str = Field(..., description="Chat id, e.g. 50761234567@s.whatsapp.net")
    body: str = Field(..., description="Message text content")
    typing_time: Optional[int] = Field(
        None, ge=0, le=60, description="Simulated typing duration in seconds"
    )


class SendInteractiveWire(BaseModel):
    """Request body for POST /messages/interactive (quick-reply buttons).

    Whapi wraps the prompt in `body: {"text": ...}` and each button in a
    `quick_reply` object -- shapes that must not leak past the mapper.
    """

    to: str = Field(..., description="Chat id, e.g. 50761234567@s.whatsapp.net")
    type: str = Field("button", description="Whapi's interactive message kind")
    body: Dict[str, str] = Field(..., description='{"text": "..."} prompt')
    action: Dict[str, List[Dict[str, str]]] = Field(
        ..., description='{"buttons": [{type, title, id}, ...]}'
    )
