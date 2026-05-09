import httpx
from typing import Optional
from core.config import settings


class AttachmentRepository:
    """Repository for pipefy_attachments table using Supabase REST API."""

    def __init__(self):
        self.base_url = f"{settings.SUPABASE_URL}/rest/v1"
        self.headers = {
            "apikey": settings.SUPABASE_SERVICE_ROLE_KEY,
            "Authorization": f"Bearer {settings.SUPABASE_SERVICE_ROLE_KEY}",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        }

    async def get_by_storage_path(self, storage_path: str) -> Optional[dict]:
        print(f"Querying for existing attachment with storage_path={storage_path}")
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/pipefy_attachments",
                    headers=self.headers,
                    params={"storage_path": f"eq.{storage_path}", "limit": "1"},
                )
                response.raise_for_status()
                data = response.json()
                print(f"Queried for storage_path={storage_path}, found {len(data)} records")
                return data[0] if data else None
        except httpx.HTTPError as e:
            print(f"Error querying for storage_path={storage_path}: {str(e)}")
            return None

    async def get_by_card_id(self, pipefy_card_id: str) -> list[dict]:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/pipefy_attachments",
                headers=self.headers,
                params={"pipefy_card_id": f"eq.{pipefy_card_id}"},
            )
            response.raise_for_status()
            return response.json()

    async def upsert(self, record: dict) -> dict:
        headers = {
            **self.headers,
            "Prefer": "resolution=merge-duplicates,return=representation",
        }
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/pipefy_attachments",
                headers=headers,
                json=record,
            )
            response.raise_for_status()
            data = response.json()
            return data[0] if isinstance(data, list) else data
