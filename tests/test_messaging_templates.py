"""Tests for the template domain model.

Pure domain, no I/O: these rules are what keep one call site working across
providers that render locally (Whapi) and providers that render remotely
(Meta/Twilio). Storage is tested separately.
"""

import pytest

from integrations.messaging.templates import MessageTemplate, extract_placeholders

DELIVERY = MessageTemplate(
    name="delivery_notification",
    body="Hola {customer_name}, tienes una cotización para tu {car_info}.",
    params=("customer_name", "car_info"),
)


class TestExtractPlaceholders:
    def test_finds_single_brace_placeholders(self):
        assert extract_placeholders("Hola {name}, tu {car}") == ("name", "car")

    def test_finds_double_brace_placeholders(self):
        # The frontend interpolator accepts both forms, so the validator must too.
        assert extract_placeholders("Hola {{ name }}") == ("name",)

    def test_deduplicates_while_preserving_order(self):
        assert extract_placeholders("{b} {a} {b}") == ("b", "a")

    def test_returns_empty_for_copy_without_placeholders(self):
        assert extract_placeholders("Sin variables") == ()


class TestMissingParams:
    def test_reports_absent_declared_params(self):
        assert DELIVERY.missing_params({"customer_name": "Diego"}) == ("car_info",)

    def test_empty_when_all_supplied(self):
        assert DELIVERY.missing_params(
            {"customer_name": "Diego", "car_info": "Hilux"}
        ) == ()

    def test_extra_params_are_not_a_problem(self):
        assert DELIVERY.missing_params(
            {"customer_name": "D", "car_info": "H", "order_number": "TP-1"}
        ) == ()


class TestRender:
    def test_substitutes_named_parameters(self):
        rendered = DELIVERY.render(
            {"customer_name": "Diego", "car_info": "Toyota Camry 2020"}
        )

        assert "Hola Diego" in rendered
        assert "Toyota Camry 2020" in rendered

    def test_leaves_no_unfilled_placeholders(self):
        rendered = DELIVERY.render({"customer_name": "Ana", "car_info": "Hilux 2019"})

        assert "{" not in rendered and "}" not in rendered

    def test_raises_when_a_required_param_is_missing(self):
        with pytest.raises(KeyError) as exc:
            DELIVERY.render({"customer_name": "Diego"})

        assert "car_info" in exc.value.args[0]
