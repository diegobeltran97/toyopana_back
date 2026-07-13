from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Path, Query, status


from schemas.customer import CustomerSearch, CustomerCreate, CustomerOut
from schemas.vehicle import VehicleSearch, VehicleCreate, VehicleOut
from schemas.order import OrderCreate, OrderFullCreate, OrderOut, OrderUpdate, OrderFullUpdate
from services import orders_service, order_files_service
from repositories.orders import CustomerRepository, VehicleRepository

router = APIRouter()


@router.post(
    "/customers/search",
    response_model=List[CustomerOut],
    summary="Search customers",
    tags=["orders"],
)
async def search_customers(
    body: CustomerSearch,
    organization_id: str = Query(..., description="Organization to search within"),
):
    """
    Search customers within an organization by name/phone/national_id.

    This is a read, so it goes straight to the repository.
    """
    repo = CustomerRepository()
    return await repo.search_customers(
        organization_id,
        name=body.name,
        phone=body.phone,
        national_id=body.national_id,
    )


@router.post(
    "/customers",
    response_model=CustomerOut,
    summary="Find or create a customer",
    tags=["orders"],
)
async def create_customer(
    body: CustomerCreate,
    organization_id: str = Query(..., description="Organization the customer belongs to"),
):
    """Return an existing customer (matched by national_id) or create a new one."""
    return await orders_service.find_or_create_customer(organization_id, body)


@router.post(
    "/vehicles/search",
    response_model=List[VehicleOut],
    summary="Search vehicles",
    tags=["orders"],
)
async def search_vehicles(
    body: VehicleSearch,
    organization_id: str = Query(..., description="Organization to search within"),
):
    """
    Search vehicles within an organization by plate/make/model.

    This is a read, so it goes straight to the repository.
    """
    repo = VehicleRepository()
    return await repo.search_vehicles(
        organization_id,
        plate=body.plate,
        make=body.make,
        model=body.model,
    )


@router.post(
    "/vehicles",
    response_model=VehicleOut,
    summary="Find or create a vehicle",
    tags=["orders"],
)
async def create_vehicle(body: VehicleCreate):
    """Return an existing vehicle (matched by plate) or create a new one."""
    return await orders_service.find_or_create_vehicle(str(body.organization_id), body)


@router.post(
    "",
    response_model=OrderOut,
    summary="Create an order",
    tags=["orders"],
)
async def create_order(body: OrderCreate):
    """Create an order and return it (id is the order identifier)."""
    
    
    return await orders_service.create_order(body)


@router.get(
    "/fullOrderDetails",
    response_model=List[Dict[str, Any]],
    summary="List all orders with customer, vehicle and files",
    tags=["orders"],
)
async def full_order_details(
    organization_id: Optional[str] = Query(
        None, description="Filter by organization"
    ),
    status: Optional[List[str]] = Query(
        None,
        description=(
            "Filter by one or more order statuses "
            "(recibido/proceso/listo/entregado). Repeat the param to pass "
            "several: ?status=recibido&status=pagado"
        ),
    ),
    limit: int = Query(100, ge=1, le=200, description="Max orders to return"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    sign_urls: bool = Query(
        True, description="Attach short-lived signed URLs to each file"
    ),
):
    """
    Return all orders, each with its `customer`, `vehicle` and `order_files[]`
    nested. Orders without files are still included (files = []). Private files
    come with a fresh `signed_url` per file unless `sign_urls=false`.
    """
    return await orders_service.get_full_order_details(
        organization_id=organization_id,
        status=status,
        limit=limit,
        offset=offset,
        sign_urls=sign_urls,
    )


@router.post("/fullOrder",
             response_model=OrderOut,
             summary="Create an order with files",
             tags=["orders"]
             )
async def create_full_order(body: OrderFullCreate) -> OrderOut:
    """Create an order and return it with his files """
    


    
    # Define the properties to remove
    to_remove = ["files", "uploaded_by", "label"]
    
    for prop in to_remove:
        delattr(body, prop)
    
    order = await orders_service.create_order(body)


    return order


@router.get(
    "/fullOrderDetails/{order_id}",
    response_model=Dict[str, Any],
    summary="Get a single order with customer, vehicle and files",
    tags=["orders"],
)
async def get_full_order_detail(
    order_id: str = Path(..., description="The order id"),
    sign_urls: bool = Query(True, description="Attach signed URLs to files"),
):
    return await orders_service.get_full_order_detail_by_id(order_id, sign_urls=sign_urls)


@router.patch(
    "/fullOrderDetails/{order_id}",
    response_model=Dict[str, Any],
    summary="Update order, customer, and/or vehicle fields",
    tags=["orders"],
)
async def update_full_order_detail(
    body: OrderFullUpdate,
    order_id: str = Path(..., description="The order id"),
):
    return await orders_service.update_full_order_detail(order_id, body)


@router.patch(
    "/{order_id}",
    response_model=OrderOut,
    summary="Update an order",
    tags=["orders"],
)
async def update_order(
    body: OrderUpdate,
    order_id: str = Path(..., description="The order id to update"),
) -> OrderOut:
    """Partially update an order (only the fields provided are changed)."""
    return await orders_service.update_order(order_id, body)


@router.delete(
    "/{order_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an order",
    tags=["orders"],
)
async def delete_order(
    order_id: str = Path(..., description="The order id to delete"),
):
    """Delete an order and its files (DB rows cascade; Storage is cleaned up)."""
    await orders_service.delete_order(order_id)
    
    
    
