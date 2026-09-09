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


async def avisar_cambio_de_estado(
    provider: MessagingProvider,
    *,
    anterior: str,
    cita: Dict[str, Any],
) -> None:
    """Avisa al cliente si el cambio de estado le concierne. Nunca lanza."""
    nuevo = str(cita.get("status") or "")

    if (anterior, nuevo) not in _AVISAR:
        return

    cliente = cita.get("customer") or {}
    telefono = cliente.get("phone")
    if not telefono:
        # Un cliente sin teléfono cargado no tiene a dónde recibir el aviso.
        # No es un error: el taller lo verá igual en su calendario.
        logger.info("Cita %s sin teléfono; no se avisa", cita.get("id"))
        return

    # Misma compuerta que las respuestas del bot: mientras se prueba, solo los
    # números listados reciben mensajes.
    if not puede_recibir(telefono):
        return

    try:
        cuerpo = _mensaje(
            nuevo,
            (cliente.get("name") or "").split(" ")[0] or "",
            _cuando_legible(cita["scheduled_at"]),
        )
        if cuerpo is None:
            return

        resultado = await provider.send_text(
            OutboundMessage(phone=telefono, body=cuerpo)
        )
    except Exception:
        logger.exception("No se pudo avisar el cambio de estado de la cita %s",
                         cita.get("id"))
        return

    if not resultado.ok:
        logger.error(
            "El proveedor rechazó el aviso de la cita %s: %s",
            cita.get("id"), resultado.error,
        )
        return

    logger.info("Avisado el paso %s -> %s de la cita %s", anterior, nuevo, cita.get("id"))
