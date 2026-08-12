"""Repository for marketing metric queries against Supabase (PostgREST).

wa_messages has no organization_id of its own; it is scoped to an organization
through its conversation (wa_messages.conversation_id -> wa_conversations.id)
using PostgREST embedded-resource filtering (`wa_conversations!inner(...)`).
"""

import logging
from typing import Optional, Set

import httpx
from fastapi import HTTPException

from core.config import settings

logger = logging.getLogger(__name__)

# PostgREST caps the number of rows a single request can return (server-side
# max-rows setting); a query with more matches than this is silently
# truncated rather than erroring. This is a soft ceiling to make truncation
# observable via logs rather than a hard guarantee of completeness. If
# message volume grows past this, switch to full keyset pagination or a
# Postgres RPC that aggregates server-side (documented follow-up).
_MAX_CONVERSATION_ROWS = 10000


class MarketingRepository:
    """Read-only aggregate queries over wa_messages / wa_conversations."""

    def __init__(self):
        self.supabase_url = settings.SUPABASE_URL
        self.service_role_key = settings.SUPABASE_SERVICE_ROLE_KEY
        self.base_url = f"{self.supabase_url}/rest/v1"
        self.headers = {
            "apikey": self.service_role_key,
            "Authorization": f"Bearer {self.service_role_key}",
            "Content-Type": "application/json",
        }

    def _scoped_params(self, organization_id: str) -> dict:
        """Base params scoping wa_messages to an org via its conversation."""
        return {
            "select": "conversation_id,wa_conversations!inner(organization_id)",
            "wa_conversations.organization_id": f"eq.{organization_id}",
        }

    async def count_outbound_messages(
        self,
        organization_id: str,
        sent_after: str,
        sent_before: Optional[str] = None,
    ) -> int:
        """
        Count outbound wa_messages for an org within a time window.

        Uses PostgREST `Prefer: count=exact` and reads the total from the
        Content-Range response header, so no rows need to be transferred.

        Args:
            organization_id: The organization UUID to scope by (via conversation)
            sent_after: ISO timestamp; only count messages with sent_at >= this
            sent_before: Optional ISO timestamp; only messages with sent_at < this

        Returns:
            The exact number of matching outbound messages.
        """
        params = self._scoped_params(organization_id)
        params["direction"] = "eq.outbound"
        sent_filters = [f"gte.{sent_after}"]
        if sent_before:
            sent_filters.append(f"lt.{sent_before}")
        params["sent_at"] = sent_filters
        params["limit"] = "1"

        headers = {**self.headers, "Prefer": "count=exact"}
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/wa_messages", params=params, headers=headers
            )
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                detail = response.json() if response.text else str(exc)
                logger.error("Error counting outbound messages: %s", detail)
                raise HTTPException(status_code=response.status_code, detail=detail)
            return int(response.headers.get("Content-Range", "0-0/0").split("/")[1])

    async def conversation_ids_with_message(
        self,
        organization_id: str,
        direction: str,
        sent_after: str,
    ) -> Set[str]:
        """
        Return the set of conversation ids that have >=1 message of `direction`
        since `sent_after`, scoped to the org. Dedupes in Python (a conversation
        may have many messages).

        Args:
            organization_id: The organization UUID to scope by (via conversation)
            direction: 'outbound' or 'inbound'
            sent_after: ISO timestamp; only messages with sent_at >= this

        Returns:
            Distinct conversation ids matching the filter.
        """
        params = self._scoped_params(organization_id)
        params["direction"] = f"eq.{direction}"
        params["sent_at"] = f"gte.{sent_after}"
        params["limit"] = str(_MAX_CONVERSATION_ROWS)

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/wa_messages", params=params, headers=self.headers
            )
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                detail = response.json() if response.text else str(exc)
                logger.error("Error fetching conversation ids: %s", detail)
                raise HTTPException(status_code=response.status_code, detail=detail)
            rows = response.json()
            if len(rows) >= _MAX_CONVERSATION_ROWS:
                logger.warning(
                    "conversation_ids_with_message hit the %d-row cap for org %s "
                    "(direction=%s); results may be truncated and response_rate "
                    "may be approximate.",
                    _MAX_CONVERSATION_ROWS,
                    organization_id,
                    direction,
                )
            return {row["conversation_id"] for row in rows if row.get("conversation_id")}
