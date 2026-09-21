"""Tests for services/cita_aviso.py -- telling the customer what happened.

Without this, a customer who books through the web agenda waits forever: the
shop accepts the request in its calendar and nobody tells them. That is worse
than the paper agenda, where at least somebody was looking at it.

The governing rule is the same as the webhook's post-200 half: the status
change already happened and is the source of truth, so NOTHING here may raise.
A WhatsApp that fails to send must not roll back an accepted appointment.
"""

from datetime import datetime, timezone

import pytest

import uuid

import services.cita_aviso as aviso
from schemas.cita import CitaRead, CitaStatus
from core.result import Result
from schemas.messaging import SentMessage

ORG = "11111111-1111-1111-1111-111111111111"


class FakeProvider:
    def __init__(self, result=None):
        self.result = result or Result.success(SentMessage(id="m1", to="x", status="sent"))
        self.enviados = []

    async def send_text(self, msg):
        self.enviados.append(msg)
        return self.result


def _cita(estado="agendada", telefono="+50768510658"):
    return {
        "id": "33333333-3333-3333-3333-333333333333",
        "status": estado,
        "scheduled_at": datetime(2026, 9, 15, 13, 0, tzinfo=timezone.utc),
        "customer": {"name": "Juan Pérez", "phone": telefono},
    }


class TestCuandoSeAvisa:
    async def test_aceptar_una_solicitud_avisa_al_cliente(self, ):
        provider = FakeProvider()

        await aviso.avisar_cambio_de_cita(
            provider, anterior="solicitada", cita=_cita("agendada")
        )

        assert len(provider.enviados) == 1

    async def test_rechazar_una_solicitud_tambien_avisa(self):
        provider = FakeProvider()

        await aviso.avisar_cambio_de_cita(
            provider, anterior="solicitada", cita=_cita("cancelada")
        )

        assert len(provider.enviados) == 1

    async def test_no_se_avisa_un_cambio_entre_estados_internos(self):
        """agendada -> confirmada es trabajo interno del taller. El cliente no
        pidió saber cada movimiento de la agenda."""
        provider = FakeProvider()

        await aviso.avisar_cambio_de_cita(
            provider, anterior="agendada", cita=_cita("confirmada")
        )

        assert provider.enviados == []

    async def test_no_se_avisa_si_el_estado_no_cambio(self):
        provider = FakeProvider()

        await aviso.avisar_cambio_de_cita(
            provider, anterior="solicitada", cita=_cita("solicitada")
        )

        assert provider.enviados == []


class TestQueDiceElMensaje:
    async def _texto(self, estado):
        provider = FakeProvider()
        await aviso.avisar_cambio_de_cita(
            provider, anterior="solicitada", cita=_cita(estado)
        )
        return provider.enviados[0].body

    async def test_al_aceptar_dice_confirmada(self):
        texto = await self._texto("agendada")

        assert "onfirmada" in texto

    async def test_al_aceptar_lleva_la_fecha_en_hora_de_panama(self):
        """13:00 UTC son las 8:00 a.m. en Panamá. Mandar la hora UTC citaría al
        cliente cinco horas tarde."""
        texto = await self._texto("agendada")

        assert "8:00 a.m." in texto

    async def test_al_aceptar_saluda_por_su_nombre(self):
        assert "Juan" in await self._texto("agendada")

    async def test_al_rechazar_NO_dice_confirmada(self):
        texto = await self._texto("cancelada")

        assert "onfirmada" not in texto

    async def test_el_mensaje_no_tiene_puntuacion_repetida(self):
        """La hora ya termina en "a.m."/"p.m."; agregar un punto detrás deja
        "8:00 a.m..", que se ve descuidado en un mensaje al cliente."""
        texto = await self._texto("agendada")

        assert ".." not in texto

    async def test_al_rechazar_invita_a_elegir_otra_hora(self):
        """Un rechazo seco pierde al cliente; el objetivo es reagendar."""
        texto = await self._texto("cancelada")

        assert "otra" in texto.lower() or "otro" in texto.lower()


