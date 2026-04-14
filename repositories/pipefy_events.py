import httpx
from typing import Optional, Dict, Any
from core.config import settings
from schemas.pipefy_events import PipefyEventUpdateActions, PipefyEventResponse


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
        pipe_id: Optional[str] = None,
        actions_taken: Optional[Dict[str, Any]] = None
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
            
            if actions_taken:
                payload["actions_taken"] = actions_taken

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
        # Configure httpx client with increased limits for large JSON payloads
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(60.0, connect=10.0),
            limits=httpx.Limits(max_connections=100, max_keepalive_connections=20)
        ) as client:
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


    async def update_event_actions_by_id(
        self,
        event_id: str,
        update_data: PipefyEventUpdateActions
    ) -> PipefyEventResponse:
        """
        Update the actions taken for a specific event by ID

        Args:
            event_id: The event UUID to update
            update_data: PipefyEventUpdateActions schema with actions_taken data

        Returns:
            The updated event record as PipefyEventResponse

        Raises:
            httpx.HTTPError: If the request fails
        """
        payload = update_data.model_dump(exclude_unset=True)

        async with httpx.AsyncClient() as client:
            response = await client.patch(
                f"{self.base_url}/pipefy_events?id=eq.{event_id}",
                json=payload,
                headers=self.headers
            )
            response.raise_for_status()

            result = response.json()
            event_data = result[0] if isinstance(result, list) else result

            return PipefyEventResponse(**event_data)

    async def bulk_create_events(
        self,
        events: list[Dict[str, Any]]
    ) -> list[Dict[str, Any]]:
        """
        Create multiple Pipefy event records in a single request

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
            List of created event records

        Raises:
            httpx.HTTPError: If the request fails
        """
        if not events:
            return []

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/pipefy_events",
                json=events,
                headers=self.headers
            )
            response.raise_for_status()

            return response.json()
