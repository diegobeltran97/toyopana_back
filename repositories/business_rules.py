"""Repository for the business rules tables, via PostgREST.

Reads `business_hours`, `business_calendar`, `service_types` and the accepted
citas that occupy a day, and hands them to services/business_rules.py — which
holds the logic and never touches I/O.

Two conversions live here and nowhere else, because both fail silently if they
are wrong:

  * PostgREST returns times as "08:00:00"; the rules module compares `time`
    objects. Comparing a string against a time does not raise, it just answers
    False and resolves the whole day wrong.
  * `scheduled_at` is a timestamptz. A cita at 13:00 UTC is 08:00 in Panama;
    handing the UTC hour to the block maths would place it five blocks late.

Uses the service_role key: these tables have RLS enabled with zero policies.
Mirrors MessageTemplateRepository's headers and error handling.
"""

import logging
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import httpx

from core.config import settings
from services.business_rules import BLOQUE_MINUTOS, PANAMA, a_hora_local

logger = logging.getLogger(__name__)

# Los únicos estados que ocupan un bloque. Una solicitud pendiente NO ocupa:
# si contara, cinco personas pidiendo las 10 a.m. dejarían el bloque en rojo
# sin que el taller hubiera aceptado ninguna.
ESTADOS_QUE_OCUPAN = ("agendada", "confirmada")


def _a_time(valor: Optional[str]) -> Optional[time]:
    """"08:00:00" -> time(8). None se queda en None (día cerrado)."""
    if valor is None:
        return None
    return time.fromisoformat(valor)


class BusinessRulesRepository:
    """Lectura de las reglas del negocio de una organización."""

    def __init__(self):
        self.base_url = f"{settings.SUPABASE_URL}/rest/v1"
        self.headers = {
            "apikey": settings.SUPABASE_SERVICE_ROLE_KEY,
            "Authorization": f"Bearer {settings.SUPABASE_SERVICE_ROLE_KEY}",
            "Content-Type": "application/json",
        }

    async def _get(self, tabla: str, params: Dict[str, Any]) -> List[dict]:
        async with httpx.AsyncClient(timeout=10.0) as http:
            response = await http.get(
                f"{self.base_url}/{tabla}", params=params, headers=self.headers
            )
        response.raise_for_status()
        return response.json()

    async def semana(self, organization_id: str) -> Dict[int, Dict[str, Any]]:
        """La plantilla semanal, indexada por día (0=domingo … 6=sábado)."""
        filas = await self._get(
            "business_hours",
            {
                "select": "weekday,is_open,opens_at,closes_at,max_citas,capacidad_simultanea",
                "organization_id": f"eq.{organization_id}",
            },
        )
        return {
            fila["weekday"]: {
                "is_open": fila["is_open"],
                "opens_at": _a_time(fila["opens_at"]),
                "closes_at": _a_time(fila["closes_at"]),
                "max_citas": fila["max_citas"],
                "capacidad_simultanea": fila["capacidad_simultanea"],
            }
            for fila in filas
        }

    async def excepciones(
        self, organization_id: str, desde: date, hasta: date
    ) -> Dict[date, Dict[str, Any]]:
        """Feriados y horarios especiales del rango, indexados por fecha."""
        filas = await self._get(
            "business_calendar",
            {
                "select": "date,is_open,opens_at,closes_at,max_citas,capacidad_simultanea,reason",
                "organization_id": f"eq.{organization_id}",
                "date": f"gte.{desde.isoformat()}",
                "and": f"(date.lte.{hasta.isoformat()})",
            },
        )
        return {
            date.fromisoformat(fila["date"]): {
                "is_open": fila["is_open"],
                "opens_at": _a_time(fila["opens_at"]),
                "closes_at": _a_time(fila["closes_at"]),
                "max_citas": fila["max_citas"],
                "capacidad_simultanea": fila["capacidad_simultanea"],
                "reason": fila["reason"],
            }
            for fila in filas
        }

    async def citas_que_ocupan(
        self, organization_id: str, dia: date
    ) -> List[Tuple[time, int]]:
        """Las citas aceptadas de un día, como (hora local de inicio, duración).

        El rango se calcula en hora de Panamá: el día local empieza a las 05:00
        UTC, así que filtrar por medianoche UTC se comería las citas de la
        mañana.
        """
        inicio = datetime.combine(dia, time.min, tzinfo=PANAMA)
        fin = datetime.combine(dia + timedelta(days=1), time.min, tzinfo=PANAMA)

        filas = await self._get(
            "citas",
            {
                "select": "scheduled_at,service_types(duration_minutes)",
                "organization_id": f"eq.{organization_id}",
                "status": f"in.({','.join(ESTADOS_QUE_OCUPAN)})",
                "scheduled_at": f"gte.{inicio.astimezone(timezone.utc).isoformat()}",
                "and": f"(scheduled_at.lt.{fin.astimezone(timezone.utc).isoformat()})",
            },
        )

        citas: List[Tuple[time, int]] = []
        for fila in filas:
            local = a_hora_local(datetime.fromisoformat(fila["scheduled_at"]))
            servicio = fila.get("service_types") or {}
            # service_type_id es nullable: sin servicio, ocupa el bloque mínimo.
            duracion = servicio.get("duration_minutes") or BLOQUE_MINUTOS
            citas.append((local.time(), duracion))
        return citas

    # ------------------------------------------------------------------
    # Escrituras (pantalla de ajustes)
    # ------------------------------------------------------------------

    async def guardar_horario(self, organization_id: str, dias: List[dict]) -> None:
        """Upsert de la semana completa.

        Upsert y no delete+insert: borrar primero deja al taller sin horario
        durante un instante, y si la escritura falla se queda sin ninguno --
        que resuelve CERRADO y le apaga la agenda.
        """
        filas = [{"organization_id": organization_id, **d} for d in dias]
        async with httpx.AsyncClient(timeout=10.0) as http:
            response = await http.post(
                f"{self.base_url}/business_hours",
                json=filas,
                headers={**self.headers,
                         "Prefer": "return=minimal,resolution=merge-duplicates"},
                params={"on_conflict": "organization_id,weekday"},
            )
        response.raise_for_status()

    async def crear_servicio(self, organization_id: str, datos: dict) -> dict:
        """Alta de un tipo de servicio."""
        async with httpx.AsyncClient(timeout=10.0) as http:
            response = await http.post(
                f"{self.base_url}/service_types",
                json={"organization_id": organization_id, **datos},
                headers={**self.headers, "Prefer": "return=representation"},
            )
        response.raise_for_status()
        filas = response.json()
        return filas[0] if filas else {}

    async def guardar_dia_especial(self, organization_id: str, datos: dict) -> None:
        """Upsert de una excepción por fecha (feriado, horario especial)."""
        async with httpx.AsyncClient(timeout=10.0) as http:
            response = await http.post(
                f"{self.base_url}/business_calendar",
                json={"organization_id": organization_id, **datos},
                headers={**self.headers,
                         "Prefer": "return=minimal,resolution=merge-duplicates"},
                params={"on_conflict": "organization_id,date"},
            )
        response.raise_for_status()

    async def servicios(self, organization_id: str) -> List[dict]:
        """El catálogo activo, en el orden en que debe mostrarse."""
        return await self._get(
            "service_types",
            {
                "select": "id,name,duration_minutes,sort_order",
                "organization_id": f"eq.{organization_id}",
                "active": "is.true",
                "order": "sort_order.asc,name.asc",
            },
        )
