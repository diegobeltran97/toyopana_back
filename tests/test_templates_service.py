"""Tests for template authoring rules (services/templates_service.py).

The rule that matters: a template's declared params must match the
{placeholders} in its body. Drift renders a literal "{car_info}" into a
customer's message on Whapi, and is a rejected submission on Meta/Twilio --
so it is refused at authoring time rather than discovered at send time.
"""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from services import templates_service

ORG = "22222222-2222-2222-2222-222222222222"

VALID = {
    "name": "delivery_notification",
    "body": "Hola {customer_name}, tu {car_info}.",
    "params": ["customer_name", "car_info"],
}


@pytest.fixture
def repo():
    with patch.object(templates_service, "MessageTemplateRepository") as factory:
        instance = factory.return_value
        instance.create = AsyncMock(side_effect=lambda org, data: {"id": "t1", **data})
        instance.update = AsyncMock(side_effect=lambda org, tid, data: {"id": tid, **data})
        instance.delete = AsyncMock(return_value=True)
        instance.list = AsyncMock(return_value=[])
        yield instance


class TestCreateValidation:
    async def test_accepts_a_template_whose_params_match_its_body(self, repo):
        row = await templates_service.create_template(ORG, dict(VALID))

        assert row["name"] == "delivery_notification"
        repo.create.assert_awaited_once()

    async def test_rejects_a_placeholder_missing_from_params(self, repo):
        bad = {**VALID, "params": ["customer_name"]}  # body still uses car_info

        with pytest.raises(HTTPException) as exc:
            await templates_service.create_template(ORG, bad)

        assert exc.value.status_code == 422
        assert "car_info" in exc.value.detail
        repo.create.assert_not_awaited()

    async def test_rejects_a_param_not_used_in_the_body(self, repo):
        bad = {**VALID, "params": [*VALID["params"], "order_number"]}

        with pytest.raises(HTTPException) as exc:
            await templates_service.create_template(ORG, bad)

        assert exc.value.status_code == 422
        assert "order_number" in exc.value.detail
        repo.create.assert_not_awaited()

    async def test_accepts_copy_with_no_placeholders(self, repo):
        row = await templates_service.create_template(
            ORG, {"name": "aviso", "body": "Estamos cerrados hoy.", "params": []}
        )

        assert row["name"] == "aviso"


class TestUpdateValidation:
    async def test_validates_the_post_patch_state_not_just_the_new_field(self, repo):
        # Body gains {order_number} while params are untouched: the patch is
        # individually plausible but the resulting template is inconsistent.
        repo.list = AsyncMock(
            return_value=[{"id": "t1", **VALID}]
        )

        with pytest.raises(HTTPException) as exc:
            await templates_service.update_template(
                ORG, "t1", {"body": "Hola {customer_name} {car_info} {order_number}"}
            )

        assert exc.value.status_code == 422
        assert "order_number" in exc.value.detail

    async def test_allows_a_consistent_patch(self, repo):
        repo.list = AsyncMock(return_value=[{"id": "t1", **VALID}])

        row = await templates_service.update_template(
            ORG,
            "t1",
            {"body": "Hola {customer_name}.", "params": ["customer_name"]},
        )

        assert row["id"] == "t1"

    async def test_patch_without_body_or_params_skips_validation(self, repo):
        row = await templates_service.update_template(ORG, "t1", {"is_active": False})

        assert row["is_active"] is False

    async def test_missing_template_is_404(self, repo):
        repo.update = AsyncMock(return_value=None)

        with pytest.raises(HTTPException) as exc:
            await templates_service.update_template(ORG, "nope", {"language": "en"})

        assert exc.value.status_code == 404


class TestDelete:
    async def test_missing_template_is_404(self, repo):
        repo.delete = AsyncMock(return_value=False)

        with pytest.raises(HTTPException) as exc:
            await templates_service.delete_template(ORG, "nope")

        assert exc.value.status_code == 404
