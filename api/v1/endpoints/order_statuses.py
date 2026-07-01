"""
API endpoints for order status management.

Provides CRUD operations for order statuses (workshop and followup types).
"""

from typing import Optional

from fastapi import APIRouter, Path, Query

from schemas.order_status import (
    OrderStatusCreate,
    OrderStatusList,
    OrderStatusOut,
    OrderStatusUpdate,
)
from services import order_statuses_service

router = APIRouter()


@router.post(
    "",
    response_model=OrderStatusOut,
    status_code=201,
    summary="Create a new order status",
    tags=["order-statuses"],
)
async def create_order_status(data: OrderStatusCreate):
    """
    Create a new order status.

    **Args:**
    - **status_type**: Type of status ('workshop' or 'followup')
    - **code**: Unique code identifier (e.g., 'recibido', 'en_proceso')
    - **label**: Human-readable display label
    - **sort_order**: Order for displaying (lower = earlier in sequence)
    - **is_terminal**: Whether this is a final status (optional, default False)

    **Returns:**
    - Created order status with ID and timestamp

    **Raises:**
    - **409**: Status code already exists
    - **400**: Invalid data
    """
    return await order_statuses_service.create_status(data)


@router.get(
    "",
    response_model=OrderStatusList,
    summary="List all order statuses",
    tags=["order-statuses"],
)
async def list_order_statuses(
    status_type: Optional[str] = Query(
        None, description="Filter by status type ('workshop' or 'followup')"
    ),
    limit: int = Query(100, ge=1, le=500, description="Maximum records to return"),
    offset: int = Query(0, ge=0, description="Number of records to skip"),
):
    """
    List all order statuses with optional filtering.

    Returns statuses ordered by type and sort_order.
    Includes counts for workshop and followup statuses.

    **Query Parameters:**
    - **status_type**: Optional filter ('workshop' or 'followup')
    - **limit**: Max records (1-500, default 100)
    - **offset**: Records to skip (default 0)

    **Returns:**
    - List of statuses with total and type-specific counts
    """
    return await order_statuses_service.list_statuses(status_type, limit, offset)


@router.get(
    "/{status_id}",
    response_model=OrderStatusOut,
    summary="Get order status by ID",
    tags=["order-statuses"],
)
async def get_order_status(
    status_id: str = Path(..., description="UUID of the order status"),
):
    """
    Get a single order status by its UUID.

    **Path Parameters:**
    - **status_id**: UUID of the status

    **Returns:**
    - Order status details

    **Raises:**
    - **404**: Status not found
    """
    return await order_statuses_service.get_status_by_id(status_id)


@router.get(
    "/code/{code}",
    response_model=OrderStatusOut,
    summary="Get order status by code",
    tags=["order-statuses"],
)
async def get_order_status_by_code(
    code: str = Path(..., description="Status code (e.g., 'recibido', 'en_proceso')"),
):
    """
    Get a single order status by its unique code.

    **Path Parameters:**
    - **code**: Status code identifier

    **Returns:**
    - Order status details

    **Raises:**
    - **404**: Status not found
    """
    return await order_statuses_service.get_status_by_code(code)


@router.patch(
    "/{status_id}",
    response_model=OrderStatusOut,
    summary="Update an order status",
    tags=["order-statuses"],
)
async def update_order_status(
    data: OrderStatusUpdate,
    status_id: str = Path(..., description="UUID of the order status"),
):
    """
    Update an existing order status.

    All fields are optional. Only provided fields will be updated.

    **Path Parameters:**
    - **status_id**: UUID of the status to update

    **Body (all optional):**
    - **status_type**: Change status type
    - **code**: Update code (must be unique)
    - **label**: Update display label
    - **sort_order**: Update ordering
    - **is_terminal**: Update terminal flag

    **Returns:**
    - Updated order status

    **Raises:**
    - **404**: Status not found
    - **409**: New code conflicts with existing status
    - **400**: No fields provided for update
    """
    return await order_statuses_service.update_status(status_id, data)


@router.delete(
    "/{status_id}",
    summary="Delete an order status",
    tags=["order-statuses"],
)
async def delete_order_status(
    status_id: str = Path(..., description="UUID of the order status"),
):
    """
    Delete an order status.

    **Warning:** This will fail if the status is referenced by:
    - Existing orders (orders.order_status)
    - Order status history records

    **Path Parameters:**
    - **status_id**: UUID of the status to delete

    **Returns:**
    - Success message

    **Raises:**
    - **404**: Status not found
    - **409**: Status is referenced and cannot be deleted
    """
    return await order_statuses_service.delete_status(status_id)
