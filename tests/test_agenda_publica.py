"""API tests for /api/public/agenda (endpoints/agenda_publica.py).

These are the FIRST routes in this application with no session, so what they
must prove is not that they work but that they refuse: a bad token, an expired
one, and above all a caller trying to name someone else's organization.

The service layer is monkeypatched; nothing here reaches the network.
"""

from datetime import date, time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import api.v1.endpoints.agenda_publica as agenda
import services.agenda_service as agenda_service_module
from services.agenda_token import crear_token

# La función real, capturada antes de que el fixture autouse la sustituya:
# TestNaceComoSolicitud prueba su comportamiento, no el del doble.
SOLICITAR_REAL = agenda_service_module.solicitar_cita

SECRETO = "un-secreto-largo-de-prueba"
ORG = "11111111-1111-1111-1111-111111111111"
OTRA_ORG = "99999999-9999-9999-9999-999999999999"
CUSTOMER = "22222222-2222-2222-2222-222222222222"

app = FastAPI()
app.include_router(agenda.router, prefix="/api/public")
client = TestClient(app)


@pytest.fixture(autouse=True)
def _secreto(monkeypatch):
    monkeypatch.setattr(agenda.settings, "AGENDA_TOKEN_SECRET", SECRETO, raising=False)


@pytest.fixture(autouse=True)
def _sin_db(monkeypatch):
    """Registra las llamadas al servicio en vez de tocar Supabase."""
    llamadas: list = []

    async def fake_disponibilidad(organization_id, dias):
        llamadas.append(("disponibilidad", organization_id, dias))
        return [
            {"fecha": date(2026, 9, 15), "abierto": True,
             "bloques": [{"hora": time(8), "libre": True},
                         {"hora": time(9), "libre": False}]},
        ]

    async def fake_solicitar(**kwargs):
        llamadas.append(("solicitar", kwargs))
        return {"id": "33333333-3333-3333-3333-333333333333",
                "scheduled_at": "2026-09-15T13:00:00+00:00", "status": "solicitada"}

    monkeypatch.setattr(agenda.agenda_service, "disponibilidad", fake_disponibilidad)
    monkeypatch.setattr(agenda.agenda_service, "solicitar_cita", fake_solicitar)
    return llamadas


def _token(org=ORG, customer=CUSTOMER, ttl=48):
    return crear_token(org, customer, ttl_horas=ttl, secreto=SECRETO)


class TestQuienPuedeEntrar:
    def test_un_token_valido_ve_la_agenda(self):
        assert client.get(f"/api/public/agenda/{_token()}").status_code == 200

    def test_un_token_inventado_no(self):
        assert client.get("/api/public/agenda/inventado").status_code == 403

    def test_un_token_alterado_no(self):
        t = _token()
        assert client.get(f"/api/public/agenda/{t[:-1]}x").status_code == 403

    def test_un_token_vencido_devuelve_410(self):
        """410 y no 403: el link fue válido y caducó, y la pantalla necesita
        distinguirlo para decir "pide uno nuevo" en vez de "no tienes acceso"."""
        assert client.get(f"/api/public/agenda/{_token(ttl=-1)}").status_code == 410

    def test_sin_secreto_configurado_no_entra_nadie(self, monkeypatch):
        """Falla cerrado: un .env incompleto no abre la agenda a todos."""
        monkeypatch.setattr(agenda.settings, "AGENDA_TOKEN_SECRET", "", raising=False)

        assert client.get(f"/api/public/agenda/{_token()}").status_code == 403


class TestElTenantSaleDelToken:
    """El riesgo central de una ruta sin sesión."""

    def test_la_organizacion_sale_del_token(self, _sin_db):
        client.get(f"/api/public/agenda/{_token()}")

        assert _sin_db[0][1] == ORG

    def test_un_parametro_de_organizacion_se_ignora(self, _sin_db):
        client.get(f"/api/public/agenda/{_token()}?organization_id={OTRA_ORG}")

        assert _sin_db[0][1] == ORG

    def test_al_reservar_el_cliente_tambien_sale_del_token(self, _sin_db):
        client.post(
            f"/api/public/agenda/{_token()}/solicitar",
            json={"fecha": "2026-09-15", "hora": "08:00", "nombre": "Juan Pérez"},
        )

        _, kwargs = _sin_db[-1]
        assert kwargs["organization_id"] == ORG
        assert kwargs["customer_id"] == CUSTOMER

    def test_un_customer_id_en_el_cuerpo_se_ignora(self, _sin_db):
        """Aceptarlo dejaría agendar a nombre de otra persona."""
        client.post(
            f"/api/public/agenda/{_token()}/solicitar",
            json={"fecha": "2026-09-15", "hora": "08:00", "nombre": "Juan",
                  "customer_id": "44444444-4444-4444-4444-444444444444"},
        )

        assert _sin_db[-1][1]["customer_id"] == CUSTOMER


