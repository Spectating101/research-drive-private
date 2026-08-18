"""A plain Discover request must reach the public catalogue adapters.

The chat fast path used to require the researcher to say the implementation
word ``live`` before it searched outside the local source map.  That made
Discover behave like a small cache rather than an outward-facing data search.
"""

from __future__ import annotations


class _Gateway:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int, bool]] = []

    def discover_source_search(self, query: str, *, limit: int, live: bool) -> dict:
        self.calls.append((query, limit, live))
        return {
            "results": [
                {
                    "source_id": "huggingface",
                    "title": "Patent abstracts",
                    "access_mode": "live_connector",
                }
            ],
            "search_mode": "live",
        }


def test_plain_discover_request_uses_live_catalogues() -> None:
    from scripts.research_data_mcp.desk_direct_turns import try_direct_discover_search_turn

    gateway = _Gateway()
    turn = try_direct_discover_search_turn(
        gateway,
        "Search Discover for US patent grants and citations",
        {},
    )

    assert turn is not None
    assert gateway.calls == [("US patent grants and citations", 12, True)]
    assert turn.action_result["search_mode"] == "live"
