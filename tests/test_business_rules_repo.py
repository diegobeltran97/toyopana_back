"""Tests for BusinessRulesRepository (repositories/business_rules.py).

The HTTP layer is replaced with a fake httpx.AsyncClient, so these assert the
PostgREST request the repository builds and how it parses the answer, without
touching the network. Same shape as tests/test_marketing_repository.py.

`app/.env` points at PRODUCTION Supabase, so a repository test that reaches the
network reads and could write real data. Nothing here may leave the process.
"""

from datetime import date, time

import pytest

import repositories.business_rules as repo_module
from repositories.business_rules import BusinessRulesRepository

ORG = "11111111-1111-1111-1111-111111111111"
SERVICIO = "33333333-3333-3333-3333-333333333333"
FILA_SERVICIO = {
    "id": SERVICIO,
    "name": "Alineación",
    "duration_minutes": 90,
    "active": True,
    "sort_order": 0,
}


class FakeResponse:
    def __init__(self, json_data=None):
        self._json = json_data if json_data is not None else []
        self.text = "ok"

    def json(self):
        return self._json

    def raise_for_status(self):
        return None


class FakeAsyncClient:
    """Records every request and answers with canned rows, keyed by table name."""

    calls: list = []

    def __init__(self, por_tabla):
        self._por_tabla = por_tabla

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, url, params=None, headers=None):
        FakeAsyncClient.calls.append({"url": url, "params": params})
        tabla = url.rsplit("/", 1)[-1]
        return FakeResponse(self._por_tabla.get(tabla, []))

    async def patch(self, url, json=None, params=None, headers=None):
        FakeAsyncClient.calls.append(
            {"url": url, "params": params, "json": json, "headers": headers}
        )
        tabla = url.rsplit("/", 1)[-1]
        return FakeResponse(self._por_tabla.get(tabla, []))

    async def post(self, url, json=None, params=None, headers=None):
        FakeAsyncClient.calls.append(
            {"url": url, "params": params, "json": json, "headers": headers}
        )
        tabla = url.rsplit("/", 1)[-1]
        return FakeResponse(self._por_tabla.get(tabla, []))

    async def delete(self, url, params=None, headers=None):
        FakeAsyncClient.calls.append(
            {"url": url, "params": params, "json": None, "headers": headers}
        )
        tabla = url.rsplit("/", 1)[-1]
        return FakeResponse(self._por_tabla.get(tabla, []))


@pytest.fixture(autouse=True)
def _sin_red(monkeypatch):
    """Ningún test de este módulo toca la red. Se instala antes que nada."""
    FakeAsyncClient.calls = []

    def _fabricar(por_tabla):
        monkeypatch.setattr(
            repo_module.httpx, "AsyncClient", lambda **kw: FakeAsyncClient(por_tabla)
        )

    return _fabricar


class TestSemana:
    async def test_devuelve_el_horario_indexado_por_dia_de_la_semana(self, _sin_red):
        _sin_red({"business_hours": [
            {"weekday": 1, "is_open": True, "opens_at": "08:00:00", "closes_at": "17:00:00",
             "max_citas": None, "capacidad_simultanea": 1},
            {"weekday": 6, "is_open": True, "opens_at": "08:00:00", "closes_at": "15:00:00",
             "max_citas": None, "capacidad_simultanea": 1},
        ]})

        semana = await BusinessRulesRepository().semana(ORG)

        assert set(semana) == {1, 6}

    async def test_convierte_las_horas_de_texto_a_objetos_time(self, _sin_red):
        """PostgREST devuelve "08:00:00"; el módulo de reglas espera `time`.
        Comparar un string con un time no falla: da False y el día entero se
        resuelve mal en silencio."""
        _sin_red({"business_hours": [
            {"weekday": 1, "is_open": True, "opens_at": "08:00:00", "closes_at": "17:00:00",
             "max_citas": None, "capacidad_simultanea": 1},
        ]})

        semana = await BusinessRulesRepository().semana(ORG)

        assert semana[1]["opens_at"] == time(8)
        assert semana[1]["closes_at"] == time(17)

    async def test_un_dia_cerrado_no_trae_horas(self, _sin_red):
        _sin_red({"business_hours": [
            {"weekday": 0, "is_open": False, "opens_at": None, "closes_at": None,
             "max_citas": None, "capacidad_simultanea": 1},
        ]})

        semana = await BusinessRulesRepository().semana(ORG)

        assert semana[0]["opens_at"] is None

    async def test_filtra_por_organizacion(self, _sin_red):
        _sin_red({"business_hours": []})

        await BusinessRulesRepository().semana(ORG)

        assert FakeAsyncClient.calls[-1]["params"]["organization_id"] == f"eq.{ORG}"


class TestExcepciones:
    async def test_devuelve_las_excepciones_indexadas_por_fecha(self, _sin_red):
        _sin_red({"business_calendar": [
            {"date": "2026-12-25", "is_open": False, "opens_at": None, "closes_at": None,
             "max_citas": None, "capacidad_simultanea": None, "reason": "Navidad"},
        ]})

        excepciones = await BusinessRulesRepository().excepciones(
            ORG, date(2026, 12, 1), date(2026, 12, 31)
        )

        assert date(2026, 12, 25) in excepciones

    async def test_pide_solo_el_rango_solicitado(self, _sin_red):
        _sin_red({"business_calendar": []})

        await BusinessRulesRepository().excepciones(ORG, date(2026, 12, 1), date(2026, 12, 31))

        params = FakeAsyncClient.calls[-1]["params"]
        assert params["date"] == "gte.2026-12-01"
        assert params["and"] == "(date.lte.2026-12-31)"


