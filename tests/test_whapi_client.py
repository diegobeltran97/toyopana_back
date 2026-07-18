"""Tests for the Whapi Gateway (integrations/whapi/client.py).

Uses httpx.MockTransport so we exercise the real request/response handling
code without touching the network.
"""

import httpx
import pytest

from integrations.whapi.client import WhapiClient


def make_client(handler) -> WhapiClient:
    transport = httpx.MockTransport(handler)
    http = httpx.AsyncClient(transport=transport)
    return WhapiClient(token="secret-token", base_url="https://gate.whapi.cloud", http=http)


class TestToResult:
    def test_200_is_success_with_json_body(self):
        resp = httpx.Response(200, json={"sent": True})
        result = WhapiClient._to_result(resp)
        assert result.ok is True
        assert result.value == {"sent": True}

    def test_201_is_success(self):
        resp = httpx.Response(201, json={"ok": 1})
        assert WhapiClient._to_result(resp).ok is True

    def test_401_maps_to_auth_failed(self):
        result = WhapiClient._to_result(httpx.Response(401, text="nope"))
        assert result.ok is False
        assert result.error == "auth_failed"
        assert result.status_code == 401

    def test_429_maps_to_rate_limit(self):
        assert WhapiClient._to_result(httpx.Response(429)).error == "rate_limit"

    def test_unknown_status_maps_to_unexpected_error(self):
        result = WhapiClient._to_result(httpx.Response(418, text="teapot"))
        assert result.error == "unexpected_error"
        assert result.status_code == 418


class TestPostTextMessage:
    async def test_sends_bearer_auth_to_messages_text_endpoint(self):
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["url"] = str(request.url)
            seen["method"] = request.method
            seen["auth"] = request.headers.get("Authorization")
            seen["body"] = request.read().decode()
            return httpx.Response(200, json={"sent": True, "message": {"id": "m1"}})

        client = make_client(handler)
        result = await client.post_text_message(
            {"to": "50761234567@s.whatsapp.net", "body": "Hola"}
        )

        assert result.ok is True
        assert result.value["message"]["id"] == "m1"
        assert seen["url"] == "https://gate.whapi.cloud/messages/text"
        assert seen["method"] == "POST"
        assert seen["auth"] == "Bearer secret-token"
        assert "Hola" in seen["body"]

    async def test_timeout_becomes_timeout_result(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.TimeoutException("too slow", request=request)

        client = make_client(handler)
        result = await client.post_text_message({"to": "x", "body": "y"})

        assert result.ok is False
        assert result.error == "timeout"

    async def test_upstream_401_bubbles_up_as_auth_failed(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, text="bad token")

        client = make_client(handler)
        result = await client.post_text_message({"to": "x", "body": "y"})

        assert result.ok is False
        assert result.error == "auth_failed"
