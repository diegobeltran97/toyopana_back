import httpx
from typing import Optional, Dict, Any
from core.config import settings


class PipefyEventsBackupRepository:
    """Repository for managing Pipefy events backup in Supabase"""

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

    async def create_backup_event(
        self,
        organization_id: str,
        event_type: str,
        raw_payload: Dict[str, Any],
        pipefy_card_id: Optional[str] = None,
        pipe_id: Optional[str] = None,
        actions_taken: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Create a new backup event record in pipefy_events_backup table

        Args:
            organization_id: The organization UUID
            event_type: The event action type (e.g., card.create, card.move)
            raw_payload: The complete webhook payload as JSON
            pipefy_card_id: Optional Pipefy card ID
            pipe_id: Optional Pipefy pipe ID
            actions_taken: Optional actions taken data

        Returns:
            The created backup event record
        """
        async with httpx.AsyncClient() as client:
            payload = {
                "organization_id": organization_id,
                "event_type": event_type,
                "raw_payload": raw_payload,
            }

            if actions_taken:
                payload["actions_taken"] = actions_taken

            if pipefy_card_id:
                payload["pipefy_card_id"] = pipefy_card_id

            if pipe_id:
                payload["pipe_id"] = pipe_id

            response = await client.post(
                f"{self.base_url}/pipefy_events_backup",
                json=payload,
                headers=self.headers
            )
            response.raise_for_status()

            result = response.json()
            return result[0] if isinstance(result, list) else result

    async def bulk_create_backup_events(
        self,
        events: list[Dict[str, Any]]
    ) -> list[Dict[str, Any]]:
        """
        Create multiple backup event records in a single request

        Args:
            events: List of event dictionaries to create
                Each event should contain:
                - organization_id: str
                - event_type: str
                - raw_payload: dict
                - pipefy_card_id: str (optional)
                - pipe_id: str (optional)
                - actions_taken: dict (optional)

        Returns:
            List of created backup event records

        Raises:
            httpx.HTTPError: If the request fails
        """
        if not events:
            return []

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/pipefy_events_backup",
                json=events,
                headers=self.headers
            )
            response.raise_for_status()

            return response.json()

    async def get_backup_events_by_organization(
        self,
        organization_id: str,
        limit: int = 100
    ) -> list[Dict[str, Any]]:
        """
        Get all backup events for a specific organization

        Args:
            organization_id: The organization UUID
            limit: Maximum number of events to return

        Returns:
            List of backup event records
        """
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(60.0, connect=10.0),
            limits=httpx.Limits(max_connections=100, max_keepalive_connections=20)
        ) as client:
            response = await client.get(
                f"{self.base_url}/pipefy_events_backup",
                params={
                    "organization_id": f"eq.{organization_id}",
                    "order": "created_at.desc",
                    "limit": limit
                },
                headers=self.headers
            )
            response.raise_for_status()
            return response.json()
