#!/usr/bin/env python3
"""Dataset advisor — measured desk facts only (no catalog fit ranking).

Former token-score / hard-coded GDELT/SEC wallpaper was a script brain.
Composer judges fit via Ask + MCP; this returns what the desk holds or can collect.
"""

from __future__ import annotations

from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from scripts.research_data_mcp.gateway import ResearchDataGateway


class DatasetAdvisor:
    def __init__(self, gateway: ResearchDataGateway) -> None:
        self.gateway = gateway

    def advise(
        self,
        goal: str,
        *,
        current_dataset_id: str = "",
        current_task_id: str = "",
        limit: int = 5,
        rail_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        goal = goal.strip()
        if not goal:
            raise ValueError("goal is required — describe what you are trying to analyze or procure")

        from scripts.research_data_mcp.desk_ask_grounding import measure_ask_desk

        desk = measure_ask_desk(
            self.gateway, goal, candidate_limit=limit, rail_context=rail_context
        )
        held = [dict(r) for r in (desk.get("held") or [])[:limit] if isinstance(r, dict)]
        routes = [dict(r) for r in (desk.get("routes") or [])[:3] if isinstance(r, dict)]
        strong = bool(desk.get("strong_held"))
        current = (current_dataset_id or current_task_id or "").strip()

        recommended: list[dict[str, str]] = []
        for row in held:
            rid = str(row.get("dataset_id") or row.get("id") or "").strip()
            if not rid:
                continue
            recommended.append(
                {
                    "id": rid,
                    "kind": "registry_dataset",
                    "reason": "measured Library hold (Ask DESK_FACTS)",
                }
            )
        for row in routes:
            if strong:
                break
            sid = str(row.get("source_id") or "").strip()
            if not sid:
                continue
            recommended.append(
                {
                    "id": sid,
                    "kind": "declared_route",
                    "reason": str(row.get("why") or row.get("selection_reason") or "declared collectable route"),
                }
            )
            if len(recommended) >= limit:
                break

        not_recommended: list[dict[str, str]] = []
        held_ids = {r["id"].lower() for r in recommended if r["kind"] == "registry_dataset"}
        if current and held_ids and current.lower() not in held_ids:
            not_recommended.append(
                {
                    "id": current,
                    "kind": "user_selection",
                    "reason": (
                        f"'{current}' is not among measured holdings for this goal. "
                        "Composer should verify before treating it as a fit."
                    ),
                }
            )

        if strong and held:
            verdict = "use_held"
            message = (
                f"Library holds {len(held)} measured dataset(s) for “{goal}”. "
                "Composer judges whether they fit the analysis."
            )
            next_steps = [
                f"research_describe_dataset('{recommended[0]['id']}')"
                if recommended
                else "research_discover_desk",
                "ask Composer via /library/chat",
            ]
        elif routes:
            verdict = "collect_route"
            message = (
                f"Nothing strong held; {len(routes)} declared route(s) could supply “{goal}”."
            )
            next_steps = [
                "research_discover_desk",
                f"collect via source_id={routes[0].get('source_id')}" if routes else "paste_url",
                "ask Composer via /library/chat",
            ]
        elif held:
            verdict = "weak_held"
            message = (
                f"Only weak lexical hits for “{goal}” — verify before use; "
                "do not treat as ranked recommendations."
            )
            next_steps = ["research_discover_desk", "ask Composer via /library/chat"]
        else:
            verdict = "ask_composer"
            message = (
                f"No measured hold or declared route for “{goal}”. "
                "Ask Composer (MCP) or paste a URL — catalog token ranking is disabled."
            )
            next_steps = [
                "research_discover_desk",
                "research_web_discover",
                "ask Composer via /library/chat",
            ]

        # Compat for callers that still branch on good_fit / wrong_fit / partial_fit.
        legacy_verdict = {
            "use_held": "good_fit",
            "weak_held": "partial_fit",
            "collect_route": "partial_fit",
            "ask_composer": "wrong_fit" if not_recommended else "wrong_fit",
        }.get(verdict, "wrong_fit")

        return {
            "verdict": legacy_verdict,
            "desk_verdict": verdict,
            "message": message,
            "recommended": recommended[:limit],
            "not_recommended": not_recommended,
            "next_steps": next_steps,
            "engine": "ask_desk_facts",
            "goal": goal,
            "held_count": len(held),
            "route_count": 0 if strong else len(routes),
            "strong_held": strong,
            "advisor_note": (
                "Measured Ask DESK_FACTS (incl. synthesis peers) — no catalog fit ranking. "
                "Composer judges fit via Ask/MCP."
            ),
            "stack": "advise_l0_hands",
        }
