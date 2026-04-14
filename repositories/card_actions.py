import httpx
from typing import List, Dict, Any
from core.config import settings


class CardActionsRepository:
    """Repository for managing card actions in Supabase"""

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

    async def get_actions_by_card(
        self,
        organization_id: str,
        pipefy_card_id: str
    ) -> List[Dict[str, Any]]:
        """
        Get all actions already taken for a specific card

        Args:
            organization_id: The organization UUID
            pipefy_card_id: The Pipefy card ID

        Returns:
            List of action records for this card
        """
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/card_actions",
                params={
                    "organization_id": f"eq.{organization_id}",
                    "pipefy_card_id": f"eq.{pipefy_card_id}",
                    "order": "performed_at.desc"
                },
                headers=self.headers
            )
            response.raise_for_status()
            return response.json()

    async def get_actions_by_multiple_cards(
        self,
        organization_id: str,
        card_ids: List[str]
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Get all actions for multiple cards in one query
        Returns a dictionary mapping card_id -> list of actions

        Args:
            organization_id: The organization UUID
            card_ids: List of Pipefy card IDs

        Returns:
            Dictionary with card_id as key and list of actions as value
        """
        if not card_ids:
            return {}

        async with httpx.AsyncClient() as client:
            # Supabase PostgREST syntax for IN query
            card_ids_param = ",".join(card_ids)
            response = await client.get(
                f"{self.base_url}/card_actions",
                params={
                    "organization_id": f"eq.{organization_id}",
                    "pipefy_card_id": f"in.({card_ids_param})",
                    "order": "performed_at.desc"
                },
                headers=self.headers
            )
            response.raise_for_status()
            actions = response.json()

            # Group actions by card_id
            actions_by_card: Dict[str, List[Dict[str, Any]]] = {}
            for action in actions:
                card_id = action.get("pipefy_card_id")
                if card_id:
                    if card_id not in actions_by_card:
                        actions_by_card[card_id] = []
                    actions_by_card[card_id].append(action)

            return actions_by_card
