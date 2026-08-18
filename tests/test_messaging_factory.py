"""Tests for the provider factory -- the config-driven switch.

Mirrors the reference gateway's provider.factory.test.ts: the point of the
registry is that the active provider follows configuration, and that a bad
value fails loudly instead of quietly using the wrong vendor.
"""

import pytest

from integrations.messaging import factory
from integrations.messaging.base import MessagingProvider
from integrations.whapi.credentials import WhapiCredentials
from integrations.whapi.provider import WhapiProvider


class TestProviderSelection:
    def test_whapi_setting_yields_the_whapi_provider(self, monkeypatch):
        monkeypatch.setattr(factory.settings, "WHATSAPP_PROVIDER", "whapi")

        provider = factory.get_messaging_provider()

        assert isinstance(provider, WhapiProvider)
        assert isinstance(provider, MessagingProvider)

    def test_unknown_provider_raises_instead_of_falling_back(self, monkeypatch):
        monkeypatch.setattr(factory.settings, "WHATSAPP_PROVIDER", "meta")

        with pytest.raises(ValueError) as exc:
            factory.get_messaging_provider()

        assert "meta" in str(exc.value)
        assert "whapi" in str(exc.value)  # names the valid options

    def test_startup_check_rejects_an_unknown_provider(self, monkeypatch):
        monkeypatch.setattr(factory.settings, "WHATSAPP_PROVIDER", "typo")

        with pytest.raises(ValueError):
            factory.verify_provider_configured()

    def test_startup_check_passes_for_the_default(self, monkeypatch):
        monkeypatch.setattr(factory.settings, "WHATSAPP_PROVIDER", "whapi")

        assert factory.verify_provider_configured() == "whapi"

    def test_every_builder_has_a_credential_source(self):
        # The two registries are keyed by the same names; a provider with a
        # builder but no credentials would only fail at send time.
        assert set(factory._PROVIDER_BUILDERS) == set(factory._ENV_CREDENTIALS)


class TestCredentialInjection:
    def test_builders_take_credentials_rather_than_reading_settings(self):
        # The seam that lets per-organization config replace env config later:
        # a builder must work from a plain mapping alone.
        provider = factory._build_whapi(
            {"token": "tok_123", "base_url": "https://example.test"}
        )

        assert isinstance(provider, MessagingProvider)

    def test_credentials_are_validated(self):
        import pydantic

        with pytest.raises(pydantic.ValidationError):
            factory._build_whapi({"base_url": "https://example.test"})  # no token

    def test_base_url_defaults_when_absent(self):
        creds = WhapiCredentials.model_validate({"token": "tok_123"})

        assert creds.base_url == "https://gate.whapi.cloud"
