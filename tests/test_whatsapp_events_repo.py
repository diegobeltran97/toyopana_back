"""Tests for repositories/whatsapp_events.py.

Only the pure part: how an event that the parser could not read gets an
idempotency key. Everything else in that module is I/O.
"""

from repositories.whatsapp_events import stable_event_id


class TestStableEventId:
    def test_the_same_payload_always_yields_the_same_id(self):
        """Python's hash() is salted per process, so an id built with it would
        change on every restart -- and a provider retry after a deploy would be
        stored twice, which is exactly what this table exists to prevent."""
        payload = {"event": {"type": "statuses"}, "channel_id": "TOYOPANA-M72HC"}

        assert stable_event_id(payload) == stable_event_id(payload)

    def test_key_order_does_not_change_the_id(self):
        a = {"channel_id": "X", "event": {"type": "statuses"}}
        b = {"event": {"type": "statuses"}, "channel_id": "X"}

        assert stable_event_id(a) == stable_event_id(b)

    def test_different_payloads_yield_different_ids(self):
        a = stable_event_id({"channel_id": "X"})
        b = stable_event_id({"channel_id": "Y"})

        assert a != b
