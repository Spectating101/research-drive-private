from pathlib import Path


def replace_once(path: str, old: str, new: str, label: str) -> None:
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected one match in {path}, found {count}")
    p.write_text(text.replace(old, new, 1), encoding="utf-8")


path = "drive/scripts/research_data_mcp/gateway.py"
replace_once(
    path,
    '''        try:\n            crafted = route.get("collect_plan") if isinstance(route.get("collect_plan"), dict) else None\n''',
    '''        crafted_result = False\n        try:\n            crafted = route.get("collect_plan") if isinstance(route.get("collect_plan"), dict) else None\n''',
    "initialize crafted result",
)
replace_once(
    path,
    '''                linked = store.link_job(intent_id, job)\n                return {\n                    "intent": self._discover_intent_with_job(linked),\n                    "job": job,\n                    "crafted": True,\n                }\n\n            connector_id = str(route.get("connector_id") or "")\n''',
    '''                crafted_result = True\n            else:\n                connector_id = str(route.get("connector_id") or "")\n                if not connector_id:\n                    raise ValueError(\n                        "selected route needs either an AI-crafted collect_plan or a verified connector_id"\n                    )\n                from scripts.research_data_mcp.discover_collect_plan import resolve_discover_collect_plan\n\n                plan = dict(\n                    resolve_discover_collect_plan(\n                        self.procurement,\n                        self.repo_root,\n                        connector_id=connector_id,\n                        source_id=str(\n                            (state.get("candidate") or {}).get("source_id")\n                            or intent.get("source_id")\n                            or ""\n                        ),\n                        limit=min(max(int(limit), 1), 2000),\n                        title=str(intent.get("title") or ""),\n                        url=str(route.get("url") or route.get("source_url") or ""),\n                        candidate_key=str(\n                            route.get("candidate_key")\n                            or (state.get("candidate") or {}).get("candidate_key")\n                            or ""\n                        ),\n                        doi=str(route.get("doi") or (state.get("candidate") or {}).get("doi") or ""),\n                        external_id=str(\n                            route.get("external_id")\n                            or (state.get("candidate") or {}).get("external_id")\n                            or ""\n                        ),\n                        provider=str(\n                            route.get("provider")\n                            or (state.get("candidate") or {}).get("provider")\n                            or ""\n                        ),\n                        kind=str(route.get("kind") or (state.get("candidate") or {}).get("kind") or ""),\n                        dataset_id=str(\n                            route.get("dataset_id")\n                            or (state.get("candidate") or {}).get("dataset_id")\n                            or ""\n                        ),\n                    )\n                )\n                plan.update(\n                    {\n                        "discover_intent_id": intent_id,\n                        "candidate_key": route.get("candidate_key")\n                        or (state.get("candidate") or {}).get("candidate_key")\n                        or "",\n                        "destination": route.get("destination") or plan.get("destination") or "",\n                        "refresh_strategy": route.get("refresh") or "",\n                    }\n                )\n                submitted = self.jobs.submit(\n                    plan.get("title") or intent.get("title") or "Discover collection",\n                    plan,\n                    {\n                        "source": "discover_intent",\n                        "discover_intent_id": intent_id,\n                        "idempotency_key": f"discover:{intent_id}",\n                        "research_need": intent.get("research_need") or "",\n                        "route_id": selected_id,\n                        "connector_id": connector_id,\n                    },\n                    auto_approve=False,\n                )\n                job = submitted.get("job") or {}\n                if not job:\n                    raise ValueError(str(submitted.get("error") or "Discover collection plan is not launchable"))\n\n            connector_id = "__already_resolved__"\n''',
    "move crafted link outside queue try",
)
# The first patch emitted a catalog branch after the crafted branch. Remove that
# now-duplicated block between the sentinel and the common exception handler.
p = Path(path)
text = p.read_text(encoding="utf-8")
sentinel = '            connector_id = "__already_resolved__"\n'
start = text.index(sentinel) + len(sentinel)
end = text.index("        except Exception as exc:\n", start)
text = text[:start] + text[end:]
p.write_text(text, encoding="utf-8")

replace_once(
    path,
    '''        linked = store.link_job(intent_id, job)\n        return {"intent": self._discover_intent_with_job(linked), "job": job}\n''',
    '''        linked = store.link_job(intent_id, job)\n        out = {"intent": self._discover_intent_with_job(linked), "job": job}\n        if crafted_result:\n            out["crafted"] = True\n        return out\n''',
    "preserve crafted response after final link",
)

print("Adjusted Discover submit so linked jobs are never rolled back")
