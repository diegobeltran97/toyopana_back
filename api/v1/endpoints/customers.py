from typing import List, Optional

from fastapi import APIRouter, Path, Query

from schemas.customer import CustomerDetail, CustomerListItem
from services import customers_service

router = APIRouter()


@router.get(
    "",
    response_model=List[CustomerListItem],
    summary="List customers with visit counts",
    tags=["customers"],
)
async def list_customers(
    organization_id: str = Query(..., description="Organization to list customers for"),
    search: Optional[str] = Query(
        None, description="Filter by name/phone/national_id (case-insensitive partial match)"
    ),
    limit: int = Query(100, ge=1, le=200, description="Max customers to return"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
):
    """
    Return the client directory for an organization.

    Each customer row is annotated with `visitas` (total order count),
    computed via a single PostgREST embedded-count query. This route is
    intentionally open (no auth dependency), matching the sibling
    `/orders/customers/*` routes.
    """
    return await customers_service.list_customers(
        organization_id, search=search, limit=limit, offset=offset
    )


@router.get(
    "/{customer_id}",
    response_model=CustomerDetail,
    summary="Get a customer's profile with order history",
    tags=["customers"],
)
async def get_customer_detail(
    customer_id: str = Path(..., description="The customer id"),
):
    """
    Return a single customer's profile: identity, visit stats
    (`visitas`, `ticket_promedio`, `is_frequent`) and full order history with
    each order's vehicle and technician embedded. Raises 404 if the customer
    doesn't exist.
    """
    return await customers_service.get_customer_detail(customer_id)
