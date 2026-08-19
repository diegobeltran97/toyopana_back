"""Messaging HTTP endpoints (thin boundary).

Translates HTTP <-> use-case calls only. All business logic lives in the
MessagingService facade; all transport logic lives in the Whapi integration.
"""

import logging
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from api.deps import get_current_user
from integrations.messaging.base import MessagingProvider
from integrations.messaging.factory import get_messaging_provider
from schemas.messaging import SentMessage
from schemas.order_messaging import OrderPayload
from services import templates_service
from services.messaging_service import MessagingService
from services.order_messaging_service import send_ws_message_for_order

router = APIRouter()
logger = logging.getLogger(__name__)


def require_organization_id(current_user: dict) -> str:
    """Pull the caller's organization out of the authenticated user.

    Templates are per-tenant, so the org must come from the token and never
    from the request body. Mirrors the citas routes.
    """
    organization_id = current_user.get("organization_id")
    if not organization_id:
        raise HTTPException(
            status_code=403, detail="El usuario no pertenece a una organización"
        )
    return str(organization_id)


class SendTextRequest(BaseModel):
    """Request body for sending a free-form text message."""

    to: str = Field(..., description="Recipient phone number (any human format)")
    message: str = Field(..., min_length=1, description="Text to send")
    typing_time: Optional[int] = Field(
        None, ge=0, le=60, description="Optional simulated typing seconds (0-60)"
    )

    class Config:
        json_schema_extra = {
            "example": {"to": "6123 4567", "message": "Hola, ¿cómo estás?"}
        }


class SendWsMessageRequest(BaseModel):
    """Request body: send a WhatsApp message and advance the order status.

    Template-only by design. Business-initiated outreach must reference
    approved copy by name -- operator free text is not accepted here, because
    official providers (Meta/Twilio) reject it outside the 24h
    customer-service window. Free-form replies have their own endpoint
    (POST /send-text) and will be window-gated once inbound webhooks land.
    """

    to: str = Field(..., description="Recipient phone number (any human format)")
    order: OrderPayload = Field(..., description="Full order object; requires `id`")
    template: str = Field(
        ..., description="Registered template name, e.g. 'delivery_notification'"
    )
    params: Dict[str, str] = Field(
        default_factory=dict, description="Values for the template's parameters"
    )


class TemplateResponse(BaseModel):
    """A backend-owned message template."""

    id: str = Field(..., description="Template row id")
    name: str = Field(..., description="Template name used when sending")
    body: str = Field(..., description="Copy, with {param} placeholders")
    params: List[str] = Field(..., description="Parameter names the body requires")
    language: str = Field(..., description="Template language code")


class SendWsMessageResponse(BaseModel):
    """Outcome of send-ws-message."""

    sent: bool = Field(..., description="True if the provider accepted the message")
    id: Optional[str] = Field(None, description="Provider message id")
    to: Optional[str] = Field(None, description="Normalized recipient id")
    order_id: str = Field(..., description="The order the send targeted")
    status_updated: bool = Field(
        ..., description="Did the order advance to 'contactado'"
    )
    order_status: Optional[str] = Field(
        None, description="New status code when updated, else null"
    )


# Stable Result.error code -> (HTTP status, client-facing message).
_ERROR_HTTP = {
    "auth_failed": (status.HTTP_502_BAD_GATEWAY, "WhatsApp provider authentication failed."),
    "forbidden": (status.HTTP_502_BAD_GATEWAY, "WhatsApp provider rejected the recipient."),
    "trial_limit_exceeded": (status.HTTP_402_PAYMENT_REQUIRED, "WhatsApp provider trial limit reached."),
    "rate_limit": (status.HTTP_429_TOO_MANY_REQUESTS, "Rate limit exceeded, try again later."),
    "timeout": (status.HTTP_504_GATEWAY_TIMEOUT, "WhatsApp request timed out."),
    "bad_request": (status.HTTP_400_BAD_REQUEST, "WhatsApp provider rejected the request."),
    "spam_blocked": (status.HTTP_429_TOO_MANY_REQUESTS, "Message blocked to prevent spam."),
}
_DEFAULT_ERROR = (status.HTTP_502_BAD_GATEWAY, "Failed to send WhatsApp message.")


@router.get(
    "/templates",
    response_model=List[TemplateResponse],
    status_code=status.HTTP_200_OK,
    summary="List the available message templates",
    tags=["messaging"],
)
async def list_message_templates(
    current_user: dict = Depends(get_current_user),
) -> List[TemplateResponse]:
    """Return the organization's templates.

    The frontend reads its message copy from here rather than hardcoding a
    second version, so the two can never drift. On an official provider this
    copy is the local mirror of what is approved upstream.
    """
    organization_id = require_organization_id(current_user)
    rows = await templates_service.list_templates(organization_id)
    return [
        TemplateResponse(
            id=row["id"],
            name=row["name"],
            body=row["body"],
            params=list(row.get("params") or []),
            language=row.get("language") or "es",
        )
        for row in rows
    ]


@router.post(
    "/send-text",
    response_model=SentMessage,
    status_code=status.HTTP_200_OK,
    summary="Send a WhatsApp text message",
    tags=["messaging"],
)
async def send_text(
    payload: SendTextRequest,
    provider: MessagingProvider = Depends(get_messaging_provider),
) -> SentMessage:
    """Send a free-form text message to a recipient via the messaging provider."""
    service = MessagingService(provider)
    result = await service.send_message(
        phone=payload.to,
        message=payload.message,
    )

    if result.ok:
        assert result.value is not None  # narrow: ok Result always carries a value
        logger.info("Message %s sent to %s", result.value.id, result.value.to)
        return result.value

    logger.error("Send failed: %s (%s)", result.error, result.details)
    http_status, detail = _ERROR_HTTP.get(result.error or "", _DEFAULT_ERROR)
    raise HTTPException(status_code=http_status, detail=detail)


@router.post(
    "/send-ws-message",
    response_model=SendWsMessageResponse,
    status_code=status.HTTP_200_OK,
    summary="Send a WhatsApp message and advance the order status",
    tags=["messaging"],
)
async def send_ws_message(
    payload: SendWsMessageRequest,
    provider: MessagingProvider = Depends(get_messaging_provider),
    current_user: dict = Depends(get_current_user),
) -> SendWsMessageResponse:
    """Send a message, then advance the order to 'contactado' on success."""
    result = await send_ws_message_for_order(
        provider,
        organization_id=require_organization_id(current_user),
        to=payload.to,
        order=payload.order,
        template=payload.template,
        params=payload.params,
    )

    if result.ok:
        outcome = result.value
        assert outcome is not None  # narrow: ok Result always carries a value
        logger.info(
            "send-ws-message: sent %s to order %s (status_updated=%s)",
            outcome.sent.id,
            outcome.order_id,
            outcome.status_updated,
        )
        return SendWsMessageResponse(
            sent=outcome.sent.status == "sent",
            id=outcome.sent.id,
            to=outcome.sent.to,
            order_id=outcome.order_id,
            status_updated=outcome.status_updated,
            order_status=outcome.order_status,
        )

    logger.error("send-ws-message failed: %s (%s)", result.error, result.details)
    http_status, detail = _ERROR_HTTP.get(result.error or "", _DEFAULT_ERROR)
    raise HTTPException(status_code=http_status, detail=detail)