class TestNadaPuedeRomperse:
    """El cambio de estado ya ocurrió y es la verdad. Un aviso que falla se
    registra, nunca revierte ni lanza."""

    async def test_un_fallo_del_proveedor_no_lanza(self):
        provider = FakeProvider(Result.failure("rate_limit", status_code=429))

        await aviso.avisar_cambio_de_cita(
            provider, anterior="solicitada", cita=_cita("agendada")
        )

    async def test_una_excepcion_del_proveedor_no_lanza(self):
        class Explota:
            async def send_text(self, msg):
                raise RuntimeError("whapi caída")

        await aviso.avisar_cambio_de_cita(
            Explota(), anterior="solicitada", cita=_cita("agendada")
        )

    async def test_una_cita_sin_telefono_no_lanza(self):
        """El cliente puede no tener teléfono cargado; no hay a dónde avisar."""
        provider = FakeProvider()

        await aviso.avisar_cambio_de_cita(
            provider, anterior="solicitada", cita=_cita("agendada", telefono=None)
        )

        assert provider.enviados == []

    async def test_una_cita_sin_cliente_no_lanza(self):
        provider = FakeProvider()
        cita = {**_cita("agendada")}
        del cita["customer"]

        await aviso.avisar_cambio_de_cita(provider, anterior="solicitada", cita=cita)

        assert provider.enviados == []


class TestAllowlistDeTesting:
    """El aviso también respeta WHATSAPP_ALLOWED_NUMBERS.

    Hueco encontrado probando en el navegador: el flag frenaba las respuestas
    del bot entrante pero NO estos avisos, así que confirmar una cita en el
    panel le mandaba un WhatsApp real a un cliente real — que es exactamente lo
    que el flag existe para evitar mientras se prueba.
    """

    @pytest.fixture
    def allowlist(self, monkeypatch):
        def _set(valor):
            monkeypatch.setattr(
                aviso.settings, "WHATSAPP_ALLOWED_NUMBERS", valor, raising=False
            )
        return _set

    async def test_un_numero_listado_recibe_el_aviso(self, allowlist):
        allowlist("50768510658")
        provider = FakeProvider()

        await aviso.avisar_cambio_de_cita(
            provider, anterior="solicitada", cita=_cita("agendada")
        )

        assert len(provider.enviados) == 1

    async def test_un_numero_no_listado_no_recibe_nada(self, allowlist):
        allowlist("50768510658")
        provider = FakeProvider()

        await aviso.avisar_cambio_de_cita(
            provider, anterior="solicitada",
            cita=_cita("agendada", telefono="+50761112222"),
        )

        assert provider.enviados == []

    async def test_vacio_deja_pasar_a_todos(self, allowlist):
        """El default. Olvidar configurarlo no puede callar los avisos en
        producción."""
        allowlist("")
        provider = FakeProvider()

        await aviso.avisar_cambio_de_cita(
            provider, anterior="solicitada",
            cita=_cita("agendada", telefono="+50761112222"),
        )

        assert len(provider.enviados) == 1


