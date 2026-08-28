"""Repository for wa_conversations / wa_messages against Supabase via PostgREST.

Uses the service_role key: both tables have RLS enabled with zero policies
(migration 004), so no other key can reach them.

wa_messages has no organization_id of its own -- it is scoped to an org through
its conversation, the same shape repositories/marketing.py already relies on.

Mirrors MessageTemplateRepository's headers and error handling.
"""

import logging
from typing import Any, Dict, Optional

import httpx

from core.config import settings

logger = logging.getLogger(__name__)


def _headers(prefer: str = "return=representation") -> Dict[str, str]:
    return {
        "apikey": settings.SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {settings.SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": "application/json",
        "Prefer": prefer,
    }


def _base_url() -> str:
    return f"{settings.SUPABASE_URL}/rest/v1"


async def upsert_conversation(
    *, organization_id: str, chat_id: str, customer_id: Optional[str] = None
) -> Dict[str, Any]:
    """Find or create the conversation for a chat, and refresh last_message_at.

    Upsert on the table's own UNIQUE (organization_id, wa_chat_id) rather than
    a read-then-write, so two messages arriving at once cannot both decide the
    conversation is new.

    Returns the row, whose `status` decides whether the bot may reply at all.
    """
    row = {
        "organization_id": organization_id,
        "wa_chat_id": chat_id,
        "last_message_at": "now()",
    }
    if customer_id:
        row["customer_id"] = customer_id

    async with httpx.AsyncClient(timeout=10.0) as http:
        response = await http.post(
            f"{_base_url()}/wa_conversations",
            json=row,
            headers=_headers("return=representation,resolution=merge-duplicates"),
            params={"on_conflict": "organization_id,wa_chat_id"},
        )
    response.raise_for_status()
    rows = response.json()
    return rows[0] if rows else {}


async def record_message(
    *,
    conversation_id: str,
    direction: str,
    wa_message_id: Optional[str] = None,
    body: Optional[str] = None,
    media_url: Optional[str] = None,
) -> None:
    """Append one message to a conversation.

    A duplicate wa_message_id (409) is swallowed: wa_messages.wa_message_id is
    UNIQUE precisely so a provider retry cannot double-write the thread, and
    hitting it means the guarantee worked.
    """
    row = {
        "conversation_id": conversation_id,
        "direction": direction,
        "wa_message_id": wa_message_id,
        "body": body,
        "media_url": media_url,
    }

    async with httpx.AsyncClient(timeout=10.0) as http:
        response = await http.post(
            f"{_base_url()}/wa_messages", json=row, headers=_headers("return=minimal")
        )

    if response.status_code == 409:
        logger.info("Mensaje %s ya registrado; es un reintento", wa_message_id)
        return

    response.raise_for_status()


async def touch_last_inbound(*, organization_id: str, phone: str) -> None:
    """Stamp customers.last_inbound_at, the 24h customer-service window.

    Matched on whatsapp_id or phone; a customer we do not know yet simply
    matches nothing, which is fine -- the window only matters for people
    already in the CRM.
    """
    async with httpx.AsyncClient(timeout=10.0) as http:
        await http.patch(
            f"{_base_url()}/customers",
            json={"last_inbound_at": "now()"},
            headers=_headers("return=minimal"),
            params={
                "organization_id": f"eq.{organization_id}",
                "or": f"(phone.eq.{phone},whatsapp_id.eq.{phone})",
            },
        )
