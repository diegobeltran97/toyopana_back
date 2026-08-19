"""Whapi implementation of the MessagingProvider port (Strategy).

Orchestrates the mapper (domain <-> wire) and the client (transport) to
fulfil the port's contract. Contains no transport details and no business
rules -- just the wiring between the two.
"""

from core.result import Result
from schemas.messaging import OutboundMessage, OutboundTemplate, SentMessage
from integrations.whapi import mapper
from integrations.whapi.client import WhapiClient


class WhapiProvider:
    """MessagingProvider backed by Whapi.cloud."""

    def __init__(self, client: WhapiClient):
        self._client = client

    async def send_text(self, msg: OutboundMessage) -> Result[SentMessage]:
        raw = await self._client.post_text_message(mapper.outbound_to_wire(msg))
        if not raw.ok:
            # Propagate the transport failure unchanged (stable error codes).
            return Result.failure(
                raw.error or "unexpected_error", raw.status_code, raw.details
            )
        return Result.success(mapper.wire_to_sent(raw.value or {}))

    async def send_template(self, msg: OutboundTemplate) -> Result[SentMessage]:
        """Render the resolved copy locally, then send it as plain text.

        Whapi has no template API, so "supporting templates" here means
        rendering client-side. The call site is unaffected by that choice --
        which is the point of routing through the port.
        """
        try:
            payload = mapper.template_to_wire(msg)
        except (KeyError, IndexError) as exc:
            # Fail loudly rather than sending copy with unfilled placeholders.
            return Result.failure(
                "bad_request", details=f"Unresolved template param: {exc}"
            )

        raw = await self._client.post_text_message(payload)
        if not raw.ok:
            return Result.failure(
                raw.error or "unexpected_error", raw.status_code, raw.details
            )
        return Result.success(mapper.wire_to_sent(raw.value or {}))
