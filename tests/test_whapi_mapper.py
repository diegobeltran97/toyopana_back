"""Tests for the Whapi Adapter/Mapper (integrations/whapi/mapper.py).

The mapper is the isolation seam: all knowledge of "Whapi calls it
chat_id / @s.whatsapp.net" lives here and nowhere else.
"""

from schemas.messaging import OutboundMessage, SentMessage
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
