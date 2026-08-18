"""Orchestrates "send a WhatsApp message, then advance the order" as one
backend-owned use-case.

Coordinates two facades without polluting either: MessagingService stays
provider-only, orders_service stays messaging-unaware. Two future seams live
here and nowhere else:
  1. ``_is_send_allowed`` -- pre-send anti-spam guard (no-op today).
  2. the post-send step sequence -- advancing the status is step A.
"""

import logging
from dataclasses import dataclass
from typing import Mapping, Optional

from core.result import Result
from integrations.messaging.base import MessagingProvider
from schemas.messaging import SentMessage
from schemas.order import OrderFullUpdate, OrderUpdate
from schemas.order_messaging import OrderPayload
from services import orders_service
from services.messaging_service import MessagingService

logger = logging.getLogger(__name__)

# The single place the target follow-up status is defined.
WS_MESSAGE_TARGET_STATUS = "contactado"


@dataclass(frozen=True, slots=True)
class SendWsMessageOutcome:
    """The value carried by a successful orchestrator Result."""

    sent: SentMessage
    order_id: str
    status_updated: bool
    order_status: Optional[str]


def _is_send_allowed(order: OrderPayload) -> bool:
    """Pre-send anti-spam guard (SEAM #1).

    FUTURE: real rules go here -- e.g. no re-send within N hours, a per-order
    or per-customer cap, respecting opt-out. The whole order is available so a
    rule can read any field. Today it always allows the send.
    """
    return True


async def send_ws_message_for_order(
    provider: MessagingProvider,
    organization_id: str,
    to: str,
    order: OrderPayload,
    template: str,
    params: Optional[Mapping[str, str]] = None,
) -> Result[SendWsMessageOutcome]:
    """Send a templated message, then (only on success) advance the order.

    Template-only on purpose: this is business-initiated outreach, which
    official providers (Meta/Twilio) accept solely as approved copy referenced
    by name. Sending operator free text here would work on Whapi and then
    silently stop working on a provider switch, so the port is not given the
    chance. Free-form replies belong to the (future, window-gated) reply flow.

    Returns a failure Result if the guard blocks the send or the provider
    rejects the message (the order is left untouched). Returns a success
    Result once the message is accepted; the post-send status advance is
    best-effort and its outcome is reported via ``status_updated``.
    """
    # 0. Pre-send guard (SEAM #1).
    if not _is_send_allowed(order):
        return Result.failure("spam_blocked", details="Blocked by anti-spam guard")

    # 1. Send. Business logic stays inside MessagingService.
    sent = await MessagingService(provider).send_template_message(
        organization_id=organization_id,
        phone=to,
        template=template,
        params=params or {},
    )
    if not sent.ok:
        return Result.failure(
            sent.error, status_code=sent.status_code, details=sent.details
        )

    # 2. Post-send steps (SEAM #2). The send already succeeded, so every step
    #    here is best-effort: a failure is logged but never fails the request.
    status_updated = False
    new_status: Optional[str] = None
    try:
        await orders_service.update_full_order_detail(
            str(order.id),
            OrderFullUpdate(order=OrderUpdate(order_status=WS_MESSAGE_TARGET_STATUS)),
        )
        status_updated = True
        new_status = WS_MESSAGE_TARGET_STATUS
    except Exception as exc:  # noqa: BLE001 -- best-effort; send is source of truth
        logger.error(
            "send-ws-message: status advance failed for order %s: %s", order.id, exc
        )
    # -- FUTURE POST-SEND STEPS GO HERE --
    #    Append below, keep them best-effort, and surface each new result on
    #    SendWsMessageOutcome.

    return Result.success(
        SendWsMessageOutcome(
            sent=sent.value,
            order_id=str(order.id),
            status_updated=status_updated,
            order_status=new_status,
        )
    )
