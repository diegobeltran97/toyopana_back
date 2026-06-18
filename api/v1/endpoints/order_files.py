"""Order files endpoints.

CRUD for the `order_files` table. Files are stored privately in the
`order-files` Storage bucket, organized one folder per order
(`<order_id>/<uuid>-<filename>`). Reads return short-lived signed URLs.

Mounted under `/api/orders`, so the effective paths are:
    POST   /api/orders/{order_id}/files   upload one or more files
    GET    /api/orders/{order_id}/files   list an order's files
    GET    /api/orders/files/{file_id}    get a single file
    PATCH  /api/orders/files/{file_id}    update label / file_type
    DELETE /api/orders/files/{file_id}    delete (Storage + DB)
"""
from typing import List, Optional

from fastapi import APIRouter, File, Form, Path, UploadFile, status

from schemas.order_file import OrderFileOut, OrderFileUpdate
from services import order_files_service

router = APIRouter()


@router.post(
    "/{order_id}/files",
    response_model=List[OrderFileOut],
    status_code=status.HTTP_201_CREATED,
    summary="Upload one or more files for an order",
    tags=["orders"],
)
async def upload_order_files(
    order_id: str = Path(..., description="The order the files belong to"),
    files: List[UploadFile] = File(
        ..., description="One or more files (images or PDF, max 10MB each)"
    ),
    uploaded_by: Optional[str] = Form(
        None, description="app_users.id of the uploader (optional)"
    ),
    label: Optional[str] = Form(
        None, description="Optional label applied to every file in this batch"
    ),
):
    """Upload files into the order's folder and record them in `order_files`.

    Each returned item includes a short-lived `signed_url` the frontend can
    use to display/download the file (the bucket is private).
    """
    return await order_files_service.upload_files_for_order(
        order_id=order_id,
        files=files,
        uploaded_by=uploaded_by,
        label=label,
    )


@router.get(
    "/{order_id}/files",
    response_model=List[OrderFileOut],
    summary="List files for an order",
    tags=["orders"],
)
async def list_order_files(
    order_id: str = Path(..., description="The order to list files for"),
):
    """Return every file attached to an order, each with a fresh signed URL."""
    return await order_files_service.list_files_for_order(order_id)


@router.get(
    "/files/{file_id}",
    response_model=OrderFileOut,
    summary="Get a single order file",
    tags=["orders"],
)
async def get_order_file(
    file_id: str = Path(..., description="The order_files.id"),
):
    """Return a single order file with a fresh signed URL."""
    return await order_files_service.get_file(file_id)


@router.patch(
    "/files/{file_id}",
    response_model=OrderFileOut,
    summary="Update an order file's metadata",
    tags=["orders"],
)
async def update_order_file(
    body: OrderFileUpdate,
    file_id: str = Path(..., description="The order_files.id"),
):
    """Update editable metadata (`label` / `file_type`) on an order file."""
    return await order_files_service.update_file(file_id, body)


@router.delete(
    "/files/{file_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an order file (Storage + DB)",
    tags=["orders"],
)
async def delete_order_file(
    file_id: str = Path(..., description="The order_files.id"),
):
    """Delete an order file from both the database and Storage."""
    await order_files_service.delete_file(file_id)
