"""Typed success/failure return value shared across integrations.

Replaces the ad-hoc ``{"success": bool, ...}`` dicts so callers get a typed
result instead of guessing at dict keys. See the integration blueprint:
docs/superpowers/specs/2026-07-18-whapi-integration-blueprint-design.md
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, Optional, TypeVar

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class Result(Generic[T]):
    """A typed success or failure.

    Attributes:
        ok: True on success, False on failure.
        value: The payload on success; None on failure.
        error: Stable machine-readable error code on failure
            (e.g. "auth_failed", "rate_limit", "timeout").
        status_code: Upstream HTTP status code, when applicable.
        details: Human-readable extra context for logs/debugging.
    """

    ok: bool
    value: Optional[T] = None
    error: Optional[str] = None
    status_code: Optional[int] = None
    details: Optional[str] = None

    @classmethod
    def success(cls, value: T) -> "Result[T]":
        return cls(ok=True, value=value)

    @classmethod
    def failure(
        cls,
        error: str,
        status_code: Optional[int] = None,
        details: Optional[str] = None,
    ) -> "Result[T]":
        return cls(ok=False, error=error, status_code=status_code, details=details)
