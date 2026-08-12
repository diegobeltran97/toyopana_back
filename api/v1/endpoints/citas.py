"""HTTP routes for citas (appointments), mounted at /api/citas.

Unlike the sibling /api/customers routes (which are open and take
organization_id as a query param), every route here is authenticated and
derives the organization from the token. A cita is a write into a tenant's
calendar, so the org must not be client-supplied.
"""

from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status

from api.deps import get_current_user
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


@router.patch(
    "/{cita_id}",
    response_model=CitaRead,
    summary="Change a cita's status or reschedule it",
)
async def update_cita(
    payload: CitaUpdate,
    cita_id: str = Path(..., description="The cita id"),
    current_user: dict = Depends(get_current_user),
):
    """
    Partial update. Returns 404 when the cita doesn't belong to the caller's
    organization and 409 when the requested status transition is not allowed.
    """
    organization_id = require_organization_id(current_user)
    return await citas_service.update_cita(organization_id, cita_id, payload)
