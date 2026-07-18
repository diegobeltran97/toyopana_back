"""The messaging port (Dependency Inversion seam).

Services depend ONLY on this abstraction, never on a concrete provider. Each
provider (Whapi today, Twilio/Meta tomorrow) is one Strategy implementation
behind this Protocol.

Kept intentionally small and use-case driven: only the operations the app
actually needs live here. Provider-specific extras stay on the concrete
provider, not on the port.
"""

from typing import Protocol, runtime_checkable

from core.result import Result
from schemas.messaging import OutboundMessage, SentMessage


@runtime_checkable
class MessagingProvider(Protocol):
    """Contract every messaging provider must satisfy."""

    async def send_text(self, msg: OutboundMessage) -> Result[SentMessage]:
        """Send a plain text message to a single recipient."""
        ...
