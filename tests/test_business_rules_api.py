"""API tests for /api/ajustes (endpoints/business_rules.py).

The service layer is monkeypatched to canned results, so these assert the HTTP
boundary only: auth wiring, where organization_id comes from, validation and
status codes. Same shape as tests/test_citas_api.py.

The organization is the thing to guard here: these routes write the rules the
bot obeys, so a caller must never be able to name someone else's tenant.
"""

from datetime import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import api.v1.endpoints.business_rules as ajustes
from api.deps import get_current_user

ORG = "11111111-1111-1111-1111-111111111111"
OTRA_ORG = "99999999-9999-9999-9999-999999999999"

app = FastAPI()
app.include_router(ajustes.router, prefix="/api/ajustes")
client = TestClient(app)


@pytest.fixture(autouse=True)
def _auth():
    """Cada test corre como usuario autenticado de ORG salvo que lo cambie."""
    app.dependency_overrides[get_current_user] = lambda: {
        "id": "u1", "organization_id": ORG
    }
    yield
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def _sin_db(monkeypatch):
    """Registra las llamadas al servicio en vez de tocar Supabase."""
    llamadas: list = []

    async def fake_leer(organization_id):
        llamadas.append(("leer", organization_id))
        return {
            "horario": [
                {"weekday": 1, "is_open": True, "opens_at": time(8), "closes_at": time(17),
                 "max_citas": None, "capacidad_simultanea": 1},
            ],
            "servicios": [],
            "dias_especiales": [],
        }

    async def fake_guardar_horario(organization_id, dias):
        llamadas.append(("guardar_horario", organization_id, dias))
        return None

    async def fake_crear_servicio(organization_id, datos):
        llamadas.append(("crear_servicio", organization_id, datos))
        # Un UUID de verdad: la respuesta se valida contra ServicioRead, y un
        # doble que devuelve "s1" haría pasar un test que en producción falla.
        return {"id": "22222222-2222-2222-2222-222222222222", **datos.model_dump()}

    monkeypatch.setattr(ajustes.business_rules_service, "leer_ajustes", fake_leer)
    monkeypatch.setattr(ajustes.business_rules_service, "guardar_horario", fake_guardar_horario)
    monkeypatch.setattr(ajustes.business_rules_service, "crear_servicio", fake_crear_servicio)
    return llamadas


class TestAutenticacion:
    def test_sin_sesion_no_se_leen_los_ajustes(self):
        app.dependency_overrides.clear()

        assert client.get("/api/ajustes").status_code == 401

    def test_un_usuario_sin_organizacion_no_pasa(self):
        app.dependency_overrides[get_current_user] = lambda: {"id": "u1"}

        assert client.get("/api/ajustes").status_code == 403

    def test_la_organizacion_sale_del_token(self, _sin_db):
        client.get("/api/ajustes")

        assert _sin_db[0] == ("leer", ORG)

    def test_no_se_puede_pedir_la_organizacion_de_otro(self, _sin_db):
        """El parámetro se ignora: el tenant sale del token y de ningún otro
        lado. Aceptarlo sería leer los ajustes de otro cliente."""
        client.get(f"/api/ajustes?organization_id={OTRA_ORG}")

        assert _sin_db[0] == ("leer", ORG)


class TestLeerAjustes:
    def test_devuelve_horario_servicios_y_dias_especiales(self):
        cuerpo = client.get("/api/ajustes").json()

        assert set(cuerpo) == {"horario", "servicios", "dias_especiales"}


class TestGuardarHorario:
    def _dia(self, **extra):
        base = {"weekday": 1, "is_open": True, "opens_at": "08:00", "closes_at": "17:00"}
        return {**base, **extra}

    def test_guarda_el_horario_de_la_semana(self, _sin_db):
        r = client.put("/api/ajustes/horario", json={"dias": [self._dia()]})

        assert r.status_code == 200
        assert _sin_db[-1][0] == "guardar_horario"

    def test_rechaza_un_dia_abierto_sin_horas(self):
        """Mismo CHECK que la base, pero fallando aquí con un mensaje legible
        en vez de con un error de Postgres."""
        r = client.put("/api/ajustes/horario",
                       json={"dias": [self._dia(opens_at=None, closes_at=None)]})

        assert r.status_code == 422

    def test_rechaza_que_cierre_antes_de_abrir(self):
        r = client.put("/api/ajustes/horario",
                       json={"dias": [self._dia(opens_at="17:00", closes_at="08:00")]})

        assert r.status_code == 422

    def test_rechaza_un_dia_de_la_semana_invalido(self):
        r = client.put("/api/ajustes/horario", json={"dias": [self._dia(weekday=7)]})

        assert r.status_code == 422

    def test_rechaza_capacidad_cero(self):
        r = client.put("/api/ajustes/horario",
                       json={"dias": [self._dia(capacidad_simultanea=0)]})

        assert r.status_code == 422

    def test_un_dia_cerrado_no_necesita_horas(self):
        r = client.put("/api/ajustes/horario",
                       json={"dias": [{"weekday": 0, "is_open": False}]})

        assert r.status_code == 200


class TestServicios:
    def test_crea_un_servicio(self, _sin_db):
        r = client.post("/api/ajustes/servicios",
                        json={"name": "Cambio de amortiguadores", "duration_minutes": 120})

        assert r.status_code == 201

    def test_rechaza_una_duracion_menor_a_una_hora(self):
        """Regla del negocio: una cita dura mínimo una hora."""
        r = client.post("/api/ajustes/servicios",
                        json={"name": "Revisión rápida", "duration_minutes": 30})

        assert r.status_code == 422

    def test_una_hora_exacta_se_acepta(self):
        r = client.post("/api/ajustes/servicios",
                        json={"name": "Revisión", "duration_minutes": 60})

        assert r.status_code == 201

    def test_rechaza_un_nombre_vacio(self):
        r = client.post("/api/ajustes/servicios",
                        json={"name": "  ", "duration_minutes": 60})

        assert r.status_code == 422
