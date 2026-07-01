"""
Business logic for order status management.

This service handles validation, business rules, and orchestration
for order status operations.
"""

import logging
from typing import Dict, List, Optional

from fastapi import HTTPException

from core.config import settings
from repositories.order_statuses import OrderStatusRepository
from schemas.order_status import (
    OrderStatusCreate,
    OrderStatusList,
    OrderStatusOut,
    OrderStatusUpdate,
)

logger = logging.getLogger(__name__)

# Initialize repository
_repo = OrderStatusRepository(
    base_url=settings.SUPABASE_URL,
    api_key=settings.SUPABASE_SERVICE_ROLE_KEY,
)


async def create_status(data: OrderStatusCreate) -> OrderStatusOut:
    """
    Create a new order status.

    Args:
        data: Status creation data

    Returns:
        Created status

    Raises:
        HTTPException 409: If status code already exists
        HTTPException 400: If validation fails
    """
    # Check if code already exists
    existing = await _repo.get_status_by_code(data.code)
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Status code '{data.code}' already exists",
        )

    # Create the status
    status_dict = data.model_dump()
    created = await _repo.create_status(status_dict)

    return OrderStatusOut(**created)


async def get_status_by_id(status_id: str) -> OrderStatusOut:
    """
    Get an order status by ID.

    Args:
        status_id: UUID of the status

    Returns:
        Status details

    Raises:
        HTTPException 404: If status not found
    """
    status = await _repo.get_status_by_id(status_id)
    if not status:
        raise HTTPException(status_code=404, detail="Status not found")

    return OrderStatusOut(**status)


async def get_status_by_code(code: str) -> OrderStatusOut:
    """
    Get an order status by code.

    Args:
        code: Status code

    Returns:
        Status details

    Raises:
        HTTPException 404: If status not found
    """
    status = await _repo.get_status_by_code(code)
    if not status:
        raise HTTPException(status_code=404, detail=f"Status '{code}' not found")

    return OrderStatusOut(**status)


async def list_statuses(
    status_type: Optional[str] = None, limit: int = 100, offset: int = 0
) -> OrderStatusList:
    """
    List all order statuses with pagination and filtering.

    Args:
        status_type: Optional filter by 'workshop' or 'followup'
        limit: Maximum number of records to return
        offset: Number of records to skip

    Returns:
        Paginated list of statuses with counts
    """
    # Validate status_type if provided
    if status_type and status_type not in ["workshop", "followup"]:
        raise HTTPException(
            status_code=400,
            detail="status_type must be 'workshop' or 'followup'",
        )

    # Get statuses and counts in parallel
    statuses = await _repo.list_statuses(status_type, limit, offset)
    counts = await _repo.count_statuses(status_type)

    return OrderStatusList(
        statuses=[OrderStatusOut(**s) for s in statuses],
        total=counts["total"],
        workshop_count=counts["workshop_count"],
        followup_count=counts["followup_count"],
    )


async def update_status(status_id: str, data: OrderStatusUpdate) -> OrderStatusOut:
    """
    Update an order status.

    Args:
        status_id: UUID of the status to update
        data: Fields to update

    Returns:
        Updated status

    Raises:
        HTTPException 404: If status not found
        HTTPException 409: If new code conflicts with existing status
        HTTPException 400: If update is empty
    """
    # Check if status exists
    existing = await _repo.get_status_by_id(status_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Status not found")

    # Get only provided fields
    update_dict = data.model_dump(exclude_unset=True)
    if not update_dict:
        raise HTTPException(status_code=400, detail="No fields to update")

    # If code is being updated, check for conflicts
    if "code" in update_dict and update_dict["code"] != existing["code"]:
        code_check = await _repo.get_status_by_code(update_dict["code"])
        if code_check:
            raise HTTPException(
                status_code=409,
                detail=f"Status code '{update_dict['code']}' already exists",
            )

    # Update the status
    updated = await _repo.update_status(status_id, update_dict)
    if not updated:
        raise HTTPException(status_code=404, detail="Status not found")

    return OrderStatusOut(**updated)


async def delete_status(status_id: str) -> Dict[str, str]:
    """
    Delete an order status.

    Note: Will fail if status is referenced by orders or order_status_history.

    Args:
        status_id: UUID of the status to delete

    Returns:
        Success message

    Raises:
        HTTPException 404: If status not found
        HTTPException 409: If status is referenced by orders
    """
    # Check if status exists
    existing = await _repo.get_status_by_id(status_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Status not found")

    # Attempt to delete (will raise if foreign key constraint fails)
    try:
        await _repo.delete_status(status_id)
        return {"message": f"Status '{existing['code']}' deleted successfully"}
    except HTTPException as exc:
        if exc.status_code == 409 or "foreign key" in str(exc.detail).lower():
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Cannot delete status '{existing['code']}' because it is "
                    "referenced by existing orders or status history"
                ),
            )
        raise
