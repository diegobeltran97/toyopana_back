import httpx
from typing import Optional, Dict, Any
from core.config import settings


class PipefyEventsRepository:
    """Repository for managing Pipefy events in Supabase"""

    def __init__(self):
        self.supabase_url = settings.SUPABASE_URL
        self.service_role_key = settings.SUPABASE_SERVICE_ROLE_KEY
        self.base_url = f"{self.supabase_url}/rest/v1"
        self.headers = {
            "apikey": self.service_role_key,
            "Authorization": f"Bearer {self.service_role_key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation"
        }

    async def create_event(
        self,
        organization_id: str,
        event_type: str,
        raw_payload: Dict[str, Any],
        pipefy_card_id: Optional[str] = None,
        pipe_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a new Pipefy event record in the database

        Args:
            organization_id: The organization UUID
            event_type: The event action type (e.g., card.create, card.move)
            raw_payload: The complete webhook payload as JSON
            pipefy_card_id: Optional Pipefy card ID
            pipe_id: Optional Pipefy pipe ID

        Returns:
            The created event record
        """
        async with httpx.AsyncClient() as client:
            payload = {
                "organization_id": organization_id,
                "event_type": event_type,
                "raw_payload": raw_payload,
            }

            if pipefy_card_id:
                payload["pipefy_card_id"] = pipefy_card_id

            if pipe_id:
                payload["pipe_id"] = pipe_id

            response = await client.post(
                f"{self.base_url}/pipefy_events",
                json=payload,
                headers=self.headers
            )
            response.raise_for_status()

            result = response.json()
            return result[0] if isinstance(result, list) else result

    async def get_events_by_organization(
        self,
        organization_id: str,
        limit: int = 100
    ) -> list[Dict[str, Any]]:
        """
        Get all events for a specific organization

        Args:
            organization_id: The organization UUID
            limit: Maximum number of events to return

        Returns:
            List of event records
        """
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/pipefy_events",
                params={
                    "organization_id": f"eq.{organization_id}",
                    "order": "created_at.desc",
                    "limit": limit
                },
                headers=self.headers
            )
            response.raise_for_status()
            return response.json()

    async def get_events_by_card(
        self,
        pipefy_card_id: str,
        limit: int = 100
    ) -> list[Dict[str, Any]]:
        """
        Get all events for a specific Pipefy card

        Args:
            pipefy_card_id: The Pipefy card ID
            limit: Maximum number of events to return

        Returns:
            List of event records
        """
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/pipefy_events",
                params={
                    "pipefy_card_id": f"eq.{pipefy_card_id}",
                    "order": "created_at.desc",
                    "limit": limit
                },
                headers=self.headers
            )
            response.raise_for_status()
            return response.json()

