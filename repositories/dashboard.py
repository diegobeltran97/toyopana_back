"""Repository for dashboard metric queries against Supabase (PostgREST)."""

import logging
from typing import List, Optional

import httpx
from fastapi import HTTPException

from core.config import settings

logger = logging.getLogger(__name__)


class DashboardRepository:
    """Read-only aggregate queries over orders / order_status_history."""

    def __init__(self):
        self.supabase_url = settings.SUPABASE_URL
        self.service_role_key = settings.SUPABASE_SERVICE_ROLE_KEY
        self.base_url = f"{self.supabase_url}/rest/v1"
        self.headers = {
            "apikey": self.service_role_key,
            "Authorization": f"Bearer {self.service_role_key}",
            "Content-Type": "application/json",
        }

    async def count_orders(
        self,
        organization_id: str,
        received_after: Optional[str] = None,
        statuses: Optional[List[str]] = None,
    ) -> int:
        """
        Count orders for an organization, optionally filtered.

        Uses PostgREST `Prefer: count=exact` and reads the total from the
        Content-Range response header (like OrderStatusRepository.count_statuses),
        so no rows need to be transferred.

        Args:
            organization_id: The organization UUID to scope by
            received_after: ISO timestamp; only count orders with received_at >= this
            statuses: Only count orders whose order_status is in this list

        Returns:
            The exact number of matching orders.
        """
        params = {
            "organization_id": f"eq.{organization_id}",
            "select": "id",
            "limit": "1",
        }
        if received_after:
            params["received_at"] = f"gte.{received_after}"
        if statuses:
            # PostgREST `in.(...)`; values double-quoted so slugs stay intact.
            quoted = ",".join(f'"{s}"' for s in statuses)
            params["order_status"] = f"in.({quoted})"

        headers = {**self.headers, "Prefer": "count=exact"}
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/orders", params=params, headers=headers
            )
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                detail = response.json() if response.text else str(exc)
                logger.error("Error counting orders: %s", detail)
                raise HTTPException(status_code=response.status_code, detail=detail)
            return int(response.headers.get("Content-Range", "0-0/0").split("/")[1])

    async def count_orders_reached_status(
        self,
        organization_id: str,
        to_status: str,
        changed_after: str,
    ) -> int:
        """
        Count distinct orders that transitioned to `to_status` since a time.

        Reads order_status_history rows (select=order_id) and dedupes in
        Python, because an order can transition to the same status more than
        once and orders.completed_at is not reliably populated.

        Args:
            organization_id: The organization UUID to scope by
            to_status: The status code the order transitioned into (e.g. 'pagado')
            changed_after: ISO timestamp; only transitions with changed_at >= this

        Returns:
            The number of distinct orders that reached the status in the window.
        """
        params = {
            "organization_id": f"eq.{organization_id}",
            "to_status": f"eq.{to_status}",
            "changed_at": f"gte.{changed_after}",
            "select": "order_id",
        }
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/order_status_history",
                params=params,
                headers=self.headers,
            )
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                detail = response.json() if response.text else str(exc)
                logger.error("Error counting status transitions: %s", detail)
                raise HTTPException(status_code=response.status_code, detail=detail)
            rows = response.json()
            return len({row["order_id"] for row in rows if row.get("order_id")})
