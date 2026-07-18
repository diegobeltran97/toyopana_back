"""Factory + dependency provider for the messaging integration.

Picks and constructs the concrete provider from configuration, and owns the
single shared ``httpx.AsyncClient`` so connections are reused across requests
(instead of creating a new client on every call).

Used as a FastAPI dependency:  ``Depends(get_messaging_provider)``.
"""

import httpx

from core.config import settings
from integrations.messaging.base import MessagingProvider
from integrations.whapi.client import WhapiClient
from integrations.whapi.provider import WhapiProvider

# One client for the whole process. httpx.AsyncClient is safe to share and
# pools connections. It lives for the app's lifetime.
# NOTE: settings still expose WHAPIFY_* names; the blueprint's rename to
# WHAPI_* is deferred so existing .env files keep working.
_http_client = httpx.AsyncClient(timeout=30.0)


def get_messaging_provider() -> MessagingProvider:
    """Factory Method: build the active messaging provider from config."""
    client = WhapiClient(
        token=settings.WHAPIFY_API_TOKEN,
        base_url=settings.WHAPIFY_BASE_URL,
        http=_http_client,
    )
    return WhapiProvider(client)
