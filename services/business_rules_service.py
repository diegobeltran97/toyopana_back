"""Settings use-cases for the business rules.

Thin on purpose: the shapes are validated by the schemas and the arithmetic
lives in services/business_rules.py. This only wires the two together and keeps
the endpoint from talking to a repository directly.
"""

import logging
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from repositories.business_rules import BusinessRulesRepository
from schemas.business_rules import (
    DiaEspecialCreate,
    HorarioSemanal,
    ServicioCreate,
    ServicioUpdate,
)

logger = logging.getLogger(__name__)

# Cuánto futuro trae la pantalla de ajustes al listar días especiales. Un año
# cubre la temporada de feriados sin traer historia que nadie va a mirar.
_HORIZONTE_DIAS = 365


async def leer_ajustes(organization_id: str) -> Dict[str, Any]:
    """Todo lo que la pantalla de ajustes necesita, en una sola lectura."""
    repo = BusinessRulesRepository()

    semana = await repo.semana(organization_id)
    # Con inactivos: un servicio apagado tiene que verse en ajustes o no
    # habría forma de reactivarlo. Todo lo demás pide solo los activos.
    servicios = await repo.servicios(organization_id, incluir_inactivos=True)

    hoy = date.today()
    excepciones = await repo.excepciones(
        organization_id, hoy, hoy + timedelta(days=_HORIZONTE_DIAS)
    )

    return {
        "horario": [
            {"weekday": dow, **fila} for dow, fila in sorted(semana.items())
        ],
        "servicios": servicios,
        "dias_especiales": [
            {"date": fecha, **fila} for fecha, fila in sorted(excepciones.items())
        ],
    }


async def guardar_horario(organization_id: str, horario: HorarioSemanal) -> None:
    """Guarda la semana. Las horas se serializan a texto para PostgREST."""
    dias: List[dict] = []
    for dia in horario.dias:
        fila = dia.model_dump()
        fila["opens_at"] = dia.opens_at.isoformat() if dia.opens_at else None
        fila["closes_at"] = dia.closes_at.isoformat() if dia.closes_at else None
        dias.append(fila)

    await BusinessRulesRepository().guardar_horario(organization_id, dias)


async def crear_servicio(organization_id: str, servicio: ServicioCreate) -> dict:
    """Alta de un tipo de servicio."""
    return await BusinessRulesRepository().crear_servicio(
        organization_id, servicio.model_dump()
    )


async def guardar_dia_especial(organization_id: str, dia: DiaEspecialCreate) -> None:
    """Alta o cambio de un feriado / horario especial."""
    fila = dia.model_dump()
    fila["date"] = dia.date.isoformat()
    fila["opens_at"] = dia.opens_at.isoformat() if dia.opens_at else None
    fila["closes_at"] = dia.closes_at.isoformat() if dia.closes_at else None

    await BusinessRulesRepository().guardar_dia_especial(organization_id, fila)


async def actualizar_servicio(
    organization_id: str, servicio_id: str, cambios: ServicioUpdate
) -> Optional[dict]:
    """Cambio parcial de un servicio. None si no existe en esta organización."""
    return await BusinessRulesRepository().actualizar_servicio(
        organization_id, servicio_id, cambios.model_dump(exclude_unset=True)
    )
