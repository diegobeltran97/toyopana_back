import logging
from statistics import mean
from typing import Any, Dict, List, Optional

from fastapi import HTTPException

from repositories.orders import CustomerRepository

logger = logging.getLogger(__name__)


async def list_customers(
    organization_id: str,
    search: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    """
    Return the client directory for an organization, each row annotated with
    its visit count.

    Args:
        organization_id: The organization UUID to list customers for
        search: Optional term matched against name/phone/national_id
        limit: Max customers to return
        offset: Pagination offset

    Returns:
        A list of dicts shaped like CustomerListItem (raw `orders` embed
        replaced by a flat `visitas` count).
    """
    repo = CustomerRepository()
    rows = await repo.list_with_order_counts(
        organization_id, search=search, limit=limit, offset=offset
    )

    customers: List[Dict[str, Any]] = []
    for row in rows:
        orders_count = row.pop("orders", None)
        visitas = orders_count[0]["count"] if orders_count else 0
        customers.append({**row, "visitas": visitas})

    logger.info(
        "Listed %d customer(s) for org %s (search=%r)",
        len(customers),
        organization_id,
        search,
    )
    return customers


async def get_customer_detail(customer_id: str) -> Dict[str, Any]:
    """
    Return a customer's full profile: identity, visit stats and order
    history, shaped for the CustomerDetail schema.

    Args:
        customer_id: The customer UUID

    Returns:
        A dict matching CustomerDetail.

    Raises:
        HTTPException: 404 if no customer matches the given id.
    """
    repo = CustomerRepository()
    row = await repo.get_detail_with_orders(customer_id)
    if not row:
        raise HTTPException(status_code=404, detail="Customer not found")

    orders: List[Dict[str, Any]] = row.pop("orders", None) or []

    # Flatten the embedded technician object ({"name": ...} | None) -> str | None
    for order in orders:
        technician = order.get("technician")
        order["technician"] = technician["name"] if technician else None

    visitas = len(orders)
    amounts = [
        order["total_amount"]
        for order in orders
        if order.get("total_amount") is not None
    ]
    ticket_promedio = round(mean(amounts), 2) if amounts else None
    is_frequent = visitas >= 5

    logger.info("Fetched detail for customer %s (%d order(s))", customer_id, visitas)

    return {
        **row,
        "visitas": visitas,
        "ticket_promedio": ticket_promedio,
        "is_frequent": is_frequent,
        "orders": orders,
    }
