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

    def test_accepts_a_fourth_option(self):
        """Four options are legal in the domain -- the adapter renders them as
        a list instead of buttons. See TestCuatroOpcionesUsanLista."""
        msg = OutboundInteractive(
            phone="61234567",
            body="Elige",
            buttons=[OutboundButton(id=f"b{i}", title=f"Opción {i}") for i in range(4)],
        )

        assert len(msg.buttons) == 4

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


class TestInternationalNumbersAreNotMangled:
    """Regression: a reply to a non-Panama number went to a number that does
    not exist.

    to_whatsapp_id was written for the outbound case, where an operator types a
    local Panama number. The inbound path now feeds it the E.164 that
    from_whatsapp_id produced, and blindly prefixing 507 to an already
    international number silently invents a new one. Whapi ACCEPTS the send and
    returns a message id, so nothing looks wrong until the customer says they
    got nothing.

    The `+` is the unambiguous signal: by definition it means the country code
    is already there.
    """

    def test_an_e164_number_keeps_its_own_country_code(self):
        assert mapper.to_whatsapp_id("+13135555657") == "13135555657@s.whatsapp.net"

    def test_round_trips_a_us_number(self):
        chat_id = "13135555657@s.whatsapp.net"

        assert mapper.to_whatsapp_id(mapper.from_whatsapp_id(chat_id)) == chat_id

    def test_round_trips_a_colombian_number(self):
        chat_id = "573001234567@s.whatsapp.net"

        assert mapper.to_whatsapp_id(mapper.from_whatsapp_id(chat_id)) == chat_id

    def test_a_local_number_without_a_plus_still_gets_panama(self):
        """The original behaviour, which the outbound flow depends on."""
        assert mapper.to_whatsapp_id("6123 4567") == "50761234567@s.whatsapp.net"


class TestCuatroOpcionesUsanLista:
    """WhatsApp caps quick-reply buttons at 3. A fourth option is only
    expressible as a list message -- same endpoint, different payload.

    The choice lives in the mapper, not in the caller: the business says
    "offer these options" and the adapter picks the mechanism that fits. A
    service that had to know about the limit would leak WhatsApp into the
    domain, and would have to change again for a provider with other caps.
    """

    def _menu(self, n):
        return OutboundInteractive(
            phone="6851 0658",
            body="¿En qué te podemos ayudar?",
            buttons=[OutboundButton(id=f"op{i}", title=f"Opción {i}") for i in range(n)],
        )

    def test_tres_opciones_siguen_siendo_botones(self):
        assert mapper.interactive_to_wire(self._menu(3))["type"] == "button"

    def test_cuatro_opciones_se_envian_como_lista(self):
        assert mapper.interactive_to_wire(self._menu(4))["type"] == "list"

    def test_la_lista_conserva_los_ids_que_son_la_llave_de_ruteo(self):
        wire = mapper.interactive_to_wire(self._menu(4))

        filas = wire["action"]["list"]["sections"][0]["rows"]
        assert [f["id"] for f in filas] == ["op0", "op1", "op2", "op3"]

    def test_la_lista_trae_una_etiqueta_para_abrirla(self):
        """Without a label WhatsApp shows no way to open the list."""
        wire = mapper.interactive_to_wire(self._menu(4))

        assert wire["action"]["list"]["label"]

    def test_se_aceptan_hasta_diez_opciones(self):
        assert mapper.interactive_to_wire(self._menu(10))["type"] == "list"

    def test_once_opciones_se_rechazan(self):
        """WhatsApp's list cap. Fails here instead of as a 400 from Whapi."""
        with pytest.raises(ValidationError):
            self._menu(11)
