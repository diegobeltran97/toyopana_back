"""Telling the customer what the shop decided about their request.

This is what closes the loop the web agenda opens. A customer picks an hour,
the shop accepts it in the calendar — and without this, nobody tells them.
They wait, and eventually someone has to remember to write by hand, which is
exactly the manual work the feature was supposed to remove.

Only the two transitions the CUSTOMER is waiting on produce a message:

    solicitada -> agendada    "quedó confirmada"
    solicitada -> cancelada   "no pudimos, escoge otra hora"

Anything else is the shop's internal bookkeeping (agendada -> confirmada is a
staff move) and the customer never asked to hear about it.

También se avisa cuando el taller le mueve la hora a una cita ya aceptada: el
cliente no tiene otra forma de enterarse y llegaría a la hora vieja.

NOTHING HERE MAY RAISE. The status change already happened and is the source of
truth; a WhatsApp that fails to send must never roll back an accepted
appointment. Same rule as the webhook's post-200 half.
"""

import logging
from datetime import datetime
from typing import Any, Dict, Optional

from core.config import settings
from integrations.messaging.base import MessagingProvider
from services.allowlist import puede_recibir
from schemas.messaging import OutboundMessage
from services.business_rules import a_hora_local

logger = logging.getLogger(__name__)

# Las únicas transiciones que el cliente está esperando. La llave es
# (estado anterior, estado nuevo).
_AVISAR = {
    ("solicitada", "agendada"),
    ("solicitada", "cancelada"),
}

_DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
_MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
          "agosto", "septiembre", "octubre", "noviembre", "diciembre"]


def _texto_de_estado(valor: Any) -> str:
    """El estado como texto, venga como enum o como string.

    `cita.model_dump()` deja `status` como CitaStatus, y `str(CitaStatus.agendada)`
    da "CitaStatus.agendada". Comparar eso contra "agendada" falla, y el aviso se
    saltaba EN SILENCIO: confirmar una cita no le llegaba a nadie y no aparecía
    ningún error. Un fallo así solo se descubre cuando un cliente pregunta por
    qué no le avisaron.
    """
    return str(getattr(valor, "value", valor) or "")


def _cuando_legible(momento: datetime) -> str:
    """"viernes 15 de septiembre a las 8:00 a.m.", en hora del taller.

    En hora local y no UTC: 13:00 UTC son las 8:00 a.m. en Panamá, y mandar la
    hora UTC citaría al cliente cinco horas tarde.
    """
    local = a_hora_local(momento)
    sufijo = "a.m." if local.hour < 12 else "p.m."
    hora12 = local.hour % 12 or 12
    return (
        f"{_DIAS[local.weekday()]} {local.day} de {_MESES[local.month - 1]} "
        f"a las {hora12}:{local.minute:02d} {sufijo}"
    )


def _a_momento(valor: Any) -> Optional[datetime]:
    """Un `scheduled_at` como datetime, venga como datetime o como texto.

    PostgREST devuelve timestamptz como "2026-09-15T13:00:00+00:00", y
    `cita.model_dump()` lo deja como datetime. Compararlos crudos no falla:
    da "distinto" siempre, y mandaría un aviso en cada PATCH aunque nadie
    hubiera movido nada. Es el mismo modo de fallo silencioso que ya mordió
    con el estado como enum.
    """
    if valor is None:
        return None
    if isinstance(valor, datetime):
        return valor
    try:
        return datetime.fromisoformat(str(valor))
    except ValueError:
        logger.warning("scheduled_at ilegible: %r", valor)
        return None


def _mensaje(nuevo_estado: str, nombre: str, cuando: str) -> Optional[str]:
    """La copia de cada aviso."""
    if nuevo_estado == "agendada":
        return (
            f"✅ ¡Listo {nombre}! Tu cita quedó *confirmada* para el {cuando}\n\n"
            "Te esperamos en Suspensiones Toyopana, Plaza Toledo, Local #6.\n\n"
            "Si necesitas cambiarla, escríbenos por aquí."
        )

    if nuevo_estado == "cancelada":
        # Un rechazo seco pierde al cliente. El objetivo de este mensaje no es
        # informar que no se pudo, es que escoja otra hora.
        return (
            f"Hola {nombre}, para el {cuando} no tenemos espacio 😔\n\n"
            "¿Te sirve otra fecha? Escríbenos y con gusto buscamos un horario "
            "que te quede bien."
        )

    return None


# Los estados en que mover la cita le concierne al cliente. Una `solicitada`
# movida es el taller proponiendo otra hora, y eso va por su propio flujo.
_MOVIBLES = {"agendada", "confirmada"}


def _mensaje_de_cambio_de_hora(nombre: str, antes: str, ahora: str) -> str:
    # `antes` y `ahora` ya terminan en "a.m."/"p.m." (_cuando_legible): un punto
    # detrás de cualquiera de los dos deja "8:00 a.m..", que se ve descuidado.
    return (
        f"📅 Hola {nombre}, movimos tu cita para el {ahora}\n\n"
        f"Antes era el {antes} — si no te sirve, escríbenos y buscamos otra."
    )


