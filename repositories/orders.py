import logging
import httpx
from typing import List, Dict, Any, Optional
from fastapi import HTTPException
from core.config import settings

logger = logging.getLogger(__name__)


class CustomerRepository:
    """Repository for managing customers in Supabase"""

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

    async def search_customers(
        self,
        organization_id: str,
        name: Optional[str] = None,
        phone: Optional[str] = None,
        national_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Search customers within an organization

        Filters by organization_id and applies a case-insensitive partial
        match (ilike) for each of name/phone/national_id that is provided.

        Args:
            organization_id: The organization UUID
            name: Optional name fragment to match
            phone: Optional phone fragment to match
            national_id: Optional national_id fragment to match

        Returns:
            List of matching customer records
        """
        params: Dict[str, Any] = {
            "organization_id": f"eq.{organization_id}"
        }
        if name:
            params["name"] = f"ilike.*{name}*"
        if phone:
            params["phone"] = f"ilike.*{phone}*"
        if national_id:
            params["national_id"] = f"ilike.*{national_id}*"

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/customers",
                params=params,
                headers=self.headers
            )
            response.raise_for_status()
            return response.json()

    async def create_customer(
        self,
        organization_id: str,
        data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Create a new customer record in Supabase

        Args:
            organization_id: The organization UUID the customer belongs to
            data: Dictionary containing customer fields (name, phone, etc.)

        Returns:
            The created customer record from Supabase
        """
        payload = {**data, "organization_id": str(organization_id)}
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/customers",
                json=payload,
                headers=self.headers
            )
            response.raise_for_status()
            return response.json()[0]  # Return the created record


class VehicleRepository:
    """Repository for managing vehicles in Supabase"""

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

    async def search_vehicles(
        self,
        organization_id: str,
        plate: Optional[str] = None,
        make: Optional[str] = None,
        model: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Search vehicles within an organization

        Filters by organization_id and applies a case-insensitive partial
        match (ilike) for each of plate/make/model that is provided.

        Args:
            organization_id: The organization UUID
            plate: Optional plate fragment to match
            make: Optional make fragment to match
            model: Optional model fragment to match

        Returns:
            List of matching vehicle records
        """
        params: Dict[str, Any] = {
            "organization_id": f"eq.{organization_id}"
        }
        if plate:
            params["plate"] = f"ilike.*{plate}*"
        if make:
            params["make"] = f"ilike.*{make}*"
        if model:
            params["model"] = f"ilike.*{model}*"

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/vehicles",
                params=params,
                headers=self.headers
            )
            response.raise_for_status()
            return response.json()

    async def get_vehicle_by_plate(
        self,
        plate: str,
        organization_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get a single vehicle by plate within an organization

        Args:
            plate: The vehicle plate to look up
            organization_id: The organization UUID

        Returns:
            The matching vehicle record, or None if not found
        """
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/vehicles",
                params={
                    "plate": f"eq.{plate}",
                    "organization_id": f"eq.{organization_id}",
                    "limit": 1
                },
                headers=self.headers
            )
            response.raise_for_status()
            rows = response.json()
            return rows[0] if rows else None

    async def create_vehicle(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create a new vehicle record in Supabase

        Args:
            data: Dictionary containing vehicle fields (plate, make, model, etc.)

        Returns:
            The created vehicle record from Supabase
        """
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/vehicles",
                json=data,
                headers=self.headers
            )
            response.raise_for_status()
            return response.json()[0]  # Return the created record


class OrderRepository:
    """Repository for managing orders in Supabase"""

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

    async def create_order(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create a new order record in Supabase

        Args:
            data: Dictionary containing order fields (organization_id,
                customer_id, vehicle_id, received_at, etc.)

        Returns:
            The created order record from Supabase (including DB-generated
            fields such as id, date_order and total_amount)
        """
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/orders",
                json=data,
                headers=self.headers
            )
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                # Surface the real PostgREST error (the failing column /
                # constraint) instead of swallowing it into a dict that would
                # then break OrderOut validation in the service layer.
                detail = response.json() if response.text else str(exc)
                logger.error("Error creating order: %s", detail)
                raise HTTPException(status_code=response.status_code, detail=detail)
            return response.json()[0]  # Return the created record
