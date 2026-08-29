"""Whapi inbound wire format -> domain DTOs.

The inbound counterpart to mapper.py. Everything Whapi-specific about a
received message is decoded here: the ``@s.whatsapp.net`` suffix, the
``from_me`` flag, the ``reply.<type>.id`` nesting, and timestamps in seconds.

``parse()`` returns a *list* because Whapi batches several messages into one
POST. Typing it as a single event loses messages silently.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List

from schemas.inbound import InboundMessage
from integrations.whapi.mapper import from_whatsapp_id

logger = logging.getLogger(__name__)

PROVIDER = "whapi"

# Message types the bot actually understands. Anything else is stored raw in
# whatsapp_events but produces NO domain event, so it can never trigger a
# reply. An allowlist, not a denylist, on purpose: WhatsApp emits protocol
# notifications (type "unknown", source "system") that Whapi forwards with
# from_me false and no content. Filtering only on from_me let those through as
# if a customer had written, and the bot answered the welcome menu three times
# for every real message. Adding media support means adding types here,
# deliberately.
HANDLED_TYPES = frozenset({"text", "reply"})

# Whapi echoes back the button id we sent with its own prefix
# ("ButtonsV3:menu_cotizacion"). Stripping it here is what makes the id we send
# equal the id we receive -- without it, deterministic routing on reply_id
# silently never matches.
_REPLY_ID_PREFIXES = ("ButtonsV3:",)


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

    raw_id = (reply.get(kind) or {}).get("id")
    if not raw_id:
        return None

    for prefix in _REPLY_ID_PREFIXES:
        if raw_id.startswith(prefix):
            return raw_id[len(prefix):]
    return raw_id


def parse(raw: Dict[str, Any]) -> List[InboundMessage]:
    """Decode a Whapi webhook body into domain events.

    Two kinds are dropped:

      * ``from_me`` -- our own outbound traffic, echoed back. Answering it
        would have the bot talk to itself.
      * any type outside HANDLED_TYPES -- notably WhatsApp's system
        notifications, which arrive with from_me false and no content at all.

    Both are still stored raw by the caller; they just produce no domain event.
    """
    events: List[InboundMessage] = []

    for message in raw.get("messages") or []:
        if message.get("from_me"):
            continue

        if message.get("type") not in HANDLED_TYPES:
            logger.info(
                "Mensaje %s de tipo %r ignorado (source=%r)",
                message.get("id"),
                message.get("type"),
                message.get("source"),
            )
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
