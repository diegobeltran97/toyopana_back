import logging
from typing import Any, Dict, List, Optional

import httpx
from fastapi import HTTPException

from core.config import settings

logger = logging.getLogger(__name__)


class OrderFileRepository:
    """Repository for the `order_files` table via the Supabase REST API.

    Only persists metadata rows. The actual bytes live in the private
    `order-files` Storage bucket (handled in the service layer).
    """

    def __init__(self) -> None:
        self.supabase_url = settings.SUPABASE_URL
        self.service_role_key = settings.SUPABASE_SERVICE_ROLE_KEY
        self.base_url = f"{self.supabase_url}/rest/v1"
        self.headers = {
            "apikey": self.service_role_key,
            "Authorization": f"Bearer {self.service_role_key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        }

    def _raise_for_status(self, response: httpx.Response, action: str) -> None:
        """Surface the real PostgREST error instead of a generic 500."""
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            detail = response.json() if response.text else str(exc)
            logger.error("Error %s order file(s): %s", action, detail)
            raise HTTPException(status_code=response.status_code, detail=detail)

    async def create_many(
        self, records: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Bulk-insert order_file rows and return the created records."""
        if not records:
            return []
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/order_files",
                json=records,
                headers=self.headers,
            )
            self._raise_for_status(response, "creating")
            return response.json()

    async def list_by_order(self, order_id: str) -> List[Dict[str, Any]]:
        """Return every file attached to an order, oldest first."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/order_files",
                params={
                    "order_id": f"eq.{order_id}",
                    "order": "uploaded_at.asc",
                },
                headers=self.headers,
            )
            self._raise_for_status(response, "listing")
            return response.json()

    async def get_by_id(self, file_id: str) -> Optional[Dict[str, Any]]:
        """Return a single order_file row, or None if it doesn't exist."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/order_files",
                params={"id": f"eq.{file_id}", "limit": 1},
                headers=self.headers,
            )
            self._raise_for_status(response, "fetching")
            rows = response.json()
            return rows[0] if rows else None

    async def update(
        self, file_id: str, data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Patch editable metadata (label / file_type) on a file row."""
        async with httpx.AsyncClient() as client:
            response = await client.patch(
                f"{self.base_url}/order_files",
                params={"id": f"eq.{file_id}"},
                json=data,
                headers=self.headers,
            )
            self._raise_for_status(response, "updating")
            rows = response.json()
            return rows[0] if rows else None

    async def delete(self, file_id: str) -> Optional[Dict[str, Any]]:
        """Delete a file row and return it (so the caller can clean Storage)."""
        async with httpx.AsyncClient() as client:
            response = await client.delete(
                f"{self.base_url}/order_files",
                params={"id": f"eq.{file_id}"},
                headers=self.headers,
            )
            self._raise_for_status(response, "deleting")
            rows = response.json()
            return rows[0] if rows else None
