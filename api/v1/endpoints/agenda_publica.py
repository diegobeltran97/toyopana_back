"""Public booking page routes, mounted at /api/public/agenda.

THE FIRST ROUTES IN THIS APPLICATION WITHOUT A SESSION.

    organization_id  <- token, and ONLY the token
    quién es          <- lo que la persona escribe en la página

The link is generic: it carries no customer, so an employee can share one
without first finding the person in the CRM — the common case, since someone
writing from an unknown number has no record yet. Whoever opens it identifies
themselves with name and phone, and find_or_create_customer (idempotent) does
the rest.

There is deliberately NO organization_id parameter, not even an optional one:
accepting one would let anyone read another shop's availability. A customer_id
in the body is likewise ignored — the customer is resolved by phone, not by an
id the caller supplies.

They live under /api/public/ so the routing table itself says which surface has
no session, and nobody adds a route here by accident.
"""

import logging
from datetime import date, time
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Path, Query, status
from pydantic import BaseModel, Field, field_validator

from core.config import settings
from services import agenda_service
from services.agenda_token import (
    DatosToken,
    TokenInvalido,
    TokenVencido,
    leer_token,
)

router = APIRouter()
logger = logging.getLogger(__name__)

# Cuánto futuro puede pedir la pantalla. Acotado: un horizonte abierto haría
# resolver meses de agenda para una pantalla que muestra una semana.
DIAS_MAX = 14
DIAS_DEFAULT = 7


class BloqueOut(BaseModel):
    hora: time
    libre: bool


class DiaOut(BaseModel):
    fecha: date
    abierto: bool
    bloques: List[BloqueOut]


class ServicioOut(BaseModel):
    """Un servicio del catálogo, como lo ve quien abre el link.

    Sin `active`: si llegó hasta aquí, está activo. Mandar el campo invitaría
    a que la pantalla lo filtre otra vez, duplicando la decisión.
    """

    id: str
    name: str
    duration_minutes: int


class AgendaOut(BaseModel):
    dias: List[DiaOut]
    # El catálogo viaja con la agenda y no en otra llamada: la pantalla los
    # necesita juntos para pintarse, y dos viajes son latencia sin nada a cambio.
    servicios: List[ServicioOut] = []


class SolicitudIn(BaseModel):
    """Lo que la persona llena en la pantalla.

    Sin organization_id a propósito: sale del token. Un customer_id extra en el
    cuerpo se ignora — el cliente se resuelve por teléfono.
    """

    fecha: date
    hora: time
    nombre: str = Field(..., min_length=1, max_length=120)
    # Obligatorio: el link es genérico, así que este es el único dato con el que
    # después se le confirma la cita. Sin él el taller puede aceptarla y no
    # tener a dónde avisar.
    telefono: str = Field(..., min_length=1, max_length=40)
    service_type_id: Optional[str] = Field(
        None, description="Opcional: qué necesita el carro"
    )

    @field_validator("nombre")
    @classmethod
    def _nombre_con_contenido(cls, v: str) -> str:
        limpio = v.strip()
        if not limpio:
            raise ValueError("El nombre no puede estar vacío")
        return limpio

    @field_validator("telefono")
    @classmethod
    def _telefono_utilizable(cls, v: str) -> str:
        """Al menos 8 dígitos: un celular panameño.

        La gente escribe "6851-0658", "+507 6851 0658" o "68510658" y las tres
        valen. Ocho y no siete porque la confirmación va por WhatsApp, y eso
        exige un celular — un fijo (7 dígitos) nunca la recibiría. Un número
        incompleto es una confirmación que no llega, y eso se descubre el día
        que el cliente no aparece.
        """
        digitos = "".join(filter(str.isdigit, v))
        if len(digitos) < 8:
            raise ValueError("El teléfono no parece completo")
        return v.strip()


class SolicitudOut(BaseModel):
    id: str
    scheduled_at: str
    # Siempre 'solicitada'. Es lo que impide que el cliente se vaya creyendo
    # que ya tiene cita confirmada.
    status: str


def _verificar(token: str) -> DatosToken:
    """Resuelve el token del path, o corta la petición.

    403 para un token que nunca fue nuestro; 410 para uno que caducó — la
    pantalla necesita distinguirlos para decir "pide un link nuevo" en vez de
    "no tienes acceso".
    """
    try:
        return leer_token(token, secreto=settings.AGENDA_TOKEN_SECRET or None)
    except TokenVencido:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="El link ya venció")
    except (TokenInvalido, ValueError):
        # Un secreto sin configurar cae aquí (ValueError): falla cerrado.
        logger.warning("Link de agenda rechazado")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Link inválido")


@router.get(
    "/agenda/{token}",
    response_model=AgendaOut,
    summary="Ver los horarios disponibles",
    tags=["agenda-publica"],
)
async def ver_agenda(
    token: str = Path(..., description="Token firmado del link"),
    dias: int = Query(DIAS_DEFAULT, ge=1, le=DIAS_MAX),
) -> AgendaOut:
    """Los próximos días con sus bloques de una hora."""
    datos = _verificar(token)

    resultado = await agenda_service.disponibilidad(datos.organization_id, dias)
    servicios = await agenda_service.servicios_ofrecidos(datos.organization_id)

    return AgendaOut(
        dias=[DiaOut(**d) for d in resultado],
        servicios=[ServicioOut(**s) for s in servicios],
    )


@router.post(
    "/agenda/{token}/solicitar",
    response_model=SolicitudOut,
    status_code=status.HTTP_201_CREATED,
    summary="Pedir una hora (queda pendiente de confirmación)",
    tags=["agenda-publica"],
)
async def solicitar(
    solicitud: SolicitudIn,
    token: str = Path(..., description="Token firmado del link"),
) -> SolicitudOut:
    """Registra la solicitud. NO agenda: el taller la confirma después."""
    datos = _verificar(token)

    # El `service_type_id` viene del cuerpo, así que hay que comprobar que es
    # de este taller. Sin esto, conocer un UUID dejaría meterle a una cita un
    # servicio ajeno — con su duración, que es lo que decide cuánto ocupa.
    if solicitud.service_type_id is not None:
        catalogo = await agenda_service.servicios_ofrecidos(datos.organization_id)
        if solicitud.service_type_id not in {s["id"] for s in catalogo}:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Ese servicio no está disponible",
            )

    cita = await agenda_service.solicitar_cita(
        organization_id=datos.organization_id,
        fecha=solicitud.fecha,
        hora=solicitud.hora,
        nombre=solicitud.nombre,
        telefono=solicitud.telefono,
        service_type_id=solicitud.service_type_id,
    )

    # create_cita devuelve un CitaRead, no un dict: acceso por atributo.
    return SolicitudOut(
        id=str(cita.id),
        scheduled_at=cita.scheduled_at.isoformat(),
        status=cita.status.value,
    )
