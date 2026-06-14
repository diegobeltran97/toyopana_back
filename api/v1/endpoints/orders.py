from typing import List

from fastapi import APIRouter, Query

from schemas.customer import CustomerSearch, CustomerCreate, CustomerOut
from schemas.vehicle import VehicleSearch, VehicleCreate, VehicleOut
from schemas.order import OrderCreate, OrderOut
from services import orders_service
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