def _destinatario(cita: Dict[str, Any]) -> Optional[tuple]:
    """A quién se le escribe: (teléfono, primer nombre). None si no se puede.

    El cliente del CRM manda cuando existe (cita creada en el panel); si no, los
    datos que la persona dejó en la agenda web. Sin este segundo caso ninguna
    solicitud recibiría confirmación, que es justo para lo que existe.
    """
    cliente = cita.get("customer") or {}
    telefono = cliente.get("phone") or cita.get("solicitante_telefono")
    nombre_completo = cliente.get("name") or cita.get("solicitante_nombre") or ""

    if not telefono:
        # Un cliente sin teléfono cargado no tiene a dónde recibir el aviso.
        # No es un error: el taller lo verá igual en su calendario.
        logger.info("Cita %s sin teléfono; no se avisa", cita.get("id"))
        return None

    # Misma compuerta que las respuestas del bot: mientras se prueba, solo los
    # números listados reciben mensajes.
    if not puede_recibir(telefono):
        return None

    return telefono, nombre_completo.split(" ")[0]


async def _entregar(
    provider: MessagingProvider,
    telefono: str,
    cuerpo: Optional[str],
    cita_id: Any,
) -> None:
    """Manda el mensaje y registra el resultado. NUNCA lanza."""
    if cuerpo is None:
        return

    try:
        resultado = await provider.send_text(
            OutboundMessage(phone=telefono, body=cuerpo)
        )
    except Exception:
        logger.exception("No se pudo avisar la cita %s", cita_id)
        return

    if not resultado.ok:
        logger.error(
            "El proveedor rechazó el aviso de la cita %s: %s", cita_id, resultado.error
        )
        return

    logger.info("Avisada la cita %s", cita_id)


# Una cita que NACE firme: el taller la agendó por el cliente, por teléfono o en
# el mostrador. El cliente no pidió nada por la web, así que este es el único
# mensaje que va a recibir — sin él tiene una cita de la que nunca se enteró.
#
# Una cita que nace 'solicitada' NO entra aquí: todavía no está aceptada, y la
# página pública ya le dijo que queda pendiente de confirmación. Su aviso sale
# cuando el taller la acepta, por avisar_cambio_de_cita.
_NACE_FIRME = {"agendada", "confirmada"}


async def avisar_cita_nueva(
    provider: MessagingProvider,
    *,
    cita: Dict[str, Any],
) -> None:
    """Le confirma al cliente la cita que el taller le agendó. Nunca lanza."""
    estado = _texto_de_estado(cita.get("status"))
    if estado not in _NACE_FIRME:
        return

    destino = _destinatario(cita)
    if destino is None:
        return
    telefono, nombre = destino

    try:
        # La misma copia que recibe quien pidió la hora por la web y se la
        # aceptaron: para el cliente las dos cosas son "tengo cita el tal día".
        cuerpo = _mensaje("agendada", nombre, _cuando_legible(cita["scheduled_at"]))
    except Exception:
        logger.exception("No se pudo armar el aviso de la cita %s", cita.get("id"))
        return

    await _entregar(provider, telefono, cuerpo, cita.get("id"))


async def avisar_cambio_de_cita(
    provider: MessagingProvider,
    *,
    anterior: Any,
    scheduled_at_anterior: Any = None,
    cita: Dict[str, Any],
) -> None:
    """Avisa al cliente si el cambio le concierne. Nunca lanza.

    Cubre dos cosas distintas, y en este orden:

      1. El cambio de estado que el cliente estaba esperando.
      2. Que el taller le haya movido la hora a una cita ya aceptada.

    Si en el mismo PATCH cambian las dos, **gana el del estado**: uno solo.
    Aceptar y mover en el mismo gesto es un caso real, y dos WhatsApps
    seguidos se ven descuidados.
    """
    nuevo = _texto_de_estado(cita.get("status"))
    previo = _texto_de_estado(anterior)

    antes = _a_momento(scheduled_at_anterior)
    ahora = _a_momento(cita.get("scheduled_at"))
    movida = antes is not None and ahora is not None and antes != ahora

    cambio_de_estado = (previo, nuevo) in _AVISAR

    if not cambio_de_estado and not (movida and nuevo in _MOVIBLES):
        return

    destino = _destinatario(cita)
    if destino is None:
        return
    telefono, nombre = destino

    try:
        if cambio_de_estado:
            cuerpo = _mensaje(nuevo, nombre, _cuando_legible(cita["scheduled_at"]))
        else:
            cuerpo = _mensaje_de_cambio_de_hora(
                nombre, _cuando_legible(antes), _cuando_legible(ahora)
            )
    except Exception:
        logger.exception("No se pudo armar el aviso de la cita %s", cita.get("id"))
        return

    await _entregar(provider, telefono, cuerpo, cita.get("id"))
