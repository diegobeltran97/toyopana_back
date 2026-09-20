"""Tests for services/business_rules.py -- resolving a day and its hour blocks.

Pure functions: no database, no clock. The repository hands them plain data and
they answer "is this day open, until when, and which hours are still free".

This is the layer the appointment agenda reads to decide what a customer may
even see, so its failure mode is not an error message -- it is a customer
booking an hour the shop cannot honour, or a shop looking full when it is not.
"""

from datetime import date, datetime, time, timezone

import pytest

from services.business_rules import (
    PANAMA,
    Bloque,
    DiaHabil,
    a_hora_local,
    bloques_del_dia,
    bloques_que_ocupa,
    cabe_antes_del_cierre,
    feriados_de_panama,
    ocupacion_de_citas,
    resolver_dia,
    texto_de_horario,
)

# La semana real de Suspensiones Toyopana, sembrada por la migración 005.
SEMANA = {
    0: {"is_open": False},
    1: {"is_open": True, "opens_at": time(8), "closes_at": time(17)},
    2: {"is_open": True, "opens_at": time(8), "closes_at": time(17)},
    3: {"is_open": True, "opens_at": time(8), "closes_at": time(17)},
    4: {"is_open": True, "opens_at": time(8), "closes_at": time(17)},
    5: {"is_open": True, "opens_at": time(8), "closes_at": time(17)},
    6: {"is_open": True, "opens_at": time(8), "closes_at": time(15)},
}

DOMINGO = date(2026, 9, 13)
MARTES = date(2026, 9, 15)
SABADO = date(2026, 9, 19)


class TestResolverDia:
    def test_el_domingo_esta_cerrado(self):
        assert resolver_dia(DOMINGO, SEMANA).abierto is False

    def test_un_martes_abre_de_ocho_a_cinco(self):
        dia = resolver_dia(MARTES, SEMANA)

        assert (dia.abierto, dia.abre, dia.cierra) == (True, time(8), time(17))

    def test_el_sabado_cierra_mas_temprano(self):
        assert resolver_dia(SABADO, SEMANA).cierra == time(15)

    def test_sin_configuracion_el_dia_esta_CERRADO(self):
        """Falla cerrado. Una organización recién creada no puede empezar a
        aceptar citas a cualquier hora porque nadie configuró su horario."""
        assert resolver_dia(MARTES, {}).abierto is False


class TestExcepcionesPorFecha:
    def test_un_feriado_cierra_un_dia_normalmente_abierto(self):
        excepciones = {MARTES: {"is_open": False, "reason": "Día de los Mártires"}}

        assert resolver_dia(MARTES, SEMANA, excepciones).abierto is False

    def test_una_excepcion_puede_abrir_un_domingo(self):
        excepciones = {
            DOMINGO: {"is_open": True, "opens_at": time(9), "closes_at": time(13)}
        }

        dia = resolver_dia(DOMINGO, SEMANA, excepciones)

        assert (dia.abierto, dia.abre, dia.cierra) == (True, time(9), time(13))

    def test_la_excepcion_hereda_la_capacidad_cuando_no_la_trae(self):
        """NULL en la excepción significa "como siempre", no "sin capacidad"."""
        semana = {**SEMANA, 2: {**SEMANA[2], "capacidad_simultanea": 3}}
        excepciones = {MARTES: {"is_open": True, "opens_at": time(8), "closes_at": time(12)}}

        assert resolver_dia(MARTES, semana, excepciones).capacidad_simultanea == 3

    def test_la_excepcion_puede_pisar_la_capacidad(self):
        semana = {**SEMANA, 2: {**SEMANA[2], "capacidad_simultanea": 3}}
        excepciones = {
            MARTES: {
                "is_open": True,
                "opens_at": time(8),
                "closes_at": time(12),
                "capacidad_simultanea": 1,
            }
        }

        assert resolver_dia(MARTES, semana, excepciones).capacidad_simultanea == 1


class TestCabeAntesDelCierre:
    """La única cosa para la que se usa la duración del servicio. Evita la cita
    que cabe según el horario pero que el taller no alcanza a terminar."""

    def _martes(self):
        return resolver_dia(MARTES, SEMANA)

    def test_dos_horas_a_las_cuatro_y_media_no_alcanzan(self):
        assert cabe_antes_del_cierre(self._martes(), time(16, 30), 120) is False

    def test_dos_horas_a_las_dos_si_alcanzan(self):
        assert cabe_antes_del_cierre(self._martes(), time(14), 120) is True

    def test_una_hora_que_termina_justo_al_cierre_cabe(self):
        """Terminar a las 17:00 en punto es válido: el taller cierra a esa hora,
        no antes."""
        assert cabe_antes_del_cierre(self._martes(), time(16), 60) is True

    def test_empezar_antes_de_abrir_no_vale(self):
        assert cabe_antes_del_cierre(self._martes(), time(7), 60) is False

    def test_en_un_dia_cerrado_nunca_cabe(self):
        assert cabe_antes_del_cierre(resolver_dia(DOMINGO, SEMANA), time(10), 60) is False


