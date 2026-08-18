"""Adapter/Mapper between Whapi's wire format and the domain DTOs.

This is the isolation seam. All Whapi-specific shape knowledge
(the ``@s.whatsapp.net`` suffix, the ``chat_id`` field name, the
``{"sent": ..., "message": {...}}`` envelope) lives here so services and
endpoints never see it.
"""

from typing import Any, Dict

from schemas.messaging import OutboundMessage, OutboundTemplate, SentMessage
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


def template_to_wire(msg: OutboundTemplate) -> Dict[str, Any]:
    """Resolved OutboundTemplate -> Whapi POST /messages/text body.

    Whapi has no template endpoint, so the copy is rendered here and sent as
    ordinary text. ``msg.language`` and ``msg.provider_template_name`` are
    intentionally ignored -- Whapi has no concept of either. An official
    provider's mapper does the opposite: it sends the approved name and the
    params by reference and never touches ``body``.

    Raises:
        KeyError: if a parameter the copy requires was not supplied. Callers
            validate first; this is the last line of defence against sending
            a message with a literal ``{car_info}`` in it.
    """
    return SendTextWire(
        to=to_whatsapp_id(msg.phone),
        body=msg.body.format(**msg.params).strip(),
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