class TestVerDisponibilidad:
    def test_devuelve_los_dias_con_sus_bloques(self):
        cuerpo = client.get(f"/api/public/agenda/{_token()}").json()

        assert cuerpo["dias"][0]["bloques"][0]["hora"] == "08:00:00"

    def test_marca_cuales_estan_libres(self):
        cuerpo = client.get(f"/api/public/agenda/{_token()}").json()

        assert [b["libre"] for b in cuerpo["dias"][0]["bloques"]] == [True, False]

    def test_no_pide_mas_de_dos_semanas(self):
        """Un horizonte abierto haría al taller resolver meses de agenda para
        una pantalla que muestra una semana."""
        r = client.get(f"/api/public/agenda/{_token()}?dias=90")

        assert r.status_code == 422


class TestReservar:
    def _reservar(self, **extra):
        cuerpo = {"fecha": "2026-09-15", "hora": "08:00", "nombre": "Juan Pérez"}
        return client.post(f"/api/public/agenda/{_token()}/solicitar",
                           json={**cuerpo, **extra})

    def test_crea_la_solicitud(self):
        assert self._reservar().status_code == 201

    def test_la_respuesta_dice_que_esta_PENDIENTE(self):
        """Lo que impide que el cliente se vaya creyendo que tiene cita."""
        assert self._reservar().json()["status"] == "solicitada"

    def test_el_nombre_es_obligatorio(self):
        """Del token sale el teléfono, no el nombre: si escribió desde un número
        desconocido, no sabemos quién es."""
        r = client.post(f"/api/public/agenda/{_token()}/solicitar",
                        json={"fecha": "2026-09-15", "hora": "08:00"})

        assert r.status_code == 422

    def test_un_nombre_vacio_no_vale(self):
        assert self._reservar(nombre="   ").status_code == 422

    def test_el_servicio_es_opcional(self):
        assert self._reservar().status_code == 201

    def test_se_puede_indicar_un_servicio(self, _sin_db):
        sid = "55555555-5555-5555-5555-555555555555"

        self._reservar(service_type_id=sid)

        assert _sin_db[-1][1]["service_type_id"] == sid

    def test_reservar_con_token_vencido_no_crea_nada(self, _sin_db):
        client.post(f"/api/public/agenda/{_token(ttl=-1)}/solicitar",
                    json={"fecha": "2026-09-15", "hora": "08:00", "nombre": "Juan"})

        assert _sin_db == []


class TestNaceComoSolicitud:
    """Lo que impide que el cliente se vaya creyendo que tiene cita.

    Antes de la migración 006 create_cita quemaba 'agendada': una cita pedida
    desde la web nacía FIRME sin que nadie del taller la hubiera visto.
    """

    async def _crear(self, monkeypatch, **extra):
        """Corre la función REAL con create_cita sustituido, y devuelve el
        CitaCreate que se habría guardado."""
        creadas = []

        async def fake_create(org, data, repo=None):
            creadas.append(data)
            return {"id": "33333333-3333-3333-3333-333333333333",
                    "scheduled_at": "2026-09-15T13:00:00+00:00",
                    "status": data.status.value}

        monkeypatch.setattr(agenda_service_module.citas_service, "create_cita", fake_create)

        await SOLICITAR_REAL(
            organization_id=ORG, customer_id=CUSTOMER,
            fecha=date(2026, 9, 15), hora=time(8), nombre="Juan Pérez", **extra,
        )
        return creadas[0]

    async def test_la_cita_se_crea_como_solicitada(self, monkeypatch):
        cita = await self._crear(monkeypatch)

        assert cita.status.value == "solicitada"

    async def test_queda_marcada_como_creada_por_el_bot(self, monkeypatch):
        """Después de aceptarla el estado ya no dice de dónde vino; created_via
        es cómo se demuestra cuántas citas produjo el bot."""
        cita = await self._crear(monkeypatch)

        assert cita.created_via == "bot"

    async def test_la_hora_se_guarda_en_zona_de_panama(self, monkeypatch):
        """08:00 en Panamá son las 13:00 UTC. Combinar sin zona correría la
        cita cinco horas."""
        cita = await self._crear(monkeypatch)

        assert cita.scheduled_at.utcoffset().total_seconds() == -5 * 3600

    async def test_el_nombre_del_cliente_no_se_guarda_como_servicio(self, monkeypatch):
        """Bug de la primera versión: el nombre se pasaba en service_type."""
        cita = await self._crear(monkeypatch)

        assert cita.service_type != "Juan Pérez"
