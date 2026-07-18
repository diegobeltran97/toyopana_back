"""Adapter/Mapper between Whapi's wire format and the domain DTOs.

This is the isolation seam. All Whapi-specific shape knowledge
(the ``@s.whatsapp.net`` suffix, the ``chat_id`` field name, the
``{"sent": ..., "message": {...}}`` envelope) lives here so services and
endpoints never see it.
"""

from typing import Any, Dict

from schemas.messaging import OutboundMessage, SentMessage
from integrations.whapi.wire import SendTextWire

# Panama country code. Kept here because "what a phone number means" is a
# provider/transport concern, not a business one.
DEFAULT_COUNTRY_CODE = "507"


def to_whatsapp_id(phone: str, country_code: str = DEFAULT_COUNTRY_CODE) -> str:
    """Normalize a human phone number into a Whapi chat id.

    Strips non-digits and ensures the country code prefix, then appends the
    ``@s.whatsapp.net`` suffix Whapi expects.
    """
    digits = "".join(filter(str.isdigit, phone))
    if not digits.startswith(country_code):
        digits = country_code + digits
    return f"{digits}@s.whatsapp.net"


def outbound_to_wire(msg: OutboundMessage) -> Dict[str, Any]:
    """Domain OutboundMessage -> Whapi POST /messages/text body."""
    return SendTextWire(
        to=to_whatsapp_id(msg.phone),
        body=msg.body,
        typing_time=msg.typing_time,
    ).model_dump(exclude_none=True)


def wire_to_sent(raw: Dict[str, Any]) -> SentMessage:
    """Whapi send response -> domain SentMessage."""
    message = raw.get("message") or {}
    return SentMessage(
        id=message.get("id"),
        to=message.get("chat_id") or message.get("to"),
        status="sent" if raw.get("sent") else "failed",
    )
