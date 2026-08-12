"""Business logic for citas (appointments).

Owns three things the layers around it must not: the America/Panama day-range
expansion the calendar queries with, the status-transition table, and the
updated_at column (there is no DB trigger — DB logic is banned in this project).

Repositories are injectable so every rule here is unit-testable without I/O.
"""

import logging
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

from fastapi import HTTPException

from repositories.citas import CitaRepository
from schemas.cita import CitaCreate, CitaRead, CitaStatus, CitaUpdate
from services.cita_reminders import schedule_reminders

logger = logging.getLogger(__name__)

PANAMA_TZ = ZoneInfo("America/Panama")

# Legal status moves. A cita starts 'agendada'; the three end states are
# terminal. 'cumplida' will normally be reached by the deferred cita->order
# conversion, but is allowed manually too (a walk-in recorded after the fact).
ALLOWED_TRANSITIONS: Dict[str, set] = {
    "agendada": {"confirmada", "cancelada", "no_show", "cumplida"},
    "confirmada": {"cumplida", "cancelada", "no_show"},
    "cumplida": set(),
    "no_show": set(),
    "cancelada": set(),
}


def range_bounds(date_from: date, date_to: date) -> Tuple[str, str]:
    """
    Turn an inclusive local day range into half-open UTC ISO bounds.

    The calendar asks for whole days in Panama; `scheduled_at` is a timestamptz.
    The upper bound is the day AFTER date_to at local midnight, and the query
    uses `< upper`, so a 23:30 cita on the last day is still inside the range.

    Args:
        date_from: First day to include (local Panama date).
        date_to: Last day to include (local Panama date, inclusive).

    Returns:
        (scheduled_from, scheduled_before) as UTC ISO strings.

    Raises:
        HTTPException 400: when date_to is before date_from.
    """
    if date_to < date_from:
        raise HTTPException(
            status_code=400, detail="'to' no puede ser anterior a 'from'"
        )

    start_local = datetime.combine(date_from, time.min, tzinfo=PANAMA_TZ)
    end_local = datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=PANAMA_TZ)

    return (
        start_local.astimezone(timezone.utc).isoformat(),
        end_local.astimezone(timezone.utc).isoformat(),
    )


async def create_cita(
    organization_id: str,
    data: CitaCreate,
    *,
    repo: Optional[CitaRepository] = None,
) -> CitaRead:
    """
    Book a cita for an existing customer.

    The cita always starts 'agendada'. The organization comes from the caller
    (the authenticated user), never from the payload.

    Args:
        organization_id: Owning organization UUID.
        data: The validated booking payload.
        repo: Injectable repository (defaults to the real one).

    Returns:
        The created cita.
    """
    repo = repo or CitaRepository()

    payload: Dict[str, Any] = {
        "customer_id": str(data.customer_id),
        "scheduled_at": data.scheduled_at.isoformat(),
        "service_type": data.service_type,
        "status": CitaStatus.agendada.value,
    }
    row = await repo.create(organization_id, payload)
    cita = CitaRead.model_validate(row)

    # Trigger point for the 24h/2h WhatsApp reminders. No scheduler in v1, so
    # this only records intent; a failure here must never fail the booking.
    try:
        schedule_reminders(str(cita.id), cita.scheduled_at)
    except Exception:  # pragma: no cover - defensive
        logger.exception("Could not plan reminders for cita %s", cita.id)

    return cita


async def list_citas(
    organization_id: str,
    date_from: date,
    date_to: date,
    status: Optional[CitaStatus] = None,
    *,
    repo: Optional[CitaRepository] = None,
) -> List[CitaRead]:
    """
    List an org's citas for an inclusive range of local days, earliest first.

    Args:
        organization_id: Owning organization UUID.
        date_from: First day to include (Panama local date).
        date_to: Last day to include (Panama local date, inclusive).
        status: Optional status filter.
        repo: Injectable repository (defaults to the real one).

    Returns:
        The citas in the window, each with its customer embedded.
    """
    repo = repo or CitaRepository()
    scheduled_from, scheduled_before = range_bounds(date_from, date_to)

    rows = await repo.list_range(
        organization_id,
        scheduled_from=scheduled_from,
        scheduled_before=scheduled_before,
        status=status.value if status else None,
    )
    return [CitaRead.model_validate(row) for row in rows]


async def update_cita(
    organization_id: str,
    cita_id: str,
    data: CitaUpdate,
    *,
    repo: Optional[CitaRepository] = None,
) -> CitaRead:
    """
    Change a cita's status and/or reschedule it.

    Args:
        organization_id: Owning organization UUID (also the write guard).
        cita_id: The cita to patch.
        data: Partial update; only the fields actually sent are written.
        repo: Injectable repository (defaults to the real one).

    Returns:
        The updated cita.

    Raises:
        HTTPException 400: empty body.
        HTTPException 404: no such cita in this organization.
        HTTPException 409: illegal status transition.
    """
    repo = repo or CitaRepository()

    fields = data.model_dump(exclude_unset=True)
    if not fields:
        raise HTTPException(status_code=400, detail="No hay campos para actualizar")

    current = await repo.get(cita_id, organization_id)
    if current is None:
        raise HTTPException(status_code=404, detail="Cita no encontrada")

    payload: Dict[str, Any] = {}

    if "status" in fields:
        new_status = data.status.value
        old_status = current["status"]
        # Re-sending the current status is a no-op, not a conflict.
        if new_status != old_status and new_status not in ALLOWED_TRANSITIONS.get(
            old_status, set()
        ):
            raise HTTPException(
                status_code=409,
                detail=f"Transición inválida: '{old_status}' → '{new_status}'",
            )
        payload["status"] = new_status

    if "scheduled_at" in fields:
        payload["scheduled_at"] = data.scheduled_at.isoformat()
    if "service_type" in fields:
        payload["service_type"] = data.service_type
    if "vehicle_id" in fields:
        payload["vehicle_id"] = str(data.vehicle_id) if data.vehicle_id else None

    # No DB trigger maintains this column — the service layer owns it.
    payload["updated_at"] = datetime.now(timezone.utc).isoformat()

    row = await repo.update(cita_id, organization_id, payload)
    if row is None:
        raise HTTPException(status_code=404, detail="Cita no encontrada")

    return CitaRead.model_validate(row)
