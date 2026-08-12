"""API tests for /api/citas (endpoints/citas.py).

The service is monkeypatched to canned results so these assert the HTTP
boundary only: auth wiring, where organization_id comes from, query-param
validation, and status codes. Same shape as tests/test_marketing_api.py.
"""

import uuid
from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import api.v1.endpoints.citas as citas_endpoint
from api.deps import get_current_user
from schemas.cita import CitaCustomer, CitaRead, CitaStatus

ORG = "11111111-1111-1111-1111-111111111111"
CITA_ID = "22222222-2222-2222-2222-222222222222"
CUSTOMER_ID = "33333333-3333-3333-3333-333333333333"

app = FastAPI()
app.include_router(citas_endpoint.router, prefix="/api/citas")
client = TestClient(app)


def _canned(status=CitaStatus.agendada):
    now = datetime.now(timezone.utc)
    return CitaRead(
        id=uuid.UUID(CITA_ID),
        organization_id=uuid.UUID(ORG),
        customer_id=uuid.UUID(CUSTOMER_ID),
        scheduled_at=datetime(2026, 9, 10, 20, 0, tzinfo=timezone.utc),
        service_type="Cambio de aceite",
        status=status,
        created_at=now,
        updated_at=now,
        customer=CitaCustomer(id=uuid.UUID(CUSTOMER_ID), name="Juan Pérez", phone="+50761234567"),
    )


@pytest.fixture(autouse=True)
def _auth_override():
    """Every test runs as an authenticated user of ORG unless it overrides this."""
    app.dependency_overrides[get_current_user] = lambda: {
        "id": "user-1",
        "organization_id": ORG,
    }
    yield
    app.dependency_overrides.clear()


def test_list_requires_from_and_to():
    response = client.get("/api/citas")
    assert response.status_code == 422


def test_list_passes_dates_through_and_returns_citas(monkeypatch):
    seen = {}

    async def fake_list(organization_id, date_from, date_to, status=None):
        seen.update(
            organization_id=organization_id,
            date_from=date_from,
            date_to=date_to,
            status=status,
        )
        return [_canned()]

    monkeypatch.setattr(citas_endpoint.citas_service, "list_citas", fake_list)

    response = client.get("/api/citas", params={"from": "2026-09-01", "to": "2026-09-30"})

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["customer"]["name"] == "Juan Pérez"
    assert body[0]["status"] == "agendada"
    # The org comes from the token, never the query string.
    assert seen["organization_id"] == ORG
    assert str(seen["date_from"]) == "2026-09-01"
    assert str(seen["date_to"]) == "2026-09-30"
    assert seen["status"] is None


def test_list_forwards_status_filter(monkeypatch):
    seen = {}

    async def fake_list(organization_id, date_from, date_to, status=None):
        seen["status"] = status
        return []

    monkeypatch.setattr(citas_endpoint.citas_service, "list_citas", fake_list)

    response = client.get(
        "/api/citas",
        params={"from": "2026-09-01", "to": "2026-09-30", "status": "confirmada"},
    )

    assert response.status_code == 200
    assert seen["status"] is CitaStatus.confirmada


def test_list_rejects_unknown_status():
    response = client.get(
        "/api/citas", params={"from": "2026-09-01", "to": "2026-09-30", "status": "pendiente"}
    )
    assert response.status_code == 422


def test_create_returns_201(monkeypatch):
    seen = {}

    async def fake_create(organization_id, data):
        seen["organization_id"] = organization_id
        seen["customer_id"] = str(data.customer_id)
        return _canned()

    monkeypatch.setattr(citas_endpoint.citas_service, "create_cita", fake_create)

    response = client.post(
        "/api/citas",
        json={
            "customer_id": CUSTOMER_ID,
            "scheduled_at": "2026-09-10T15:00:00-05:00",
            "service_type": "Cambio de aceite",
        },
    )

    assert response.status_code == 201
    assert response.json()["id"] == CITA_ID
    assert seen["organization_id"] == ORG
    assert seen["customer_id"] == CUSTOMER_ID


def test_create_ignores_an_organization_id_in_the_body(monkeypatch):
    """Tenancy is not negotiable from the client side."""
    seen = {}

    async def fake_create(organization_id, data):
        seen["organization_id"] = organization_id
        return _canned()

    monkeypatch.setattr(citas_endpoint.citas_service, "create_cita", fake_create)

    response = client.post(
        "/api/citas",
        json={
            "customer_id": CUSTOMER_ID,
            "scheduled_at": "2026-09-10T15:00:00-05:00",
            "organization_id": "99999999-9999-9999-9999-999999999999",
        },
    )

    assert response.status_code == 201
    assert seen["organization_id"] == ORG


def test_patch_returns_updated_cita(monkeypatch):
    async def fake_update(organization_id, cita_id, data):
        assert organization_id == ORG
        assert cita_id == CITA_ID
        return _canned(status=CitaStatus.confirmada)

    monkeypatch.setattr(citas_endpoint.citas_service, "update_cita", fake_update)

    response = client.patch(f"/api/citas/{CITA_ID}", json={"status": "confirmada"})

    assert response.status_code == 200
    assert response.json()["status"] == "confirmada"


def test_403_when_the_user_has_no_organization():
    """get_current_user's fallback branch (api/deps.py) omits organization_id."""
    app.dependency_overrides[get_current_user] = lambda: {
        "id": "user-1",
        "email": "x@y.z",
        "role": "admin",
    }

    response = client.get("/api/citas", params={"from": "2026-09-01", "to": "2026-09-30"})

    assert response.status_code == 403
