"""Inbound WhatsApp webhooks (thin boundary).

The caller is a machine that retries with backoff, so the status code is part
of the contract, not decoration:

    before the 200  ->  ACCEPTING the event. A failure here is honest: we did
                        not take it, and we want the retry.
    after  the 200  ->  PROCESSING the event. Never touches the status code;
                        failures are recorded, not signalled upstream.

That line is why this module does NOT share the legacy Pipefy route's habit
(endpoints/webhook.py:106) of turning every exception into a 500 -- with a
retrying provider, one of our own bugs would become a retry storm and
duplicate messages to a real customer.
"""

import logging
import secrets
from typing import Any, Dict, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status

from core.config import settings
from integrations.messaging.base import MessagingProvider
from integrations.messaging.factory import get_messaging_provider
from integrations.whapi import parser
from repositories.whatsapp_events import accept_event
from services.inbound_service import handle_inbound

router = APIRouter()
logger = logging.getLogger(__name__)

WEBHOOK_TOKEN_HEADER = "X-Webhook-Token"


def _verify(request: Request, path_secret: Optional[str] = None) -> None:
    """Authenticate the caller by shared secret, from the path or a header.

    Whapi does not sign its payloads AND its panel cannot send custom headers
    -- only a URL -- so the path segment is the channel that actually works
    today. The header is kept because it is strictly better where available:
    a URL is written to the host's and every proxy's access logs, a header is
    not. A move to Meta (which signs) or a Whapi that gains header support then
    needs no change here.

    compare_digest, not `==`, so the comparison does not leak the secret's
    length or prefix through timing -- with `==` an attacker can recover the
    secret one character at a time by measuring how long the check takes.
    """
    expected = getattr(settings, "WHAPI_WEBHOOK_SECRET", "") or ""

    # An empty configured secret must never read as "no authentication
    # required", so it fails closed before anything is compared.
    if not expected:
        logger.error("WHAPI_WEBHOOK_SECRET sin configurar; se rechaza todo")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    candidates = [request.headers.get(WEBHOOK_TOKEN_HEADER) or "", path_secret or ""]
    # compare_digest against every candidate rather than short-circuiting, so
    # the work done does not depend on which channel carried the secret.
    if not any(secrets.compare_digest(c, expected) for c in candidates):
        # Deliberately no body logged: an unauthenticated caller's payload is
        # not ours to record.
        logger.warning("Webhook de Whapi rechazado: token inválido o ausente")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")


@router.post(
    "/webhooks/whatsapp/whapi/{path_secret}",
    status_code=status.HTTP_200_OK,
    summary="Receive inbound WhatsApp events from Whapi (secret in the path)",
    tags=["webhooks"],
)
@router.post(
    "/webhooks/whatsapp/whapi",
    status_code=status.HTTP_200_OK,
    summary="Receive inbound WhatsApp events from Whapi",
    tags=["webhooks"],
)
async def receive_whapi_webhook(
    request: Request,
    background: BackgroundTasks,
    provider: MessagingProvider = Depends(get_messaging_provider),
    path_secret: Optional[str] = None,
) -> Dict[str, Any]:
    """Accept inbound events from Whapi and store them for processing.

    Takes `Request`, not a Pydantic body, on purpose: the secret has to be
    checked against the raw bytes before anything is parsed. Meta and Twilio
    sign the raw body, and Twilio does not even send JSON -- keeping the raw
    request here is what lets a second provider reuse this shape.
    """
    _verify(request, path_secret)

    try:
        raw = await request.json()
    except Exception:
        # Unparseable JSON can never succeed on a retry. Answering 4xx would
        # make Whapi keep trying forever.
        logger.error("Webhook de Whapi con cuerpo no-JSON; descartado")
        return {"accepted": 0, "reason": "invalid_json"}

    events = parser.parse(raw)

    # SEAM: single-tenant today. When organization_credentials lands, this
    # becomes a lookup of parser.channel_id(raw) -> organization_id, and the
    # secret compared in _verify becomes that tenant's own.
    organization_id = str(settings.ORGANIZATION_ID)

    if not events:
        # Nothing we act on -- a status update, one of our own outbound
        # messages echoed back, or a shape the parser does not know yet. Store
        # it anyway so it can be replayed, and answer 200: a retry of this
        # would produce the same nothing.
        await accept_event(organization_id=organization_id, event=None, raw_payload=raw)
        return {"accepted": 0}

    accepted = 0
    for event in events:
        # A failure here propagates: we have NOT accepted the event, so the
        # 500 that results is correct and we want Whapi's retry.
        is_new = await accept_event(
            organization_id=organization_id, event=event, raw_payload=raw
        )

        # A retry of an event we already took must not reach the customer a
        # second time. This is what the whatsapp_events UNIQUE constraint buys.
        if not is_new:
            logger.info("Evento %s duplicado; no se reprocesa", event.provider_event_id)
            continue

        accepted += 1

        # -- EVERYTHING PAST THIS POINT IS POST-200 WORK --
        #    Scheduled, not awaited: Whapi's 200 must not wait on our database
        #    or on the reply going out. handle_inbound never raises, so a
        #    failure in there can never change the status code above.
        background.add_task(
            handle_inbound, provider, organization_id=organization_id, event=event
        )

    return {"accepted": accepted}
