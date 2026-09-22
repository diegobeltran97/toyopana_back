"""Pydantic models for citas (appointments).

A cita is an intention to visit, booked before the vehicle arrives. It is NOT
an order: the order is created separately at reception. `converted_order_id` is
the one-way bridge to the order that eventually fulfilled the cita — the column
exists, but nothing writes it in this iteration.
"""

import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, model_validator


class CitaStatus(str, Enum):
    """Lifecycle of a cita. Mirrors the citas_status_check DB constraint."""

    # Entrada del ciclo: el cliente la pidió por la agenda web, nadie la ha
    # mirado. No ocupa cupo hasta que el taller la acepte.
    solicitada = "solicitada"
    agendada = "agendada"
    confirmada = "confirmada"
    cumplida = "cumplida"
    no_show = "no_show"
    cancelada = "cancelada"


class CitaCreate(BaseModel):
    """Booking payload. The org comes from the JWT, never from the body."""

    # Opcional: una solicitud desde la agenda web no tiene ficha en el CRM
    # todavía, y crearla ensuciaría el directorio con gente que quizá nunca
    # aparezca. Entonces viajan `solicitante_*` en su lugar.
    customer_id: Optional[uuid.UUID] = None
    scheduled_at: datetime
    service_type: Optional[str] = None
    service_type_id: Optional[uuid.UUID] = None
    # 'agendada' por defecto: el modal del taller crea citas firmes. La agenda
    # web pasa 'solicitada' explícitamente.
    status: CitaStatus = CitaStatus.agendada
    created_via: Optional[str] = None
    solicitud_texto: Optional[str] = None
    # Quién la pidió, mientras no sea todavía un cliente del CRM.
    solicitante_nombre: Optional[str] = None
    solicitante_telefono: Optional[str] = None


class CitaUpdate(BaseModel):
    """Partial update: status change and/or reschedule. Only sent fields apply."""

    status: Optional[CitaStatus] = None
    scheduled_at: Optional[datetime] = None
    service_type: Optional[str] = None
    vehicle_id: Optional[uuid.UUID] = None


class CitaCustomer(BaseModel):
    """Customer snapshot embedded in a cita, for calendar display."""

    id: uuid.UUID
    name: str
    phone: Optional[str] = None


class CitaRead(BaseModel):
    """A cita as returned by the API."""

    id: uuid.UUID
    organization_id: uuid.UUID
    customer_id: Optional[uuid.UUID] = None
    vehicle_id: Optional[uuid.UUID] = None
    scheduled_at: datetime
    service_type: Optional[str] = None
    status: CitaStatus
    converted_order_id: Optional[uuid.UUID] = None
    service_type_id: Optional[uuid.UUID] = None
    # Nombre del servicio del catálogo, cuando `service_type_id` apunta a uno.
    # Ambos son nullable y la mayoría de las citas hoy no tiene service_type_id
    # -- el panel debe mostrar este nombre cuando exista, el `service_type` de
    # texto libre cuando no, y nada cuando ninguno de los dos está.
    service_type_name: Optional[str] = None
    created_via: Optional[str] = None
    solicitud_texto: Optional[str] = None
    solicitante_nombre: Optional[str] = None
    solicitante_telefono: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    customer: Optional[CitaCustomer] = None

    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode="before")
    @classmethod
    def _aplanar_service_types(cls, data: Any) -> Any:
        """PostgREST entrega el catálogo anidado: `{"service_types": {"name":
        ...}}` (repositories/citas.py embebe `service_types(name)` vía
        service_type_id). Se aplana aquí a `service_type_name` para que quien
        consuma CitaRead no tenga que mirar dos campos distintos por lo mismo.
        """
        if isinstance(data, dict) and "service_type_name" not in data:
            embebido = data.get("service_types")
            if isinstance(embebido, dict):
                data = {**data, "service_type_name": embebido.get("name")}
        return data
