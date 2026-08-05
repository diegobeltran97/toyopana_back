from typing import List

from fastapi import APIRouter, Path, Query, status

from schemas.field_definition import FieldDefinitionCreate, FieldDefinitionOut
from services import field_definitions_service

router = APIRouter()


@router.get(
    "",
    response_model=List[FieldDefinitionOut],
    summary="List an organization's custom field definitions",
    tags=["field-definitions"],
)
async def list_field_definitions(
    organization_id: str = Query(..., description="Organization to list fields for"),
):
    return await field_definitions_service.list_definitions(organization_id)


@router.post(
    "",
    response_model=FieldDefinitionOut,
    summary="Create a custom field definition",
    tags=["field-definitions"],
)
async def create_field_definition(
    body: FieldDefinitionCreate,
    organization_id: str = Query(..., description="Organization the field belongs to"),
):
    return await field_definitions_service.create_definition(organization_id, body)


@router.delete(
    "/{field_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a custom field definition",
    tags=["field-definitions"],
)
async def delete_field_definition(
    field_id: str = Path(..., description="The field definition id to delete"),
):
    await field_definitions_service.delete_definition(field_id)
