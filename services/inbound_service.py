"""The post-200 half of the inbound webhook: persist, then reply.

Everything in this module runs after the provider already received its 200, so
the governing rule is that nothing may raise. There is no status code left to
carry a failure, and an exception here would only kill a background task and
lose the message we just stored.

Two seams are deliberately marked and live nowhere else:
  1. `_decide_reply` -- today a hardcoded welcome menu. This is where the
     deterministic reply_id routing and then the LLM go.
  2. the post-persist step order -- replying is step A.
"""

import logging
from typing import Optional

from core.config import settings
from integrations.messaging.base import MessagingProvider
from repositories.conversations import (
    record_message,
    touch_last_inbound,
    upsert_conversation,
)
from schemas.inbound import InboundMessage
from schemas.messaging import OutboundButton, OutboundInteractive

logger = logging.getLogger(__name__)

# Only this status means the bot owns the conversation. 'waiting', 'agent' and
# 'resolved' all mean a human is involved, and the bot must not talk over them.
BOT_OWNED_STATUS = "bot"


def _welcome_menu(phone: str) -> OutboundInteractive:
    """The hardcoded welcome menu.

    HARDCODED ON PURPOSE, FOR NOW. When tenant_bot_config lands this copy comes
    from that tenant's row instead -- the shape does not change, only where the
    strings come from.

    The button ids are the contract with the inbound side: they come back as
    `reply.buttons_reply.id`, which is what lets the next message be routed
    deterministically instead of being read by an LLM.
    """
    return OutboundInteractive(
        phone=phone,
        body=(
            "Hola 👋 Gracias por contactar a Suspensiones Toyopana. "
            "¿En qué te podemos ayudar?"
        ),
        buttons=[
            OutboundButton(id="menu_agendar_cita", title="Agendar cita"),
            OutboundButton(id="menu_cotizacion", title="Cotización"),
            OutboundButton(id="menu_otro", title="Otro"),
        ],
    )


def _only_digits(phone: str) -> str:
    """Compare numbers by their digits alone.

    The setting is typed by a human, so "+507 6851-0658", "507 6851 0658" and
    "50768510658" all have to mean the same number. A formatting difference
    silently stopping the replies would look exactly like a broken bot.
    """
    return "".join(filter(str.isdigit, phone))


def _is_reply_allowed(phone: str) -> bool:
    """Testing-mode allowlist.

    Empty setting means disabled: everyone gets a reply. That direction matters
    -- forgetting to configure this can never silence the bot, while setting it
    by accident is loud (every skip is logged) and obvious.
    """
    raw = getattr(settings, "WHATSAPP_ALLOWED_NUMBERS", "") or ""
    allowed = {_only_digits(n) for n in raw.split(",") if _only_digits(n)}

    if not allowed:
        return True

    return _only_digits(phone) in allowed


def _decide_reply(event: InboundMessage) -> Optional[OutboundInteractive]:
    """Decide what to answer (SEAM).

    FUTURE, in this order:
      1. `event.reply_id` is set -> deterministic handler for that menu option.
         Costs nothing and covers most traffic.
      2. free text -> the DecisionEngine (Claude) with org-scoped tools.
    Today it always answers the welcome menu.
    """
    return _welcome_menu(event.from_phone)


async def handle_inbound(
    provider: MessagingProvider,
    *,
    organization_id: str,
    event: InboundMessage,
) -> None:
    """Persist an inbound message and reply to it. Never raises."""
    try:
        conversation = await upsert_conversation(
            organization_id=organization_id, chat_id=event.chat_id
        )
        conversation_id = conversation.get("id")

        await record_message(
            conversation_id=conversation_id,
            direction="inbound",
            wa_message_id=event.provider_event_id,
            body=event.body,
        )
        await touch_last_inbound(organization_id=organization_id, phone=event.from_phone)
    except Exception:
        # The message is already in whatsapp_events, so it is replayable.
        logger.exception("No se pudo persistir el mensaje entrante %s", event.provider_event_id)
        return

    if conversation.get("status") != BOT_OWNED_STATUS:
        logger.info(
            "Conversación %s en estado %r; el bot no responde",
            conversation_id,
            conversation.get("status"),
        )
        return

    # Testing-mode gate. Placed here, after persistence, on purpose: an
    # unlisted customer's message is still recorded, so testing never costs
    # visibility into what real people are sending.
    if not _is_reply_allowed(event.from_phone):
        logger.warning(
            "WHATSAPP_ALLOWED_NUMBERS activo: no se responde a %s", event.from_phone
        )
        return

    reply = _decide_reply(event)
    if reply is None:
        return

    try:
        result = await provider.send_interactive(reply)
    except Exception:
        logger.exception("Falló el envío de la respuesta a %s", event.from_phone)
        return

    if not result.ok:
        logger.error("El proveedor rechazó la respuesta: %s (%s)", result.error, result.details)
        return

    # Record our own side of the thread. Without this the conversation has a
    # gap and repositories/marketing.py undercounts messages sent.
    try:
        await record_message(
            conversation_id=conversation_id,
            direction="outbound",
            wa_message_id=result.value.id if result.value else None,
            body=reply.body,
        )
    except Exception:
        logger.exception("No se pudo registrar la respuesta enviada")
