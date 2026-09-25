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

import asyncio
import logging
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Union

from core.config import settings
from integrations.messaging.base import MessagingProvider
from repositories.business_rules import BusinessRulesRepository
from services.agenda_token import crear_token
from services.allowlist import puede_recibir
from services.business_rules import texto_de_horario
from repositories.conversations import (
    ceder_a_un_humano,
    devolver_al_bot,
    record_message,
    tocar_estado_bot,
    touch_last_inbound,
    upsert_conversation,
)
from schemas.inbound import InboundMessage
from schemas.messaging import OutboundButton, OutboundInteractive, OutboundMessage

logger = logging.getLogger(__name__)

# Only this status means the bot owns the conversation. 'waiting', 'agent' and
# 'resolved' all mean a human is involved, and the bot must not talk over them.
BOT_OWNED_STATUS = "bot"

# El estado que el propio bot se pone cuando ya no tiene nada útil que decir.
# Es el ÚNICO que se revierte solo: 'agent' y 'resolved' los puso una persona.
ESTADO_CEDIDO = "waiting"

# Cuánto silencio del cliente hace falta para que la conversación empiece de
# cero y el saludo vuelva a tener sentido.
#
# Se mide sobre el silencio DEL CLIENTE y no sobre la última vez que habló el
# bot. El taller contesta desde su propio WhatsApp y esos mensajes no nos
# llegan (parser.py descarta from_me), así que medir desde el bot haría
# aparecer el menú en medio de una conversación que una persona está
# atendiendo. Que el cliente escriba es la única señal de vida que tenemos.
VENTANA_DE_SESION = timedelta(hours=24)

# How long to wait for the customer to stop typing before answering.
#
# Measured on the pilot's first four days: 25% of inbound messages arrive
# within 25s of the previous one in the same chat. People send one question as
# several messages -- "Buenas" / "venden cubre carter?" / "Elantra 2011" -- and
# answering each fragment means replying before they finished, three times.
#
# The cost is latency: the customer waits this long for an answer. Button taps
# skip it entirely, since a tap is already a complete thought.
DEBOUNCE_SECONDS: float = 25.0

# Messages waiting to be answered, and the timer that will answer them.
# In-process on purpose for now: a single Render instance, and a restart loses
# only the pending REPLY -- every message is already persisted and replayable.
# When that stops being acceptable, whatsapp_events.process_status is the queue
# a real worker would read.
_buffers: Dict[str, List[InboundMessage]] = {}
_timers: Dict[str, asyncio.Task] = {}


def _reset_debounce() -> None:
    """Drop all pending state. For tests."""
    for task in _timers.values():
        task.cancel()
    _timers.clear()
    _buffers.clear()


