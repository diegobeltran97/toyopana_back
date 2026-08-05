import uuid

import pytest
from pydantic import ValidationError

from schemas.field_definition import (
    FieldDefinitionCreate,
    FieldDefinitionOut,
    OrderFieldValueUpsert,
)


def test_field_definition_create_accepts_allowed_type():
    model = FieldDefinitionCreate(
        field_name="¿Requiere de contacto?",
        field_type="dropdown",
        field_options=["Sí", "No"],
        required=True,
        display_order=0,
    )
    assert model.field_type == "dropdown"
    assert model.field_options == ["Sí", "No"]


def test_field_definition_create_rejects_bad_type():
    with pytest.raises(ValidationError):
        FieldDefinitionCreate(field_name="Edad", field_type="number")


def test_field_definition_out_parses_db_row():
    row = {
        "id": str(uuid.uuid4()),
        "organization_id": str(uuid.uuid4()),
        "service_type": None,
        "field_name": "Color",
        "field_type": "text",
        "field_options": None,
        "required": False,
        "display_order": 2,
    }
    out = FieldDefinitionOut.model_validate(row)
    assert out.field_name == "Color"
    assert out.display_order == 2


def test_order_field_value_upsert_minimal():
    v = OrderFieldValueUpsert(
        field_definition_id=uuid.uuid4(), value="Sí"
    )
    assert v.value == "Sí"
