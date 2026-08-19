"""Message template domain model (provider-neutral).

A template is a *named* piece of copy with named parameters. Who renders it
depends on the provider, and that difference is the whole reason this exists:

  * Unofficial providers (Whapi, Baileys) have no template concept. Their
    adapter renders ``body`` locally and sends plain text.
  * Official providers (Meta Cloud API, Twilio) require the copy to be
    pre-approved on *their* side. Their adapter ignores ``body`` and sends
    ``provider_template_name`` + params by reference.

So ``body`` is the copy for locally-rendering providers, not the source of
truth for official ones.

Storage lives in ``repositories/message_templates.py``; resolution and
parameter validation live in ``services/templates_service.py``. This module is
pure domain -- no I/O -- so the rendering rules can be unit-tested without a
database and reused by any provider.
"""

import re
from dataclasses import dataclass, field
from typing import Mapping, Optional, Tuple

# Matches {param} and {{ param }}, mirroring the frontend's interpolation.
_PLACEHOLDER_RE = re.compile(r"\{\{\s*(\w+)\s*\}\}|\{\s*(\w+)\s*\}")


def extract_placeholders(body: str) -> Tuple[str, ...]:
    """Every distinct ``{param}`` appearing in a template body, in order.

    Used to validate authored templates: a declared parameter list that has
    drifted from the copy is silent on Whapi (rendered locally, leaving a
    literal ``{car_info}`` in the message) but a rejected submission on Meta.
    """
    seen: list[str] = []
    for double, single in _PLACEHOLDER_RE.findall(body):
        name = double or single
        if name not in seen:
            seen.append(name)
    return tuple(seen)


@dataclass(frozen=True, slots=True)
class MessageTemplate:
    """A named template plus the parameters it expects."""

    name: str
    body: str
    params: Tuple[str, ...] = field(default=())
    language: str = "es"
    # Class B only: the approved template's name on the provider's side.
    provider_template_name: Optional[str] = None

    def missing_params(self, params: Mapping[str, str]) -> Tuple[str, ...]:
        """Declared parameters absent from ``params``.

        Checked before dispatch so the failure is identical on every provider,
        rather than surfacing as a local render error on one and an upstream
        rejection on another.
        """
        return tuple(p for p in self.params if p not in params)

    def render(self, params: Mapping[str, str]) -> str:
        """Render the local copy. Only used by providers that render client-side.

        Raises:
            KeyError: if a required parameter is missing. Callers should use
                ``missing_params`` first; this is the last line of defence
                against sending copy with unfilled placeholders.
        """
        missing = self.missing_params(params)
        if missing:
            raise KeyError(", ".join(missing))
        return self.body.format(**params).strip()
