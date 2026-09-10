"""HTTP routes for citas (appointments), mounted at /api/citas.

Unlike the sibling /api/customers routes (which are open and take
organization_id as a query param), every route here is authenticated and
derives the organization from the token. A cita is a write into a tenant's
calendar, so the org must not be client-supplied.
"""

from datetime import date
from typing import List, Optional

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Path,
    Query,
    status,
)

from pydantic import BaseModel, Field

from api.deps import get_current_user
from core.config import settings
from services.agenda_token import TTL_HORAS_DEFAULT, crear_token, leer_token
from integrations.messaging.base import MessagingProvider
from integrations.messaging.factory import get_messaging_provider
from services.cita_aviso import avisar_cambio_de_estado
from schemas.cita import CitaCreate, CitaRead, CitaStatus, CitaUpdate
from services import citas_service

router = APIRouter()


def require_organization_id(current_user: dict) -> str:
    """
    Pull the caller's organization out of the authenticated user.

    get_current_user falls back to a bare auth-user dict when the app_users row
    is missing (see api/deps.py); such a user has no tenant and cannot touch
    citas.

    Raises:
        HTTPException 403: the user is not attached to an organization.
    """
    organization_id = current_user.get("organization_id")
    if not organization_id:
        raise HTTPException(
            status_code=403, detail="El usuario no pertenece a una organización"
        )
    return str(organization_id)


@router.get(
    "",
    response_model=List[CitaRead],
    summary="List citas in a date range (calendar)",
)
async def list_citas(
    date_from: date = Query(
        ..., alias="from", description="Primer día del rango (inclusive), YYYY-MM-DD"
    ),
    date_to: date = Query(
        ..., alias="to", description="Último día del rango (inclusive), YYYY-MM-DD"
    ),
    cita_status: Optional[CitaStatus] = Query(
        None, alias="status", description="Filtro opcional por estado"
    ),
    current_user: dict = Depends(get_current_user),
):
    """
    Return the organization's citas between two local (America/Panama) days,
    both endpoints inclusive, ordered by time. Each cita carries its customer.

    `from` / `to` are aliased because `from` is a Python keyword.
    """
    organization_id = require_organization_id(current_user)
    return await citas_service.list_citas(
        organization_id, date_from, date_to, status=cita_status
    )


@router.post(
    "",
    response_model=CitaRead,
    status_code=status.HTTP_201_CREATED,
    summary="Book a cita for an existing customer",
)
async def create_cita(
    payload: CitaCreate,
    current_user: dict = Depends(get_current_user),
):
    """
    Create a cita in state 'agendada'.

    A cita is an intention, not an order: no vehicle is required and no order is
    created here. The order is born later, at reception.
    """
    organization_id = require_organization_id(current_user)
    return await citas_service.create_cita(organization_id, payload)


# ---------------------------------------------------------------------------
# Rutas literales ANTES de las paramétricas.
#
# FastAPI resuelve en orden de declaración: con `/{cita_id}` declarada primero,
# un futuro `POST /{cita_id}` capturaría "/link-agenda" y este endpoint
# devolvería 405 sin que nadie entienda por qué.
# ---------------------------------------------------------------------------


class LinkAgendaResponse(BaseModel):
    """El link listo para copiar o mandar por WhatsApp."""

    url: str
    expira_en: int = Field(..., description="Epoch en segundos")
    horas_de_vigencia: int


@router.post(
    "/link-agenda",
    response_model=LinkAgendaResponse,
    summary="Generar el link de agenda para un cliente",
)
async def generar_link_agenda(
    current_user: dict = Depends(get_current_user),
) -> LinkAgendaResponse:
    """Arma el link firmado que el taller le manda al cliente por WhatsApp.

    El link es GENÉRICO: no lleva cliente. El empleado lo comparte sin tener que
    buscar antes a la persona en el CRM — que es el caso común, porque alguien
    que escribe desde un número desconocido todavía no tiene ficha. Quien lo
    abre se identifica con nombre y teléfono en la página.

    La organización sale del token del EMPLEADO y queda firmada dentro del link,
    así que un taller no puede emitir uno que agende en la agenda de otro.

    Sin AGENDA_TOKEN_SECRET responde 503 en vez de emitir un link que nadie
    podría abrir: un error claro aquí ahorra la confusión de un cliente que
    recibe un link muerto.
    """
    organization_id = require_organization_id(current_user)

    if not settings.AGENDA_TOKEN_SECRET:
        raise HTTPException(
            status_code=503,
            # Lo lee alguien en una pantalla, no en un log: dice qué falta y
            # dónde, sin jerga.
            detail=(
                "Los links de agenda no están habilitados todavía. "
                "Falta configurar AGENDA_TOKEN_SECRET en el servidor."
            ),
        )

    token = crear_token(organization_id)
    datos = leer_token(token)

    return LinkAgendaResponse(
        url=f"{settings.AGENDA_BASE_URL.rstrip('/')}/agenda/{token}",
        expira_en=datos.expira_en,
        horas_de_vigencia=TTL_HORAS_DEFAULT,
    )


@router.patch(
    "/{cita_id}",
    response_model=CitaRead,
    summary="Change a cita's status or reschedule it",
)
async def update_cita(
    payload: CitaUpdate,
    background: BackgroundTasks,
    cita_id: str = Path(..., description="The cita id"),
    current_user: dict = Depends(get_current_user),
    provider: MessagingProvider = Depends(get_messaging_provider),
):
    """
    Partial update. Returns 404 when the cita doesn't belong to the caller's
    organization and 409 when the requested status transition is not allowed.

    Accepting or rejecting a customer's request also messages them on WhatsApp.
    That is what closes the loop the web agenda opens: without it the shop
    accepts the appointment and nobody tells the customer, who keeps waiting.
    """
    organization_id = require_organization_id(current_user)

    # El estado anterior, ANTES de tocar la fila: el aviso depende de de dónde
    # viene el cambio, y después del update ese dato ya se perdió.
    previo = await citas_service.estado_actual(organization_id, cita_id)
    anterior = (previo or {}).get("status", "")

    cita = await citas_service.update_cita(organization_id, cita_id, payload)

    # En segundo plano: el cambio ya se guardó y es la verdad, así que el 200
    # no puede quedar esperando a que WhatsApp responda. avisar_cambio_de_estado
    # nunca lanza, de modo que un fallo suyo no puede tocar este status code.
    background.add_task(
        avisar_cambio_de_estado,
        provider,
        anterior=anterior,
        cita=cita.model_dump(),
    )

    return cita


@router.delete(
    "/{cita_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Permanently delete a cita",
)
async def delete_cita(
    cita_id: str = Path(..., description="The cita id"),
    current_user: dict = Depends(get_current_user),
):
    """
    Hard-delete a cita.

    This is for bookings that should never have existed. To record that a
    customer cancelled, PATCH the status to 'cancelada' instead — that keeps the
    row, and with it the cancellation history.

    Returns 404 when the cita doesn't belong to the caller's organization.
    """
    organization_id = require_organization_id(current_user)
    await citas_service.delete_cita(organization_id, cita_id)
