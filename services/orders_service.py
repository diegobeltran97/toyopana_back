import logging
from typing import Any, Dict, List, Optional

from fastapi import HTTPException

from repositories.orders import (
    CustomerRepository,
    VehicleRepository,
    OrderRepository,
)
from repositories.order_files import OrderFileRepository
from schemas.customer import CustomerCreate, CustomerOut
from schemas.vehicle import VehicleCreate, VehicleOut
from schemas.order import OrderCreate, OrderOut, OrderUpdate, OrderFullUpdate
from services import order_files_service

logger = logging.getLogger(__name__)


async def find_or_create_customer(
    organization_id: str,
    data: CustomerCreate,
) -> CustomerOut:
    """
    Return an existing customer (matched by national_id within the
    organization) or create a new one.

    Args:
        organization_id: The organization the customer belongs to
        data: Validated customer payload

    Returns:
        CustomerOut for the existing or newly created customer
    """
    repo = CustomerRepository()

    # 1. Try to find an existing customer by national_id within the org
    if data.national_id:
        matches = await repo.search_customers(
            organization_id,
            national_id=data.national_id,
        )
        if matches:
            logger.info(
                "Customer matched by national_id in org %s", organization_id
            )
            return CustomerOut.model_validate(matches[0])

    # 2. Not found (or no national_id) -> create a new customer
    created = await repo.create_customer(
        organization_id,
        data.model_dump(mode="json"),
    )
    logger.info("Customer created in org %s", organization_id)
    return CustomerOut.model_validate(created)


async def find_or_create_vehicle(
    organization_id: str,
    data: VehicleCreate,
) -> VehicleOut:
    """
    Return an existing vehicle (matched by plate within the organization)
    or create a new one.

    If the vehicle already exists, the DB record is returned as-is — its
    make/model/year are treated as the source of truth even if they differ
    from what the user typed.

    Args:
        organization_id: The organization the vehicle belongs to
        data: Validated vehicle payload

    Returns:
        VehicleOut for the existing or newly created vehicle
    """
    repo = VehicleRepository()

    # 1. Try to find an existing vehicle by plate within the org
    existing = await repo.get_vehicle_by_plate(data.plate, organization_id)
    if existing:
        logger.info(
            "Vehicle matched by plate %s in org %s", data.plate, organization_id
        )
        # 2. Return DB truth (make/model/year may differ from user input)
        return VehicleOut.model_validate(existing)

    # 3. Not found -> create a new vehicle
    created = await repo.create_vehicle(data.model_dump(mode="json"))
    logger.info("Vehicle created with plate %s in org %s", data.plate, organization_id)
    return VehicleOut.model_validate(created)


async def create_order(data: OrderCreate) -> OrderOut:
    """
    Create an order and return it.

    Args:
        data: Validated order payload

    Returns:
        OrderOut including DB-generated fields (id, date_order, total_amount)
    """
    repo = OrderRepository()
    
    
   
    created = await repo.create_order(data.model_dump(mode="json"))
    logger.info("Order created in org %s", data.organization_id)
    return OrderOut.model_validate(created)


async def get_full_order_details(
    organization_id: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    sign_urls: bool = True,
) -> List[Dict[str, Any]]:
    """
    Return all orders with their customer, vehicle and files nested.

    Each order is a dict with embedded "customer", "vehicle" and an
    "order_files" array. Because the bucket is private, every file gets a
    short-lived `signed_url` (unless `sign_urls` is False) so the frontend
    can render it directly.

    Args:
        organization_id: Optional org filter
        status: Optional status filter
        limit: Max number of orders to return
        offset: Pagination offset
        sign_urls: Whether to attach signed URLs to embedded files

    Returns:
        A list of nested order dicts.
    """
    repo = OrderRepository()
    orders = await repo.list_full_details(
        organization_id=organization_id,
        status=status,
        limit=limit,
        offset=offset,
    )

    if sign_urls:
        # Collect every file path across all orders and sign them in one
        # concurrent batch, then map the signed URLs back onto each file.
        paths = [
            file["file_url"]
            for order in orders
            for file in (order.get("order_files") or [])
            if file.get("file_url")
        ]
        signed = await order_files_service.sign_paths(paths)
        for order in orders:
            for file in order.get("order_files") or []:
                file["signed_url"] = signed.get(file.get("file_url"))

    logger.info("Returned full details for %d order(s)", len(orders))
    return orders


