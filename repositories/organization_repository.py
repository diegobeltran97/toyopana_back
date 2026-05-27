import httpx
from typing import List, Dict, Any
from core.config import settings


class OrganizationRepository:
    """Repository for managing organizations in Supabase"""

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

    async def create_organization(self, organization_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create a new organization record in Supabase

        Args:
            organization_data: Dictionary containing organization fields (name, legal_name, tax_id, etc.)

        Returns:
            The created organization record from Supabase
        """
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/organization",
                json=organization_data,
                headers=self.headers
            )
            response.raise_for_status()
            return response.json()[0]  # Return the created record