"""Whapi inbound wire format -> domain DTOs.

The inbound counterpart to mapper.py. Everything Whapi-specific about a
received message is decoded here: the ``@s.whatsapp.net`` suffix, the
``from_me`` flag, the ``reply.<type>.id`` nesting, and timestamps in seconds.

``parse()`` returns a *list* because Whapi batches several messages into one
POST. Typing it as a single event loses messages silently.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List

from schemas.inbound import InboundMessage
from integrations.whapi.mapper import from_whatsapp_id

PROVIDER = "whapi"


def channel_id(raw: Dict[str, Any]) -> str:
    """The channel the event arrived on -- the key that resolves the tenant.

    Read before authentication, because each organization has its own webhook
    secret and we need to know whose secret to compare against.
    """
    return raw.get("channel_id") or ""


def _reply_id(message: Dict[str, Any]) -> str | None:
    """Pull the tapped option's id out of an interactive reply.

    Whapi nests the payload under a key named by ``reply.type``
    (``buttons_reply``, ``list_reply``, ...), so resolving it by that name
    covers every variant instead of one branch per kind.
    """
    reply = message.get("reply")
    if not reply:
        return None
    kind = reply.get("type")
    if not kind:
        return None
    return (reply.get(kind) or {}).get("id")


def parse(raw: Dict[str, Any]) -> List[InboundMessage]:
    """Decode a Whapi webhook body into domain events.

    Messages we sent ourselves (``from_me``) are dropped: echoing our own
    outbound traffic back through the bot would have it answer itself.
    """
    events: List[InboundMessage] = []

    for message in raw.get("messages") or []:
        if message.get("from_me"):
            continue

        events.append(
            InboundMessage(
                provider=PROVIDER,
                provider_event_id=message["id"],
                chat_id=message["chat_id"],
                from_phone=from_whatsapp_id(message.get("from") or message["chat_id"]),
                from_name=message.get("from_name"),
                body=(message.get("text") or {}).get("body"),
                reply_id=_reply_id(message),
                # Whapi sends seconds, not milliseconds.
                received_at=datetime.fromtimestamp(message["timestamp"], tz=timezone.utc),
            )
        )

    return events
