"""
Manual test script for order statuses API endpoints.

Run this after starting the server to verify the CRUD operations work.
"""

import httpx
import asyncio


BASE_URL = "http://localhost:8000/api/order-statuses"


async def test_order_statuses_crud():
    """Test all CRUD operations for order statuses."""

    async with httpx.AsyncClient() as client:
        print("=" * 60)
        print("Testing Order Statuses CRUD API")
        print("=" * 60)

        # Test 1: List all statuses
        print("\n1. GET /api/order-statuses - List all statuses")
        response = await client.get(BASE_URL)
        print(f"Status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"Total statuses: {data['total']}")
            print(f"Workshop statuses: {data['workshop_count']}")
            print(f"Followup statuses: {data['followup_count']}")
            print(f"First status: {data['statuses'][0] if data['statuses'] else 'None'}")

        # Test 2: Filter by workshop
        print("\n2. GET /api/order-statuses?status_type=workshop - Filter workshop")
        response = await client.get(f"{BASE_URL}?status_type=workshop")
        print(f"Status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"Workshop statuses found: {len(data['statuses'])}")
            for status in data['statuses'][:3]:
                print(f"  - {status['code']}: {status['label']} (order: {status['sort_order']})")

        # Test 3: Get by code
        print("\n3. GET /api/order-statuses/code/recibido - Get by code")
        response = await client.get(f"{BASE_URL}/code/recibido")
        print(f"Status: {response.status_code}")
        if response.status_code == 200:
            status = response.json()
            print(f"Found: {status['label']} (type: {status['status_type']})")

        # Test 4: Create new status (for testing only)
        print("\n4. POST /api/order-statuses - Create new status")
        new_status = {
            "status_type": "workshop",
            "code": "test_status",
            "label": "Test Status",
            "sort_order": 999,
            "is_terminal": False
        }
        response = await client.post(BASE_URL, json=new_status)
        print(f"Status: {response.status_code}")
        created_id = None
        if response.status_code == 201:
            created = response.json()
            created_id = created['id']
            print(f"Created: {created['label']} (ID: {created_id})")
        elif response.status_code == 409:
            print("Status already exists (expected if running multiple times)")
            # Try to get the existing one
            response = await client.get(f"{BASE_URL}/code/test_status")
            if response.status_code == 200:
                created_id = response.json()['id']

        # Test 5: Update status
        if created_id:
            print(f"\n5. PATCH /api/order-statuses/{created_id} - Update status")
            update_data = {
                "label": "Updated Test Status",
                "sort_order": 1000
            }
            response = await client.patch(f"{BASE_URL}/{created_id}", json=update_data)
            print(f"Status: {response.status_code}")
            if response.status_code == 200:
                updated = response.json()
                print(f"Updated: {updated['label']} (order: {updated['sort_order']})")

        # Test 6: Get by ID
        if created_id:
            print(f"\n6. GET /api/order-statuses/{created_id} - Get by ID")
            response = await client.get(f"{BASE_URL}/{created_id}")
            print(f"Status: {response.status_code}")
            if response.status_code == 200:
                status = response.json()
                print(f"Found: {status['label']}")

        # Test 7: Delete status
        if created_id:
            print(f"\n7. DELETE /api/order-statuses/{created_id} - Delete status")
            response = await client.delete(f"{BASE_URL}/{created_id}")
            print(f"Status: {response.status_code}")
            if response.status_code == 200:
                result = response.json()
                print(f"Result: {result['message']}")

        print("\n" + "=" * 60)
        print("Tests completed!")
        print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_order_statuses_crud())
