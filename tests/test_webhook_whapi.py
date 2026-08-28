"""API tests for POST /api/webhooks/whatsapp/whapi (endpoints/webhooks.py).

These assert the HTTP contract only -- the persistence layer is monkeypatched.
The contract matters more than usual here because the caller is a machine that
retries with backoff:

    before the 200  ->  the event is being ACCEPTED (may fail, ask for a retry)
    after  the 200  ->  the event is being PROCESSED (never touches the status)

Getting that backwards turns one of our own bugs into a retry storm and
duplicate replies to a real customer. endpoints/webhook.py (Pipefy, legacy) does
exactly that: any exception becomes a 500.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import api.v1.endpoints.webhooks as webhooks_endpoint

SECRET = "un-secreto-de-prueba"

TEXT_PAYLOAD = {
    "messages": [
        {
            "id": "p.w30M7fgwWD4XwHu.g4CA-gBgTwl0rVw",
            "from_me": False,
            "type": "text",
            "chat_id": "50761234567@s.whatsapp.net",
            "timestamp": 1712995245,
            "text": {"body": "Hola, ya está listo mi repuesto?"},
            "from": "50761234567",
            "from_name": "Juan Pérez",
        }
    ],
    "event": {"type": "messages", "event": "post"},
    "channel_id": "TOYOPANA-M72HC",
}

app = FastAPI()
app.include_router(webhooks_endpoint.router, prefix="/api")
client = TestClient(app)

# Separate client for the "our own code blew up" case. TestClient re-raises
# server exceptions by default, which hides the status code the provider would
# actually receive; the real app turns them into a 500 (main.py:32).
crashing_client = TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _secret(monkeypatch):
    monkeypatch.setattr(webhooks_endpoint.settings, "WHAPI_WEBHOOK_SECRET", SECRET, raising=False)


@pytest.fixture(autouse=True)
def _no_background_work(monkeypatch):
    """Neutralize the post-200 half for EVERY test in this module.

    TestClient runs BackgroundTasks for real after the response. Without this,
    the tests below reach the live Supabase project AND the live Whapi account
    -- which is not hypothetical: an earlier run of this file inserted rows
    into production and sent four real WhatsApp messages to the number in the
    fixture payload. Tests that assert on the scheduling override this with
    their own recorder.
    """

    async def inert(*_args, **_kwargs):
        return None

    monkeypatch.setattr(webhooks_endpoint, "handle_inbound", inert)


@pytest.fixture(autouse=True)
def _no_db(monkeypatch):
    """Record accepted events in a list instead of hitting Supabase."""
    accepted: list = []

    async def fake_accept(*, organization_id, event, raw_payload):
        accepted.append((organization_id, event, raw_payload))
        return True  # True == newly stored (not a duplicate)

    monkeypatch.setattr(webhooks_endpoint, "accept_event", fake_accept)
    return accepted


def _post(payload=None, secret=SECRET):
    headers = {"X-Webhook-Token": secret} if secret is not None else {}
    return client.post(
        "/api/webhooks/whatsapp/whapi", json=payload or TEXT_PAYLOAD, headers=headers
    )


class TestAuthentication:
    def test_a_correct_secret_is_accepted(self):
        assert _post().status_code == 200

    def test_a_missing_header_is_rejected(self):
        assert _post(secret=None).status_code == 403

    def test_a_wrong_secret_is_rejected(self):
        assert _post(secret="no-es-el-secreto").status_code == 403

    def test_a_rejected_request_is_never_processed(self, _no_db):
        _post(secret="no-es-el-secreto")

        assert _no_db == []


class TestAcceptingEvents:
    def test_a_valid_message_is_handed_to_the_store(self, _no_db):
        _post()

        assert len(_no_db) == 1

    def test_the_parsed_event_carries_the_message_body(self, _no_db):
        _post()

        _, event, _ = _no_db[0]
        assert event.body == "Hola, ya está listo mi repuesto?"

    def test_the_raw_payload_is_stored_verbatim_for_reprocessing(self, _no_db):
        _post()

        _, _, raw = _no_db[0]
        assert raw == TEXT_PAYLOAD


class TestErrorContract:
    def test_json_the_parser_cannot_read_is_answered_200(self):
        """A 4xx would make Whapi retry something that can never succeed."""
        assert _post({"algo": "inesperado"}).status_code == 200

    def test_a_payload_with_only_our_own_messages_is_answered_200(self):
        payload = {**TEXT_PAYLOAD, "messages": [{**TEXT_PAYLOAD["messages"][0], "from_me": True}]}

        assert _post(payload).status_code == 200

    def test_a_storage_failure_is_answered_500_so_whapi_retries(self, monkeypatch):
        """The one case where we DO want the retry: we never accepted the event."""

        async def boom(**_):
            raise RuntimeError("supabase caída")

        monkeypatch.setattr(webhooks_endpoint, "accept_event", boom)

        response = crashing_client.post(
            "/api/webhooks/whatsapp/whapi",
            json=TEXT_PAYLOAD,
            headers={"X-Webhook-Token": SECRET},
        )

        assert response.status_code == 500


class TestPostTwoHundredProcessing:
    """The webhook must hand accepted messages to the background half.

    Scheduled, not awaited inline: Whapi's 200 must not wait on our database
    or on the reply going out.
    """

    def test_an_accepted_message_is_queued_for_processing(self, monkeypatch, _no_db):
        handled = []

        async def fake_handle(provider, *, organization_id, event):
            handled.append(event)

        monkeypatch.setattr(webhooks_endpoint, "handle_inbound", fake_handle)

        _post()

        assert len(handled) == 1
        assert handled[0].body == "Hola, ya está listo mi repuesto?"

    def test_a_duplicate_retry_is_not_processed_a_second_time(self, monkeypatch):
        """The whole point of the whatsapp_events UNIQUE constraint: Whapi
        retrying must not make us reply to the customer twice."""
        handled = []

        async def already_stored(**_):
            return False  # False == the event was already in the table

        async def fake_handle(provider, *, organization_id, event):
            handled.append(event)

        monkeypatch.setattr(webhooks_endpoint, "accept_event", already_stored)
        monkeypatch.setattr(webhooks_endpoint, "handle_inbound", fake_handle)

        response = _post()

        assert response.status_code == 200
        assert handled == []


class TestSecretInThePath:
    """Fallback for providers that cannot send custom headers -- which is
    Whapi's case: its panel offers no header configuration, only a URL.

    The secret in the path authenticates just as well, at the cost of being
    written to access logs (Render's, and any proxy's) where a header would
    not be. Accepted deliberately; see the spec's decision 2.
    """

    def _post_path(self, secret):
        return client.post(
            f"/api/webhooks/whatsapp/whapi/{secret}", json=TEXT_PAYLOAD
        )

    def test_the_correct_secret_in_the_path_is_accepted(self):
        assert self._post_path(SECRET).status_code == 200

    def test_a_wrong_secret_in_the_path_is_rejected(self):
        assert self._post_path("no-es-el-secreto").status_code == 403

    def test_a_path_secret_still_reaches_the_store(self, _no_db):
        self._post_path(SECRET)

        assert len(_no_db) == 1

    def test_the_header_route_keeps_working(self):
        """Kept so a move to a provider that signs (Meta) or a future Whapi
        that supports headers needs no change here."""
        assert _post().status_code == 200
