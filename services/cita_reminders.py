"""WhatsApp reminder templates for citas — structure only, no scheduler.

Why templates-as-data now: today messages go out through Whapi (free-form
text), but Meta's Cloud API only accepts pre-approved templates addressed BY
NAME with positional params. Declaring each reminder as a named template with
an explicit param list means that migration is a name -> approved-template
mapping, with no message rewriting.

v1 wires the trigger point only: create_cita calls schedule_reminders(), which
computes when each reminder WOULD fire and records the intent in the log. The
cron/queue that actually sends them is a documented follow-up.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List, Tuple

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ReminderTemplate:
    """One named reminder: when it fires, what it needs, and what it says."""

    name: str
    offset_before: timedelta
    params: Tuple[str, ...]
    body: str


@dataclass(frozen=True)
class PlannedReminder:
    """A template resolved against a concrete cita: which one, and when."""

    template_name: str
    fire_at: datetime


REMINDER_TEMPLATES: Tuple[ReminderTemplate, ...] = (
    ReminderTemplate(
        name="recordatorio_cita_24h",
        offset_before=timedelta(hours=24),
        params=("nombre_cliente", "fecha_hora", "servicio"),
        body=(
            "Hola {nombre_cliente}, le recordamos su cita en Toyopana para "
            "{servicio} el {fecha_hora}. ¿Nos confirma su asistencia?"
        ),
    ),
    ReminderTemplate(
        name="recordatorio_cita_2h",
        offset_before=timedelta(hours=2),
        params=("nombre_cliente", "fecha_hora", "servicio"),
        body=(
            "Hola {nombre_cliente}, su cita en Toyopana para {servicio} es hoy "
            "a las {fecha_hora}. ¡Le esperamos!"
        ),
    ),
)


def planned_reminders(scheduled_at: datetime) -> List[PlannedReminder]:
    """
    Resolve every template against a cita's time.

    Args:
        scheduled_at: When the cita is booked for (timezone-aware).

    Returns:
        One PlannedReminder per template, in template order.
    """
    return [
        PlannedReminder(
            template_name=template.name,
            fire_at=scheduled_at - template.offset_before,
        )
        for template in REMINDER_TEMPLATES
    ]


def schedule_reminders(cita_id: str, scheduled_at: datetime) -> List[PlannedReminder]:
    """
    Trigger point called on cita creation.

    v1 computes the fire times and logs the intent — there is no scheduler yet,
    so nothing is enqueued and nothing is sent. This function is where the
    future cron/queue enqueue call goes; keeping the call site live now means
    the follow-up only has to change this body.

    Args:
        cita_id: The cita the reminders belong to.
        scheduled_at: When the cita is booked for (timezone-aware).

    Returns:
        The reminders that would be sent.
    """
    plans = planned_reminders(scheduled_at)
    for plan in plans:
        logger.info(
            "Reminder planned (not scheduled — no scheduler in v1): cita=%s "
            "template=%s fire_at=%s",
            cita_id,
            plan.template_name,
            plan.fire_at.isoformat(),
        )
    return plans
