from scripts.research_data_mcp.desk_resources import _query_engine_up


def test_query_engine_remains_up_when_desk_is_degraded() -> None:
    assert _query_engine_up(
        {"service": "research_library_api", "status": "degraded"}
    )


def test_query_engine_requires_a_serving_health_payload() -> None:
    assert not _query_engine_up(None)
    assert not _query_engine_up({"service": "research_library_api", "status": "error"})
    assert not _query_engine_up({"status": "ok"})
