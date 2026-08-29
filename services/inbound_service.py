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
from schemas.messaging import OutboundButton, OutboundInteractive, OutboundMessage

logger = logging.getLogger(__name__)

# Only this status means the bot owns the conversation. 'waiting', 'agent' and
# 'resolved' all mean a human is involved, and the bot must not talk over them.
BOT_OWNED_STATUS = "bot"


# ---------------------------------------------------------------------------
# The reply tree.
#
# A dict, not a table, ON PURPOSE and for now. The expensive part of this
# feature was never the storage -- it is knowing what the flow should say, and
# a dict teaches that just as well as a schema would while the pilot customer
# is still telling us what he wants. Moving it to a `flow jsonb` column on
# tenant_bot_config is mechanical once the shape stops changing.
#
# Each node: `mensaje` (required) plus optional `botones`. A node with no
# buttons goes out as plain text -- WhatsApp requires at least one button on an
# interactive message, so the two cannot share a send path.
#
# WhatsApp caps interactive messages at 3 buttons. Needing a fourth option
# means switching to a list message (up to 10), which is a different Whapi
# payload shape.
# ---------------------------------------------------------------------------

NODO_INICIAL = "inicio"

FLUJO: dict = {
    "inicio": {
        "mensaje": (
            "Hola 👋 Gracias por contactar a Suspensiones Toyopana. "
            "¿En qué te podemos ayudar?"
        ),
        "botones": [
            ("menu_agendar_cita", "Agendar cita"),
            ("menu_cotizacion", "Cotización"),
            ("menu_horarios", "Horarios y ubicación"),
        ],
    },
    "menu_horarios": {
        # Los asteriscos son negrita en WhatsApp, no markdown nuestro.
        "mensaje": (
            "🕐 *Horario de atención*\n"
            "Lunes a viernes: 8:00 a.m. – 5:00 p.m.\n"
            "Sábados: 8:00 a.m. – 3:00 p.m.\n"
            "Domingos: cerrado\n\n"
            "📍 *Cómo llegar*\n"
            "Vía Fernández de Córdoba, Vista Hermosa.\n"
            "Plaza Toledo, Local #6 — busca el aviso en letras verdes "
            "que dice *Suspensiones Toyopana*.\n\n"
            "Estamos frente a la entrada del taller AutoColor, "
            "al lado de Burger King.\n\n"
            "🗺️ En Waze o Google Maps búscanos como *Suspensiones Toyopana*.\n\n"
            "¿Necesitas algo más? Escríbenos y con gusto te ayudamos."
        ),
    },
    "menu_agendar_cita": {
        "mensaje": (
            "Con gusto te agendamos 📅\n\n"
            "Indícanos qué día y hora te quedan bien, y el modelo de tu vehículo. "
            "Un asesor te confirma en breve."
        ),
    },
    "menu_cotizacion": {
        "mensaje": (
            "Para cotizarte necesitamos 🛠️\n\n"
            "• La pieza que buscas\n"
            "• Marca, modelo y año del vehículo\n\n"
            "Escríbenos esos datos y te pasamos precio y disponibilidad."
        ),
    },
}


def _node_to_message(node: dict, phone: str):
    """A tree node -> the outbound DTO its shape calls for.

    Buttons or no buttons decides which provider call is legal, so the branch
    lives here rather than being re-derived at the send site.
    """
    botones = node.get("botones") or []

    if not botones:
        return OutboundMessage(phone=phone, body=node["mensaje"])

    return OutboundInteractive(
        phone=phone,
        body=node["mensaje"],
        buttons=[OutboundButton(id=bid, title=titulo) for bid, titulo in botones],
    )


def _welcome_menu(phone: str) -> OutboundInteractive:
    """The tree's entry node."""
    return _node_to_message(FLUJO[NODO_INICIAL], phone)


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


def _decide_reply(event: InboundMessage):
    """Decide what to answer (SEAM).

    1. A tapped button routes through the tree. Deterministic, costs nothing,
       and covers the traffic we can anticipate.
    2. Anything else -- free text, or a button id the tree no longer has
       (an old chat still showing a retired menu) -- falls back to the welcome
       menu. THIS is where the DecisionEngine (Claude) goes: the fallback is
       the seam, not a dead end.
    """
    node = FLUJO.get(event.reply_id or "")
    if node is not None:
        return _node_to_message(node, event.from_phone)

    # -- FUTURE: DecisionEngine(Claude).decide(event) goes here --
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
        # A text node and a button node are different provider calls; sending a
        # buttonless message through send_interactive would be rejected.
        if isinstance(reply, OutboundInteractive):
            result = await provider.send_interactive(reply)
        else:
            result = await provider.send_text(reply)
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
