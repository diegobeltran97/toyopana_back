"""Tests for MarketingRepository (repositories/marketing.py).

The repository's HTTP layer is replaced with a fake httpx.AsyncClient so the
tests assert the PostgREST request it builds and how it parses the response,
without touching the network.
"""

import logging

import repositories.marketing as marketing_repo_module
from repositories.marketing import MarketingRepository


class FakeResponse:
    def __init__(self, *, json_data=None, headers=None):
        self._json = json_data if json_data is not None else []
        self.headers = headers or {}
        self.text = "ok"

    def json(self):
        return self._json

    def raise_for_status(self):
        return None


class FakeAsyncClient:
    """Records the last GET call and returns a canned response."""

    last_call: dict = {}

    def __init__(self, response: FakeResponse):
        self._response = response

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, url, params=None, headers=None):
        FakeAsyncClient.last_call = {"url": url, "params": params, "headers": headers}
        return self._response


def _patch_client(monkeypatch, response: FakeResponse):
    monkeypatch.setattr(
        marketing_repo_module.httpx,
        "AsyncClient",
        lambda *a, **k: FakeAsyncClient(response),
    )


async def test_count_outbound_messages_parses_content_range(monkeypatch):
    _patch_client(monkeypatch, FakeResponse(headers={"Content-Range": "0-0/42"}))
    repo = MarketingRepository()

    count = await repo.count_outbound_messages(
        "org-1", sent_after="2026-08-10T05:00:00+00:00"
    )

    assert count == 42
    call = FakeAsyncClient.last_call
    assert call["url"].endswith("/wa_messages")
    assert call["params"]["direction"] == "eq.outbound"
    assert call["params"]["wa_conversations.organization_id"] == "eq.org-1"
    assert call["params"]["sent_at"] == ["gte.2026-08-10T05:00:00+00:00"]
    assert call["headers"]["Prefer"] == "count=exact"


async def test_count_outbound_messages_adds_upper_bound(monkeypatch):
    _patch_client(monkeypatch, FakeResponse(headers={"Content-Range": "0-0/3"}))
    repo = MarketingRepository()

    await repo.count_outbound_messages(
        "org-1",
        sent_after="2026-08-09T05:00:00+00:00",
        sent_before="2026-08-10T05:00:00+00:00",
    )

    assert FakeAsyncClient.last_call["params"]["sent_at"] == [
        "gte.2026-08-09T05:00:00+00:00",
        "lt.2026-08-10T05:00:00+00:00",
    ]


async def test_conversation_ids_dedupe_into_set(monkeypatch):
    _patch_client(
        monkeypatch,
        FakeResponse(
            json_data=[
                {"conversation_id": "c1"},
                {"conversation_id": "c2"},
                {"conversation_id": "c1"},
                {"conversation_id": None},
            ]
        ),
    )
    repo = MarketingRepository()

    ids = await repo.conversation_ids_with_message(
        "org-1", "inbound", "2026-08-03T05:00:00+00:00"
    )

    assert ids == {"c1", "c2"}
    assert FakeAsyncClient.last_call["params"]["direction"] == "eq.inbound"


async def test_conversation_ids_sends_row_cap_limit(monkeypatch):
    _patch_client(monkeypatch, FakeResponse(json_data=[{"conversation_id": "c1"}]))
    repo = MarketingRepository()

    await repo.conversation_ids_with_message(
        "org-1", "inbound", "2026-08-03T05:00:00+00:00"
    )

    assert FakeAsyncClient.last_call["params"]["limit"] == str(
        marketing_repo_module._MAX_CONVERSATION_ROWS
    )


async def test_conversation_ids_warns_when_row_cap_is_hit(monkeypatch, caplog):
    max_rows = marketing_repo_module._MAX_CONVERSATION_ROWS
    rows = [{"conversation_id": f"c{i}"} for i in range(max_rows)]
    _patch_client(monkeypatch, FakeResponse(json_data=rows))
    repo = MarketingRepository()

    with caplog.at_level(logging.WARNING, logger="repositories.marketing"):
        ids = await repo.conversation_ids_with_message(
            "org-1", "outbound", "2026-08-03T05:00:00+00:00"
        )

    assert len(ids) == max_rows
    assert FakeAsyncClient.last_call["params"]["limit"] == str(max_rows)
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert "org-1" in warnings[0].message
    assert "truncated" in warnings[0].message.lower()
