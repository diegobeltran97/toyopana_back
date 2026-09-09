"""Use-cases behind the public booking page.

Puts together the business rules (which hours exist and which are free) and the
citas repository (creating the request). Everything it needs about WHO is
asking arrives as arguments, resolved from the signed token by the endpoint --
never from the request body.
"""

import logging
from datetime import date, datetime, time, timedelta
from typing import Any, Dict, List, Optional

from repositories.business_rules import BusinessRulesRepository
from services import citas_service
from services.business_rules import (
    PANAMA,
    bloques_del_dia,
    cabe_antes_del_cierre,
    ocupacion_de_citas,
    resolver_dia,
)
from schemas.cita import CitaCreate, CitaStatus

logger = logging.getLogger(__name__)

# El estado con el que nace una cita pedida por el cliente. El taller la revisa
# y la acepta; hasta entonces no ocupa cupo.
ESTADO_SOLICITADA = CitaStatus.solicitada.value


async def disponibilidad(organization_id: str, dias: int) -> List[Dict[str, Any]]:
    """Los próximos N días con sus bloques, marcando cuáles se pueden pedir.

    Los bloques ocupados igual se devuelven, marcados: mostrar un día con
    huecos explica por qué no hay más opciones; devolver solo los libres hace
    ver un día medio vacío como si el taller no atendiera.
    """
    repo = BusinessRulesRepository()
    hoy = date.today()

    semana = await repo.semana(organization_id)
    excepciones = await repo.excepciones(organization_id, hoy, hoy + timedelta(days=dias))

    resultado: List[Dict[str, Any]] = []
    for offset in range(dias):
        fecha = hoy + timedelta(days=offset)
        dia = resolver_dia(fecha, semana, excepciones)

        if not dia.abierto:
            resultado.append({"fecha": fecha, "abierto": False, "bloques": []})
            continue

        citas = await repo.citas_que_ocupan(organization_id, fecha)
        bloques = bloques_del_dia(dia, ocupacion_de_citas(citas), len(citas))

        resultado.append({
            "fecha": fecha,
            "abierto": True,
            "bloques": [{"hora": b.hora, "libre": b.libre} for b in bloques],
        })

    return resultado


async def solicitar_cita(
    *,
    organization_id: str,
    customer_id: str,
    fecha: date,
    hora: time,
    nombre: str,
    service_type_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Registra la solicitud del cliente. Nunca crea una cita confirmada.

    `organization_id` y `customer_id` llegan del token, jamás del cuerpo del
    request: son la única razón por la que esta ruta puede vivir sin sesión.
    """
    # La hora llega en local y scheduled_at es timestamptz: combinarla sin zona
    # correría la cita cinco horas.
    cuando = datetime.combine(fecha, hora, tzinfo=PANAMA)

    return await citas_service.create_cita(
        organization_id,
        CitaCreate(
            customer_id=customer_id,
            scheduled_at=cuando,
            service_type_id=service_type_id,
            # Nace como SOLICITUD, no como cita firme: es lo único que impide
            # que el cliente se vaya creyendo que el taller lo espera.
            status=CitaStatus.solicitada,
            created_via="bot",
            # Lo que el cliente escribió, tal cual. Después de aceptar la cita
            # el estado ya no dice de dónde vino ni quién la pidió.
            solicitud_texto=f"Pedida por {nombre} desde la agenda web",
        ),
    )
