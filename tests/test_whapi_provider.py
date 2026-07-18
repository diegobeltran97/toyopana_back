"""Tests for the Whapi provider/Strategy (integrations/whapi/provider.py).

The provider is tested with a fake client injected in its place -- no HTTP,
no mocks of internals, just a small hand-written double that satisfies the
one method the provider uses.
"""

from core.result import Result
from schemas.messaging import OutboundMessage
from integrations.messaging.base import MessagingProvider
from integrations.whapi.provider import WhapiProvider


class FakeClient:
    """Records the payload it was called with and returns a canned Result."""

    def __init__(self, result: Result):
        self._result = result
        self.received_payload = None

    async def post_text_message(self, payload):
        self.received_payload = payload
        return self._result


class TestSendText:
    async def test_maps_domain_message_and_returns_sent_message(self):
        client = FakeClient(
            Result.success(
                {"sent": True, "message": {"id": "m1", "chat_id": "50761234567@s.whatsapp.net"}}
            )
        )
        provider = WhapiProvider(client)

        result = await provider.send_text(OutboundMessage(phone="6123 4567", body="Hola"))

        assert result.ok is True
        assert result.value.id == "m1"
        assert result.value.to == "50761234567@s.whatsapp.net"
        assert result.value.status == "sent"
        # The provider mapped the domain phone into a Whapi chat id before sending.
        assert client.received_payload["to"] == "50761234567@s.whatsapp.net"
        assert client.received_payload["body"] == "Hola"

    async def test_propagates_client_failure_without_calling_mapper(self):
        client = FakeClient(Result.failure("rate_limit", status_code=429))
        provider = WhapiProvider(client)

        result = await provider.send_text(OutboundMessage(phone="61234567", body="Hi"))

        assert result.ok is False
        assert result.error == "rate_limit"
        assert result.status_code == 429
        assert result.value is None


def test_whapi_provider_satisfies_messaging_port():
    provider = WhapiProvider(client=FakeClient(Result.success({})))
    assert isinstance(provider, MessagingProvider)
