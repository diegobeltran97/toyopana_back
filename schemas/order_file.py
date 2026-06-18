import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class OrderFileOut(BaseModel):
    """A single file attached to an order.

    `file_url` stores the object path inside the private `order-files`
    bucket (e.g. ``<order_id>/<uuid>-photo.jpg``). Since the bucket is
    private, `signed_url` carries a short-lived URL the frontend can use
    to actually display/download the file.
    """

    id: uuid.UUID
    order_id: uuid.UUID
    uploaded_by: Optional[uuid.UUID] = None
    file_url: str  # storage object path within the bucket
    file_type: Optional[str] = None  # MIME type, e.g. "image/jpeg"
    label: Optional[str] = None
    uploaded_at: datetime
    signed_url: Optional[str] = None  # generated on read, not stored

    model_config = ConfigDict(from_attributes=True)


class OrderFileUpdate(BaseModel):
    """Editable metadata on an order file (the bytes are immutable)."""

    label: Optional[str] = Field(default=None, max_length=255)
    file_type: Optional[str] = Field(default=None, max_length=255)
