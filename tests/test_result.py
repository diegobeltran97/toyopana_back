"""Tests for the typed Result object (core/result.py)."""

from core.result import Result


def test_success_carries_value_and_is_ok():
    result = Result.success({"id": "msg_123"})

    assert result.ok is True
    assert result.value == {"id": "msg_123"}
    assert result.error is None


def test_failure_carries_error_code_and_is_not_ok():
    result = Result.failure("auth_failed", status_code=401, details="bad token")

    assert result.ok is False
    assert result.value is None
    assert result.error == "auth_failed"
    assert result.status_code == 401
    assert result.details == "bad token"


def test_failure_without_optional_fields():
    result = Result.failure("timeout")

    assert result.ok is False
    assert result.error == "timeout"
    assert result.status_code is None
    assert result.details is None


def test_result_is_immutable():
    import dataclasses

    result = Result.success("ok")
    try:
        result.ok = False  # type: ignore[misc]
        assert False, "Result should be frozen/immutable"
    except dataclasses.FrozenInstanceError:
        pass
