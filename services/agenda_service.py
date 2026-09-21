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
from schemas.cita import CitaCreate, CitaRead, CitaStatus

logger = logging.getLogger(__name__)

# El indicativo de Panamá. Un celular local se teclea sin él ("68510658") y
# Whapi necesita el número completo para entregar, así que se completa AQUÍ, al
# guardar. Normalizarlo solo al enviar dejaría el dato a medias en la base y
# haría que el aviso dependa de que alguien más se acuerde de completarlo.
INDICATIVO = "507"

# Cuánta anticipación mínima pide el taller antes de una cita. Nadie sale
# corriendo para llegar en quince minutos, y el taller necesita ver la
# solicitud antes de que aparezca el carro.
#
# Constante con nombre y no columna: el número lo eligió el spec, no el
# taller. Si resulta molesto, cambiarlo cuesta una línea — y si el taller
# pide poder ajustarlo, ahí se vuelve columna.
ANTICIPACION_MINIMA_MINUTOS = 120


def normalizar_telefono(telefono: str) -> str:
    """Lo que la gente teclea -> E.164.

    "6851-0658", "+507 6851 0658" y "50768510658" son el mismo número y todos
    salen como "+50768510658".
    """
    digitos = "".join(filter(str.isdigit, telefono))
    if not digitos.startswith(INDICATIVO):
        digitos = INDICATIVO + digitos
    return f"+{digitos}"


async def disponibilidad(organization_id: str, dias: int) -> List[Dict[str, Any]]:
    """Los próximos N días con sus bloques, marcando cuáles se pueden pedir.

    Los bloques ocupados igual se devuelven, marcados: mostrar un día con
    huecos explica por qué no hay más opciones; devolver solo los libres hace
    ver un día medio vacío como si el taller no atendiera.

    Aquí vive el reloj. `bloques_del_dia()` es puro y recibe la hora límite ya
    calculada.
    """
    repo = BusinessRulesRepository()

    # En hora de Panamá y no `date.today()`: con el servidor en UTC, a las
    # 00:30 UTC ya es "mañana" mientras en Panamá siguen siendo las 7:30 p.m.
    # de hoy, y la agenda se saltaría el día en curso entero.
    ahora = datetime.now(PANAMA)
    hoy = ahora.date()
    limite = ahora + timedelta(minutes=ANTICIPACION_MINIMA_MINUTOS)

    semana = await repo.semana(organization_id)
    excepciones = await repo.excepciones(organization_id, hoy, hoy + timedelta(days=dias))

    resultado: List[Dict[str, Any]] = []
    for offset in range(dias):
        fecha = hoy + timedelta(days=offset)
        dia = resolver_dia(fecha, semana, excepciones)

        if not dia.abierto:
            resultado.append({"fecha": fecha, "abierto": False, "bloques": []})
            continue

        # `time.max` cuando el margen ya empujó el límite al día siguiente: el
        # día de hoy entero queda sin horas, pero sigue ABIERTO. El taller sí
        # abrió; la pantalla debe decir "no quedan horas", no "cerrado".
        if fecha < limite.date():
            desde = time.max
        elif fecha == limite.date():
            desde = limite.time()
        else:
            desde = None

        citas = await repo.citas_que_ocupan(organization_id, fecha)
        bloques = bloques_del_dia(
            dia, ocupacion_de_citas(citas), len(citas), desde=desde
        )

        resultado.append({
            "fecha": fecha,
            "abierto": True,
            "bloques": [{"hora": b.hora, "libre": b.libre} for b in bloques],
        })

    return resultado


async def solicitar_cita(
    *,
    organization_id: str,
    fecha: date,
    hora: time,
    nombre: str,
    telefono: str,
    service_type_id: Optional[str] = None,
) -> CitaRead:
    """Registra la solicitud. Nunca crea una cita confirmada.

    `organization_id` llega del token, jamás del cuerpo del request: es la
    única razón por la que esta ruta puede vivir sin sesión.

    NO crea un cliente. El CRM es de la gente que de verdad lleva su carro al
    taller, cargada con el formulario; alguien que solo pidió una hora todavía
    no es eso, y darle ficha llena el directorio de personas que quizá nunca
    aparezcan. Nombre y teléfono viven en la propia cita hasta entonces.
    """
    # La hora llega en local y scheduled_at es timestamptz: combinarla sin zona
    # correría la cita cinco horas.
    cuando = datetime.combine(fecha, hora, tzinfo=PANAMA)

    return await citas_service.create_cita(
        organization_id,
        CitaCreate(
            # SIN customer_id: pedir una cita no crea un cliente en el CRM. El
            # taller lo da de alta con el formulario el día que la persona
            # aparezca con el carro.
            scheduled_at=cuando,
            service_type_id=service_type_id,
            # Nace como SOLICITUD, no como cita firme: es lo único que impide
            # que el cliente se vaya creyendo que el taller lo espera.
            status=CitaStatus.solicitada,
            created_via="bot",
            # Lo que el cliente escribió, tal cual. Después de aceptar la cita
            # el estado ya no dice de dónde vino ni quién la pidió.
            solicitante_nombre=nombre,
            solicitante_telefono=normalizar_telefono(telefono),
            solicitud_texto="Pedida desde la agenda web",
        ),
    )
