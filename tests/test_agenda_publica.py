"""API tests for /api/public/agenda (endpoints/agenda_publica.py).

These are the FIRST routes in this application with no session, so what they
must prove is not that they work but that they refuse: a bad token, an expired
one, and above all a caller trying to name someone else's organization.

The service layer is monkeypatched; nothing here reaches the network.
"""

import uuid
from datetime import date, datetime, time, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import api.v1.endpoints.agenda_publica as agenda
import services.agenda_service as agenda_service_module
from schemas.cita import CitaRead, CitaStatus
from schemas.customer import CustomerOut
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
        # CitaRead, no dict: es lo que devuelve create_cita de verdad. Un doble
        # que devuelve un dict hace pasar un endpoint que en producción falla
        # con "'CitaRead' object is not subscriptable".
        return CitaRead(
            id=uuid.UUID("33333333-3333-3333-3333-333333333333"),
            organization_id=uuid.UUID(ORG),
            customer_id=uuid.UUID(CUSTOMER),
            scheduled_at=datetime(2026, 9, 15, 13, 0, tzinfo=timezone.utc),
            status=CitaStatus.solicitada,
            created_at=datetime(2026, 9, 8, tzinfo=timezone.utc),
            updated_at=datetime(2026, 9, 8, tzinfo=timezone.utc),
        )

    monkeypatch.setattr(agenda.agenda_service, "disponibilidad", fake_disponibilidad)
    monkeypatch.setattr(agenda.agenda_service, "solicitar_cita", fake_solicitar)
    return llamadas


def _token(org=ORG, ttl=48):
    return crear_token(org, ttl_horas=ttl, secreto=SECRETO)


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

    def test_el_cliente_se_identifica_en_la_pagina(self, _sin_db):
        client.post(
            f"/api/public/agenda/{_token()}/solicitar",
            json={"fecha": "2026-09-15", "hora": "08:00", "nombre": "Juan Pérez",
                  "telefono": "6851-0658"},
        )

        _, kwargs = _sin_db[-1]
        assert kwargs["organization_id"] == ORG
        assert kwargs["nombre"] == "Juan Pérez"
        assert kwargs["telefono"] == "6851-0658"

    def test_un_customer_id_en_el_cuerpo_se_ignora(self, _sin_db):
        """El cliente se resuelve por teléfono, no por un id que el cliente
        mande: aceptarlo dejaría agendar en la ficha de otra persona."""
        client.post(
            f"/api/public/agenda/{_token()}/solicitar",
            json={"fecha": "2026-09-15", "hora": "08:00", "nombre": "Juan",
                  "telefono": "6851-0658",
                  "customer_id": "44444444-4444-4444-4444-444444444444"},
        )

        assert "customer_id" not in _sin_db[-1][1]


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
        cuerpo = {"fecha": "2026-09-15", "hora": "08:00",
                  "nombre": "Juan Pérez", "telefono": "6851-0658"}
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
                    json={"fecha": "2026-09-15", "hora": "08:00", "nombre": "Juan",
                  "telefono": "6851-0658"})

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
            return CitaRead(
                id=uuid.UUID("33333333-3333-3333-3333-333333333333"),
                organization_id=uuid.UUID(ORG),
                customer_id=data.customer_id,
                scheduled_at=data.scheduled_at,
                status=data.status,
                created_at=datetime(2026, 9, 8, tzinfo=timezone.utc),
                updated_at=datetime(2026, 9, 8, tzinfo=timezone.utc),
            )

        async def fake_find_customer(org, data):
            # CustomerOut, no dict: es lo que devuelve find_or_create_customer
            # de verdad. Un doble que devuelve un dict hace pasar un servicio
            # que en producción falla con "not subscriptable" -- ya pasó dos
            # veces en este módulo.
            return CustomerOut(
                id=uuid.UUID(CUSTOMER),
                name=data.name,
                phone=data.phone,
                created_at=datetime(2026, 9, 8, tzinfo=timezone.utc),
            )

        monkeypatch.setattr(agenda_service_module.citas_service, "create_cita", fake_create)
        monkeypatch.setattr(agenda_service_module.orders_service,
                            "find_or_create_customer", fake_find_customer)

        await SOLICITAR_REAL(
            organization_id=ORG,
            fecha=date(2026, 9, 15), hora=time(8),
            nombre="Juan Pérez", telefono="6851-0658", **extra,
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


class TestTelefonoObligatorio:
    """Sin cliente en el token, el teléfono es cómo le avisamos después.

    Un link genérico no sabe a quién se lo mandaron: si la persona no deja un
    teléfono, el taller puede aceptar la cita y no tener a dónde confirmarla.
    """

    def _reservar(self, **extra):
        cuerpo = {"fecha": "2026-09-15", "hora": "08:00", "nombre": "Juan Pérez",
                  "telefono": "6851-0658"}
        cuerpo.update(extra)
        return client.post(f"/api/public/agenda/{_token()}/solicitar", json=cuerpo)

    def test_sin_telefono_no_se_acepta(self):
        r = client.post(f"/api/public/agenda/{_token()}/solicitar",
                        json={"fecha": "2026-09-15", "hora": "08:00", "nombre": "Juan"})

        assert r.status_code == 422

    def test_un_telefono_vacio_no_vale(self):
        assert self._reservar(telefono="   ").status_code == 422

    def test_un_telefono_incompleto_no_vale(self):
        """"63343-23" son siete dígitos: no alcanza para un celular panameño, y
        la confirmación va por WhatsApp. Es un caso real -- ese teléfono está
        así en el CRM de producción."""
        assert self._reservar(telefono="63343-23").status_code == 422

    def test_acepta_el_formato_que_la_gente_escribe(self):
        for formato in ("6851-0658", "+507 6851 0658", "68510658", "507 6851-0658"):
            assert self._reservar(telefono=formato).status_code == 201, formato
