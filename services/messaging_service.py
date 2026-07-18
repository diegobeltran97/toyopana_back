"""Messaging Facade -- provider-agnostic business use-cases.

The single, simple entry point the API layer talks to. It speaks domain terms
(a phone and a message string) and delegates to whatever MessagingProvider is
injected. It never imports Whapi directly.
"""

from typing import Optional

from core.result import Result
from integrations.messaging.base import MessagingProvider
from schemas.messaging import OutboundMessage, SentMessage


class MessagingService:
    """Facade over the messaging integration subsystem."""

    def __init__(self, provider: MessagingProvider):
        self._provider = provider

    async def send_message(
        self,
        phone: str,
        message: str,
        typing_time: Optional[int] = None,
    ) -> Result[SentMessage]:
        """Send a free-form text message to a recipient.

        Args:
            phone: Recipient phone number in any human format.
            message: The text to send.
            typing_time: Optional simulated typing duration (seconds).
        """
        outbound = OutboundMessage(phone=phone, body=message, typing_time=typing_time)
        return await self._provider.send_text(outbound)
