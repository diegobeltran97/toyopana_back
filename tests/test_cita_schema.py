"""Tests for the cita schemas (schemas/cita.py)."""

import uuid
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from schemas.cita import CitaCreate, CitaCustomer, CitaRead, CitaStatus, CitaUpdate


def test_status_enum_has_the_six_lifecycle_values():
    """'solicitada' entró con la migración 006: es la cita que el cliente pidió
    por la agenda web y que el taller todavía no ha mirado."""
    assert {s.value for s in CitaStatus} == {
        "solicitada",
        "agendada",
        "confirmada",
        "cumplida",
        "no_show",
        "cancelada",
    }


def test_create_requires_customer_and_time():
    with pytest.raises(ValidationError):
        CitaCreate(service_type="Cambio de aceite")


def test_create_defaults_service_type_to_none():
    payload = CitaCreate(
        customer_id=uuid.uuid4(), scheduled_at=datetime.now(timezone.utc)
    )
    assert payload.service_type is None


def test_update_is_fully_partial():
    """An empty PATCH body is valid; exclude_unset yields no fields to write."""
    update = CitaUpdate()
    assert update.model_dump(exclude_unset=True) == {}


def test_update_rejects_unknown_status():
    with pytest.raises(ValidationError):
        CitaUpdate(status="pendiente")


def test_read_accepts_embedded_customer_and_null_bridge():
    cita = CitaRead(
        id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        customer_id=uuid.uuid4(),
        scheduled_at=datetime.now(timezone.utc),
        status="agendada",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        customer={"id": str(uuid.uuid4()), "name": "Juan Pérez", "phone": "+50761234567"},
    )
    assert cita.status is CitaStatus.agendada
    assert cita.converted_order_id is None
    assert cita.vehicle_id is None
    assert isinstance(cita.customer, CitaCustomer)
    assert cita.customer.name == "Juan Pérez"


def test_read_flattens_the_catalog_service_name_from_the_embed():
    """PostgREST entrega el catálogo anidado (repositories/citas.py embebe
    `service_types(name)`); CitaRead lo aplana a `service_type_name` para que
    el panel no tenga que mirar dos campos distintos por lo mismo."""
    cita = CitaRead(
        id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        scheduled_at=datetime.now(timezone.utc),
        status="agendada",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        service_types={"name": "Cambio de amortiguadores"},
    )
    assert cita.service_type_name == "Cambio de amortiguadores"


def test_read_service_type_name_is_none_without_a_catalog_service():
    """La mayoría de las citas hoy no tiene service_type_id: ni el embed nulo
    de PostgREST ni su ausencia deben reventar la lectura."""
    cita = CitaRead(
        id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        scheduled_at=datetime.now(timezone.utc),
        status="agendada",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        service_types=None,
    )
    assert cita.service_type_name is None


def test_read_tolerates_customer_without_phone():
    """PostgREST returns phone: null for customers with no number on file."""
    cita = CitaRead(
        id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        customer_id=uuid.uuid4(),
        scheduled_at=datetime.now(timezone.utc),
        status="confirmada",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        customer={"id": str(uuid.uuid4()), "name": "Taller Los Andes", "phone": None},
    )
    assert cita.customer.phone is None