class TestSolicitudSinClienteEnElCRM:
    """Una cita pedida por la web no tiene ficha: el teléfono está en la cita.

    Si el aviso solo mirara `customer`, ninguna solicitud de la agenda recibiría
    confirmación -- que es justamente el caso para el que existe.
    """

    def _solicitud(self, estado="agendada"):
        return {
            "id": "44444444-4444-4444-4444-444444444444",
            "status": estado,
            "scheduled_at": datetime(2026, 9, 15, 13, 0, tzinfo=timezone.utc),
            "customer": None,
            "solicitante_nombre": "Marta Rodríguez",
            "solicitante_telefono": "+50768510658",
        }

    async def test_le_llega_el_aviso(self):
        provider = FakeProvider()

        await aviso.avisar_cambio_de_cita(
            provider, anterior="solicitada", cita=self._solicitud()
        )

        assert len(provider.enviados) == 1

    async def test_va_al_telefono_que_dejo(self):
        provider = FakeProvider()

        await aviso.avisar_cambio_de_cita(
            provider, anterior="solicitada", cita=self._solicitud()
        )

        assert provider.enviados[0].phone == "+50768510658"

    async def test_la_saluda_por_el_nombre_que_escribio(self):
        provider = FakeProvider()

        await aviso.avisar_cambio_de_cita(
            provider, anterior="solicitada", cita=self._solicitud()
        )

        assert "Marta" in provider.enviados[0].body

    async def test_el_cliente_del_CRM_manda_cuando_existe(self):
        """Una cita creada en el panel sí tiene ficha; esa es la fuente."""
        provider = FakeProvider()
        cita = {**self._solicitud(),
                "customer": {"name": "Juan Pérez", "phone": "+50761112222"}}

        await aviso.avisar_cambio_de_cita(provider, anterior="solicitada", cita=cita)

        assert provider.enviados[0].phone == "+50761112222"


class TestElEstadoPuedeLlegarComoEnum:
    """El endpoint pasa `cita.model_dump()`, que deja `status` como CitaStatus,
    no como texto.

    Bug real de producción: `str(CitaStatus.agendada)` da "CitaStatus.agendada",
    la comparación con "agendada" fallaba, y el aviso se saltaba EN SILENCIO --
    confirmar una cita en el panel no le llegaba a nadie y no aparecía ningún
    error en los logs.

    Los tests no lo vieron porque pasaban el estado como string literal.
    """

    def _cita_real(self, estado=CitaStatus.agendada):
        """Un CitaRead volcado tal como lo hace el endpoint."""
        return CitaRead(
            id=uuid.uuid4(),
            organization_id=uuid.uuid4(),
            scheduled_at=datetime(2026, 9, 15, 13, 0, tzinfo=timezone.utc),
            status=estado,
            created_at=datetime(2026, 9, 8, tzinfo=timezone.utc),
            updated_at=datetime(2026, 9, 8, tzinfo=timezone.utc),
            solicitante_nombre="Diego Sastoque",
            solicitante_telefono="+50768510658",
        ).model_dump()

    async def test_aceptar_avisa_aunque_el_estado_sea_un_enum(self):
        provider = FakeProvider()

        await aviso.avisar_cambio_de_cita(
            provider, anterior="solicitada", cita=self._cita_real()
        )

        assert len(provider.enviados) == 1

    async def test_rechazar_tambien(self):
        provider = FakeProvider()

        await aviso.avisar_cambio_de_cita(
            provider, anterior="solicitada",
            cita=self._cita_real(CitaStatus.cancelada),
        )

        assert len(provider.enviados) == 1

    async def test_el_anterior_tambien_puede_ser_enum(self):
        """update_cita devuelve el estado previo desde la fila; según de dónde
        venga puede ser enum o texto."""
        provider = FakeProvider()

        await aviso.avisar_cambio_de_cita(
            provider, anterior=CitaStatus.solicitada, cita=self._cita_real()
        )

        assert len(provider.enviados) == 1