class TestZonaHoraria:
    """Validar en UTC rechazaría las citas de la mañana: el lunes 8:30 a.m. en
    Panamá es 13:30 UTC."""

    def test_una_hora_utc_se_convierte_a_hora_de_panama(self):
        utc = datetime(2026, 9, 15, 13, 30, tzinfo=timezone.utc)

        local = a_hora_local(utc)

        assert (local.hour, local.minute) == (8, 30)

    def test_esa_misma_hora_cae_dentro_del_horario_de_atencion(self):
        utc = datetime(2026, 9, 15, 13, 30, tzinfo=timezone.utc)
        local = a_hora_local(utc)

        dia = resolver_dia(local.date(), SEMANA)

        assert cabe_antes_del_cierre(dia, local.time(), 60) is True

    def test_un_datetime_sin_zona_se_rechaza(self):
        """Un datetime ingenuo es una ambigüedad de cinco horas. Fallar es mejor
        que adivinar la zona."""
        with pytest.raises(ValueError):
            a_hora_local(datetime(2026, 9, 15, 13, 30))


class TestBloquesQueOcupa:
    def test_una_cita_de_una_hora_ocupa_un_bloque(self):
        assert bloques_que_ocupa(time(10), 60) == [time(10)]

    def test_una_cita_de_dos_horas_ocupa_dos_bloques(self):
        assert bloques_que_ocupa(time(10), 120) == [time(10), time(11)]

    def test_una_duracion_que_no_es_multiplo_redondea_hacia_arriba(self):
        """90 minutos ocupan dos bloques: el taller no puede alquilar la media
        hora sobrante a otro carro."""
        assert bloques_que_ocupa(time(10), 90) == [time(10), time(11)]


class TestBloquesDelDia:
    def _martes(self, **extra):
        base = resolver_dia(MARTES, SEMANA)
        return DiaHabil(**{**base.__dict__, **extra})

    def test_un_dia_de_ocho_a_cinco_da_nueve_bloques(self):
        assert len(bloques_del_dia(self._martes())) == 9

    def test_el_sabado_da_siete(self):
        assert len(bloques_del_dia(resolver_dia(SABADO, SEMANA))) == 7

    def test_un_dia_cerrado_no_da_ninguno(self):
        assert bloques_del_dia(resolver_dia(DOMINGO, SEMANA)) == []

    def test_los_bloques_empiezan_a_la_hora_de_apertura(self):
        assert bloques_del_dia(self._martes())[0].hora == time(8)

    def test_el_ultimo_bloque_empieza_una_hora_antes_del_cierre(self):
        assert bloques_del_dia(self._martes())[-1].hora == time(16)

    def test_con_capacidad_uno_una_cita_ocupa_su_bloque(self):
        bloques = bloques_del_dia(self._martes(), ocupacion={time(10): 1})

        assert next(b for b in bloques if b.hora == time(10)).libre is False

    def test_los_demas_bloques_siguen_libres(self):
        bloques = bloques_del_dia(self._martes(), ocupacion={time(10): 1})

        assert next(b for b in bloques if b.hora == time(11)).libre is True

    def test_con_capacidad_dos_una_sola_cita_no_llena_el_bloque(self):
        bloques = bloques_del_dia(
            self._martes(capacidad_simultanea=2), ocupacion={time(10): 1}
        )

        assert next(b for b in bloques if b.hora == time(10)).libre is True

    def test_con_capacidad_dos_dos_citas_si_lo_llenan(self):
        bloques = bloques_del_dia(
            self._martes(capacidad_simultanea=2), ocupacion={time(10): 2}
        )

        assert next(b for b in bloques if b.hora == time(10)).libre is False

    def test_alcanzar_el_tope_del_dia_cierra_todos_los_bloques(self):
        """El tope diario y la capacidad por hora son límites distintos:
        se puede llegar al tope del día con horas todavía libres."""
        bloques = bloques_del_dia(self._martes(max_citas=4), citas_aceptadas=4)

        assert all(not b.libre for b in bloques)

    def test_por_debajo_del_tope_los_bloques_siguen_libres(self):
        bloques = bloques_del_dia(self._martes(max_citas=4), citas_aceptadas=3)

        assert all(b.libre for b in bloques)

    def test_sin_tope_diario_el_conteo_de_citas_no_cierra_nada(self):
        bloques = bloques_del_dia(self._martes(), citas_aceptadas=99)

        assert all(b.libre for b in bloques)


class TestOcupacionDeCitas:
    """Cuántos carros hay en cada bloque, a partir de las citas del día.

    Puro a propósito: el repositorio trae las filas, esto las cuenta. Contar mal
    aquí no lanza ningún error — solo hace que el taller se vea lleno cuando no
    lo está, o al revés.
    """

    def test_sin_citas_no_hay_ocupacion(self):
        assert ocupacion_de_citas([]) == {}

    def test_una_cita_de_una_hora_ocupa_su_bloque(self):
        assert ocupacion_de_citas([(time(10), 60)]) == {time(10): 1}

    def test_una_cita_de_dos_horas_ocupa_dos_bloques(self):
        assert ocupacion_de_citas([(time(10), 120)]) == {time(10): 1, time(11): 1}

    def test_dos_citas_a_la_misma_hora_se_suman(self):
        assert ocupacion_de_citas([(time(10), 60), (time(10), 60)]) == {time(10): 2}

    def test_citas_que_se_solapan_parcialmente_se_suman_donde_coinciden(self):
        """Una de 8 a 10 y otra de 9 a 10: a las 9 hay dos carros."""
        ocupacion = ocupacion_de_citas([(time(8), 120), (time(9), 60)])

        assert ocupacion == {time(8): 1, time(9): 2}


