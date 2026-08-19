"""Message-template business rules: authoring and resolution.

Two responsibilities:

  * **Authoring** (CRUD) -- with one rule enforced on every write: a template's
    declared ``params`` must match the ``{placeholders}`` actually in its body.
    Drift is invisible on Whapi (rendered locally, leaving a literal
    ``{car_info}`` in a customer's message) but a rejected submission on
    Meta/Twilio, so it is refused up front rather than at send time.
  * **Resolution** -- turning a template name into the resolved copy the
    messaging port dispatches. This is the seam the hardcoded registry used to
    fill; providers never reach the store themselves.
"""

import logging
from typing import Any, Dict, List, Optional

from fastapi import HTTPException, status

from integrations.messaging.templates import MessageTemplate, extract_placeholders
from repositories.message_templates import MessageTemplateRepository, to_domain

logger = logging.getLogger(__name__)


def _validate_params_match_body(body: str, params: List[str]) -> None:
    """Refuse a template whose declared params disagree with its copy."""
    in_body = set(extract_placeholders(body))
    declared = set(params)

    undeclared = sorted(in_body - declared)
    unused = sorted(declared - in_body)

    problems = []
    if undeclared:
        problems.append(f"placeholders missing from params: {', '.join(undeclared)}")
    if unused:
        problems.append(f"params not used in body: {', '.join(unused)}")
    if problems:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="; ".join(problems),
        )


async def list_templates(organization_id: str) -> List[Dict[str, Any]]:
    """Every active template for an organization."""
    return await MessageTemplateRepository().list(organization_id)


async def resolve(organization_id: str, name: str) -> Optional[MessageTemplate]:
    """Look up a template by name and return the domain model, or None.

    SEAM: this is what the send path calls. It replaced the hardcoded registry
    and is the only place the store is read during a send.
    """
    row = await MessageTemplateRepository().get_by_name(organization_id, name)
    return to_domain(row) if row else None


async def create_template(
    organization_id: str, data: Dict[str, Any]
) -> Dict[str, Any]:
    """Author a new template."""
    _validate_params_match_body(data["body"], data.get("params") or [])
    return await MessageTemplateRepository().create(organization_id, data)


async def update_template(
    organization_id: str, template_id: str, data: Dict[str, Any]
) -> Dict[str, Any]:
    """Edit a template. Validates body/params together, even on a partial patch."""
    repo = MessageTemplateRepository()

    if "body" in data or "params" in data:
        current = await repo.list(organization_id, active_only=False)
        existing = next((r for r in current if r["id"] == template_id), None)
        if existing is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Template not found"
            )
        # Validate the post-patch state, not just the fields supplied.
        body = data.get("body", existing["body"])
        params = data.get("params", existing.get("params") or [])
        _validate_params_match_body(body, params)

    row = await repo.update(organization_id, template_id, data)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Template not found"
        )
    return row


async def delete_template(organization_id: str, template_id: str) -> None:
    """Remove a template."""
    if not await MessageTemplateRepository().delete(organization_id, template_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Template not found"
        )
