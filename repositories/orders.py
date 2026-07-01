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

        Filters by organization_id and matches a case-insensitive partial
        (ilike) on ANY of the provided fields (name / phone / national_id),
        so a single search term can hit any of them.

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

        # Top-level PostgREST filters are AND-ed, so combine the provided
        # field matches under an `or=(...)` group to get OR semantics.
        or_filters: List[str] = []
        if name:
            or_filters.append(f"name.ilike.*{name}*")
        if phone:
            or_filters.append(f"phone.ilike.*{phone}*")
        if national_id:
            or_filters.append(f"national_id.ilike.*{national_id}*")
        if or_filters:
            params["or"] = "(" + ",".join(or_filters) + ")"

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/customers",
                params=params,
                headers=self.headers
            )
            response.raise_for_status()
            return response.json()

    async def update_customer(
        self, customer_id: str, data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        async with httpx.AsyncClient() as client:
            response = await client.patch(
                f"{self.base_url}/customers",
                params={"id": f"eq.{customer_id}"},
                json=data,
                headers=self.headers,
            )
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                detail = response.json() if response.text else str(exc)
                logger.error("Error updating customer %s: %s", customer_id, detail)
                raise HTTPException(status_code=response.status_code, detail=detail)
            rows = response.json()
            return rows[0] if rows else None

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

        Filters by organization_id and matches a case-insensitive partial
        (ilike) on ANY of the provided fields (plate / make / model), so a
        single search term can hit any of them.

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

        # Top-level PostgREST filters are AND-ed, so combine the provided
        # field matches under an `or=(...)` group to get OR semantics.
        or_filters: List[str] = []
        if plate:
            or_filters.append(f"plate.ilike.*{plate}*")
        if make:
            or_filters.append(f"make.ilike.*{make}*")
        if model:
            or_filters.append(f"model.ilike.*{model}*")
        if or_filters:
            params["or"] = "(" + ",".join(or_filters) + ")"

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

    async def update_vehicle(
        self, vehicle_id: str, data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        async with httpx.AsyncClient() as client:
            response = await client.patch(
                f"{self.base_url}/vehicles",
                params={"id": f"eq.{vehicle_id}"},
                json=data,
                headers=self.headers,
            )
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                detail = response.json() if response.text else str(exc)
                logger.error("Error updating vehicle %s: %s", vehicle_id, detail)
                raise HTTPException(status_code=response.status_code, detail=detail)
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

    async def get_full_detail_by_id(
        self, order_id: str
    ) -> Optional[Dict[str, Any]]:
        params = {
            "id": f"eq.{order_id}",
            "select": "*,customer:customers(*),vehicle:vehicles(*),order_files(*)",
            "limit": "1",
        }
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/orders",
                params=params,
                headers=self.headers,
            )
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                detail = response.json() if response.text else str(exc)
                logger.error("Error fetching full detail for order %s: %s", order_id, detail)
                raise HTTPException(status_code=response.status_code, detail=detail)
            rows = response.json()
            return rows[0] if rows else None

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

    async def list_full_details(
        self,
        organization_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """
        List orders with their customer, vehicle and files embedded.

        Uses PostgREST resource embedding to return nested JSON in a single
        round trip (no flat cartesian join, no duplicated order rows). The
        embeds are LEFT joins, so EVERY order is returned:
            - "customer": related customers row, or null
            - "vehicle":  related vehicles row, or null
            - "order_files": list of the order's files ([] when none)

        Args:
            organization_id: Optional org filter
            status: Optional status filter
            limit: Max number of orders to return (applies to orders, not rows)
            offset: Pagination offset

        Returns:
            A list of order dicts with embedded relations.
        """
        params: Dict[str, Any] = {
            "select": (
                "*,"
                "customer:customers(*),"
                "vehicle:vehicles(*),"
                "order_files(*)"
            ),
            "order": "date_order.desc",
            "limit": str(limit),
            "offset": str(offset),
        }
        if organization_id:
            params["organization_id"] = f"eq.{organization_id}"
        if status:
            params["order_status"] = f"eq.{status}"

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/orders",
                params=params,
                headers=self.headers,
            )
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                detail = response.json() if response.text else str(exc)
                logger.error("Error listing full order details: %s", detail)
                raise HTTPException(status_code=response.status_code, detail=detail)
            return response.json()

    async def update_order(
        self, order_id: str, data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Patch an order's fields and return the updated record.

        Args:
            order_id: The order UUID to update
            data: Partial fields to set (only the columns provided)

        Returns:
            The updated order record, or None if no order matched.
        """
        async with httpx.AsyncClient() as client:
            response = await client.patch(
                f"{self.base_url}/orders",
                params={"id": f"eq.{order_id}"},
                json=data,
                headers=self.headers,
            )
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                detail = response.json() if response.text else str(exc)
                logger.error("Error updating order %s: %s", order_id, detail)
                raise HTTPException(status_code=response.status_code, detail=detail)
            rows = response.json()
            return rows[0] if rows else None

    async def delete_order(self, order_id: str) -> Optional[Dict[str, Any]]:
        """
        Delete an order and return the deleted record.

        Child rows (order_files, order_items, order_field_values) are removed
        automatically by ON DELETE CASCADE. Storage objects are NOT, so the
        caller is responsible for cleaning the bucket.

        Args:
            order_id: The order UUID to delete

        Returns:
            The deleted order record, or None if no order matched.
        """
        async with httpx.AsyncClient() as client:
            response = await client.delete(
                f"{self.base_url}/orders",
                params={"id": f"eq.{order_id}"},
                headers=self.headers,
            )
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                detail = response.json() if response.text else str(exc)
                logger.error("Error deleting order %s: %s", order_id, detail)
                raise HTTPException(status_code=response.status_code, detail=detail)
            rows = response.json()
            return rows[0] if rows else None
