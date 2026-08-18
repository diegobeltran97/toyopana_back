"""Messaging Facade -- provider-agnostic business use-cases.

The single, simple entry point the API layer talks to. It speaks domain terms
(a phone and a message string) and delegates to whatever MessagingProvider is
injected. It never imports Whapi directly.
"""

from typing import Mapping, Optional

from core.result import Result
from integrations.messaging.base import MessagingProvider
from schemas.messaging import OutboundMessage, OutboundTemplate, SentMessage
from services import templates_service


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

    async def send_template_message(
        self,
        organization_id: str,
        phone: str,
        template: str,
        params: Optional[Mapping[str, str]] = None,
        typing_time: Optional[int] = None,
    ) -> Result[SentMessage]:
        """Resolve a template by name and send it.

        Prefer this over send_message for business-initiated messages: it is
        the only form official providers accept outside the 24h window.

        Resolution and parameter validation happen here rather than in the
        provider, so every provider fails identically on a missing parameter
        instead of one erroring locally and another being rejected upstream.

        Args:
            organization_id: Owning organization (templates are per-tenant).
            phone: Recipient phone number in any human format.
            template: Template name.
            params: Values for the template's parameters.
            typing_time: Optional simulated typing duration (seconds).
        """
        values = dict(params or {})

        resolved = await templates_service.resolve(organization_id, template)
        if resolved is None:
            return Result.failure("unknown_template", details=template)

        missing = resolved.missing_params(values)
        if missing:
            return Result.failure(
                "bad_request",
                details=f"Missing template param(s): {', '.join(missing)}",
            )

        outbound = OutboundTemplate(
            phone=phone,
            name=resolved.name,
            params=values,
            body=resolved.body,
            language=resolved.language,
            provider_template_name=resolved.provider_template_name,
            typing_time=typing_time,
        )
        return await self._provider.send_template(outbound)