class TestTextoDeHorario:
    """El horario que el bot le dice al cliente, generado desde la tabla.

    Existe para cerrar un riesgo concreto: hasta ahora el horario estaba
    quemado en el nodo `menu_horarios` Y se iba a validar contra la tabla. Dos
    fuentes para el mismo dato es una que se queda vieja — el taller cambia su
    sábado en ajustes y el bot sigue diciendo la hora anterior.
    """

    def test_agrupa_los_dias_seguidos_con_el_mismo_horario(self):
        texto = texto_de_horario(SEMANA)

        assert "Lunes a viernes: 8:00 a.m. – 5:00 p.m." in texto

    def test_un_dia_suelto_se_nombra_en_plural(self):
        texto = texto_de_horario(SEMANA)

        assert "Sábados: 8:00 a.m. – 3:00 p.m." in texto

    def test_los_dias_cerrados_tambien_se_dicen(self):
        """Callar el domingo deja al cliente sin saber si puede ir."""
        assert "Domingos: cerrado" in texto_de_horario(SEMANA)

    def test_la_semana_empieza_en_lunes_aunque_la_tabla_empiece_en_domingo(self):
        texto = texto_de_horario(SEMANA)

        assert texto.index("Lunes") < texto.index("Domingos")

    def test_una_semana_toda_igual_se_dice_en_una_linea(self):
        semana = {d: {"is_open": True, "opens_at": time(9), "closes_at": time(18)} for d in range(7)}

        assert texto_de_horario(semana).count("\n") == 0

    def test_cambiar_el_sabado_cambia_el_texto(self):
        """La prueba de que el dato manda: si el taller mueve su sábado en
        ajustes, el bot lo dice distinto sin tocar código."""
        semana = {**SEMANA, 6: {"is_open": True, "opens_at": time(8), "closes_at": time(13)}}

        assert "Sábados: 8:00 a.m. – 1:00 p.m." in texto_de_horario(semana)

    def test_sin_configuracion_no_inventa_un_horario(self):
        """Devolver "" deja que el llamador decida qué decir. Inventarse
        "Lunes a domingo: cerrado" sería afirmar algo que nadie configuró."""
        assert texto_de_horario({}) == ""

    def test_el_mediodia_se_escribe_bien(self):
        semana = {1: {"is_open": True, "opens_at": time(12), "closes_at": time(13)}}

        assert "12:00 p.m. – 1:00 p.m." in texto_de_horario(semana)


class TestFeriadosDePanama:
    """El calendario que carga la pantalla de ajustes de una vez.

    Las fechas móviles son el punto: Carnaval y Viernes Santo dependen de la
    Pascua, así que una lista quemada queda vieja el año siguiente sin que
    nadie lo note hasta que el taller abre un lunes de Carnaval.
    """

    def test_el_ano_trae_los_catorce_feriados(self):
        assert len(feriados_de_panama(2026)) == 14

    def test_los_fijos_caen_donde_deben(self):
        fechas = dict(feriados_de_panama(2026))

        assert fechas[date(2026, 1, 1)] == "Año Nuevo"
        assert fechas[date(2026, 1, 9)] == "Día de los Mártires"
        assert fechas[date(2026, 12, 25)] == "Navidad"

    def test_carnaval_y_viernes_santo_se_mueven_con_la_pascua(self):
        """2026: Pascua el 5 de abril. 2027: el 28 de marzo."""
        fechas_2026 = dict(feriados_de_panama(2026))
        fechas_2027 = dict(feriados_de_panama(2027))

        assert fechas_2026[date(2026, 2, 16)] == "Lunes de Carnaval"
        assert fechas_2026[date(2026, 2, 17)] == "Martes de Carnaval"
        assert fechas_2026[date(2026, 4, 3)] == "Viernes Santo"

        assert fechas_2027[date(2027, 2, 8)] == "Lunes de Carnaval"
        assert fechas_2027[date(2027, 2, 9)] == "Martes de Carnaval"
        assert fechas_2027[date(2027, 3, 26)] == "Viernes Santo"

    def test_viene_ordenada_por_fecha(self):
        """La pantalla la muestra tal cual; ordenarla en el front sería otra
        copia de la misma decisión."""
        feriados = feriados_de_panama(2026)

        assert feriados == sorted(feriados)

    def test_ninguna_fecha_se_repite(self):
        """Dos motivos en la misma fecha reventarían el UNIQUE
        (organization_id, date) de business_calendar al cargarlos."""
        feriados = feriados_de_panama(2026)

        assert len({fecha for fecha, _ in feriados}) == len(feriados)
