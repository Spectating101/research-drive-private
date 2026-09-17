from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_candidate_service_identity_is_resolved_after_selected_env() -> None:
    script = (
        ROOT / "drive/scripts/research_query_engine/verify_front_door_restartability.sh"
    ).read_text(encoding="utf-8")

    source_at = script.index('set -a; . "$env_file"; set +a')
    unit_at = script.index('unit="${FRONT_DOOR_SERVICE_UNIT:-research-drive-front-door.service}"')
    wait_at = script.index('max_wait="${RESTARTABILITY_MAX_WAIT_SECONDS:-45}"')

    assert source_at < unit_at
    assert source_at < wait_at
