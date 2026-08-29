"""Tests for the Whapi inbound parser (integrations/whapi/parser.py).

The parser is the inbound isolation seam: every Whapi-specific shape
(``@s.whatsapp.net``, ``from_me``, the ``reply.<type>.id`` nesting, seconds-based
timestamps) dies here so services only ever see domain DTOs.

The payloads below are copied from Whapi's own documentation
(support.whapi.cloud/help-desk/receiving/webhooks/incoming-webhooks-format),
not invented for the test.
"""

from datetime import datetime, timezone

from integrations.whapi import parser


TEXT_PAYLOAD = {
    "messages": [
        {
            "id": "p.w30M7fgwWD4XwHu.g4CA-gBgTwl0rVw",
            "from_me": False,
            "type": "text",
            "chat_id": "50761234567@s.whatsapp.net",
            "timestamp": 1712995245,
            "source": "mobile",
            "text": {"body": "Hola, ya está listo mi repuesto?"},
            "from": "50761234567",
            "from_name": "Juan Pérez",
        }
    ],
    "event": {"type": "messages", "event": "post"},
    "channel_id": "TOYOPANA-M72HC",
}

BUTTON_REPLY_PAYLOAD = {
    "messages": [
        {
            "id": "g0jEG0ZsSobn4yNGGU3TAg-gDYOS60TLw",
            "from_me": False,
            "type": "reply",
            "chat_id": "50761234567@s.whatsapp.net",
            "timestamp": 1726126124,
            "source": "mobile",
            "reply": {
                "type": "buttons_reply",
                "buttons_reply": {"id": "menu_cotizacion", "title": "Cotizar"},
            },
            "from": "50761234567",
            "from_name": "Juan Pérez",
        }
    ],
    "event": {"type": "messages", "event": "post"},
    "channel_id": "TOYOPANA-M72HC",
}

LIST_REPLY_PAYLOAD = {
    "messages": [
        {
            "id": "abc123",
            "from_me": False,
            "type": "reply",
            "chat_id": "50761234567@s.whatsapp.net",
            "timestamp": 1726126124,
            "reply": {
                "type": "list_reply",
                "list_reply": {"id": "menu_cita", "title": "Agendar cita"},
            },
            "from": "50761234567",
        }
    ],
    "event": {"type": "messages", "event": "post"},
    "channel_id": "TOYOPANA-M72HC",
}


class TestParseTextMessage:
    def test_returns_one_event_for_one_message(self):
        assert len(parser.parse(TEXT_PAYLOAD)) == 1

    def test_maps_the_message_body(self):
        [event] = parser.parse(TEXT_PAYLOAD)

        assert event.body == "Hola, ya está listo mi repuesto?"

    def test_carries_the_provider_message_id_for_idempotency(self):
        [event] = parser.parse(TEXT_PAYLOAD)

        assert event.provider_event_id == "p.w30M7fgwWD4XwHu.g4CA-gBgTwl0rVw"

    def test_normalizes_the_sender_to_e164(self):
        [event] = parser.parse(TEXT_PAYLOAD)

        assert event.from_phone == "+50761234567"

    def test_preserves_the_raw_chat_id_for_the_conversation_upsert(self):
        """wa_conversations keys on (organization_id, wa_chat_id), so the
        provider's own id has to survive the trip."""
        [event] = parser.parse(TEXT_PAYLOAD)

        assert event.chat_id == "50761234567@s.whatsapp.net"

    def test_maps_the_sender_name(self):
        [event] = parser.parse(TEXT_PAYLOAD)

        assert event.from_name == "Juan Pérez"

    def test_reads_the_timestamp_as_seconds_not_milliseconds(self):
        [event] = parser.parse(TEXT_PAYLOAD)

        assert event.received_at == datetime(2024, 4, 13, 8, 0, 45, tzinfo=timezone.utc)

    def test_a_plain_text_message_has_no_reply_id(self):
        [event] = parser.parse(TEXT_PAYLOAD)

        assert event.reply_id is None


class TestParseInteractiveReplies:
    def test_button_reply_id_lands_in_reply_id(self):
        [event] = parser.parse(BUTTON_REPLY_PAYLOAD)

        assert event.reply_id == "menu_cotizacion"

    def test_list_reply_id_lands_in_reply_id(self):
        """Whapi nests the payload under a key named by reply.type, so both
        buttons_reply and list_reply have to resolve without a special case
        per variant."""
        [event] = parser.parse(LIST_REPLY_PAYLOAD)

        assert event.reply_id == "menu_cita"


