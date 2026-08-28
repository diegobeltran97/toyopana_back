"""Repository for whatsapp_events against Supabase via PostgREST.

Uses the service_role key: `whatsapp_events` has RLS enabled with zero
policies, so no other key can reach it.

This table is the acceptance ledger for inbound webhooks. Its
UNIQUE (provider, provider_event_id) is what makes a provider retry a no-op:
we insert first, and a conflict tells us we have already seen the event.

Mirrors MessageTemplateRepository's shape (same headers, same error handling).
"""

import hashlib
import json
import logging
from typing import Any, Dict, Optional

import httpx

from core.config import settings
from schemas.inbound import InboundMessage

logger = logging.getLogger(__name__)


def stable_event_id(raw_payload: Dict[str, Any]) -> str:
    """Derive an idempotency key for an event that carries no message id.

    Must survive a process restart: Python's built-in hash() is salted per
    process, so an id built from it would differ after every deploy and the
    provider's retry would be stored a second time -- defeating the UNIQUE
    constraint this key feeds. sort_keys makes it independent of key order.
    """
    canonical = json.dumps(raw_payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class WhatsappEventsRepository:
    """Append-only store of raw provider payloads."""

    def __init__(self):
        self.base_url = f"{settings.SUPABASE_URL}/rest/v1"
        self.headers = {
            "apikey": settings.SUPABASE_SERVICE_ROLE_KEY,
            "Authorization": f"Bearer {settings.SUPABASE_SERVICE_ROLE_KEY}",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        }

    async def insert_if_new(
        self,
        *,
        organization_id: str,
        provider: str,
        provider_event_id: str,
        event_type: str,
        raw_payload: Dict[str, Any],
    ) -> bool:
        """Store a raw event. Returns False if we had already stored it.

        A 409 from PostgREST means the UNIQUE constraint fired, i.e. the
        provider is retrying an event we already accepted. That is not an
        error -- it is the idempotency guarantee doing its job, and the caller
        answers 200 without reprocessing.
        """
        row = {
            "organization_id": organization_id,
            "provider": provider,
            "provider_event_id": provider_event_id,
            "event_type": event_type,
            "raw_payload": raw_payload,
            "process_status": "pending",
        }

        async with httpx.AsyncClient(timeout=10.0) as http:
            response = await http.post(
                f"{self.base_url}/whatsapp_events", json=row, headers=self.headers
            )

        if response.status_code == 409:
            logger.info("Evento %s ya almacenado; es un reintento", provider_event_id)
            return False

        # Anything else that is not a success must raise: we have NOT accepted
        # the event, and the caller needs to answer 500 so the provider retries.
        response.raise_for_status()
        return True


async def accept_event(
    *,
    organization_id: str,
    event: Optional[InboundMessage],
    raw_payload: Dict[str, Any],
) -> bool:
    """Accept one inbound webhook event: persist the raw payload.

    `event` is None when the parser could not read the payload -- it is still
    stored, typed 'unknown', so nothing is lost and it can be replayed once the
    parser learns the shape.
    """
    repo = WhatsappEventsRepository()

    if event is None:
        return await repo.insert_if_new(
            organization_id=organization_id,
            provider="whapi",
            # No message id to key on; the payload's own content is the best
            # identity we have for de-duplicating statuses and unreadable events.
            provider_event_id=f"unknown:{stable_event_id(raw_payload)}",
            event_type="unknown",
            raw_payload=raw_payload,
        )

    return await repo.insert_if_new(
        organization_id=organization_id,
        provider=event.provider,
        provider_event_id=event.provider_event_id,
        event_type="message",
        raw_payload=raw_payload,
    )
