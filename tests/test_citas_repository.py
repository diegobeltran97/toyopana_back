"""Tests for CitaRepository (repositories/citas.py).

The HTTP layer is replaced with a fake httpx.AsyncClient (same approach as
tests/test_marketing_repository.py) so the tests assert the PostgREST request
that gets built and how the response is parsed, with no network access.
"""

import httpx
import pytest
from fastapi import HTTPException

import repositories.citas as citas_repo_module
from repositories.citas import CitaRepository

ORG = "11111111-1111-1111-1111-111111111111"
CITA_ID = "22222222-2222-2222-2222-222222222222"


class FakeResponse:
    def __init__(self, *, json_data=None, status_code=200, ok=True):
        self._json = json_data if json_data is not None else []
        self.status_code = status_code
        self.headers = {}
        self.text = "body"
        self._ok = ok

    def json(self):
        return self._json

    def raise_for_status(self):
        if not self._ok:
            raise httpx.HTTPStatusError("boom", request=None, response=None)


class FakeAsyncClient:
    """Records every call and replays a queue of canned responses."""

    calls: list = []

    def __init__(self, responses):
        self._responses = list(responses)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def _next(self):
        return self._responses.pop(0)

    async def get(self, url, params=None, headers=None):
        FakeAsyncClient.calls.append(
            {"method": "GET", "url": url, "params": params, "headers": headers}
        )
        return self._next()

    async def post(self, url, json=None, headers=None):
        FakeAsyncClient.calls.append(
            {"method": "POST", "url": url, "json": json, "headers": headers}
        )
        return self._next()

    async def patch(self, url, params=None, json=None, headers=None):
        FakeAsyncClient.calls.append(
            {
                "method": "PATCH",
                "url": url,
                "params": params,
                "json": json,
                "headers": headers,
            }
        )
        return self._next()


def _patch_client(monkeypatch, *responses):
    FakeAsyncClient.calls = []
    monkeypatch.setattr(
        citas_repo_module.httpx,
        "AsyncClient",
        lambda *a, **k: FakeAsyncClient(responses),
    )


async def test_create_posts_row_and_returns_it(monkeypatch):
    _patch_client(monkeypatch, FakeResponse(json_data=[{"id": CITA_ID}]))
    repo = CitaRepository()

    row = await repo.create(
        ORG, {"customer_id": "c1", "scheduled_at": "2026-09-01T15:00:00+00:00"}
    )

    assert row == {"id": CITA_ID}
    call = FakeAsyncClient.calls[0]
    assert call["method"] == "POST"
    assert call["url"].endswith("/citas")
    # The org is stamped by the repository, never taken from the caller's dict.
    assert call["json"]["organization_id"] == ORG
    assert call["headers"]["Prefer"] == "return=representation"


async def test_list_range_filters_org_and_window(monkeypatch):
    _patch_client(monkeypatch, FakeResponse(json_data=[{"id": CITA_ID}]))
    repo = CitaRepository()

    rows = await repo.list_range(
        ORG,
        scheduled_from="2026-09-01T05:00:00+00:00",
        scheduled_before="2026-10-01T05:00:00+00:00",
    )

    assert rows == [{"id": CITA_ID}]
    params = FakeAsyncClient.calls[0]["params"]
    assert params["organization_id"] == f"eq.{ORG}"
    # Upper bound is EXCLUSIVE so the last day of the range is fully included.
    assert params["scheduled_at"] == [
        "gte.2026-09-01T05:00:00+00:00",
        "lt.2026-10-01T05:00:00+00:00",
    ]
    assert params["order"] == "scheduled_at.asc"
    assert params["select"] == citas_repo_module.CITA_SELECT
    assert "status" not in params


async def test_list_range_adds_optional_status_filter(monkeypatch):
    _patch_client(monkeypatch, FakeResponse(json_data=[]))
    repo = CitaRepository()

    await repo.list_range(
        ORG,
        scheduled_from="2026-09-01T05:00:00+00:00",
        scheduled_before="2026-10-01T05:00:00+00:00",
        status="agendada",
    )

    assert FakeAsyncClient.calls[0]["params"]["status"] == "eq.agendada"


async def test_get_returns_none_when_missing(monkeypatch):
    _patch_client(monkeypatch, FakeResponse(json_data=[]))
    repo = CitaRepository()

    assert await repo.get(CITA_ID, ORG) is None


async def test_get_scopes_by_id_and_org(monkeypatch):
    _patch_client(monkeypatch, FakeResponse(json_data=[{"id": CITA_ID}]))
    repo = CitaRepository()

    row = await repo.get(CITA_ID, ORG)

    assert row == {"id": CITA_ID}
    params = FakeAsyncClient.calls[0]["params"]
    assert params["id"] == f"eq.{CITA_ID}"
    assert params["organization_id"] == f"eq.{ORG}"


async def test_update_is_tenant_scoped(monkeypatch):
    """A PATCH must never be addressable by id alone — org is a write guard."""
    _patch_client(
        monkeypatch,
        FakeResponse(json_data=[{"id": CITA_ID, "status": "confirmada"}]),
    )
    repo = CitaRepository()

    row = await repo.update(CITA_ID, ORG, {"status": "confirmada"})

    assert row["status"] == "confirmada"
    call = FakeAsyncClient.calls[0]
    assert call["method"] == "PATCH"
    assert call["params"]["id"] == f"eq.{CITA_ID}"
    assert call["params"]["organization_id"] == f"eq.{ORG}"
    assert call["json"] == {"status": "confirmada"}


async def test_update_returns_none_when_nothing_matched(monkeypatch):
    _patch_client(monkeypatch, FakeResponse(json_data=[]))
    repo = CitaRepository()

    assert await repo.update(CITA_ID, ORG, {"status": "confirmada"}) is None


async def test_postgrest_error_becomes_http_exception(monkeypatch):
    _patch_client(
        monkeypatch,
        FakeResponse(
            json_data={"message": "violates check constraint"},
            status_code=400,
            ok=False,
        ),
    )
    repo = CitaRepository()

    with pytest.raises(HTTPException) as exc:
        await repo.create(ORG, {"customer_id": "c1"})

    assert exc.value.status_code == 400
