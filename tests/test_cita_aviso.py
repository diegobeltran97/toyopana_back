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

import services.cita_aviso as aviso
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

        await aviso.avisar_cambio_de_estado(
            provider, anterior="solicitada", cita=_cita("agendada")
        )

        assert len(provider.enviados) == 1

    async def test_rechazar_una_solicitud_tambien_avisa(self):
        provider = FakeProvider()

        await aviso.avisar_cambio_de_estado(
            provider, anterior="solicitada", cita=_cita("cancelada")
        )

        assert len(provider.enviados) == 1

    async def test_no_se_avisa_un_cambio_entre_estados_internos(self):
        """agendada -> confirmada es trabajo interno del taller. El cliente no
        pidió saber cada movimiento de la agenda."""
        provider = FakeProvider()

        await aviso.avisar_cambio_de_estado(
            provider, anterior="agendada", cita=_cita("confirmada")
        )

        assert provider.enviados == []

    async def test_no_se_avisa_si_el_estado_no_cambio(self):
        provider = FakeProvider()

        await aviso.avisar_cambio_de_estado(
            provider, anterior="solicitada", cita=_cita("solicitada")
        )

        assert provider.enviados == []


class TestQueDiceElMensaje:
    async def _texto(self, estado):
        provider = FakeProvider()
        await aviso.avisar_cambio_de_estado(
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

        await aviso.avisar_cambio_de_estado(
            provider, anterior="solicitada", cita=_cita("agendada")
        )

    async def test_una_excepcion_del_proveedor_no_lanza(self):
        class Explota:
            async def send_text(self, msg):
                raise RuntimeError("whapi caída")

        await aviso.avisar_cambio_de_estado(
            Explota(), anterior="solicitada", cita=_cita("agendada")
        )

    async def test_una_cita_sin_telefono_no_lanza(self):
        """El cliente puede no tener teléfono cargado; no hay a dónde avisar."""
        provider = FakeProvider()

        await aviso.avisar_cambio_de_estado(
            provider, anterior="solicitada", cita=_cita("agendada", telefono=None)
        )

        assert provider.enviados == []

    async def test_una_cita_sin_cliente_no_lanza(self):
        provider = FakeProvider()
        cita = {**_cita("agendada")}
        del cita["customer"]

        await aviso.avisar_cambio_de_estado(provider, anterior="solicitada", cita=cita)

        assert provider.enviados == []
