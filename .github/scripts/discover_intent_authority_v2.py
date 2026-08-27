from pathlib import Path


def replace_once(path: str, old: str, new: str, label: str) -> None:
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected one match in {path}, found {count}")
    p.write_text(text.replace(old, new, 1), encoding="utf-8")


store = "drive/scripts/research_data_mcp/discover_intent_store.py"
replace_once(
    store,
    '''            if state.get("status") != "ready_for_review":\n                raise ValueError("route selection requires a reviewed Discover proposal")\n            if self._collection_started(state):\n                raise ValueError("cannot change route after collection submission has started")\n''',
    '''            if self._collection_started(state):\n                raise ValueError("cannot change route after collection submission has started")\n            if state.get("status") != "ready_for_review":\n                raise ValueError("route selection requires a reviewed Discover proposal")\n''',
    "prefer consequential-state error for route mutation",
)

gateway = "drive/scripts/research_data_mcp/gateway.py"
replace_once(
    gateway,
    '''        store = self._discover_intent_store()\n        intent = store.reserve_submission(intent_id)\n''',
    '''        store = self._discover_intent_store()\n        existing = store.get(intent_id)\n        existing_collection = dict((existing.get("state") or {}).get("collection") or {})\n        existing_job_id = str(existing_collection.get("job_id") or "").strip()\n        if existing_job_id:\n            # A repeated API submit after the consequence is durable is a read\n            # of that consequence, not permission to recreate or re-plan it.\n            job = self.jobs.get(existing_job_id)\n            if not job:\n                raise RuntimeError(\n                    f"Discover intent references missing collection job {existing_job_id}"\n                )\n            return {"intent": self._discover_intent_with_job(existing), "job": job}\n\n        intent = store.reserve_submission(intent_id)\n''',
    "make linked submission replay a read",
)

print("Applied Discover intent authority v2 replay semantics")
