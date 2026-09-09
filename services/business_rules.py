"""Resolving a business day and its hour blocks. Pure -- no I/O, no clock.

The repository reads `business_hours`, `business_calendar` and `service_types`
and hands the rows here as plain data; this module answers the only three
questions the appointment agenda needs:

  * is this date open, and until when?          -> resolver_dia
  * does a service of N minutes fit before close? -> cabe_antes_del_cierre
  * which hours are still free?                  -> bloques_del_dia

Keeping it free of I/O is what makes it cheap to test, and this is the layer
whose bugs are expensive: they do not raise, they let a customer book an hour
the shop cannot honour, or make a shop look full when it is not.

Spec: docs/superpowers/specs/2026-09-03-reglas-del-negocio-design.md
"""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from math import ceil
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple
from zoneinfo import ZoneInfo

# Toda regla de horario se evalúa en hora local del taller. Validar en UTC
# rechazaría las citas de la mañana: el lunes 8:30 a.m. en Panamá es 13:30 UTC.
PANAMA = ZoneInfo("America/Panama")

# La agenda se reparte en bloques de este tamaño. Una cita dura mínimo una hora
# (regla del negocio), así que el bloque y el mínimo coinciden.
BLOQUE_MINUTOS = 60


@dataclass(frozen=True)
class DiaHabil:
    """Cómo queda un día concreto después de aplicar plantilla y excepciones."""

    abierto: bool
    abre: Optional[time] = None
    cierra: Optional[time] = None
    max_citas: Optional[int] = None          # tope del día; None = sin tope
    capacidad_simultanea: int = 1            # cuántos carros a la misma hora


@dataclass(frozen=True)
class Bloque:
    """Una hora de la agenda, y si se puede reservar."""

    hora: time
    libre: bool


def a_hora_local(momento: datetime) -> datetime:
    """Pasa un datetime con zona a hora local del taller.

    Rechaza los ingenuos a propósito: un datetime sin zona es una ambigüedad de
    cinco horas, y adivinar produce citas con la hora corrida sin que nada
    falle visiblemente.
    """
    if momento.tzinfo is None:
        raise ValueError("Se requiere un datetime con zona horaria, no uno ingenuo")
    return momento.astimezone(PANAMA)


def resolver_dia(
    fecha: date,
    semana: Mapping[int, Mapping[str, Any]],
    excepciones: Optional[Mapping[date, Mapping[str, Any]]] = None,
) -> DiaHabil:
    """Resuelve un día concreto, en orden estricto:

        1. ¿Hay excepción para esa fecha? -> esa manda
        2. ¿No? -> la plantilla de ese día de la semana
        3. ¿Tampoco? -> CERRADO

    El paso 3 es deliberado: sin configuración, cerrado. Una organización recién
    creada no debe empezar a aceptar citas a cualquier hora.
    """
    # date.weekday() da 0=lunes; la tabla usa 0=domingo como extract(dow).
    dow = (fecha.weekday() + 1) % 7

    plantilla = semana.get(dow)
    excepcion = (excepciones or {}).get(fecha)

    fuente = excepcion if excepcion is not None else plantilla
    if fuente is None or not fuente.get("is_open"):
        return DiaHabil(abierto=False)

    # Una excepción sin capacidad hereda la de la plantilla: NULL significa
    # "como siempre", no "sin capacidad".
    capacidad = fuente.get("capacidad_simultanea")
    if capacidad is None and plantilla is not None:
        capacidad = plantilla.get("capacidad_simultanea")

    max_citas = fuente.get("max_citas")
    if max_citas is None and excepcion is not None and plantilla is not None:
        max_citas = plantilla.get("max_citas")

    return DiaHabil(
        abierto=True,
        abre=fuente.get("opens_at"),
        cierra=fuente.get("closes_at"),
        max_citas=max_citas,
        capacidad_simultanea=capacidad if capacidad is not None else 1,
    )


def _mas_minutos(hora: time, minutos: int) -> datetime:
    """Suma minutos a una hora del día, sobre una fecha cualquiera.

    time no soporta aritmética; combinar con una fecha fija es la forma directa
    de sumar sin arrastrar zona horaria a un cálculo que no la necesita.
    """
    return datetime.combine(date(2000, 1, 1), hora) + timedelta(minutes=minutos)


def cabe_antes_del_cierre(dia: DiaHabil, inicio: time, duracion_minutos: int) -> bool:
    """¿Un servicio que empieza a esa hora termina antes de cerrar?

    Es el único uso que se le da a la duración del servicio, y donde está su
    valor: evita la cita que cabe según el horario pero que el taller no
    alcanza a terminar.

    Terminar justo a la hora de cierre vale: el taller cierra a esa hora, no
    antes.
    """
    if not dia.abierto or dia.abre is None or dia.cierra is None:
        return False
    if inicio < dia.abre:
        return False

    return _mas_minutos(inicio, duracion_minutos) <= _mas_minutos(dia.cierra, 0)


def bloques_que_ocupa(inicio: time, duracion_minutos: int) -> List[time]:
    """Qué bloques de una hora consume una cita.

    Redondea hacia arriba: una cita de 90 minutos ocupa dos bloques, porque el
    taller no puede alquilarle la media hora sobrante a otro carro.
    """
    cuantos = max(1, ceil(duracion_minutos / BLOQUE_MINUTOS))
    return [
        _mas_minutos(inicio, i * BLOQUE_MINUTOS).time() for i in range(cuantos)
    ]


