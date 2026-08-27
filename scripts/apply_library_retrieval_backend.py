from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"pattern not found in {path}: {old[:120]!r}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


# Query engine: replace title-ish substring lookup with evidence-aware ranked retrieval.
replace_once(
    "drive/scripts/research_query_engine/engine.py",
    "from typing import Any\n\ncsv.field_size_limit(sys.maxsize)\n",
    "from typing import Any\n\nfrom scripts.research_data_mcp.library_retrieval import rank_registry_assets\n\ncsv.field_size_limit(sys.maxsize)\n",
)
replace_once(
    "drive/scripts/research_query_engine/engine.py",
    '''    def search_datasets(self, q: str = "", domain: str = "", readiness: str = "", access_mode: str = "", limit: int = 50) -> list[dict[str, Any]]:
        ql = q.lower().strip()
        tokens = [t for t in re.split(r"\\W+", ql) if len(t) > 2]
        patterns = [(t, re.compile(r"\\b" + re.escape(t))) for t in tokens]
        scored: list[tuple[int, dict[str, Any]]] = []
        for ds in self.list_datasets():
            text = self.searchable_text(ds)
            matched: list[str] = []
            if ql:
                if ql in text:
                    score = 100
                    matched = list(tokens) or [ql]
                elif patterns:
                    matched = [token for token, pattern in patterns if pattern.search(text)]
                    score = 10 * len(matched)
                    if score == 0:
                        continue
                else:
                    continue
            else:
                score = 0
            if domain and domain != ds.get("domain"):
                continue
            if readiness and readiness not in str(ds.get("analysis_readiness", "")):
                continue
            if access_mode and access_mode != ds.get("access_shape"):
                continue
            if ql:
                ds = dict(ds)
                ds["match_terms"] = matched
                ds["match_terms_total"] = len(tokens)
            scored.append((score, ds))
        scored.sort(key=lambda row: (-row[0], row[1].get("dataset_id", "")))
        return [ds for _, ds in scored[:limit]]
''',
    '''    def search_datasets(self, q: str = "", domain: str = "", readiness: str = "", access_mode: str = "", limit: int = 50) -> list[dict[str, Any]]:
        candidates: list[dict[str, Any]] = []
        for ds in self.list_datasets():
            if domain and domain != ds.get("domain"):
                continue
            if readiness and readiness not in str(ds.get("analysis_readiness", "")):
                continue
            if access_mode and access_mode != ds.get("access_shape"):
                continue
            candidates.append(ds)
        if not str(q or "").strip():
            return sorted(
                (dict(ds) for ds in candidates),
                key=lambda row: str(row.get("dataset_id") or ""),
            )[: max(1, int(limit or 50))]
        return rank_registry_assets(candidates, q, limit=max(1, int(limit or 50)))
''',
)

# Search service: Library/Ask can ask for holdings only, preserving the possession boundary.
replace_once(
    "drive/scripts/research_data_mcp/search.py",
    '''        limit: int = 200,
        include_ops: bool = False,
    ) -> dict[str, Any]:
''',
    '''        limit: int = 200,
        include_ops: bool = False,
        held_only: bool = False,
    ) -> dict[str, Any]:
''',
)
replace_once(
    "drive/scripts/research_data_mcp/search.py",
    '''            combined = kept_registry + kept_recovery
        total_matching = len(combined)
''',
    '''            combined = kept_registry + kept_recovery
        if held_only:
            from scripts.research_data_mcp.library_possession import is_library_holding

            combined = [row for row in combined if is_library_holding(row)]
        total_matching = len(combined)
''',
)
replace_once(
    "drive/scripts/research_data_mcp/search.py",
    '''                    "limit": bounded_limit,
                    "includes_receipt_recovery": bool(recovery_rows),
''',
    '''                    "limit": bounded_limit,
                    "held_only": bool(held_only),
                    "includes_receipt_recovery": bool(recovery_rows),
''',
)
replace_once(
    "drive/scripts/research_data_mcp/search.py",
    '''            "include_ops": bool(include_ops),
            "inventory": inventory,
''',
    '''            "include_ops": bool(include_ops),
            "held_only": bool(held_only),
            "inventory": inventory,
''',
)

# MCP/HTTP tool: explicit held-only + semantic widening controls for vague-memory Library queries.
replace_once(
    "drive/scripts/research_data_mcp/tool_handlers.py",
    '''    def research_list_datasets(
        self,
        q: str = "",
        readiness: str = "",
        access_shape: str = "",
        limit: int = 50,
    ) -> dict[str, Any]:
        """List or search registered research datasets."""
        return self.gateway.list_datasets(q=q, readiness=readiness, access_shape=access_shape, limit=min(max(limit, 1), 200))
''',
    '''    def research_list_datasets(
        self,
        q: str = "",
        readiness: str = "",
        access_shape: str = "",
        limit: int = 50,
        held_only: bool = False,
        semantic: bool = False,
    ) -> dict[str, Any]:
        """List/search research assets. Use held_only=True for Library; semantic=True for vague/conceptual recall."""
        bounded = min(max(limit, 1), 200)
        out = self.gateway.list_datasets(
            q=q,
            readiness=readiness,
            access_shape=access_shape,
            limit=bounded,
            held_only=bool(held_only),
        )
        if semantic and str(q or "").strip():
            from scripts.research_data_mcp.library_semantic_search import widen_library_result

            out = widen_library_result(
                self.gateway,
                out,
                query=q,
                limit=bounded,
                held_only=bool(held_only),
            )
        return out
''',
)

# Semantic corpus: index the same evidence dimensions as deterministic retrieval.
replace_once(
    "drive/scripts/research_data_mcp/semantic_index.py",
    "from scripts.research_data_mcp.procurement_cache import ProcurementCache, catalog_fingerprint\n",
    "from scripts.research_data_mcp.procurement_cache import ProcurementCache, catalog_fingerprint\nfrom scripts.research_data_mcp.library_retrieval import registry_search_document\n",
)
replace_once(
    "drive/scripts/research_data_mcp/semantic_index.py",
    '''        for ds in gateway.engine.list_datasets():
            blob = " ".join(
                str(ds.get(k, "")) for k in ("dataset_id", "name", "description", "grain", "recommended_use", "domain")
            )
''',
    '''        for ds in gateway.engine.list_datasets():
            blob = registry_search_document(ds)
''',
)
replace_once(
    "drive/scripts/research_data_mcp/semantic_index.py",
    '''                        "grain": ds.get("grain") or "",
                        "source": ds.get("source") or ds.get("backend") or "registry",
                        "readiness": ds.get("analysis_readiness") or "",
                        "access_shape": ds.get("access_shape") or "",
                        "shelf_hint": ds.get("shelf_hint") or "",
''',
    '''                        "grain": ds.get("grain") or "",
                        "coverage": ds.get("coverage") or ds.get("date_range") or ds.get("temporal_coverage") or "",
                        "join_keys": ds.get("join_keys") or ds.get("keys") or [],
                        "source": ds.get("source") or ds.get("source_system") or ds.get("backend") or "registry",
                        "readiness": ds.get("analysis_readiness") or "",
                        "access_shape": ds.get("access_shape") or "",
                        "asset_kind": ds.get("asset_kind") or ds.get("object_type") or "",
                        "shelf_hint": ds.get("shelf_hint") or "",
''',
)
replace_once(
    "drive/scripts/research_data_mcp/semantic_index.py",
    'INDEX_SCHEMA_VERSION = "2-access-shape"\n',
    'INDEX_SCHEMA_VERSION = "3-library-evidence"\n',
)
