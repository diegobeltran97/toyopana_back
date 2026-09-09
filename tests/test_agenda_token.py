"""Tests for services/agenda_token.py -- the signed link to the booking page.

THE TEST THAT PROTECTS THE BUSINESS. The agenda is the first page of this
application with no login, so this token is the whole access-control story: it
says which organization and which customer, and a caller who can forge one or
swap its fields is booking in someone else's shop.

Pure crypto, no I/O.
"""

import time as time_module

import pytest

from services.agenda_token import (
    TokenInvalido,
    TokenVencido,
    crear_token,
    leer_token,
)

SECRETO = "un-secreto-largo-de-prueba"
OTRO_SECRETO = "otro-secreto-distinto"
ORG = "11111111-1111-1111-1111-111111111111"


class TestIdaYVuelta:
    def test_un_token_valido_devuelve_lo_que_se_guardo(self):
        token = crear_token(ORG, secreto=SECRETO)

        datos = leer_token(token, secreto=SECRETO)

        assert datos.organization_id == ORG

    def test_el_token_es_seguro_en_una_url(self):
        """Va pegado al final de un link que se manda por WhatsApp: un '/' o un
        '+' partirían la ruta."""
        token = crear_token(ORG, secreto=SECRETO)

        assert not set("/+= ") & set(token)

    def test_dos_tokens_de_la_misma_organizacion_no_son_iguales(self):
        """Llevan su propio vencimiento, así que reusar un link viejo no sirve
        para adivinar el nuevo."""
        a = crear_token(ORG, secreto=SECRETO, ttl_horas=48)
        b = crear_token(ORG, secreto=SECRETO, ttl_horas=24)

        assert a != b


class TestFalsificacion:
    def test_un_token_alterado_se_rechaza(self):
        token = crear_token(ORG, secreto=SECRETO)
        alterado = token[:-1] + ("a" if token[-1] != "a" else "b")

        with pytest.raises(TokenInvalido):
            leer_token(alterado, secreto=SECRETO)

    def test_un_token_firmado_con_otro_secreto_se_rechaza(self):
        token = crear_token(ORG, secreto=OTRO_SECRETO)

        with pytest.raises(TokenInvalido):
            leer_token(token, secreto=SECRETO)

    def test_no_se_puede_cambiar_la_organizacion_sin_romper_la_firma(self):
        """El ataque que importa: reusar un link propio apuntando al taller de
        otro. La firma cubre el organization_id, así que cambiarlo lo invalida."""
        propio = leer_token(crear_token(ORG, secreto=SECRETO), secreto=SECRETO)
        falsificado = crear_token("99999999-9999-9999-9999-999999999999",
                                  secreto=OTRO_SECRETO)

        with pytest.raises(TokenInvalido):
            leer_token(falsificado, secreto=SECRETO)
        assert propio.organization_id == ORG

    def test_basura_se_rechaza_sin_explotar(self):
        for basura in ("", "abc", "....", "a.b.c"):
            with pytest.raises(TokenInvalido):
                leer_token(basura, secreto=SECRETO)

    def test_un_secreto_vacio_no_permite_firmar(self):
        """Falla cerrado: un .env incompleto no puede volverse "sin firma"."""
        with pytest.raises(ValueError):
            crear_token(ORG, secreto="")


class TestVencimiento:
    def test_un_token_vencido_se_rechaza(self):
        token = crear_token(ORG, secreto=SECRETO, ttl_horas=-1)

        with pytest.raises(TokenVencido):
            leer_token(token, secreto=SECRETO)

    def test_un_token_recien_creado_sirve(self):
        token = crear_token(ORG, secreto=SECRETO, ttl_horas=48)

        assert leer_token(token, secreto=SECRETO).organization_id == ORG

    def test_el_vencimiento_viaja_dentro_del_token(self):
        token = crear_token(ORG, secreto=SECRETO, ttl_horas=48)

        datos = leer_token(token, secreto=SECRETO)

        faltan = datos.expira_en - int(time_module.time())
        assert 47 * 3600 < faltan <= 48 * 3600
