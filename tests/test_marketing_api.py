"""API test for GET /api/marketing/metrics (endpoints/marketing.py).

The service is monkeypatched to a canned result so the test verifies the HTTP
boundary (route, query-param requirement, response shape) without any I/O. A
minimal FastAPI app mounts only the marketing router.
"""

from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient

import api.v1.endpoints.marketing as marketing_endpoint
from schemas.marketing import FunnelOut, MarketingMetricsOut

app = FastAPI()
app.include_router(marketing_endpoint.router, prefix="/api/marketing")
client = TestClient(app)


def _canned():
    return MarketingMetricsOut(
        messages_sent_today=47,
        messages_sent_yesterday=39,
        response_rate=0.72,
        appointments_scheduled=9,
        conversion_to_appointment=0.69,
        funnel=FunnelOut(
            requiere_de_contacto=5, contactado=4, agendado=5, finalizada=4
        ),
        generated_at=datetime.now(timezone.utc),
    )


def test_requires_organization_id():
    response = client.get("/api/marketing/metrics")
    assert response.status_code == 422


def test_returns_metrics(monkeypatch):
    async def fake_get(organization_id):
        assert organization_id == "org-1"
        return _canned()

    monkeypatch.setattr(
        marketing_endpoint.marketing_service, "get_marketing_metrics", fake_get
    )

    response = client.get(
        "/api/marketing/metrics", params={"organization_id": "org-1"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["messages_sent_today"] == 47
    assert body["appointments_scheduled"] == 9
    assert body["funnel"]["agendado"] == 5
    assert body["response_rate"] == 0.72
