"""Tests for marketing_service.get_marketing_metrics (services/marketing_service.py).

Both repositories are replaced with small fakes so the test exercises only the
service's arithmetic (funnel wiring, conversion, response rate) with no I/O.
"""

from services.marketing_service import get_marketing_metrics


class FakeDashboardRepo:
    def __init__(self, counts):
        self._counts = counts  # status code -> int

    async def count_orders(self, organization_id, statuses=None, received_after=None):
        return self._counts.get(statuses[0], 0)


class FakeMarketingRepo:
    def __init__(self, today, yesterday, outbound_ids, inbound_ids):
        self._today = today
        self._yesterday = yesterday
        self._outbound = outbound_ids
        self._inbound = inbound_ids

    async def count_outbound_messages(self, organization_id, sent_after, sent_before=None):
        return self._yesterday if sent_before else self._today

    async def conversation_ids_with_message(self, organization_id, direction, sent_after):
        return self._outbound if direction == "outbound" else self._inbound


async def test_conversion_and_response_rate_computed():
    dash = FakeDashboardRepo(
        {"requiere_de_contacto": 5, "contactado": 4, "agendado": 5, "finalizada": 4}
    )
    mkt = FakeMarketingRepo(
        today=47,
        yesterday=39,
        outbound_ids={"c1", "c2", "c3", "c4"},
        inbound_ids={"c1", "c2", "c5"},
    )

    m = await get_marketing_metrics("org-1", marketing_repo=mkt, dashboard_repo=dash)

    assert m.messages_sent_today == 47
    assert m.messages_sent_yesterday == 39
    assert m.appointments_scheduled == 5
    assert m.funnel.contactado == 4
    # agendado / (contactado + agendado + finalizada) = 5 / 13
    assert m.conversion_to_appointment == round(5 / 13, 4)
    # messaged ∩ replied = {c1, c2} over messaged {c1..c4} = 2/4
    assert m.response_rate == 0.5


async def test_null_rates_when_no_data():
    dash = FakeDashboardRepo(
        {"requiere_de_contacto": 0, "contactado": 0, "agendado": 0, "finalizada": 0}
    )
    mkt = FakeMarketingRepo(today=0, yesterday=0, outbound_ids=set(), inbound_ids=set())

    m = await get_marketing_metrics("org-1", marketing_repo=mkt, dashboard_repo=dash)

    assert m.conversion_to_appointment is None
    assert m.response_rate is None
    assert m.appointments_scheduled == 0
    assert m.funnel.requiere_de_contacto == 0