class TestCitasQueOcupan:
    """El conteo de cupo: qué citas ocupan un bloque y cuáles no."""

    async def test_solo_pide_las_citas_aceptadas(self, _sin_red):
        """agendada y confirmada ocupan; solicitada y cancelada NO. Si las
        solicitudes contaran, cinco personas pidiendo la misma hora la
        bloquearían sin que el taller aceptara ninguna."""
        _sin_red({"citas": []})

        await BusinessRulesRepository().citas_que_ocupan(ORG, date(2026, 9, 15))

        assert FakeAsyncClient.calls[-1]["params"]["status"] == "in.(agendada,confirmada)"

    async def test_devuelve_hora_local_y_duracion(self, _sin_red):
        """13:00 UTC es 08:00 en Panamá. Devolver la hora UTC pondría la cita
        cinco bloques más tarde."""
        _sin_red({"citas": [
            {"scheduled_at": "2026-09-15T13:00:00+00:00", "service_types": {"duration_minutes": 60}},
        ]})

        citas = await BusinessRulesRepository().citas_que_ocupan(ORG, date(2026, 9, 15))

        assert citas == [(time(8), 60)]

    async def test_una_cita_sin_servicio_dura_el_minimo(self, _sin_red):
        """service_type_id es nullable: una cita sin servicio asignado ocupa el
        bloque mínimo, no cero."""
        _sin_red({"citas": [
            {"scheduled_at": "2026-09-15T14:00:00+00:00", "service_types": None},
        ]})

        citas = await BusinessRulesRepository().citas_que_ocupan(ORG, date(2026, 9, 15))

        assert citas == [(time(9), 60)]

    async def test_el_rango_del_dia_se_calcula_en_hora_de_panama(self, _sin_red):
        """El día de Panamá empieza a las 05:00 UTC. Filtrar por medianoche UTC
        se comería las citas de la mañana."""
        _sin_red({"citas": []})

        await BusinessRulesRepository().citas_que_ocupan(ORG, date(2026, 9, 15))

        assert FakeAsyncClient.calls[-1]["params"]["scheduled_at"].startswith(
            "gte.2026-09-15T05:00"
        )


class TestServicios:
    async def test_devuelve_solo_los_activos(self, _sin_red):
        _sin_red({"service_types": []})

        await BusinessRulesRepository().servicios(ORG)

        assert FakeAsyncClient.calls[-1]["params"]["active"] == "is.true"

    async def test_la_pantalla_de_ajustes_puede_pedir_los_inactivos(self, _sin_red):
        """Un servicio desactivado tiene que seguir viéndose en ajustes o no
        habría forma de reactivarlo."""
        _sin_red({"service_types": []})

        await BusinessRulesRepository().servicios(ORG, incluir_inactivos=True)

        assert "active" not in FakeAsyncClient.calls[-1]["params"]

    async def test_pide_la_columna_active(self, _sin_red):
        """Sin ella ServicioRead reporta active=True por su default y la
        pantalla dibujaría todos los interruptores encendidos."""
        _sin_red({"service_types": []})

        await BusinessRulesRepository().servicios(ORG, incluir_inactivos=True)

        assert "active" in FakeAsyncClient.calls[-1]["params"]["select"]


class TestActualizarServicio:
    async def test_filtra_por_id_y_por_organizacion(self, _sin_red):
        """Sin el filtro de organización, conocer un UUID bastaría para
        editarle el catálogo a otro taller."""
        _sin_red({"service_types": [FILA_SERVICIO]})

        await BusinessRulesRepository().actualizar_servicio(
            ORG, SERVICIO, {"duration_minutes": 90}
        )

        params = FakeAsyncClient.calls[-1]["params"]
        assert params["id"] == f"eq.{SERVICIO}"
        assert params["organization_id"] == f"eq.{ORG}"

    async def test_manda_solo_los_campos_que_cambiaron(self, _sin_red):
        _sin_red({"service_types": [FILA_SERVICIO]})

        await BusinessRulesRepository().actualizar_servicio(
            ORG, SERVICIO, {"duration_minutes": 90}
        )

        assert FakeAsyncClient.calls[-1]["json"] == {"duration_minutes": 90}

    async def test_devuelve_la_fila_actualizada(self, _sin_red):
        _sin_red({"service_types": [FILA_SERVICIO]})

        fila = await BusinessRulesRepository().actualizar_servicio(
            ORG, SERVICIO, {"duration_minutes": 90}
        )

        assert fila["duration_minutes"] == 90

    async def test_sin_fila_devuelve_none(self, _sin_red):
        """PostgREST responde 200 con lista vacía cuando el filtro no encuentra
        nada: es un 404, no un error."""
        _sin_red({"service_types": []})

        fila = await BusinessRulesRepository().actualizar_servicio(
            ORG, SERVICIO, {"name": "X"}
        )

        assert fila is None
