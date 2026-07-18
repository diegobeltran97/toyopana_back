"""Whapi.cloud API Gateway.

Owns ALL transport knowledge of https://gate.whapi.cloud: the base URL, the
Bearer auth header, and how upstream HTTP status codes map to a typed Result.
It knows nothing about the application's business rules.

The shared ``_request`` method is a Template Method: every endpoint call reuses
the same auth + status->Result handling, so per-endpoint methods stay tiny.
"""

import logging
from typing import Any, Dict

import httpx

from core.result import Result

logger = logging.getLogger(__name__)

# Stable, machine-readable error codes for each upstream status.
_STATUS_ERRORS: Dict[int, str] = {
    400: "bad_request",
    401: "auth_failed",
    402: "trial_limit_exceeded",
    403: "forbidden",
    413: "payload_too_large",
    429: "rate_limit",
    500: "server_error",
}


class WhapiClient:
    """Thin async HTTP gateway to the Whapi REST API."""

    def __init__(self, token: str, base_url: str, http: httpx.AsyncClient):
        self._http = http
        self._base_url = base_url.rstrip("/")
        self._headers = {"Authorization": f"Bearer {token}"}

    async def _request(self, method: str, path: str, **kwargs: Any) -> Result[dict]:
        """Template Method: shared auth + error handling for every call."""
        url = f"{self._base_url}{path}"
        try:
            response = await self._http.request(
                method, url, headers=self._headers, **kwargs
            )
        except httpx.TimeoutException:
            logger.error("Whapi request timed out: %s %s", method, path)
            return Result.failure("timeout")
        except httpx.HTTPError as exc:  # transport-level failure
            logger.error("Whapi transport error: %s", exc)
            return Result.failure("transport_error", details=str(exc))
        return self._to_result(response)

    @staticmethod
    def _to_result(response: httpx.Response) -> Result[dict]:
        """Map an httpx.Response to a typed Result."""
        if response.status_code in (200, 201):
            return Result.success(response.json())

        error = _STATUS_ERRORS.get(response.status_code, "unexpected_error")
        logger.error("Whapi error %s: %s", response.status_code, response.text)
        return Result.failure(
            error, status_code=response.status_code, details=response.text
        )

    # ------------------------------------------------------------------
    # Endpoint methods (tiny by design)
    # ------------------------------------------------------------------

    async def post_text_message(self, payload: Dict[str, Any]) -> Result[dict]:
        """POST /messages/text"""
        return await self._request("POST", "/messages/text", json=payload)
