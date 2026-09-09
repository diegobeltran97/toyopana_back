"""The signed link that lets a customer book without logging in.

This is the whole access-control story of the public booking page: the token
says WHICH organization, signed. A caller who could forge one, or edit the
organization inside it, would be booking in someone else's shop and reading
their availability.

The link carries NO customer: it is generic, and whoever opens it says who they
are on the page (name and phone are required there). That is what lets an
employee share one link without first finding the person in the CRM -- which is
the common case, because someone writing from an unknown number has no record
yet.

Two rules the rest of the code depends on:

  * `organization_id` comes from HERE and from nowhere else. The public
    endpoints never accept it as a parameter -- same rule that governs the
    bot's tools.
  * It expires. A link shared in a WhatsApp group should not still work in a
    month.

HMAC-SHA256 over a compact payload, base64url so it survives being pasted at
the end of a URL. No external dependency: the standard library covers it, and
a JWT library here would be more surface for the same three fields.
"""

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from typing import Optional

from core.config import settings

# Cuánto vive un link por defecto. Dos días cubre "lo veo mañana" sin dejar
# links vivos indefinidamente en un chat.
TTL_HORAS_DEFAULT = 48


class TokenInvalido(Exception):
    """El token no fue emitido por nosotros, o viene alterado."""


class TokenVencido(Exception):
    """El token era válido pero ya caducó."""


@dataclass(frozen=True)
class DatosToken:
    """Lo que un token válido afirma."""

    organization_id: str
    expira_en: int  # epoch en segundos


def _b64(data: bytes) -> str:
    """base64url sin relleno: seguro dentro de una ruta."""
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _de_b64(texto: str) -> bytes:
    faltante = "=" * (-len(texto) % 4)
    return base64.urlsafe_b64decode(texto + faltante)


def _firmar(cuerpo: str, secreto: str) -> str:
    return _b64(hmac.new(secreto.encode(), cuerpo.encode(), hashlib.sha256).digest())


def _secreto_activo(secreto: Optional[str]) -> str:
    """El secreto de firma. Vacío es un error, nunca "sin firma"."""
    valor = secreto if secreto is not None else getattr(
        settings, "AGENDA_TOKEN_SECRET", ""
    )
    if not valor:
        raise ValueError(
            "AGENDA_TOKEN_SECRET sin configurar: no se pueden emitir links de agenda"
        )
    return valor


def crear_token(
    organization_id: str,
    ttl_horas: int = TTL_HORAS_DEFAULT,
    secreto: Optional[str] = None,
) -> str:
    """Emite el token que va al final del link de la agenda."""
    activo = _secreto_activo(secreto)

    cuerpo = _b64(
        json.dumps(
            {
                "o": organization_id,
                "e": int(time.time()) + ttl_horas * 3600,
            },
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
    )
    return f"{cuerpo}.{_firmar(cuerpo, activo)}"


def leer_token(token: str, secreto: Optional[str] = None) -> DatosToken:
    """Verifica un token y devuelve lo que afirma.

    Verifica la firma ANTES de mirar el contenido: el cuerpo de un token no
    verificado es texto de un desconocido.

    Raises:
        TokenInvalido: mal formado, alterado, o firmado con otro secreto.
        TokenVencido: bien firmado pero caducado.
    """
    activo = _secreto_activo(secreto)

    try:
        cuerpo, firma = token.split(".")
    except ValueError:
        raise TokenInvalido("Formato de token inválido")

    # compare_digest, no ==, para no filtrar la firma por tiempo de respuesta.
    if not hmac.compare_digest(firma, _firmar(cuerpo, activo)):
        raise TokenInvalido("Firma inválida")

    try:
        datos = json.loads(_de_b64(cuerpo))
        organization_id, expira = datos["o"], int(datos["e"])
    except Exception:
        raise TokenInvalido("Contenido de token inválido")

    if expira <= int(time.time()):
        raise TokenVencido("El link ya venció")

    return DatosToken(organization_id=organization_id, expira_en=expira)
