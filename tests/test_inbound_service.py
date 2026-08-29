"""Tests for services/inbound_service.py -- the post-200 half of the webhook.

Everything here runs AFTER the provider already got its 200, so the governing
rule is: nothing may raise. A failure is logged and recorded, never propagated,
because there is no longer a status code to put it in.

Repositories and the provider are replaced with hand-written doubles.
"""

from datetime import datetime, timezone

import pytest

import services.inbound_service as inbound_service
from core.result import Result
from schemas.inbound import InboundMessage
from schemas.messaging import SentMessage

ORG = "11111111-1111-1111-1111-111111111111"
CONVERSATION_ID = "22222222-2222-2222-2222-222222222222"


def _event_from(phone):
    """Same event, from a given sender."""
    e = _event()
    return e.model_copy(update={"from_phone": phone})


def _event(body="Hola", reply_id=None):
    return InboundMessage(
        provider="whapi",
        provider_event_id="wamid.1",
        chat_id="50768510658@s.whatsapp.net",
        from_phone="+50768510658",
        from_name="Juan Pérez",
        body=body,
        reply_id=reply_id,
        received_at=datetime(2026, 8, 28, 14, 20, tzinfo=timezone.utc),
    )


class FakeProvider:
    """Records what was sent; satisfies only what the service calls."""

    def __init__(self, result=None):
        self.result = result or Result.success(SentMessage(id="out1", to="x", status="sent"))
        self.sent = []

    async def send_interactive(self, msg):
        self.sent.append(msg)
        return self.result


@pytest.fixture
def repo(monkeypatch):
    """A stand-in for the conversation/customer persistence."""

    class Repo:
        def __init__(self):
            self.status = "bot"
            self.messages = []
            self.window_touched = False

        async def upsert_conversation(self, **kwargs):
            return {"id": CONVERSATION_ID, "status": self.status}

        async def record_message(self, **kwargs):
            self.messages.append(kwargs)

        async def touch_last_inbound(self, **kwargs):
            self.window_touched = True

    r = Repo()
    monkeypatch.setattr(inbound_service, "upsert_conversation", r.upsert_conversation)
    monkeypatch.setattr(inbound_service, "record_message", r.record_message)
    monkeypatch.setattr(inbound_service, "touch_last_inbound", r.touch_last_inbound)
    return r


class TestPersistence:
    async def test_stores_the_inbound_message(self, repo):
        await inbound_service.handle_inbound(FakeProvider(), organization_id=ORG, event=_event())

        inbound = [m for m in repo.messages if m["direction"] == "inbound"]
        assert len(inbound) == 1

    async def test_the_stored_message_keeps_the_provider_id_for_deduplication(self, repo):
        await inbound_service.handle_inbound(FakeProvider(), organization_id=ORG, event=_event())

        inbound = [m for m in repo.messages if m["direction"] == "inbound"][0]
        assert inbound["wa_message_id"] == "wamid.1"

    async def test_refreshes_the_24h_window(self, repo):
        await inbound_service.handle_inbound(FakeProvider(), organization_id=ORG, event=_event())

        assert repo.window_touched is True


class TestWelcomeReply:
    async def test_replies_with_the_welcome_menu(self, repo):
        provider = FakeProvider()

        await inbound_service.handle_inbound(provider, organization_id=ORG, event=_event())

        assert len(provider.sent) == 1

    async def test_the_menu_offers_the_three_business_options(self, repo):
        provider = FakeProvider()

        await inbound_service.handle_inbound(provider, organization_id=ORG, event=_event())

        assert [b.id for b in provider.sent[0].buttons] == [
            "menu_agendar_cita",
            "menu_cotizacion",
            "menu_otro",
        ]

    async def test_the_menu_goes_back_to_whoever_wrote_in(self, repo):
        provider = FakeProvider()

        await inbound_service.handle_inbound(provider, organization_id=ORG, event=_event())

        assert provider.sent[0].phone == "+50768510658"

    async def test_the_sent_menu_is_recorded_as_an_outbound_message(self, repo):
        """Otherwise the thread has a gap and the marketing metrics undercount."""
        await inbound_service.handle_inbound(FakeProvider(), organization_id=ORG, event=_event())

        assert [m for m in repo.messages if m["direction"] == "outbound"]


