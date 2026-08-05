import uuid
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict

# Mirrors the field_definitions_field_type_check CHECK constraint in Postgres.
FieldType = Literal["text", "text_field", "dropdown", "checkbox", "radio_button"]


class FieldDefinitionCreate(BaseModel):
    field_name: str
    field_type: FieldType
    field_options: Optional[List[str]] = None
    required: bool = False
    display_order: int = 0
    service_type: Optional[str] = None


class FieldDefinitionOut(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    service_type: Optional[str] = None
    field_name: str
    field_type: FieldType
    field_options: Optional[List[str]] = None
    required: bool
    display_order: int

    model_config = ConfigDict(from_attributes=True)


class OrderFieldValueUpsert(BaseModel):
    field_definition_id: uuid.UUID
    value: Optional[str] = None


class OrderFieldValueOut(BaseModel):
    id: uuid.UUID
    order_id: uuid.UUID
    field_definition_id: uuid.UUID
    value: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)
