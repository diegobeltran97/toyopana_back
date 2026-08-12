"""Tests for the cita reminder templates (services/cita_reminders.py).

v1 has no scheduler: these assert the template contract and the computed fire
times, which is what a future cron/queue will consume.
"""

import logging
from datetime import datetime, timedelta, timezone

from services.cita_reminders import (
    REMINDER_TEMPLATES,
    planned_reminders,
    schedule_reminders,
)


def test_two_named_templates_in_firing_order():
    names = [t.name for t in REMINDER_TEMPLATES]
    assert names == ["recordatorio_cita_24h", "recordatorio_cita_2h"]


def test_templates_declare_their_offsets():
    by_name = {t.name: t for t in REMINDER_TEMPLATES}
    assert by_name["recordatorio_cita_24h"].offset_before == timedelta(hours=24)
    assert by_name["recordatorio_cita_2h"].offset_before == timedelta(hours=2)


def test_every_template_body_uses_exactly_its_declared_params():
    """The param list is the migration contract to Meta Cloud API templates:
    a body placeholder that isn't declared would break that mapping."""
    for template in REMINDER_TEMPLATES:
        rendered = template.body.format(**{p: "X" for p in template.params})
        assert "{" not in rendered
        for param in template.params:
            assert "{" + param + "}" in template.body


def test_planned_reminders_computes_fire_times():
    scheduled_at = datetime(2026, 9, 10, 15, 0, tzinfo=timezone.utc)

    plans = planned_reminders(scheduled_at)

    assert [p.template_name for p in plans] == [
        "recordatorio_cita_24h",
        "recordatorio_cita_2h",
    ]
    assert plans[0].fire_at == datetime(2026, 9, 9, 15, 0, tzinfo=timezone.utc)
    assert plans[1].fire_at == datetime(2026, 9, 10, 13, 0, tzinfo=timezone.utc)


def test_schedule_reminders_logs_intent_and_returns_plans(caplog):
    scheduled_at = datetime(2026, 9, 10, 15, 0, tzinfo=timezone.utc)

    with caplog.at_level(logging.INFO, logger="services.cita_reminders"):
        plans = schedule_reminders("cita-1", scheduled_at)

    assert len(plans) == 2
    assert any("cita-1" in r.message for r in caplog.records)