# Nombres en el orden en que la gente lee una semana. La tabla usa 0=domingo
# (para coincidir con extract(dow)), pero un horario que empieza en domingo se
# lee raro, así que aquí se recorre de lunes a domingo.
_DIAS = {
    1: ("Lunes", "Lunes"),
    2: ("Martes", "Martes"),
    3: ("Miércoles", "Miércoles"),
    4: ("Jueves", "Jueves"),
    5: ("Viernes", "Viernes"),
    6: ("Sábado", "Sábados"),
    0: ("Domingo", "Domingos"),
}
_ORDEN_LECTURA = [1, 2, 3, 4, 5, 6, 0]


def _hora_legible(t: time) -> str:
    """time(17) -> "5:00 p.m.". Formato panameño, no 24 horas."""
    sufijo = "a.m." if t.hour < 12 else "p.m."
    hora12 = t.hour % 12 or 12
    return f"{hora12}:{t.minute:02d} {sufijo}"


def texto_de_horario(semana: Mapping[int, Mapping[str, Any]]) -> str:
    """El horario de atención, en texto, para decírselo a un cliente.

    Existe para que el horario tenga UNA sola fuente. Antes vivía quemado en el
    nodo `menu_horarios` del bot y además en esta tabla; dos copias del mismo
    dato es una que se queda vieja — el taller mueve su sábado en ajustes, el
    bot sigue diciendo la hora anterior, y alguien llega a un local cerrado.

    Agrupa los días seguidos que comparten horario, porque cinco líneas
    idénticas se leen peor que "Lunes a viernes".

    Devuelve "" cuando no hay nada configurado: inventar "cerrado toda la
    semana" sería afirmar algo que nadie dijo, y el llamador sabe mejor qué
    responder en ese caso.
    """
    if not semana:
        return ""

    def descripcion(dow: int) -> Optional[str]:
        """El horario de un día, o None si no está configurado."""
        fila = semana.get(dow)
        if fila is None:
            return None
        if not fila.get("is_open"):
            return "cerrado"
        abre, cierra = fila.get("opens_at"), fila.get("closes_at")
        if abre is None or cierra is None:
            return None
        return f"{_hora_legible(abre)} – {_hora_legible(cierra)}"

    # Agrupar corridas de días consecutivos con el mismo horario.
    lineas: List[str] = []
    grupo: List[int] = []

    def cerrar_grupo() -> None:
        if not grupo:
            return
        horario = descripcion(grupo[0])
        if len(grupo) == 1:
            etiqueta = _DIAS[grupo[0]][1]          # "Sábados"
        else:
            etiqueta = f"{_DIAS[grupo[0]][0]} a {_DIAS[grupo[-1]][0].lower()}"
        lineas.append(f"{etiqueta}: {horario}")
        grupo.clear()

    for dow in _ORDEN_LECTURA:
        actual = descripcion(dow)
        if actual is None:
            cerrar_grupo()
            continue
        if grupo and descripcion(grupo[-1]) == actual:
            grupo.append(dow)
        else:
            cerrar_grupo()
            grupo.append(dow)
    cerrar_grupo()

    return "\n".join(lineas)


def ocupacion_de_citas(
    citas: Iterable[Tuple[time, int]],
) -> Dict[time, int]:
    """Cuántos carros hay en cada bloque, a partir de las citas aceptadas.

    Cada cita es `(hora de inicio, duración en minutos)`. Una de dos horas
    cuenta en los dos bloques que ocupa, así que dos citas que se solapan
    parcialmente suman solo donde coinciden.

    Solo deben entrar citas ACEPTADAS (agendada + confirmada). Las solicitudes
    pendientes no ocupan: si contaran, cinco personas pidiendo las 10 a.m.
    dejarían el bloque en rojo sin que el taller aceptara ninguna.
    """
    ocupacion: Dict[time, int] = {}
    for inicio, duracion in citas:
        for bloque in bloques_que_ocupa(inicio, duracion):
            ocupacion[bloque] = ocupacion.get(bloque, 0) + 1
    return ocupacion


def bloques_del_dia(
    dia: DiaHabil,
    ocupacion: Optional[Mapping[time, int]] = None,
    citas_aceptadas: int = 0,
) -> List[Bloque]:
    """Los bloques de una hora del día, marcando cuáles se pueden reservar.

    Un bloque está libre si hay capacidad en esa hora Y el día no llegó a su
    tope. Son dos límites distintos: se puede llegar al tope del día con horas
    todavía vacías.

    `ocupacion` cuenta solo citas ACEPTADAS (agendada + confirmada). Las
    solicitudes pendientes no ocupan, o cinco personas pidiendo las 10 a.m.
    dejarían el bloque en rojo sin que el taller aceptara ninguna.
    """
    if not dia.abierto or dia.abre is None or dia.cierra is None:
        return []

    ocupacion = ocupacion or {}
    dia_lleno = dia.max_citas is not None and citas_aceptadas >= dia.max_citas

    bloques: List[Bloque] = []
    cursor = _mas_minutos(dia.abre, 0)
    fin = _mas_minutos(dia.cierra, 0)

    # El último bloque debe caber entero antes del cierre, de ahí el <=.
    while _mas_minutos(cursor.time(), BLOQUE_MINUTOS) <= fin:
        hora = cursor.time()
        hay_cupo = ocupacion.get(hora, 0) < dia.capacidad_simultanea
        bloques.append(Bloque(hora=hora, libre=hay_cupo and not dia_lleno))
        cursor = _mas_minutos(hora, BLOQUE_MINUTOS)

    return bloques
