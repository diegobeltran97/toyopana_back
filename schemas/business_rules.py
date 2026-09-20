"""Pydantic models for the business rules settings.

These mirror the CHECK constraints of migration 005 on purpose: the database is
the last line of defence, but a shop owner typing "closes at 8, opens at 5"
deserves a readable message, not a Postgres constraint error.
"""

from datetime import date, time
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator


class DiaHorario(BaseModel):
    """El horario de un día de la semana."""

    weekday: int = Field(..., ge=0, le=6, description="0=domingo … 6=sábado")
    is_open: bool = True
    opens_at: Optional[time] = None
    closes_at: Optional[time] = None
    max_citas: Optional[int] = Field(
        None, gt=0, description="Cuántos carros al día. Vacío = sin tope"
    )
    capacidad_simultanea: int = Field(
        1, gt=0, description="Cuántos carros a la misma hora"
    )

    @model_validator(mode="after")
    def _horas_coherentes(self) -> "DiaHorario":
        """Un día abierto necesita ambas horas, y cerrar después de abrir.

        Sin esto el bot no sabría qué validar y dejaría pasar cualquier hora.
        """
        if not self.is_open:
            return self
        if self.opens_at is None or self.closes_at is None:
            raise ValueError("Un día abierto necesita hora de apertura y de cierre")
        if self.opens_at >= self.closes_at:
            raise ValueError("La hora de cierre debe ser posterior a la de apertura")
        return self


class HorarioSemanal(BaseModel):
    """La semana completa, tal como la guarda la pantalla de ajustes."""

    dias: List[DiaHorario] = Field(..., min_length=1, max_length=7)

    @field_validator("dias")
    @classmethod
    def _sin_dias_repetidos(cls, dias: List[DiaHorario]) -> List[DiaHorario]:
        vistos = [d.weekday for d in dias]
        if len(vistos) != len(set(vistos)):
            raise ValueError("Hay días de la semana repetidos")
        return dias


class ServicioCreate(BaseModel):
    """Alta de un tipo de servicio."""

    name: str = Field(..., min_length=1, max_length=120)
    # Piso de 60: una cita dura mínimo una hora. Es regla del negocio.
    duration_minutes: int = Field(60, ge=60, le=600)
    active: bool = True
    sort_order: int = Field(0, ge=0)

    @field_validator("name")
    @classmethod
    def _nombre_con_contenido(cls, v: str) -> str:
        limpio = v.strip()
        if not limpio:
            raise ValueError("El nombre no puede estar vacío")
        return limpio


class ServicioRead(ServicioCreate):
    id: UUID


class ServicioUpdate(BaseModel):
    """Cambio parcial de un servicio: solo llegan los campos que se tocaron.

    Parcial y no completo porque la pantalla edita una celda a la vez;
    mandar el objeto entero haría que dos personas editando a la vez se
    pisaran campos que ninguna tocó.
    """

    name: Optional[str] = Field(None, min_length=1, max_length=120)
    duration_minutes: Optional[int] = Field(None, ge=60, le=600)
    active: Optional[bool] = None
    sort_order: Optional[int] = Field(None, ge=0)

    @field_validator("name")
    @classmethod
    def _nombre_con_contenido(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        limpio = v.strip()
        if not limpio:
            raise ValueError("El nombre no puede estar vacío")
        return limpio

    @model_validator(mode="after")
    def _algo_que_cambiar(self) -> "ServicioUpdate":
        """Un PATCH vacío llegaría a PostgREST como un UPDATE sin SET."""
        if not self.model_dump(exclude_unset=True):
            raise ValueError("No hay nada que cambiar")
        return self


class DiaEspecialCreate(BaseModel):
    """Un feriado o un horario especial para una fecha concreta."""

    date: date
    is_open: bool = False
    opens_at: Optional[time] = None
    closes_at: Optional[time] = None
    max_citas: Optional[int] = Field(None, gt=0)
    capacidad_simultanea: Optional[int] = Field(None, gt=0)
    reason: Optional[str] = Field(None, max_length=200)

    @model_validator(mode="after")
    def _horas_coherentes(self) -> "DiaEspecialCreate":
        if not self.is_open:
            return self
        if self.opens_at is None or self.closes_at is None:
            raise ValueError("Un día abierto necesita hora de apertura y de cierre")
        if self.opens_at >= self.closes_at:
            raise ValueError("La hora de cierre debe ser posterior a la de apertura")
        return self


class AjustesRead(BaseModel):
    """Todo lo que la pantalla de ajustes necesita en una sola llamada."""

    horario: List[DiaHorario]
    servicios: List[ServicioRead]
    dias_especiales: List[DiaEspecialCreate]