async def get_full_order_detail_by_id(
    order_id: str,
    sign_urls: bool = True,
) -> Dict[str, Any]:
    repo = OrderRepository()
    order = await repo.get_full_detail_by_id(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    if sign_urls:
        paths = [
            file["file_url"]
            for file in (order.get("order_files") or [])
            if file.get("file_url")
        ]
        signed = await order_files_service.sign_paths(paths)
        for file in order.get("order_files") or []:
            file["signed_url"] = signed.get(file.get("file_url"))

    return order


async def update_full_order_detail(
    order_id: str,
    data: OrderFullUpdate,
) -> Dict[str, Any]:
    repo = OrderRepository()
    current_order: Optional[Dict[str, Any]] = None

    if data.order:
        payload = data.order.model_dump(mode="json", exclude_unset=True)
        if payload:
            new_status = payload.get("order_status")
            if new_status:
                current_order = await repo.get_full_detail_by_id(order_id)
                if not current_order:
                    raise HTTPException(status_code=404, detail="Order not found")

            updated = await repo.update_order(order_id, payload)
            if not updated:
                raise HTTPException(status_code=404, detail="Order not found")

            if new_status and current_order:
                print("hey time to change your history:", current_order)
                from_status = current_order.get("order_status")
                if from_status != new_status:
                    await repo.create_status_history({
                        "order_id": str(order_id),
                        "organization_id": str(current_order["organization_id"]),
                        "status_type": "workshop",
                        "from_status": from_status,
                        "to_status": new_status,
                    })

    if data.customer or data.vehicle:
        if current_order is None:
            current_order = await repo.get_full_detail_by_id(order_id)
            if not current_order:
                raise HTTPException(status_code=404, detail="Order not found")

        if data.customer:
            customer_id = (current_order.get("customer") or {}).get("id")
            if customer_id:
                customer_repo = CustomerRepository()
                await customer_repo.update_customer(str(customer_id), data.customer)

        if data.vehicle:
            vehicle_id = (current_order.get("vehicle") or {}).get("id")
            if vehicle_id:
                vehicle_repo = VehicleRepository()
                await vehicle_repo.update_vehicle(str(vehicle_id), data.vehicle)

    return await get_full_order_detail_by_id(order_id)


async def update_order(order_id: str, data: OrderUpdate) -> OrderOut:
    """
    Apply a partial update to an order and return the updated record.

    Only the fields explicitly sent are written (so omitted fields keep
    their current value). Raises 404 if the order doesn't exist.
    When `status` is included, a row is inserted into order_status_history.
    """
    payload = data.model_dump(mode="json", exclude_unset=True)
    if not payload:
        raise HTTPException(status_code=400, detail="No fields to update")

    repo = OrderRepository()

    new_status = payload.get("status")
    current_order = None
    if new_status:
        current_order = await repo.get_full_detail_by_id(str(order_id))
        if not current_order:
            raise HTTPException(status_code=404, detail="Order not found")

    updated = await repo.update_order(str(order_id), payload)
    if not updated:
        raise HTTPException(status_code=404, detail="Order not found")

    if new_status and current_order:
        from_status = current_order.get("order_status")
        if from_status != new_status:
            await repo.create_status_history({
                "order_id": str(order_id),
                "organization_id": str(current_order["organization_id"]),
                "status_type": "workshop",
                "from_status": from_status,
                "to_status": new_status,
            })

    logger.info("Order %s updated (%s)", order_id, ", ".join(payload.keys()))
    return OrderOut.model_validate(updated)


async def delete_order(order_id: str) -> None:
    """
    Delete an order and clean up its Storage files.

    Child rows are removed by ON DELETE CASCADE; we additionally collect the
    order's file paths beforehand and remove the matching Storage objects so
    the private bucket doesn't accumulate orphans. Raises 404 if not found.
    """
    # 1. Grab file paths first — after the cascade delete the rows are gone.
    file_repo = OrderFileRepository()
    files = await file_repo.list_by_order(str(order_id))
    paths = [f["file_url"] for f in files if f.get("file_url")]

    # 2. Delete the order (cascades to order_files / items / field_values).
    repo = OrderRepository()
    deleted = await repo.delete_order(str(order_id))
    if not deleted:
        raise HTTPException(status_code=404, detail="Order not found")

    # 3. Best-effort Storage cleanup for the files we just orphaned.
    if paths:
        await order_files_service.remove_paths(paths)

    logger.info("Order %s deleted (%d file(s) cleaned)", order_id, len(paths))
