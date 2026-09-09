"""The testing allowlist: who may receive an outbound WhatsApp.

Shared by every path that messages a customer -- the inbound bot's replies and
the appointment notices. It lives here and not in either of them because a copy
per call site is how one of them silently stops honouring it: that already
happened once, and confirming an appointment in the panel messaged a real
customer during testing.

Empty setting means disabled: everyone gets their message. That direction
matters -- forgetting to configure this can never silence production, while
setting it by accident is loud (every skip is logged) and obvious.
"""

import logging

from core.config import settings

logger = logging.getLogger(__name__)


def _solo_digitos(telefono: str) -> str:
    """Compara por dígitos: "+507 6851-0658" y "50768510658" son el mismo."""
    return "".join(filter(str.isdigit, telefono))


def puede_recibir(telefono: str) -> bool:
    """¿Se le puede mandar un mensaje a este número?"""
    raw = getattr(settings, "WHATSAPP_ALLOWED_NUMBERS", "") or ""
    permitidos = {_solo_digitos(n) for n in raw.split(",") if _solo_digitos(n)}

    if not permitidos:
        return True

    if _solo_digitos(telefono) in permitidos:
        return True

    logger.warning("WHATSAPP_ALLOWED_NUMBERS activo: no se escribe a %s", telefono)
    return False
