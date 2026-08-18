"""Factory + dependency provider for the messaging integration.

Picks and constructs the concrete provider from configuration, and owns the
single shared ``httpx.AsyncClient`` so connections are reused across requests
(instead of creating a new client on every call).

Two registries keyed by provider name, deliberately kept separate:

  * ``_PROVIDER_BUILDERS`` -- how to build a provider from credentials.
  * ``_ENV_CREDENTIALS``   -- where those credentials come from today.

Builders take credentials as an argument and never read ``settings``, so
switching the *source* (env now, a per-organization table later) means
replacing the second registry only. Adding a provider means one entry in each.

Used as a FastAPI dependency:  ``Depends(get_messaging_provider)``.
"""

from typing import Any, Callable, Dict, Mapping

import httpx

from core.config import settings
from integrations.messaging.base import MessagingProvider
from integrations.whapi.client import WhapiClient
from integrations.whapi.credentials import WhapiCredentials
from integrations.whapi.provider import WhapiProvider

# One client for the whole process. httpx.AsyncClient is safe to share and
# pools connections. It lives for the app's lifetime. Transport is not
# credential-specific, so it is shared across providers.
_http_client = httpx.AsyncClient(timeout=30.0)


def _build_whapi(raw: Mapping[str, Any]) -> MessagingProvider:
    """Build the Whapi provider, validating its credential shape."""
    creds = WhapiCredentials.model_validate(dict(raw))
    client = WhapiClient(
        token=creds.token,
        base_url=creds.base_url,
        http=_http_client,
    )
    return WhapiProvider(client)


_PROVIDER_BUILDERS: Dict[str, Callable[[Mapping[str, Any]], MessagingProvider]] = {
    "whapi": _build_whapi,
}

# SEAM: the credential *source*. Replace with a per-organization repository
# lookup when provider setup moves to an admin page; the builders above stay
# exactly as they are.
# NOTE: settings still expose WHAPIFY_* names; the blueprint's rename to
# WHAPI_* is deferred so existing .env files keep working.
_ENV_CREDENTIALS: Dict[str, Callable[[], Dict[str, Any]]] = {
    "whapi": lambda: {
        "token": settings.WHAPIFY_API_TOKEN,
        "base_url": settings.WHAPIFY_BASE_URL,
    },
}


def verify_provider_configured() -> str:
    """Check WHATSAPP_PROVIDER names a known provider; return it.

    Called at app startup so a bad value fails on boot instead of on the first
    customer message.
    """
    name = settings.WHATSAPP_PROVIDER
    if name not in _PROVIDER_BUILDERS:
        # Fail loudly: a typo in .env must never silently fall back to another
        # vendor and send live messages through it.
        raise ValueError(
            f"Unknown WHATSAPP_PROVIDER {name!r}; "
            f"expected one of {sorted(_PROVIDER_BUILDERS)}"
        )
    return name


def get_messaging_provider() -> MessagingProvider:
    """Factory Method: build the active messaging provider from config."""
    name = verify_provider_configured()
    return _PROVIDER_BUILDERS[name](_ENV_CREDENTIALS[name]())
