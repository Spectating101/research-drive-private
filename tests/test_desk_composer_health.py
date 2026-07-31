"""Configured Composer is not considered ready until a real call succeeds."""

from __future__ import annotations


def test_configured_but_untried_is_unverified():
    from scripts.research_data_mcp.desk_composer_health import (
        _reset_composer_runtime_status,
        composer_runtime_status,
    )

    _reset_composer_runtime_status()
    status = composer_runtime_status(configured=True)
    assert status["status"] == "unverified"
    assert status["configured"] is True
    assert status["verified"] is False


def test_success_is_verified_ready():
    from scripts.research_data_mcp.desk_composer_health import (
        _reset_composer_runtime_status,
        composer_runtime_status,
        record_composer_success,
    )

    _reset_composer_runtime_status()
    record_composer_success(model="composer-test")
    status = composer_runtime_status(configured=True)
    assert status["status"] == "ready"
    assert status["verified"] is True
    assert status["model"] == "composer-test"
    assert status["checked_at"]
    assert status["error_category"] is None


def test_provider_failure_is_verified_degraded_without_raw_error():
    from scripts.research_data_mcp.desk_composer_health import (
        _reset_composer_runtime_status,
        composer_runtime_status,
        record_composer_failure,
    )

    _reset_composer_runtime_status()
    record_composer_failure(
        "cursor_sdk.errors.InternalServerError: internal: internal error",
        model="default",
    )
    status = composer_runtime_status(configured=True)
    assert status["status"] == "degraded"
    assert status["verified"] is True
    assert status["error_category"] == "provider_internal"
    assert "internal error" not in str(status)


def test_missing_configuration_is_unavailable_regardless_of_prior_call():
    from scripts.research_data_mcp.desk_composer_health import (
        _reset_composer_runtime_status,
        composer_runtime_status,
        record_composer_success,
    )

    _reset_composer_runtime_status()
    record_composer_success(model="default")
    status = composer_runtime_status(configured=False)
    assert status["status"] == "unavailable"
    assert status["configured"] is False
    assert status["verified"] is False


def test_old_success_becomes_stale_instead_of_staying_ready():
    from scripts.research_data_mcp import desk_composer_health

    desk_composer_health._reset_composer_runtime_status()
    desk_composer_health.record_composer_success(model="default")
    desk_composer_health._LAST["checked_at"] = "2000-01-01T00:00:00+00:00"

    status = desk_composer_health.composer_runtime_status(
        configured=True,
        max_age_seconds=60,
    )
    assert status["status"] == "stale"
    assert status["verified"] is False
    assert status["error_category"] == "stale_observation"
    assert status["age_seconds"] > 60