class TestHumanHandoff:
    async def test_does_not_reply_when_an_agent_owns_the_conversation(self, repo):
        """wa_conversations.status leaves 'bot' when a human takes over. Replying
        anyway would have the bot talk over its own colleague."""
        repo.status = "agent"
        provider = FakeProvider()

        await inbound_service.handle_inbound(provider, organization_id=ORG, event=_event())

        assert provider.sent == []

    async def test_still_stores_the_message_when_a_human_owns_it(self, repo):
        repo.status = "agent"

        await inbound_service.handle_inbound(FakeProvider(), organization_id=ORG, event=_event())

        assert [m for m in repo.messages if m["direction"] == "inbound"]


class TestFailuresAreContained:
    async def test_a_provider_failure_does_not_raise(self, repo):
        """We already answered 200. Raising here would only crash a background
        task and lose the message we just stored."""
        provider = FakeProvider(Result.failure("rate_limit", status_code=429))

        await inbound_service.handle_inbound(provider, organization_id=ORG, event=_event())

    async def test_a_failed_send_is_not_recorded_as_an_outbound_message(self, repo):
        provider = FakeProvider(Result.failure("rate_limit", status_code=429))

        await inbound_service.handle_inbound(provider, organization_id=ORG, event=_event())

        assert [m for m in repo.messages if m["direction"] == "outbound"] == []


class TestAllowlistDeTesting:
    """Test-mode allowlist: while testing against a live channel, only the
    numbers listed may receive a reply.

    Deliberately gated at the REPLY step, not at the webhook: an unlisted
    message is still stored, so testing does not cost visibility into what real
    customers are sending. Empty setting = disabled = everyone gets a reply,
    so forgetting to set it can never silence the bot.
    """

    @pytest.fixture
    def allowlist(self, monkeypatch):
        def _set(value):
            monkeypatch.setattr(
                inbound_service.settings, "WHATSAPP_ALLOWED_NUMBERS", value, raising=False
            )
        return _set

    async def test_a_listed_number_gets_the_welcome_menu(self, repo, allowlist):
        allowlist("50768510658")
        provider = FakeProvider()

        await inbound_service.handle_inbound(
            provider, organization_id=ORG, event=_event_from("+50768510658")
        )

        assert len(provider.sent) == 1

    async def test_an_unlisted_number_gets_no_reply(self, repo, allowlist):
        allowlist("50768510658")
        provider = FakeProvider()

        await inbound_service.handle_inbound(
            provider, organization_id=ORG, event=_event_from("+50761112222")
        )

        assert provider.sent == []

    async def test_an_unlisted_number_is_still_stored(self, repo, allowlist):
        """Testing must not blind us to what real customers are writing."""
        allowlist("50768510658")

        await inbound_service.handle_inbound(
            FakeProvider(), organization_id=ORG, event=_event_from("+50761112222")
        )

        assert [m for m in repo.messages if m["direction"] == "inbound"]

    async def test_an_empty_setting_disables_the_allowlist(self, repo, allowlist):
        """The default. Forgetting to configure it must never silence the bot."""
        allowlist("")
        provider = FakeProvider()

        await inbound_service.handle_inbound(
            provider, organization_id=ORG, event=_event_from("+50761112222")
        )

        assert len(provider.sent) == 1

    async def test_the_number_matches_however_it_is_written(self, repo, allowlist):
        """A leading + or spaces in the env var must not silently stop replies."""
        allowlist("+507 6851-0658")
        provider = FakeProvider()

        await inbound_service.handle_inbound(
            provider, organization_id=ORG, event=_event_from("+50768510658")
        )

        assert len(provider.sent) == 1

    async def test_several_numbers_can_be_listed(self, repo, allowlist):
        allowlist("50768510658, 50761112222")
        provider = FakeProvider()

        await inbound_service.handle_inbound(
            provider, organization_id=ORG, event=_event_from("+50761112222")
        )

        assert len(provider.sent) == 1
