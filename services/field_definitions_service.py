import logging
from typing import List

from fastapi import HTTPException

from repositories.field_definitions import (
    FieldDefinitionRepository,
    OrderFieldValueRepository,
)
from schemas.field_definition import (
    FieldDefinitionCreate,
    FieldDefinitionOut,
    OrderFieldValueOut,
    OrderFieldValueUpsert,
)

logger = logging.getLogger(__name__)


async def list_definitions(organization_id: str) -> List[FieldDefinitionOut]:
    repo = FieldDefinitionRepository()
    rows = await repo.list_by_org(organization_id)
    return [FieldDefinitionOut.model_validate(r) for r in rows]


async def create_definition(
    organization_id: str, data: FieldDefinitionCreate
) -> FieldDefinitionOut:
    repo = FieldDefinitionRepository()
    payload = {**data.model_dump(mode="json"), "organization_id": organization_id}
    created = await repo.create(payload)
    logger.info("Field definition '%s' created in org %s", data.field_name, organization_id)
    return FieldDefinitionOut.model_validate(created)


async def delete_definition(field_id: str) -> None:
    repo = FieldDefinitionRepository()
    deleted = await repo.delete(field_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Field definition not found")
    logger.info("Field definition %s deleted", field_id)


async def save_order_values(
    order_id: str, values: List[OrderFieldValueUpsert]
) -> List[OrderFieldValueOut]:
    repo = OrderFieldValueRepository()
    # Only persist fields that actually have a value; empty ones are dropped
    # (delete-then-insert in the repo means cleared fields disappear).
    rows = [
        {
            "order_id": order_id,
            "field_definition_id": str(v.field_definition_id),
            "value": v.value,
        }
        for v in values
        if v.value is not None and v.value.strip() != ""
    ]
    saved = await repo.replace_for_order(order_id, rows)
    logger.info("Saved %d field value(s) for order %s", len(saved), order_id)
    return [OrderFieldValueOut.model_validate(r) for r in saved]


async def get_order_values(order_id: str) -> List[OrderFieldValueOut]:
    repo = OrderFieldValueRepository()
    rows = await repo.list_by_order(order_id)
    return [OrderFieldValueOut.model_validate(r) for r in rows]
