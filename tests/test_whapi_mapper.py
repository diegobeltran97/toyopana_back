"""Tests for the Whapi Adapter/Mapper (integrations/whapi/mapper.py).

The mapper is the isolation seam: all knowledge of "Whapi calls it
chat_id / @s.whatsapp.net" lives here and nowhere else.
"""

import pytest
from pydantic import ValidationError

from schemas.messaging import (
    OutboundButton,
    OutboundInteractive,
    OutboundMessage,
    SentMessage,
)
from integrations.whapi import mapper


class TestToWhatsappId:
    def test_local_panama_number_gets_country_code_prefixed(self):
        assert mapper.to_whatsapp_id("6123 4567") == "50761234567@s.whatsapp.net"

    def test_number_with_plus_and_country_code_is_normalized(self):
        assert mapper.to_whatsapp_id("+507 6123-4567") == "50761234567@s.whatsapp.net"

    def test_already_formatted_number_is_unchanged(self):
        assert mapper.to_whatsapp_id("50761234567") == "50761234567@s.whatsapp.net"

    def test_strips_non_digit_characters(self):
        assert mapper.to_whatsapp_id("(507) 6123.4567") == "50761234567@s.whatsapp.net"


class TestOutboundToWire:
    def test_maps_phone_and_body_into_whapi_shape(self):
        wire = mapper.outbound_to_wire(OutboundMessage(phone="6123 4567", body="Hola"))

        assert wire["to"] == "50761234567@s.whatsapp.net"
        assert wire["body"] == "Hola"

    def test_omits_typing_time_when_not_provided(self):
        wire = mapper.outbound_to_wire(OutboundMessage(phone="61234567", body="Hi"))

        assert "typing_time" not in wire

    def test_includes_typing_time_when_provided(self):
        wire = mapper.outbound_to_wire(
            OutboundMessage(phone="61234567", body="Hi", typing_time=3)
        )

        assert wire["typing_time"] == 3


class TestWireToSent:
    def test_extracts_id_and_recipient_from_whapi_response(self):
        raw = {
            "sent": True,
            "message": {
                "id": "ABGGabc123",
                "chat_id": "50761234567@s.whatsapp.net",
                "type": "text",
            },
        }

        sent = mapper.wire_to_sent(raw)

        assert isinstance(sent, SentMessage)
        assert sent.id == "ABGGabc123"
        assert sent.to == "50761234567@s.whatsapp.net"
        assert sent.status == "sent"

    def test_status_reflects_not_sent_flag(self):
        raw = {"sent": False, "message": {"id": "x"}}

        sent = mapper.wire_to_sent(raw)

        assert sent.status == "failed"


class TestFromWhatsappId:
    """The inverse of to_whatsapp_id: Whapi chat id -> E.164 phone.

    Inbound messages carry `chat_id` (and `from`) in Whapi's own format. The
    domain speaks E.164, so the suffix and formatting die here, in the same
    seam that added them on the way out.
    """

    def test_strips_the_whatsapp_suffix_and_returns_e164(self):
        assert mapper.from_whatsapp_id("50761234567@s.whatsapp.net") == "+50761234567"

    def test_accepts_a_bare_number_without_the_suffix(self):
        assert mapper.from_whatsapp_id("50761234567") == "+50761234567"

    def test_is_the_inverse_of_to_whatsapp_id(self):
        assert mapper.from_whatsapp_id(mapper.to_whatsapp_id("6123 4567")) == "+50761234567"


class TestOutboundInteractiveValidation:
    """WhatsApp's own limits, enforced in the domain DTO rather than discovered
    as a 400 from the provider. They are platform limits (Meta enforces the
    same), so they belong here and not in the Whapi adapter."""

    def test_rejects_more_than_three_buttons(self):
        with pytest.raises(ValidationError):
            OutboundInteractive(
                phone="61234567",
                body="Elige",
                buttons=[OutboundButton(id=f"b{i}", title=f"Opción {i}") for i in range(4)],
            )

    def test_rejects_a_button_title_longer_than_25_characters(self):
        with pytest.raises(ValidationError):
            OutboundInteractive(
                phone="61234567",
                body="Elige",
                buttons=[OutboundButton(id="b1", title="x" * 26)],
            )

    def test_accepts_three_buttons_with_titles_at_the_limit(self):
        msg = OutboundInteractive(
            phone="61234567",
            body="Elige",
            buttons=[OutboundButton(id=f"b{i}", title="x" * 25) for i in range(3)],
        )

        assert len(msg.buttons) == 3


class TestInteractiveToWire:
    def _menu(self):
        return OutboundInteractive(
            phone="6851 0658",
            body="Hola 👋 ¿En qué te podemos ayudar?",
            buttons=[
                OutboundButton(id="menu_agendar_cita", title="Agendar cita"),
                OutboundButton(id="menu_cotizacion", title="Cotización"),
                OutboundButton(id="menu_otro", title="Otro"),
            ],
        )

    def test_normalizes_the_recipient_like_every_other_send(self):
        wire = mapper.interactive_to_wire(self._menu())

        assert wire["to"] == "50768510658@s.whatsapp.net"

    def test_declares_the_button_type_whapi_expects(self):
        wire = mapper.interactive_to_wire(self._menu())

        assert wire["type"] == "button"

    def test_puts_the_prompt_under_body_text(self):
        wire = mapper.interactive_to_wire(self._menu())

        assert wire["body"] == {"text": "Hola 👋 ¿En qué te podemos ayudar?"}

    def test_maps_each_button_into_whapis_quick_reply_shape(self):
        wire = mapper.interactive_to_wire(self._menu())

        assert wire["action"]["buttons"][0] == {
            "type": "quick_reply",
            "title": "Agendar cita",
            "id": "menu_agendar_cita",
        }

    def test_the_button_ids_survive_because_they_are_the_routing_key(self):
        """These ids come back as reply.buttons_reply.id on the next inbound
        message, and that is what routes a customer past the LLM."""
        wire = mapper.interactive_to_wire(self._menu())

        assert [b["id"] for b in wire["action"]["buttons"]] == [
            "menu_agendar_cita",
            "menu_cotizacion",
            "menu_otro",
        ]