class TestAvisoAlReprogramar:
    """El taller mueve una cita ya aceptada y el cliente tiene que enterarse.

    Sin esto el cliente llega a la hora vieja, que es exactamente el fallo que
    la agenda vino a eliminar — solo que entrando por la otra puerta.
    """

    ANTES = datetime(2026, 9, 15, 13, 0, tzinfo=timezone.utc)   # 8:00 a.m. Panamá
    DESPUES = datetime(2026, 9, 16, 19, 0, tzinfo=timezone.utc)  # 2:00 p.m. Panamá

    def _movida(self, estado="agendada"):
        cita = _cita(estado=estado)
        cita["scheduled_at"] = self.DESPUES
        return cita

    async def test_mover_una_cita_agendada_avisa(self):
        provider = FakeProvider()

        await aviso.avisar_cambio_de_cita(
            provider,
            anterior="agendada",
            scheduled_at_anterior=self.ANTES,
            cita=self._movida(),
        )

        assert len(provider.enviados) == 1

    async def test_el_mensaje_lleva_las_dos_horas(self):
        provider = FakeProvider()

        await aviso.avisar_cambio_de_cita(
            provider,
            anterior="agendada",
            scheduled_at_anterior=self.ANTES,
            cita=self._movida(),
        )

        cuerpo = provider.enviados[0].body
        assert "miércoles 16 de septiembre" in cuerpo   # la nueva
        assert "martes 15 de septiembre" in cuerpo      # la anterior

    async def test_mover_una_confirmada_tambien_avisa(self):
        provider = FakeProvider()

        await aviso.avisar_cambio_de_cita(
            provider,
            anterior="confirmada",
            scheduled_at_anterior=self.ANTES,
            cita=self._movida(estado="confirmada"),
        )

        assert len(provider.enviados) == 1

    async def test_la_misma_hora_no_avisa_nada(self):
        provider = FakeProvider()
        cita = _cita(estado="agendada")
        cita["scheduled_at"] = self.ANTES

        await aviso.avisar_cambio_de_cita(
            provider,
            anterior="agendada",
            scheduled_at_anterior=self.ANTES,
            cita=cita,
        )

        assert provider.enviados == []

    async def test_mover_una_SOLICITADA_no_avisa(self):
        """Mover una solicitud es el taller proponiendo otra hora, y eso ya va
        con su propio flujo."""
        provider = FakeProvider()

        await aviso.avisar_cambio_de_cita(
            provider,
            anterior="solicitada",
            scheduled_at_anterior=self.ANTES,
            cita=self._movida(estado="solicitada"),
        )

        assert provider.enviados == []

    async def test_estado_y_hora_a_la_vez_mandan_UN_solo_mensaje(self):
        """Aceptar y mover en el mismo gesto es un caso real. Dos WhatsApps
        seguidos se ven descuidados: gana el aviso del estado."""
        provider = FakeProvider()

        await aviso.avisar_cambio_de_cita(
            provider,
            anterior="solicitada",
            scheduled_at_anterior=self.ANTES,
            cita=self._movida(estado="agendada"),
        )

        assert len(provider.enviados) == 1
        assert "confirmada" in provider.enviados[0].body

    async def test_sin_hora_anterior_no_avisa(self):
        """Un PATCH que no tocó la hora no manda `scheduled_at_anterior`."""
        provider = FakeProvider()

        await aviso.avisar_cambio_de_cita(
            provider, anterior="agendada", cita=self._movida()
        )

        assert provider.enviados == []

    async def test_la_hora_anterior_como_TEXTO_tambien_sirve(self):
        """PostgREST devuelve timestamptz como string. Comparar un string
        contra un datetime no falla: da "distinto" siempre, y mandaría un
        aviso en cada PATCH aunque nadie moviera nada."""
        provider = FakeProvider()
        cita = _cita(estado="agendada")
        cita["scheduled_at"] = self.ANTES

        await aviso.avisar_cambio_de_cita(
            provider,
            anterior="agendada",
            scheduled_at_anterior="2026-09-15T13:00:00+00:00",
            cita=cita,
        )

        assert provider.enviados == []

    async def test_una_cita_movida_sin_telefono_no_lanza(self):
        provider = FakeProvider()
        cita = self._movida()
        cita["customer"] = {}
        cita["solicitante_telefono"] = None

        await aviso.avisar_cambio_de_cita(
            provider,
            anterior="agendada",
            scheduled_at_anterior=self.ANTES,
            cita=cita,
        )

        assert provider.enviados == []