async def wait_for_pending() -> None:
    """Await every scheduled reply. For tests."""
    tasks = [t for t in _timers.values() if not t.done()]
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)


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
            ("menu_otro", "Otro"),
        ],
        # Shown on the control that opens the list. With four options WhatsApp
        # no longer renders buttons, and the adapter switches form on its own.
        "list_label": "Ver opciones",
    },
    "menu_horarios": {
        # SIN horario quemado: lo antepone _mensaje_de_horarios() leyendo
        # business_hours. Dos copias del mismo dato es una que se queda vieja.
        # Los asteriscos son negrita en WhatsApp, no markdown nuestro.
        "mensaje": (
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
        # RESPALDO. Lo normal es mandar el link de la agenda (ver
        # _mensaje_de_agenda); este texto solo sale si no se puede emitir uno,
        # porque dejar al cliente sin respuesta es peor que negociar por chat.
        "mensaje": (
            "Con gusto te agendamos 📅\n\n"
            "Indícanos qué día y hora te quedan bien, y el modelo de tu vehículo. "
            "Un asesor te confirma en breve."
        ),
    },
    "menu_otro": {
        "mensaje": (
            "Con gusto te ayudamos 🙌\n\n"
            "Cuéntanos en qué te podemos servir y un asesor te responde "
            "en horario de atención."
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


# Free text that unambiguously names a menu option routes straight to it.
# Someone typing "cual es el horario" wants the answer, not a menu asking them
# to pick it -- and every hit here is one fewer LLM call once the model lands.
#
# Deliberately narrow. Guessing wrong is worse than showing the menu: the
# customer gets a confident answer to a question they did not ask.
PALABRAS_CLAVE: dict = {
    "menu_agendar_cita": (
        "cita",
        "agendar",
        "agenda",
        "turno",
        "reservar",
    ),
    "menu_horarios": (
        "horario",
        "horarios",
        "ubicacion",
        "direccion",
        "donde quedan",
        "donde estan",
        "como llego",
        "abren",
    ),
}


# Text WhatsApp prefills when someone taps the button on a Facebook/Instagram
# ad. It says nothing about what the customer wants -- 12% of the pilot's
# inbound traffic is this exact string.
#
# Stripped as noise rather than answered on sight: 29% of the people who send
# it follow with their real question within 25 seconds, so replying to it would
# be answering before they finished. What is left after stripping is what they
# actually asked; nothing left means they only tapped the ad.
RUIDO_DE_ANUNCIOS = (
    "¡Hola! Me gustaría conseguir más información sobre esto.",
    "¡Hola! Quiero más información",
    "Hola! Quiero más información",
)


def _quitar_ruido(texto: str) -> str:
    """Drop the ad's canned prefix, keeping whatever the customer added."""
    limpio = texto
    for enlatado in RUIDO_DE_ANUNCIOS:
        if limpio.strip().startswith(enlatado):
            limpio = limpio.strip()[len(enlatado):]
            break
    return limpio.strip()


def _normalizar(texto: str) -> str:
    """Lowercase and strip accents, so "ubicación" and "ubicacion" match.

    People type both, and a bot that answers only the accented spelling looks
    broken to whoever typed the other one.
    """
    sin_tildes = unicodedata.normalize("NFD", texto.lower())
    return "".join(c for c in sin_tildes if unicodedata.category(c) != "Mn")


def _menciona(texto: str, palabra: str) -> bool:
    """Si el texto contiene la palabra COMO PALABRA, no como pedazo de otra.

    Buscar el substring pelado hacía que "me solicitaron una cotizacion"
    mandara el link de la agenda: "soli-cita-ron" contiene "cita". El borde de
    palabra es lo que separa pedir una cita de nombrarla por accidente, y sirve
    igual para las frases de varias palabras ("donde quedan").
    """
    return re.search(rf"(?<!\w){re.escape(palabra)}(?!\w)", texto) is not None


def _nodo_por_palabra_clave(body: Optional[str]) -> Optional[str]:
    """The node a free-text message names, if any."""
    if not body:
        return None

    texto = _normalizar(body)
    for nodo, palabras in PALABRAS_CLAVE.items():
        if any(_menciona(texto, p) for p in palabras):
            return nodo
    return None


async def leer_texto_de_horario(organization_id: str) -> str:
    """El horario de atención del taller, como texto, desde business_hours.

    Aislado en su propia función para que el nodo no sepa de repositorios y
    para que los tests puedan sustituirlo sin tocar la red.
    """
    repo = BusinessRulesRepository()
    return texto_de_horario(await repo.semana(organization_id))


async def _mensaje_de_horarios(organization_id: str, phone: str) -> OutboundMessage:
    """El nodo de horarios, con el horario real antepuesto a la dirección.

    Una caída de la base no puede dejar al cliente sin respuesta: en ese caso
    se manda la dirección sola, que es mejor que el silencio.
    """
    cuerpo = FLUJO["menu_horarios"]["mensaje"]

    try:
        horario = await leer_texto_de_horario(organization_id)
    except Exception:
        logger.exception("No se pudo leer el horario; se responde sin esa sección")
        horario = ""

    if horario:
        cuerpo = f"🕐 *Horario de atención*\n{horario}\n\n{cuerpo}"

    return OutboundMessage(phone=phone, body=cuerpo)


async def _mensaje_de_agenda(organization_id: str, phone: str) -> OutboundMessage:
    """El link para que el cliente escoja su hora.

    El bot no negocia la fecha por chat: interpretar "el viernes temprano" es lo
    más frágil que se podría construir aquí, y una conversación no puede mostrar
    lo que ya está ocupado. La agenda sí.

    Si no se puede emitir el link (falta AGENDA_TOKEN_SECRET), cae al texto de
    siempre: dejar al cliente sin respuesta es peor que pedirle los datos.
    """
    try:
        base = (settings.AGENDA_BASE_URL or "").rstrip("/")
        if not base:
            raise RuntimeError("AGENDA_BASE_URL sin configurar")
        url = f"{base}/agenda/{crear_token(organization_id)}"
    except Exception:
        logger.exception("No se pudo emitir el link de agenda; se responde con el texto")
        return _node_to_message(FLUJO["menu_agendar_cita"], phone)

    return OutboundMessage(
        phone=phone,
        body=(
            "Con gusto 📅\n\n"
            "Escoge el día y la hora que te sirvan aquí:\n"
            f"{url}\n\n"
            "Queda *pendiente de confirmación* del taller — te aviso por aquí "
            "apenas la revisen."
        ),
    )


# Nodos que no son texto fijo: se arman con datos del taller. Están en un
# registro y no en ifs sueltos porque se llega a ellos por dos caminos --el
# botón y la palabra clave-- y los dos tienen que responder lo mismo.
NODOS_DINAMICOS = {
    "menu_horarios": _mensaje_de_horarios,
    "menu_agendar_cita": _mensaje_de_agenda,
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
        list_label=node.get("list_label", "Ver opciones"),
    )


def _welcome_menu(phone: str) -> OutboundInteractive:
    """The tree's entry node."""
    return _node_to_message(FLUJO[NODO_INICIAL], phone)


# ---------------------------------------------------------------------------
# El acuse de recibo: lo último que dice el bot antes de callarse.
#
# Lo manda cuando el cliente escribe algo que el árbol no cubre Y la
# conversación ya venía andando -- casi siempre porque está contestando lo que
# el propio bot le preguntó. Antes eso devolvía el menú de bienvenida: el bot
# preguntaba, le contestaban, y volvía a saludar como si nada.
#
# Callarse del todo tampoco servía: el cliente queda sin saber si lo leyeron.
# Se acusa recibo UNA vez y la conversación pasa a una persona, que es quien
# puede cotizar de verdad.
# ---------------------------------------------------------------------------

ACUSES: dict = {
    "menu_cotizacion": (
        "¡Listo! 🙌 Ya tenemos tus datos.\n\n"
        "Un asesor te confirma *precio y disponibilidad* en breve."
    ),
}

ACUSE_POR_DEFECTO = (
    "¡Listo! 🙌 Un asesor ya va a leer tu mensaje y te responde "
    "en horario de atención."
)


def _acuse(nodo: Optional[str], phone: str) -> OutboundMessage:
    """El acuse que corresponde al nodo donde venía la conversación."""
    return OutboundMessage(phone=phone, body=ACUSES.get(nodo or "", ACUSE_POR_DEFECTO))


def _momento(valor: Any) -> Optional[datetime]:
    """El texto ISO que manda PostgREST, como datetime con zona.

    Una marca ilegible se trata como si no existiera: dar la sesión por vencida
    hace que el bot salude de más, que es mucho más barato que quedarse callado
    para siempre por un dato corrupto.
    """
    if not valor:
        return None

    try:
        momento = datetime.fromisoformat(str(valor))
    except ValueError:
        logger.warning("bot_node_at ilegible (%r); se ignora la sesión", valor)
        return None

    # Sin zona se asume UTC, que es como Postgres guarda los timestamptz.
    return momento if momento.tzinfo else momento.replace(tzinfo=timezone.utc)


def _nodo_activo(conversation: dict) -> Optional[str]:
    """En qué nodo va la conversación, o None si no hay una sesión viva.

    None significa las dos cosas que se tratan igual: el bot nunca habló en
    este chat, o habló hace tanto que lo que llega ahora es una consulta nueva.
    En ambos casos el saludo es la respuesta correcta.
    """
    nodo = conversation.get("bot_node")
    if not nodo:
        return None

    desde = _momento(conversation.get("bot_node_at"))
    if desde is None or datetime.now(timezone.utc) - desde > VENTANA_DE_SESION:
        return None

    return nodo


def _sesion_vencida(conversation: dict) -> bool:
    """¿La última actividad que registramos ya pasó la ventana?

    NO es lo mismo que `_nodo_activo(...) is None`, que también da cierto
    cuando nunca hubo actividad -- y esa diferencia es la que decide si el bot
    puede retomar una conversación cedida. Reactivarlo exige que el reloj haya
    corrido de verdad: un 'waiting' sin marca de tiempo no lo puso el bot sino
    una persona, y quitárselo es hablarle encima.
    """
    desde = _momento(conversation.get("bot_node_at"))
    return desde is not None and datetime.now(timezone.utc) - desde > VENTANA_DE_SESION


# La compuerta vive en services/allowlist.py, compartida con los avisos de
# cita: una copia por sitio de uso es como uno de los dos deja de respetarla.
_is_reply_allowed = puede_recibir


@dataclass(frozen=True)
class Decision:
    """Qué contestar, y en qué deja la conversación.

    Las tres cosas viajan juntas porque se deciden juntas: quien escoge el
    mensaje es el único que sabe en qué nodo queda el cliente y si el bot
    todavía tiene algo que aportar. Devolver solo el mensaje fue lo que dejó
    la decisión sin memoria.
    """

    mensaje: Union[OutboundMessage, OutboundInteractive, None] = None
    nodo: Optional[str] = None      # el nodo que queda vigente tras responder
    ceder: bool = False             # ¿pasa a una persona después de esto?


async def _decide_reply(
    organization_id: str,
    event: InboundMessage,
    *,
    nodo_actual: Optional[str] = None,
) -> Decision:
    """Decide what to answer (SEAM).

    1. A tapped button routes through the tree. Deterministic, costs nothing,
       and covers the traffic we can anticipate.
    2. Free text that unambiguously names an option routes there too.
    3. Lo que no cae en ninguna de las dos depende de si la conversación ya
       venía andando:
         * `nodo_actual` es None -- nadie ha hablado, o el último mensaje fue
           hace más de la ventana. El saludo es la respuesta correcta.
         * `nodo_actual` tiene valor -- el bot ya habló, y lo más probable es
           que esto sea la respuesta a lo que él mismo preguntó. Repetir el
           menú ahí es el bug del 2026-09-24: se acusa recibo y pasa a una
           persona.

    THIS is where the DecisionEngine (Claude) goes: el punto 3 es la costura,
    no un callejón sin salida.
    """
    nodo_id = event.reply_id or ""
    if nodo_id in NODOS_DINAMICOS:
        mensaje = await NODOS_DINAMICOS[nodo_id](organization_id, event.from_phone)
        return Decision(mensaje, nodo=nodo_id)

    node = FLUJO.get(nodo_id)
    if node is not None:
        return Decision(_node_to_message(node, event.from_phone), nodo=nodo_id)

    # The ad's canned text carries no intent; deciding with it in the way only
    # adds noise, and will do the same to the LLM's prompt later.
    texto = _quitar_ruido(event.body or "")

    por_palabra = _nodo_por_palabra_clave(texto)
    if por_palabra is not None:
        logger.info("Texto libre ruteado a %r por palabra clave", por_palabra)
        if por_palabra in NODOS_DINAMICOS:
            mensaje = await NODOS_DINAMICOS[por_palabra](
                organization_id, event.from_phone
            )
        else:
            mensaje = _node_to_message(FLUJO[por_palabra], event.from_phone)
        return Decision(mensaje, nodo=por_palabra)

    if nodo_actual is not None:
        logger.info(
            "La conversación ya venía en %r; se acusa recibo y pasa a un humano",
            nodo_actual,
        )
        return Decision(
            _acuse(nodo_actual, event.from_phone), nodo=nodo_actual, ceder=True
        )

    # -- FUTURE: DecisionEngine(Claude).decide(event) goes here --
    return Decision(_welcome_menu(event.from_phone), nodo=NODO_INICIAL)


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

    # En qué nodo venía la conversación. Es lo que impide que el bot vuelva a
    # saludar a quien está contestándole.
    nodo_actual = _nodo_activo(conversation)
    status = conversation.get("status")

    # Un cliente que vuelve después de la ventana trae una consulta nueva, y el
    # bot tiene que poder atenderla. Solo se reactiva lo que él mismo silenció:
    # 'agent' y 'resolved' los puso una persona, y resucitar sobre eso es
    # justamente hablarle encima a un colega.
    if status == ESTADO_CEDIDO and _sesion_vencida(conversation):
        if await _sin_reventar(
            devolver_al_bot(conversation_id=conversation_id),
            "devolverle la conversación al bot",
        ):
            status = BOT_OWNED_STATUS

    if status != BOT_OWNED_STATUS:
        if status == ESTADO_CEDIDO:
            # El cliente acaba de escribir: esta conversación NO está en
            # silencio, y el reloj de la ventana tiene que reflejarlo. Sin
            # esto, a quien insiste cada pocas horas le aparecería el menú a
            # las 24 horas del último mensaje del bot, en plena conversación.
            await _sin_reventar(
                tocar_estado_bot(conversation_id=conversation_id),
                "refrescar la actividad de la conversación",
            )
        logger.info(
            "Conversación %s en estado %r; el bot no responde",
            conversation_id,
            status,
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

    # A tapped button is already a complete thought: waiting on it would be
    # latency that buys nothing.
    if event.reply_id:
        decision = await _decide_reply(
            organization_id, event, nodo_actual=nodo_actual
        )
        await _aplicar(provider, conversation_id, decision)
        return

    _schedule_reply(provider, organization_id, conversation_id, event, nodo_actual)


def _schedule_reply(
    provider: MessagingProvider,
    organization_id: str,
    conversation_id: str,
    event: InboundMessage,
    nodo_actual: Optional[str] = None,
) -> None:
    """Buffer the message and (re)start this conversation's reply timer.

    A newer message cancels the pending timer, so the burst is answered once,
    after it ends, with everything the customer said.

    El nodo viaja con el temporizador y no se relee al disparar: dentro de una
    ráfaga el bot no ha contestado, así que no ha cambiado.
    """
    _buffers.setdefault(conversation_id, []).append(event)

    pendiente = _timers.pop(conversation_id, None)
    if pendiente is not None:
        pendiente.cancel()

    _timers[conversation_id] = asyncio.create_task(
        _reply_after_quiet(provider, organization_id, conversation_id, nodo_actual)
    )


async def _reply_after_quiet(
    provider: MessagingProvider,
    organization_id: str,
    conversation_id: str,
    nodo_actual: Optional[str] = None,
) -> None:
    """Wait out the quiet period, then answer the whole burst once."""
    try:
        await asyncio.sleep(DEBOUNCE_SECONDS)
    except asyncio.CancelledError:
        return  # a newer message took over; it owns the reply now

    eventos = _buffers.pop(conversation_id, [])
    _timers.pop(conversation_id, None)
    if not eventos:
        return

    # Decide on everything they said, not just the last line: someone who asks
    # the schedule and then says "gracias" must be answered on the question.
    combinado = eventos[-1].model_copy(
        update={"body": "\n".join(e.body for e in eventos if e.body) or None}
    )

    decision = await _decide_reply(
        organization_id, combinado, nodo_actual=nodo_actual
    )
    await _aplicar(provider, conversation_id, decision)


async def _sin_reventar(corutina, que: str) -> bool:
    """Ejecuta algo que no puede tumbar el manejo del mensaje.

    Todo esto corre después del 200 al proveedor: ya no queda código de estado
    donde poner una falla, y una excepción solo mataría la tarea de fondo.
    Devuelve si salió bien, porque hay decisiones que dependen de ello.
    """
    try:
        await corutina
        return True
    except Exception:
        logger.exception("No se pudo %s", que)
        return False


async def _aplicar(
    provider: MessagingProvider, conversation_id: str, decision: Decision
) -> None:
    """Manda la respuesta y deja la conversación donde corresponde.

    El orden importa: primero se envía, y solo si el mensaje salió se guarda el
    nodo. Recordar un mensaje que nunca llegó deja al cliente mudo -- él no vio
    nada, y el bot creería que ya habló y no volvería a saludar.
    """
    if decision.mensaje is None:
        return

    if not await _send_reply(provider, conversation_id, decision.mensaje):
        return

    await _sin_reventar(
        tocar_estado_bot(conversation_id=conversation_id, nodo=decision.nodo),
        "guardar el nodo de la conversación",
    )

    if decision.ceder:
        await _sin_reventar(
            ceder_a_un_humano(conversation_id=conversation_id),
            "pasarle la conversación a una persona",
        )


async def _send_reply(
    provider: MessagingProvider, conversation_id: str, reply
) -> bool:
    """Send one reply and record it. Never raises. Devuelve si salió."""
    try:
        # A text node and a button node are different provider calls; sending a
        # buttonless message through send_interactive would be rejected.
        if isinstance(reply, OutboundInteractive):
            result = await provider.send_interactive(reply)
        else:
            result = await provider.send_text(reply)
    except Exception:
        logger.exception("Falló el envío de la respuesta a %s", reply.phone)
        return False

    if not result.ok:
        logger.error("El proveedor rechazó la respuesta: %s (%s)", result.error, result.details)
        return False

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

    return True
