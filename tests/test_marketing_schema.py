"""Tests for the marketing metrics schemas (schemas/marketing.py)."""

from datetime import datetime, timezone

from schemas.marketing import FunnelOut, MarketingMetricsOut


def test_metrics_out_allows_null_rates_and_defaults_timezone():
    metrics = MarketingMetricsOut(
        messages_sent_today=0,
        messages_sent_yesterday=0,
        response_rate=None,
        appointments_scheduled=0,
        conversion_to_appointment=None,
        funnel=FunnelOut(
            requiere_de_contacto=0, contactado=0, agendado=0, finalizada=0
        ),
        generated_at=datetime.now(timezone.utc),
    )

    assert metrics.response_rate is None
    assert metrics.conversion_to_appointment is None
    assert metrics.timezone == "America/Panama"
    assert metrics.funnel.agendado == 0
