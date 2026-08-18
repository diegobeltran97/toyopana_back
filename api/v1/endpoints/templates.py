"""HTTP routes for message templates, mounted at /api/templates.

Every route is authenticated and derives the organization from the token --
templates are tenant-owned copy that gets sent to real customers, so the org
must never be client-supplied.

Read-only listing for the send flow lives at GET /api/messaging/templates;
this module is the authoring surface.
"""

import logging
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Path, status
from pydantic import BaseModel, Field

from api.deps import get_current_user
from services import templates_service

router = APIRouter()
logger = logging.getLogger(__name__)


def require_organization_id(current_user: dict) -> str:
    """Pull the caller's organization out of the authenticated user."""
    organization_id = current_user.get("organization_id")
    if not organization_id:
        raise HTTPException(
            status_code=403, detail="El usuario no pertenece a una organización"
        )
    return str(organization_id)


class TemplateCreate(BaseModel):
    """A new template. `params` must match the {placeholders} in `body`."""

    name: str = Field(..., min_length=1, description="Unique name within the org")
    body: str = Field(..., min_length=1, description="Copy with {param} placeholders")
    params: List[str] = Field(
        default_factory=list, description="Parameter names the body uses"
    )
    language: str = Field("es", description="Template language code")


class TemplateUpdate(BaseModel):
    """A partial edit. Body/params are validated together against the result."""

    name: Optional[str] = Field(None, min_length=1)
    body: Optional[str] = Field(None, min_length=1)
    params: Optional[List[str]] = None
    language: Optional[str] = None
    is_active: Optional[bool] = None


class TemplateRead(BaseModel):
    """A stored template."""

    id: str
    name: str
    body: str
    params: List[str]
    language: str
    is_active: bool
    provider_template_name: Optional[str] = None
    approval_status: Optional[str] = None


def _to_read(row: Dict) -> TemplateRead:
    return TemplateRead(
        id=row["id"],
        name=row["name"],
        body=row["body"],
        params=list(row.get("params") or []),
        language=row.get("language") or "es",
        is_active=bool(row.get("is_active", True)),
        provider_template_name=row.get("provider_template_name"),
        approval_status=row.get("approval_status"),
    )


@router.get(
    "",
    response_model=List[TemplateRead],
    summary="List the organization's message templates",
)
async def list_templates(
    current_user: dict = Depends(get_current_user),
) -> List[TemplateRead]:
    rows = await templates_service.list_templates(require_organization_id(current_user))
    return [_to_read(row) for row in rows]


@router.post(
    "",
    response_model=TemplateRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a message template",
)
async def create_template(
    payload: TemplateCreate,
    current_user: dict = Depends(get_current_user),
) -> TemplateRead:
    row = await templates_service.create_template(
        require_organization_id(current_user),
        payload.model_dump(exclude_none=True),
    )
    return _to_read(row)


@router.patch(
    "/{template_id}",
    response_model=TemplateRead,
    summary="Edit a message template",
)
async def update_template(
    template_id: str = Path(..., description="Template id"),
    payload: TemplateUpdate = ...,
    current_user: dict = Depends(get_current_user),
) -> TemplateRead:
    row = await templates_service.update_template(
        require_organization_id(current_user),
        template_id,
        payload.model_dump(exclude_none=True),
    )
    return _to_read(row)


@router.delete(
    "/{template_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a message template",
)
async def delete_template(
    template_id: str = Path(..., description="Template id"),
    current_user: dict = Depends(get_current_user),
) -> None:
    await templates_service.delete_template(
        require_organization_id(current_user), template_id
    )
