"""
Repository for order_statuses table operations.

Handles all database interactions for order statuses via Supabase REST API.
"""

import logging
from typing import Any, Dict, List, Optional

import httpx
from fastapi import HTTPException

logger = logging.getLogger(__name__)


class OrderStatusRepository:
    """Repository for CRUD operations on order_statuses table."""

    def __init__(self, base_url: str, api_key: str):
        """
        Initialize repository with Supabase connection details.

        Args:
            base_url: Supabase project URL (e.g., https://xxx.supabase.co)
            api_key: Supabase service role key or anon key
        """
        self.base_url = f"{base_url}/rest/v1"
        self.headers = {
            "apikey": api_key,
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        }

    async def create_status(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create a new order status.

        Args:
            data: Status data (status_type, code, label, sort_order, is_terminal)

        Returns:
            Created status record

        Raises:
            HTTPException: If creation fails (e.g., duplicate code)
        """
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/order_statuses",
                json=data,
                headers=self.headers,
            )
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                detail = response.json() if response.text else str(exc)
                logger.error("Error creating order status: %s", detail)
                raise HTTPException(status_code=response.status_code, detail=detail)

            rows = response.json()
            return rows[0] if rows else {}

    async def get_status_by_id(self, status_id: str) -> Optional[Dict[str, Any]]:
        """
        Get an order status by ID.

        Args:
            status_id: UUID of the status

        Returns:
            Status record or None if not found
        """
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/order_statuses",
                params={"id": f"eq.{status_id}"},
                headers=self.headers,
            )
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                detail = response.json() if response.text else str(exc)
                logger.error("Error fetching status %s: %s", status_id, detail)
                raise HTTPException(status_code=response.status_code, detail=detail)

            rows = response.json()
            return rows[0] if rows else None

    async def get_status_by_code(self, code: str) -> Optional[Dict[str, Any]]:
        """
        Get an order status by its unique code.

        Args:
            code: Status code (e.g., 'recibido', 'en_proceso')

        Returns:
            Status record or None if not found
        """
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/order_statuses",
                params={"code": f"eq.{code}"},
                headers=self.headers,
            )
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                detail = response.json() if response.text else str(exc)
                logger.error("Error fetching status by code %s: %s", code, detail)
                raise HTTPException(status_code=response.status_code, detail=detail)

            rows = response.json()
            return rows[0] if rows else None

    async def list_statuses(
        self, status_type: Optional[str] = None, limit: int = 100, offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        List all order statuses with optional filtering.

        Args:
            status_type: Filter by status type ('workshop' or 'followup')
            limit: Maximum number of records to return
            offset: Number of records to skip

        Returns:
            List of status records ordered by status_type and sort_order
        """
        params = {
            "order": "status_type.asc,sort_order.asc",
            "limit": str(limit),
            "offset": str(offset),
        }

        if status_type:
            params["status_type"] = f"eq.{status_type}"

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/order_statuses",
                params=params,
                headers=self.headers,
            )
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                detail = response.json() if response.text else str(exc)
                logger.error("Error listing statuses: %s", detail)
                raise HTTPException(status_code=response.status_code, detail=detail)

            return response.json()

    async def count_statuses(
        self, status_type: Optional[str] = None
    ) -> Dict[str, int]:
        """
        Count order statuses by type.

        Args:
            status_type: Optional filter by status type

        Returns:
            Dict with 'total', 'workshop_count', and 'followup_count'
        """
        headers = {**self.headers, "Prefer": "count=exact"}

        async with httpx.AsyncClient() as client:
            # Get total count
            params = {}
            if status_type:
                params["status_type"] = f"eq.{status_type}"

            total_response = await client.get(
                f"{self.base_url}/order_statuses",
                params=params,
                headers=headers,
            )
            total = int(total_response.headers.get("Content-Range", "0-0/0").split("/")[1])

            # Get workshop count
            workshop_response = await client.get(
                f"{self.base_url}/order_statuses",
                params={"status_type": "eq.workshop"},
                headers=headers,
            )
            workshop_count = int(
                workshop_response.headers.get("Content-Range", "0-0/0").split("/")[1]
            )

            # Get followup count
            followup_response = await client.get(
                f"{self.base_url}/order_statuses",
                params={"status_type": "eq.followup"},
                headers=headers,
            )
            followup_count = int(
                followup_response.headers.get("Content-Range", "0-0/0").split("/")[1]
            )

            return {
                "total": total,
                "workshop_count": workshop_count,
                "followup_count": followup_count,
            }

    async def update_status(
        self, status_id: str, data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Update an order status.

        Args:
            status_id: UUID of the status to update
            data: Fields to update

        Returns:
            Updated status record or None if not found

        Raises:
            HTTPException: If update fails
        """
        async with httpx.AsyncClient() as client:
            response = await client.patch(
                f"{self.base_url}/order_statuses",
                params={"id": f"eq.{status_id}"},
                json=data,
                headers=self.headers,
            )
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                detail = response.json() if response.text else str(exc)
                logger.error("Error updating status %s: %s", status_id, detail)
                raise HTTPException(status_code=response.status_code, detail=detail)

            rows = response.json()
            return rows[0] if rows else None

    async def delete_status(self, status_id: str) -> bool:
        """
        Delete an order status.

        Note: This may fail if the status is referenced by orders or order_status_history.

        Args:
            status_id: UUID of the status to delete

        Returns:
            True if deleted successfully

        Raises:
            HTTPException: If deletion fails (e.g., foreign key constraint)
        """
        async with httpx.AsyncClient() as client:
            response = await client.delete(
                f"{self.base_url}/order_statuses",
                params={"id": f"eq.{status_id}"},
                headers=self.headers,
            )
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                detail = response.json() if response.text else str(exc)
                logger.error("Error deleting status %s: %s", status_id, detail)
                raise HTTPException(status_code=response.status_code, detail=detail)

            return True
