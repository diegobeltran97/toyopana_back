"""Public booking page routes, mounted at /api/public/agenda.

THE FIRST ROUTES IN THIS APPLICATION WITHOUT A SESSION. Everything about who is
asking comes from the signed token in the path and from nowhere else:

    organization_id  <- token
    customer_id      <- token

There is deliberately NO organization_id or customer_id parameter, not even an
optional one. Accepting either would let anyone read another shop's
availability or book in another customer's name — and an unused optional
parameter is the kind of thing a later change quietly starts honouring.

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


class AgendaOut(BaseModel):
    dias: List[DiaOut]


class SolicitudIn(BaseModel):
    """Lo que el cliente elige en la pantalla.

    No lleva organization_id ni customer_id a propósito: salen del token.
    """

    fecha: date
    hora: time
    # Obligatorio: del token sale el teléfono, no el nombre. Si escribió desde
    # un número que no teníamos, no sabemos quién es.
    nombre: str = Field(..., min_length=1, max_length=120)
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
    return AgendaOut(dias=[DiaOut(**d) for d in resultado])


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

    cita = await agenda_service.solicitar_cita(
        organization_id=datos.organization_id,
        customer_id=datos.customer_id,
        fecha=solicitud.fecha,
        hora=solicitud.hora,
        nombre=solicitud.nombre,
        service_type_id=solicitud.service_type_id,
    )

    return SolicitudOut(
        id=str(cita["id"]),
        scheduled_at=str(cita["scheduled_at"]),
        status=str(cita.get("status", agenda_service.ESTADO_SOLICITADA)),
    )
