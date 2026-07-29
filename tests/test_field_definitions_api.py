"""
Manual test script for the custom fields API.

Prereqs: server running against the STAGE Supabase project, and ORG_ID set to
a real organization id in that DB. Run: python tests/test_field_definitions_api.py
"""

import asyncio
import os

import httpx

BASE = "http://localhost:8000/api"
ORG_ID = os.environ.get("ORG_ID", "REPLACE_WITH_STAGE_ORG_ID")


async def main():
    async with httpx.AsyncClient() as client:
        print("1. Create a field definition")
        r = await client.post(
            f"{BASE}/field-definitions",
            params={"organization_id": ORG_ID},
            json={
                "field_name": "¿Requiere de contacto?",
                "field_type": "dropdown",
                "field_options": ["Sí", "No"],
                "required": True,
                "display_order": 0,
            },
        )
        print("  status:", r.status_code)
        field = r.json()
        field_id = field["id"]
        print("  created id:", field_id)

        print("2. List field definitions")
        r = await client.get(f"{BASE}/field-definitions", params={"organization_id": ORG_ID})
        print("  status:", r.status_code, "count:", len(r.json()))

        print("3. Delete the field definition")
        r = await client.delete(f"{BASE}/field-definitions/{field_id}")
        print("  status:", r.status_code, "(expect 204)")


if __name__ == "__main__":
    asyncio.run(main())
