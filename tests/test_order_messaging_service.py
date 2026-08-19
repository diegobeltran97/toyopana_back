"""Tests for the send-ws-message orchestrator.

Focus is the content fork: a template reference (portable to Meta/Twilio) vs
operator free text (Whapi-only outside the 24h window). The order-status
advance is stubbed -- it is covered by the orders tests.
"""

from unittest.mock import AsyncMock, patch

import pytest

from core.result import Result
from integrations.messaging.templates import MessageTemplate
from schemas.messaging import SentMessage
from schemas.order_messaging import OrderPayload
from services.order_messaging_service import send_ws_message_for_order

ORG = "22222222-2222-2222-2222-222222222222"

DELIVERY = MessageTemplate(
    name="delivery_notification",
    body="Hola {customer_name}, tu {car_info}.",
    params=("customer_name", "car_info"),
)


class RecordingProvider:
    """Captures which port method was used and with what."""

    def __init__(self, result=None):
        self._result = result or Result.success(
            SentMessage(id="m1", to="50761234567@s.whatsapp.net", status="sent")
        )
        self.text_calls = []
        self.template_calls = []

    async def send_text(self, msg):
        self.text_calls.append(msg)
        return self._result

    async def send_template(self, msg):
        self.template_calls.append(msg)
        return self._result


ORDER = OrderPayload(id="11111111-1111-1111-1111-111111111111")


@pytest.fixture(autouse=True)
def resolved_template():
    """Stub template resolution; storage is covered by the templates tests."""
    with patch(
        "services.messaging_service.templates_service.resolve",
        new=AsyncMock(return_value=DELIVERY),
    ) as stub:
        yield stub


@pytest.fixture
def no_status_advance():
    """Stub the post-send status advance; it is best-effort and tested elsewhere."""
    with patch(
        "services.order_messaging_service.orders_service.update_full_order_detail",
        new=AsyncMock(return_value=None),
    ) as stub:
        yield stub


class TestTemplatePath:
    async def test_template_reference_goes_through_send_template(self, no_status_advance):
        provider = RecordingProvider()

        result = await send_ws_message_for_order(
            provider,
            organization_id=ORG,
            to="6123 4567",
            order=ORDER,
            template="delivery_notification",
            params={"customer_name": "Diego", "car_info": "Toyota Camry 2020"},
        )

        assert result.ok is True
        assert provider.text_calls == []
        assert len(provider.template_calls) == 1
        sent = provider.template_calls[0]
        assert sent.name == "delivery_notification"
        assert sent.params["customer_name"] == "Diego"
        # The provider is handed resolved copy, not a bare name to look up.
        assert sent.body == DELIVERY.body

    async def test_missing_param_fails_before_reaching_the_provider(
        self, no_status_advance
    ):
        provider = RecordingProvider()

        result = await send_ws_message_for_order(
            provider,
            organization_id=ORG,
            to="61234567",
            order=ORDER,
            template="delivery_notification",
            params={"customer_name": "Diego"},  # car_info absent
        )

        assert result.ok is False
        assert result.error == "bad_request"
        assert "car_info" in result.details
        # Validated centrally so every provider fails identically.
        assert provider.template_calls == []

    async def test_unknown_template_fails_without_sending(
        self, no_status_advance, resolved_template
    ):
        resolved_template.return_value = None
        provider = RecordingProvider()

        result = await send_ws_message_for_order(
            provider,
            organization_id=ORG,
            to="61234567",
            order=ORDER,
            template="does_not_exist",
            params={},
        )

        assert result.ok is False
        assert result.error == "unknown_template"
        assert provider.template_calls == []

    async def test_resolution_is_scoped_to_the_caller_organization(
        self, no_status_advance, resolved_template
    ):
        await send_ws_message_for_order(
            RecordingProvider(),
            organization_id=ORG,
            to="61234567",
            order=ORDER,
            template="delivery_notification",
            params={"customer_name": "Ana", "car_info": "Hilux"},
        )

        # Templates are tenant-owned; a send must never read another org's copy.
        resolved_template.assert_awaited_once_with(ORG, "delivery_notification")

    async def test_advances_order_status_on_success(self, no_status_advance):
        result = await send_ws_message_for_order(
            RecordingProvider(),
            organization_id=ORG,
            to="61234567",
            order=ORDER,
            template="delivery_notification",
            params={"customer_name": "Ana", "car_info": "Hilux"},
        )

        assert result.value.status_updated is True
        assert result.value.order_status == "contactado"


class TestFreeTextIsNotReachable:
    async def test_outreach_never_uses_the_free_text_port_method(
        self, no_status_advance
    ):
        # Business-initiated sends must stay expressible as approved copy, so
        # this flow may never fall back to send_text -- that is exactly what
        # would break on a switch to Meta/Twilio.
        provider = RecordingProvider()

        await send_ws_message_for_order(
            provider,
            organization_id=ORG,
            to="61234567",
            order=ORDER,
            template="delivery_notification",
            params={"customer_name": "Ana", "car_info": "Hilux"},
        )

        assert provider.text_calls == []

    def test_endpoint_schema_rejects_a_free_text_body(self):
        import pydantic

        from api.v1.endpoints.messaging import SendWsMessageRequest

        with pytest.raises(pydantic.ValidationError):
            SendWsMessageRequest(
                to="61234567", order={"id": "1"}, message="texto libre"
            )


class TestFailurePropagation:
    async def test_provider_failure_leaves_the_order_untouched(self, no_status_advance):
        provider = RecordingProvider(Result.failure("rate_limit", status_code=429))

        result = await send_ws_message_for_order(
            provider,
            organization_id=ORG,
            to="61234567",
            order=ORDER,
            template="delivery_notification",
            params={"customer_name": "Ana", "car_info": "Hilux"},
        )

        assert result.ok is False
        assert result.error == "rate_limit"
        no_status_advance.assert_not_awaited()
