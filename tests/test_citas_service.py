"""Tests for citas_service (services/citas_service.py).

The repository is replaced with a fake so the tests exercise only the service's
rules: the Panama day-range math, the status-transition table, updated_at
stamping, and the 404/409 mapping. No I/O.
"""

import uuid
from datetime import date, datetime, timezone

import pytest
from fastapi import HTTPException

from schemas.cita import CitaCreate, CitaStatus, CitaUpdate
from services.citas_service import (
    ALLOWED_TRANSITIONS,
    create_cita,
    list_citas,
    range_bounds,
    update_cita,
)

ORG = "11111111-1111-1111-1111-111111111111"
CITA_ID = "22222222-2222-2222-2222-222222222222"
CUSTOMER_ID = "33333333-3333-3333-3333-333333333333"


def _row(**overrides):
    """A complete citas row as PostgREST would return it."""
    row = {
        "id": CITA_ID,
        "organization_id": ORG,
        "customer_id": CUSTOMER_ID,
        "vehicle_id": None,
        "scheduled_at": "2026-09-10T20:00:00+00:00",
        "service_type": "Cambio de aceite",
        "status": "agendada",
        "converted_order_id": None,
        "created_at": "2026-08-12T10:00:00+00:00",
        "updated_at": "2026-08-12T10:00:00+00:00",
        "customer": {"id": CUSTOMER_ID, "name": "Juan Pérez", "phone": "+50761234567"},
    }
    row.update(overrides)
    return row


class FakeRepo:
    def __init__(self, *, existing=None, rows=None):
        self._existing = existing
        self._rows = rows if rows is not None else []
        self.created = None
        self.updated = None
        self.listed = None

    async def create(self, organization_id, data):
        self.created = (organization_id, data)
        return _row(**{k: v for k, v in data.items() if k in _row()})

    async def list_range(self, organization_id, scheduled_from, scheduled_before, status=None):
        self.listed = {
            "organization_id": organization_id,
            "scheduled_from": scheduled_from,
            "scheduled_before": scheduled_before,
            "status": status,
        }
        return self._rows

    async def get(self, cita_id, organization_id):
        return self._existing

    async def update(self, cita_id, organization_id, data):
        self.updated = (cita_id, organization_id, data)
        return _row(**{k: v for k, v in data.items() if k in _row()})


# --- range_bounds -----------------------------------------------------------

def test_range_bounds_covers_both_endpoint_days_fully():
    """Panama is UTC-5 with no DST, so local midnight is 05:00Z."""
    start, end = range_bounds(date(2026, 9, 1), date(2026, 9, 30))

    assert start == "2026-09-01T05:00:00+00:00"
    # Exclusive end = midnight of Oct 1 local => a 23:30 cita on Sep 30 is inside.
    assert end == "2026-10-01T05:00:00+00:00"


def test_range_bounds_single_day_is_24_hours():
    start, end = range_bounds(date(2026, 9, 10), date(2026, 9, 10))

    assert start == "2026-09-10T05:00:00+00:00"
    assert end == "2026-09-11T05:00:00+00:00"


def test_range_bounds_rejects_inverted_range():
    with pytest.raises(HTTPException) as exc:
        range_bounds(date(2026, 9, 30), date(2026, 9, 1))

    assert exc.value.status_code == 400


# --- create -----------------------------------------------------------------

async def test_create_stamps_agendada_and_serializes_payload():
    repo = FakeRepo()
    payload = CitaCreate(
        customer_id=uuid.UUID(CUSTOMER_ID),
        scheduled_at=datetime(2026, 9, 10, 20, 0, tzinfo=timezone.utc),
        service_type="Cambio de aceite",
    )

    cita = await create_cita(ORG, payload, repo=repo)

    org, data = repo.created
    assert org == ORG
    assert data["status"] == "agendada"
    assert data["customer_id"] == CUSTOMER_ID  # str, not UUID — httpx must serialize it
    assert data["scheduled_at"] == "2026-09-10T20:00:00+00:00"
    assert cita.status is CitaStatus.agendada
    assert cita.customer.name == "Juan Pérez"


async def test_create_calls_the_reminder_trigger_point(monkeypatch):
    import services.citas_service as service_module

    seen = {}

    def fake_schedule(cita_id, scheduled_at):
        seen["cita_id"] = cita_id
        seen["scheduled_at"] = scheduled_at
        return []

    monkeypatch.setattr(service_module, "schedule_reminders", fake_schedule)

    await create_cita(
        ORG,
        CitaCreate(
            customer_id=uuid.UUID(CUSTOMER_ID),
            scheduled_at=datetime(2026, 9, 10, 20, 0, tzinfo=timezone.utc),
        ),
        repo=FakeRepo(),
    )

    assert seen["cita_id"] == CITA_ID


# --- list -------------------------------------------------------------------

async def test_list_passes_expanded_bounds_and_status():
    repo = FakeRepo(rows=[_row()])

    citas = await list_citas(
        ORG, date(2026, 9, 1), date(2026, 9, 30), status=CitaStatus.agendada, repo=repo
    )

    assert len(citas) == 1
    assert repo.listed["scheduled_from"] == "2026-09-01T05:00:00+00:00"
    assert repo.listed["scheduled_before"] == "2026-10-01T05:00:00+00:00"
    assert repo.listed["status"] == "agendada"  # the enum's value, not the enum


# --- update -----------------------------------------------------------------

async def test_update_404_when_cita_absent():
    with pytest.raises(HTTPException) as exc:
        await update_cita(
            ORG, CITA_ID, CitaUpdate(status=CitaStatus.confirmada), repo=FakeRepo(existing=None)
        )

    assert exc.value.status_code == 404


async def test_update_allows_a_legal_transition_and_stamps_updated_at():
    repo = FakeRepo(existing=_row(status="agendada"))

    await update_cita(ORG, CITA_ID, CitaUpdate(status=CitaStatus.confirmada), repo=repo)

    _, _, data = repo.updated
    assert data["status"] == "confirmada"
    assert "updated_at" in data  # no DB trigger — the service owns this column


async def test_update_409_on_illegal_transition():
    repo = FakeRepo(existing=_row(status="cumplida"))

    with pytest.raises(HTTPException) as exc:
        await update_cita(ORG, CITA_ID, CitaUpdate(status=CitaStatus.agendada), repo=repo)

    assert exc.value.status_code == 409


async def test_update_allows_restating_the_same_status():
    """A PATCH that re-sends the current status is a no-op, not a conflict."""
    repo = FakeRepo(existing=_row(status="agendada"))

    await update_cita(ORG, CITA_ID, CitaUpdate(status=CitaStatus.agendada), repo=repo)

    assert repo.updated is not None


async def test_reschedule_without_status_is_allowed_from_any_open_state():
    repo = FakeRepo(existing=_row(status="confirmada"))

    await update_cita(
        ORG,
        CITA_ID,
        CitaUpdate(scheduled_at=datetime(2026, 9, 11, 20, 0, tzinfo=timezone.utc)),
        repo=repo,
    )

    _, _, data = repo.updated
    assert data["scheduled_at"] == "2026-09-11T20:00:00+00:00"
    assert "status" not in data


async def test_update_400_when_body_is_empty():
    repo = FakeRepo(existing=_row())

    with pytest.raises(HTTPException) as exc:
        await update_cita(ORG, CITA_ID, CitaUpdate(), repo=repo)

    assert exc.value.status_code == 400


def test_terminal_states_have_no_outgoing_transitions():
    for terminal in ("cumplida", "no_show", "cancelada"):
        assert ALLOWED_TRANSITIONS[terminal] == set()
