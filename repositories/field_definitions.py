import logging
from typing import Any, Dict, List, Optional

import httpx
from fastapi import HTTPException

from core.config import settings

logger = logging.getLogger(__name__)


def _headers() -> Dict[str, str]:
    key = settings.SUPABASE_SERVICE_ROLE_KEY
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


class FieldDefinitionRepository:
    """CRUD for the org-level custom field definitions."""

    def __init__(self):
        self.base_url = f"{settings.SUPABASE_URL}/rest/v1"
        self.headers = _headers()

    async def list_by_org(self, organization_id: str) -> List[Dict[str, Any]]:
        params = {
            "organization_id": f"eq.{organization_id}",
            "order": "display_order.asc",
        }
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/field_definitions",
                params=params,
                headers=self.headers,
            )
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                detail = response.json() if response.text else str(exc)
                logger.error("Error listing field definitions: %s", detail)
                raise HTTPException(status_code=response.status_code, detail=detail)
            return response.json()

    async def create(self, data: Dict[str, Any]) -> Dict[str, Any]:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/field_definitions",
                json=data,
                headers=self.headers,
            )
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                detail = response.json() if response.text else str(exc)
                logger.error("Error creating field definition: %s", detail)
                raise HTTPException(status_code=response.status_code, detail=detail)
            return response.json()[0]

    async def delete(self, field_id: str) -> Optional[Dict[str, Any]]:
        async with httpx.AsyncClient() as client:
            response = await client.delete(
                f"{self.base_url}/field_definitions",
                params={"id": f"eq.{field_id}"},
                headers=self.headers,
            )
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                detail = response.json() if response.text else str(exc)
                logger.error("Error deleting field definition %s: %s", field_id, detail)
                raise HTTPException(status_code=response.status_code, detail=detail)
            rows = response.json()
            return rows[0] if rows else None


class OrderFieldValueRepository:
    """Per-order custom field values."""

    def __init__(self):
        self.base_url = f"{settings.SUPABASE_URL}/rest/v1"
        self.headers = _headers()

    async def list_by_order(self, order_id: str) -> List[Dict[str, Any]]:
        params = {
            "order_id": f"eq.{order_id}",
            "select": "*,field_definition:field_definitions(*)",
        }
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/order_field_values",
                params=params,
                headers=self.headers,
            )
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                detail = response.json() if response.text else str(exc)
                logger.error("Error listing field values for order %s: %s", order_id, detail)
                raise HTTPException(status_code=response.status_code, detail=detail)
            return response.json()

    async def replace_for_order(
        self, order_id: str, rows: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Delete existing values for the order, then insert the given rows.

        Simple and race-free enough for a single-workshop workflow; avoids the
        need to diff added/removed/changed values. `rows` should already carry
        order_id and non-empty values only.
        """
        async with httpx.AsyncClient() as client:
            # 1. Wipe existing values for this order.
            del_response = await client.delete(
                f"{self.base_url}/order_field_values",
                params={"order_id": f"eq.{order_id}"},
                headers=self.headers,
            )
            try:
                del_response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                detail = del_response.json() if del_response.text else str(exc)
                logger.error("Error clearing field values for order %s: %s", order_id, detail)
                raise HTTPException(status_code=del_response.status_code, detail=detail)

            if not rows:
                return []

            # 2. Insert the new values.
            ins_response = await client.post(
                f"{self.base_url}/order_field_values",
                json=rows,
                headers=self.headers,
            )
            try:
                ins_response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                detail = ins_response.json() if ins_response.text else str(exc)
                logger.error("Error inserting field values for order %s: %s", order_id, detail)
                raise HTTPException(status_code=ins_response.status_code, detail=detail)
            return ins_response.json()
