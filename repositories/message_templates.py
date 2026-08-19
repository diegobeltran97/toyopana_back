"""Repository for message_templates against Supabase via PostgREST.

Uses the service_role key: `message_templates` has RLS enabled with zero
policies, so no other key can reach it. EVERY method filters on
organization_id -- including the writes, where it acts as a tenant guard so a
template id from another org can never be read or patched.

Mirrors CitaRepository's shape (same headers, same _raise_for_status).
"""

import logging
from typing import Any, Dict, List, Optional

import httpx
from fastapi import HTTPException

from core.config import settings
from integrations.messaging.templates import MessageTemplate

logger = logging.getLogger(__name__)


def to_domain(row: Dict[str, Any]) -> MessageTemplate:
    """PostgREST row -> the provider-neutral domain model."""
    return MessageTemplate(
        name=row["name"],
        body=row["body"],
        params=tuple(row.get("params") or ()),
        language=row.get("language") or "es",
        provider_template_name=row.get("provider_template_name"),
    )


class MessageTemplateRepository:
    """CRUD over the `message_templates` table."""

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

    async def list(
        self, organization_id: str, active_only: bool = True
    ) -> List[Dict[str, Any]]:
        """Every template for one organization, newest name order."""
        params = {
            "organization_id": f"eq.{organization_id}",
            "select": "*",
            "order": "name.asc",
        }
        if active_only:
            params["is_active"] = "is.true"

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{self.base_url}/message_templates",
                headers=self.headers,
                params=params,
            )
        self._raise_for_status(response, "listing message templates")
        return response.json()

    async def get_by_name(
        self, organization_id: str, name: str
    ) -> Optional[Dict[str, Any]]:
        """One template by its logical name, or None. The send path's lookup."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{self.base_url}/message_templates",
                headers=self.headers,
                params={
                    "organization_id": f"eq.{organization_id}",
                    "name": f"eq.{name}",
                    "is_active": "is.true",
                    "select": "*",
                    "limit": "1",
                },
            )
        self._raise_for_status(response, f"fetching template {name}")
        rows = response.json()
        return rows[0] if rows else None

    async def create(
        self, organization_id: str, data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Insert one template, stamping the owning organization here."""
        payload = {**data, "organization_id": organization_id}
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self.base_url}/message_templates",
                headers=self.headers,
                json=payload,
            )
        self._raise_for_status(response, "creating message template")
        return response.json()[0]

    async def update(
        self, organization_id: str, template_id: str, data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Patch one template. organization_id is the tenant guard, not a filter
        convenience: without it a caller could patch another org's row by id."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.patch(
                f"{self.base_url}/message_templates",
                headers=self.headers,
                params={
                    "id": f"eq.{template_id}",
                    "organization_id": f"eq.{organization_id}",
                },
                json=data,
            )
        self._raise_for_status(response, "updating message template")
        rows = response.json()
        return rows[0] if rows else None

    async def delete(self, organization_id: str, template_id: str) -> bool:
        """Delete one template. Returns False when nothing matched."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.delete(
                f"{self.base_url}/message_templates",
                headers=self.headers,
                params={
                    "id": f"eq.{template_id}",
                    "organization_id": f"eq.{organization_id}",
                },
            )
        self._raise_for_status(response, "deleting message template")
        return bool(response.json())
