"""Repository for citas (appointments) against Supabase via PostgREST.

Uses the service_role key: `citas` has RLS enabled with zero policies, so no
other key can reach it. EVERY method filters on organization_id — including the
writes, where it acts as a tenant guard so a cita id from another org can never
be patched.
"""

import logging
from typing import Any, Dict, List, Optional

import httpx
from fastapi import HTTPException

from core.config import settings

logger = logging.getLogger(__name__)

# The calendar needs the customer's name next to each cita; PostgREST embeds it
# through the citas_customer_id_fkey relationship in the same round trip.
CITA_SELECT = "*,customer:customers(id,name,phone)"


class CitaRepository:
    """CRUD over the `citas` table."""

    def __init__(self):
        self.supabase_url = settings.SUPABASE_URL
        self.service_role_key = settings.SUPABASE_SERVICE_ROLE_KEY
        self.base_url = f"{self.supabase_url}/rest/v1"
        self.headers = {
            "apikey": self.service_role_key,
            "Authorization": f"Bearer {self.service_role_key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        }

    def _raise_for_status(self, response, action: str) -> None:
        """Surface a PostgREST failure as an HTTPException with its own status."""
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            detail = response.json() if response.text else str(exc)
            logger.error("Error %s: %s", action, detail)
            raise HTTPException(status_code=response.status_code, detail=detail)

    async def create(
        self, organization_id: str, data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Insert one cita.

        Args:
            organization_id: Owning organization; stamped onto the row here so a
                caller can never insert into another tenant.
            data: Column values (customer_id, scheduled_at, service_type, status).

        Returns:
            The created row as PostgREST returned it.
        """
        payload = {**data, "organization_id": str(organization_id)}
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/citas", json=payload, headers=self.headers
            )
            self._raise_for_status(response, "creating cita")
            return response.json()[0]

    async def list_range(
        self,
        organization_id: str,
        scheduled_from: str,
        scheduled_before: str,
        status: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        List an org's citas inside a half-open time window, earliest first.

        Args:
            organization_id: The organization UUID.
            scheduled_from: ISO timestamp, INCLUSIVE lower bound (gte).
            scheduled_before: ISO timestamp, EXCLUSIVE upper bound (lt). The
                service passes the day after the last requested day, so the
                final day of the range is fully covered.
            status: Optional exact status filter.

        Returns:
            Cita rows with their customer embedded.
        """
        params: Dict[str, Any] = {
            "select": CITA_SELECT,
            "organization_id": f"eq.{organization_id}",
            "scheduled_at": [f"gte.{scheduled_from}", f"lt.{scheduled_before}"],
            "order": "scheduled_at.asc",
        }
        if status:
            params["status"] = f"eq.{status}"

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/citas", params=params, headers=self.headers
            )
            self._raise_for_status(response, "listing citas")
            return response.json()

    async def get(
        self, cita_id: str, organization_id: str
    ) -> Optional[Dict[str, Any]]:
        """Fetch one cita scoped to its org, or None when it doesn't exist."""
        params = {
            "select": CITA_SELECT,
            "id": f"eq.{cita_id}",
            "organization_id": f"eq.{organization_id}",
            "limit": "1",
        }
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/citas", params=params, headers=self.headers
            )
            self._raise_for_status(response, f"fetching cita {cita_id}")
            rows = response.json()
            return rows[0] if rows else None

    async def update(
        self, cita_id: str, organization_id: str, data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Patch one cita, filtered by BOTH id and organization_id.

        Returns:
            The updated row, or None when no row matched (unknown id, or an id
            belonging to another organization).
        """
        params = {
            "id": f"eq.{cita_id}",
            "organization_id": f"eq.{organization_id}",
            "select": CITA_SELECT,
        }
        async with httpx.AsyncClient() as client:
            response = await client.patch(
                f"{self.base_url}/citas",
                params=params,
                json=data,
                headers=self.headers,
            )
            self._raise_for_status(response, f"updating cita {cita_id}")
            rows = response.json()
            return rows[0] if rows else None
