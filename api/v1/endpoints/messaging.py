"""Messaging HTTP endpoints (thin boundary).

Translates HTTP <-> use-case calls only. All business logic lives in the
MessagingService facade; all transport logic lives in the Whapi integration.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from integrations.messaging.base import MessagingProvider
from integrations.messaging.factory import get_messaging_provider
from schemas.messaging import SentMessage
from schemas.order_messaging import OrderPayload
from services.messaging_service import MessagingService
from services.order_messaging_service import send_ws_message_for_order

router = APIRouter()
logger = logging.getLogger(__name__)


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
    """Request body: send a WhatsApp message and advance the order status."""

    to: str = Field(..., description="Recipient phone number (any human format)")
    message: str = Field(..., min_length=1, description="Text to send")
    order: OrderPayload = Field(..., description="Full order object; requires `id`")


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
        logger.info("Message %s sent to %s", result.value.id, result.value.to)
        return result.value

    logger.error("Send failed: %s (%s)", result.error, result.details)
    http_status, detail = _ERROR_HTTP.get(result.error, _DEFAULT_ERROR)
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
) -> SendWsMessageResponse:
    """Send a message, then advance the order to 'contactado' on success."""
    result = await send_ws_message_for_order(
        provider,
        to=payload.to,
        message=payload.message,
        order=payload.order,
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
    http_status, detail = _ERROR_HTTP.get(result.error, _DEFAULT_ERROR)
    raise HTTPException(status_code=http_status, detail=detail)