class TestMessagesWeMustIgnore:
    def test_our_own_outgoing_messages_are_skipped(self):
        payload = {**TEXT_PAYLOAD, "messages": [{**TEXT_PAYLOAD["messages"][0], "from_me": True}]}

        assert parser.parse(payload) == []

    def test_a_payload_with_no_messages_yields_no_events(self):
        assert parser.parse({"event": {"type": "statuses"}, "channel_id": "X"}) == []


class TestBatchedPayloads:
    def test_two_messages_in_one_post_yield_two_events(self):
        """Whapi batches messages in a single POST. Typing this as one event
        loses messages silently."""
        first, second = TEXT_PAYLOAD["messages"][0], BUTTON_REPLY_PAYLOAD["messages"][0]
        payload = {**TEXT_PAYLOAD, "messages": [first, second]}

        assert len(parser.parse(payload)) == 2


class TestChannelRouting:
    def test_channel_id_is_exposed_for_tenant_resolution(self):
        """The tenant is resolved from channel_id, so it cannot stay buried in
        the raw payload."""
        assert parser.channel_id(TEXT_PAYLOAD) == "TOYOPANA-M72HC"


SYSTEM_MESSAGE_PAYLOAD = {
    "messages": [
        {
            "id": "O6twkPMAFbxlRw-heBkXgkAQMI",
            "from": "50768510658",
            "type": "unknown",
            "source": "system",
            "chat_id": "50768510658@s.whatsapp.net",
            "from_me": False,
            "starred": False,
            "from_name": "Diego Sastoque",
            "timestamp": 1788024098,
        }
    ],
    "event": {"type": "messages", "event": "post"},
    "channel_id": "TOYOPANA-M72HC",
}

REAL_BUTTON_REPLY_PAYLOAD = {
    "messages": [
        {
            "id": "OqhcCzaDAQfAaQ-hY5kXgkAQMI",
            "from_me": False,
            "type": "reply",
            "chat_id": "50768510658@s.whatsapp.net",
            "timestamp": 1788024125,
            "reply": {
                "type": "buttons_reply",
                # Whapi prefixes the id we sent. Captured from production.
                "buttons_reply": {"id": "ButtonsV3:menu_agendar_cita", "title": "Agendar cita"},
            },
            "from": "50768510658",
        }
    ],
    "event": {"type": "messages", "event": "post"},
    "channel_id": "TOYOPANA-M72HC",
}


class TestSystemMessagesAreIgnored:
    """Regression: the bot answered the welcome menu three times per message.

    WhatsApp emits protocol-level notifications that Whapi forwards as
    messages with `type: "unknown"`, `source: "system"` and from_me false.
    They carry no text and no reply. Filtering on from_me alone let them
    through as if a customer had written, and each one triggered a reply.

    Captured from production: one "Buenas tardes" at 12:21:35 was followed by
    two of these at 12:21:38 and 12:21:39, producing three menus in a row.
    """

    def test_a_system_message_produces_no_event(self):
        assert parser.parse(SYSTEM_MESSAGE_PAYLOAD) == []

    def test_a_type_we_do_not_handle_produces_no_event(self):
        """Unhandled types must fail closed: stored raw, never answered.
        Anything else means a future WhatsApp message kind starts making the
        bot talk on its own."""
        payload = {**TEXT_PAYLOAD, "messages": [{**TEXT_PAYLOAD["messages"][0], "type": "image"}]}

        assert parser.parse(payload) == []

    def test_a_real_message_arriving_with_system_noise_still_gets_through(self):
        """The real message must survive being batched with the noise."""
        payload = {
            **TEXT_PAYLOAD,
            "messages": [TEXT_PAYLOAD["messages"][0], SYSTEM_MESSAGE_PAYLOAD["messages"][0]],
        }

        events = parser.parse(payload)

        assert len(events) == 1
        assert events[0].body == "Hola, ya está listo mi repuesto?"


class TestButtonIdsRoundTrip:
    """The id we send must be the id we get back, or deterministic routing
    silently never matches."""

    def test_the_whapi_prefix_is_stripped_from_the_reply_id(self):
        [event] = parser.parse(REAL_BUTTON_REPLY_PAYLOAD)

        assert event.reply_id == "menu_agendar_cita"
