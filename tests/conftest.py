"""Defaults para toda la suite.

Los tests NO pueden depender del app/.env de quien los corra. De todos los
settings, WHATSAPP_ALLOWED_NUMBERS es el que cambia resultados en silencio:
basta con que alguien ponga ahí su número para probar a mano, y de pronto todo
test cuyo teléfono de fixture sea otro deja de enviar y falla -- sin que el
código haya cambiado. Pasó el 2026-09-24 al configurarlo para una prueba
manual: dos tests verdes se pusieron rojos por el .env, no por el código.
"""

import pytest

from core.config import settings


@pytest.fixture(autouse=True)
def _allowlist_abierta(monkeypatch):
    """Allowlist vacía: pasa cualquiera, que es el default de producción.

    Los tests que prueban la compuerta en sí la vuelven a poner ellos mismos —
    su monkeypatch corre después de este y gana.
    """
    monkeypatch.setattr(settings, "WHATSAPP_ALLOWED_NUMBERS", "", raising=False)
