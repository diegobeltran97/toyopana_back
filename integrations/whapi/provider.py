"""Whapi implementation of the MessagingProvider port (Strategy).

Orchestrates the mapper (domain <-> wire) and the client (transport) to
fulfil the port's contract. Contains no transport details and no business
rules -- just the wiring between the two.
"""

from core.result import Result
from schemas.messaging import OutboundMessage, SentMessage
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
            return Result.failure(raw.error, raw.status_code, raw.details)
        return Result.success(mapper.wire_to_sent(raw.value))
