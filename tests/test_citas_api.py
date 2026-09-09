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


def test_delete_returns_204_with_no_body(monkeypatch):
    seen = {}

    async def fake_delete(organization_id, cita_id):
        seen["organization_id"] = organization_id
        seen["cita_id"] = cita_id

    monkeypatch.setattr(citas_endpoint.citas_service, "delete_cita", fake_delete)

    response = client.delete(f"/api/citas/{CITA_ID}")

    assert response.status_code == 204
    assert response.content == b""
    assert seen["organization_id"] == ORG
    assert seen["cita_id"] == CITA_ID


def test_delete_403_when_the_user_has_no_organization():
    """The destructive route must enforce tenancy like every other one."""
    app.dependency_overrides[get_current_user] = lambda: {"id": "user-1"}

    response = client.delete(f"/api/citas/{CITA_ID}")

    assert response.status_code == 403


def test_403_when_the_user_has_no_organization():
    """get_current_user's fallback branch (api/deps.py) omits organization_id."""
    app.dependency_overrides[get_current_user] = lambda: {
        "id": "user-1",
        "email": "x@y.z",
        "role": "admin",
    }

    response = client.get("/api/citas", params={"from": "2026-09-01", "to": "2026-09-30"})

    assert response.status_code == 403


class TestAvisoAlCliente:
    """Aceptar o rechazar una solicitud desde el calendario le llega al cliente.

    Es lo que cierra el ciclo que abre la agenda web: sin esto el taller acepta
    la cita y nadie se lo dice al cliente, que queda esperando.
    """

    @pytest.fixture
    def avisos(self, monkeypatch):
        registrados = []

        async def fake_avisar(provider, *, anterior, cita):
            registrados.append((anterior, cita.get("status")))

        monkeypatch.setattr(citas_endpoint, "avisar_cambio_de_estado", fake_avisar)
        return registrados

    def test_aceptar_una_solicitud_dispara_el_aviso(self, monkeypatch, avisos):
        async def fake_update(org, cita_id, data, **kw):
            return _canned(status=CitaStatus.agendada)

        async def fake_get(org, cita_id):
            return {"status": "solicitada"}

        monkeypatch.setattr(citas_endpoint.citas_service, "update_cita", fake_update)
        monkeypatch.setattr(citas_endpoint.citas_service, "estado_actual", fake_get)

        client.patch(f"/api/citas/{CITA_ID}", json={"status": "agendada"})

        assert avisos == [("solicitada", CitaStatus.agendada)]

    def test_un_cambio_interno_no_dispara_aviso(self, monkeypatch, avisos):
        """agendada -> confirmada es trabajo del taller, no del cliente. El
        filtro vive en el servicio de aviso; aquí se comprueba que igual se le
        consulta con el estado anterior correcto."""
        async def fake_update(org, cita_id, data, **kw):
            return _canned(status=CitaStatus.confirmada)

        async def fake_get(org, cita_id):
            return {"status": "agendada"}

        monkeypatch.setattr(citas_endpoint.citas_service, "update_cita", fake_update)
        monkeypatch.setattr(citas_endpoint.citas_service, "estado_actual", fake_get)

        client.patch(f"/api/citas/{CITA_ID}", json={"status": "confirmada"})

        assert avisos == [("agendada", CitaStatus.confirmada)]

    def test_un_fallo_del_aviso_no_rompe_el_cambio_de_estado(self, monkeypatch):
        """El cambio ya se guardó y es la verdad: el 200 no puede depender de
        que WhatsApp responda."""
        async def fake_update(org, cita_id, data, **kw):
            return _canned(status=CitaStatus.agendada)

        async def fake_get(org, cita_id):
            return {"status": "solicitada"}

        async def explota(provider, *, anterior, cita):
            raise RuntimeError("whapi caída")

        monkeypatch.setattr(citas_endpoint.citas_service, "update_cita", fake_update)
        monkeypatch.setattr(citas_endpoint.citas_service, "estado_actual", fake_get)
        monkeypatch.setattr(citas_endpoint, "avisar_cambio_de_estado", explota)

        # TestClient re-lanza las excepciones de las tareas de fondo, lo que
        # esconde el status code que el llamador recibió de verdad: en
        # producción la respuesta ya salió antes de que la tarea corriera.
        sin_relanzar = TestClient(app, raise_server_exceptions=False)

        r = sin_relanzar.patch(f"/api/citas/{CITA_ID}", json={"status": "agendada"})

        assert r.status_code == 200


class TestGenerarLinkDeAgenda:
    """El taller genera el link que le manda al cliente por WhatsApp.

    Autenticado y con la organización tomada del token del EMPLEADO: el link
    que sale lleva firmada esa organización, así que un taller no puede emitir
    un link que agende en la agenda de otro.
    """

    @pytest.fixture(autouse=True)
    def _config(self, monkeypatch):
        monkeypatch.setattr(citas_endpoint.settings, "AGENDA_TOKEN_SECRET",
                            "secreto-de-prueba", raising=False)
        monkeypatch.setattr(citas_endpoint.settings, "AGENDA_BASE_URL",
                            "https://toyopana.app", raising=False)

    def _pedir(self):
        return client.post("/api/citas/link-agenda")

    def test_devuelve_un_link_completo(self):
        url = self._pedir().json()["url"]

        assert url.startswith("https://toyopana.app/agenda/")

    def test_el_link_no_lleva_cliente(self):
        """Genérico a propósito: el empleado lo comparte sin buscar antes a la
        persona, y quien lo abre se identifica en la página."""
        from services.agenda_token import DatosToken, leer_token

        url = self._pedir().json()["url"]
        token = url.rsplit("/", 1)[1]

        assert not hasattr(leer_token(token, secreto="secreto-de-prueba"),
                           "customer_id")

    def test_el_token_lleva_la_organizacion_del_empleado(self):
        """Un taller no puede emitir un link que agende en la agenda de otro."""
        from services.agenda_token import leer_token

        url = self._pedir().json()["url"]
        token = url.rsplit("/", 1)[1]

        assert leer_token(token, secreto="secreto-de-prueba").organization_id == ORG

    def test_dice_cuando_vence(self):
        """La pantalla lo muestra para que el empleado sepa si vale la pena
        reenviar el mismo link o pedir uno nuevo."""
        assert "expira_en" in self._pedir().json()

    def test_sin_sesion_no_se_generan_links(self):
        app.dependency_overrides.clear()

        assert self._pedir().status_code == 401

    def test_sin_secreto_configurado_falla_claro(self, monkeypatch):
        """Falla cerrado y con un mensaje que dice qué configurar, en vez de
        emitir un link que nadie va a poder abrir."""
        monkeypatch.setattr(citas_endpoint.settings, "AGENDA_TOKEN_SECRET", "",
                            raising=False)

        assert self._pedir().status_code == 503
