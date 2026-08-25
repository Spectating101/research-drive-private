#!/usr/bin/env python3
"""Lightweight semantic index over registry + queue descriptions."""

from __future__ import annotations

import json
import math
import os
import re
import site
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from scripts.research_data_mcp.procurement_cache import ProcurementCache, catalog_fingerprint

_INDEX_SINGLETON: dict[str, "SemanticCatalogIndex"] = {}
_EMBEDDING_MODELS: dict[str, Any] = {}
DEFAULT_EMBEDDING_MODEL = os.environ.get("RESEARCH_SEMANTIC_MODEL", "sentence-transformers/all-MiniLM-L6-v2")


def _tokenize(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z][a-z0-9_]{2,}", text.lower()) if t not in STOPWORDS]


STOPWORDS = frozenset(
    {
        "the",
        "and",
        "for",
        "with",
        "dataset",
        "data",
        "local",
        "from",
        "that",
        "this",
        "your",
        "have",
        "query",
        "using",
        "into",
        "research",
    }
)


def _semantic_relevance_floor() -> float:
    raw = (os.environ.get("RESEARCH_SEMANTIC_QUERY_FLOOR") or "").strip()
    try:
        return float(raw) if raw else 0.25
    except ValueError:
        return 0.25


def _semantic_tail_drop() -> float:
    """Maximum cosine drop from the best hit retained in one result set."""
    raw = (os.environ.get("RESEARCH_SEMANTIC_TAIL_DROP") or "").strip()
    try:
        return max(0.0, float(raw)) if raw else 0.16
    except ValueError:
        return 0.16


def _query_has_subject_signal(query: str, vocabulary: set[str] | None = None) -> bool:
    """Reject embedding-shaped noise without rejecting exact research identifiers.

    Sentence encoders map every string somewhere, including keyboard noise.  A
    query is eligible for semantic widening when it contains a token already
    observed in the indexed corpus, a word-like token with at least two vowels,
    or CJK text.  Exact identifiers that do not meet this boundary remain
    available through the keyword index.
    """
    text = str(query or "").strip()
    if not text:
        return False
    if re.search(r"[\u3400-\u9fff]", text):
        return True
    known = vocabulary or set()
    for token in re.findall(r"[a-z][a-z0-9_]{2,}", text.lower()):
        if token in known:
            return True
        if sum(char in "aeiouy" for char in token) >= 2:
            return True
    return False


def _require_resident_embedding_model() -> bool:
    raw = (os.environ.get("RESEARCH_SEMANTIC_BLOCK_ON_COLD_MODEL") or "").strip().lower()
    return raw not in {"1", "true", "on"}


def warm_embedding_model(model_name: str = DEFAULT_EMBEDDING_MODEL) -> bool:
    """Load the sentence-transformer ahead of traffic. ~9s, paid once per process."""
    try:
        SemanticCatalogIndex._embedding_model_instance(model_name)
        return True
    except Exception:
        return False


class SemanticCatalogIndex:
    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root
        self._docs: list[dict[str, Any]] = []
        self._df: Counter[str] = Counter()
        self._built = False
        self._embeddings: list[list[float]] | None = None
        self._embedding_model = ""

    @staticmethod
    def _source_routes(gateway: Any) -> list[dict[str, Any]]:
        """The declared procurement routes, however the gateway can supply them."""
        supplier = getattr(gateway, "source_routes_for_index", None)
        if callable(supplier):
            try:
                return list(supplier() or [])
            except Exception:
                return []
        try:
            from scripts.research_data_mcp.databank_sources import load_source_map
        except Exception:
            load_source_map = None
        if load_source_map is not None:
            try:
                return list(load_source_map(gateway.repo_root).get("sources") or [])
            except Exception:
                pass
        try:
            root = Path(getattr(gateway, "repo_root", "."))
            payload = json.loads(
                (root / "config/databank_source_map.json").read_text(encoding="utf-8")
            )
            routes = list(payload.get("sources") or [])
        except Exception:
            return []
        return SemanticCatalogIndex._with_access_scope(root, routes)

    @staticmethod
    def _with_access_scope(root: Path, routes: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Fold in what each route can reach, as the access-scope record states it."""
        try:
            scope = json.loads(
                (root / "config/databank_access_scope.json").read_text(encoding="utf-8")
            )
        except Exception:
            return routes
        by_id = {
            str(entry.get("source_id") or ""): entry
            for entry in (scope.get("sources") or [])
            if isinstance(entry, dict)
        }
        merged: list[dict[str, Any]] = []
        for route in routes:
            entry = by_id.get(str(route.get("id") or ""))
            if not entry:
                merged.append(route)
                continue
            notes = [
                str(cell.get("note") or "")
                for cell in (entry.get("coverage_cells") or [])
                if isinstance(cell, dict) and cell.get("note")
            ]
            merged.append(
                {
                    **route,
                    "reachable_products": entry.get("reachable_products") or [],
                    "coverage_notes": notes,
                    "fetch_modes": entry.get("fetch_modes") or [],
                }
            )
        return merged

    def build(self, gateway: Any) -> None:
        docs: list[dict[str, Any]] = []
        for ds in gateway.engine.list_datasets():
            blob = " ".join(
                str(ds.get(k, "")) for k in ("dataset_id", "name", "description", "grain", "recommended_use", "domain")
            )
            docs.append(
                {
                    "id": ds["dataset_id"],
                    "kind": "registry_dataset",
                    "text": blob,
                    "metadata": {
                        "dataset_id": ds.get("dataset_id"),
                        "title": ds.get("name") or ds.get("dataset_id"),
                        "description": ds.get("description") or ds.get("recommended_use") or "",
                        "grain": ds.get("grain") or "",
                        "source": ds.get("source") or ds.get("backend") or "registry",
                        "readiness": ds.get("analysis_readiness") or "",
                        "access_shape": ds.get("access_shape") or "",
                        "shelf_hint": ds.get("shelf_hint") or "",
                    },
                }
            )

        # Held datasets are residue; the offering is the routes the desk can obtain
        # through. Indexing only datasets left no meaning-based path to a source, so
        # route discovery reached a usable route for under half the needs in
        # scripts.data_catalog.bench_route_discovery. Run it for the current figure.
        for route in self._source_routes(gateway):
            route_id = str(route.get("id") or "")
            if not route_id:
                continue
            def _words(values: Any) -> str:
                if not values:
                    return ""
                if isinstance(values, str):
                    return values.replace("_", " ")
                return " ".join(str(v).replace("_", " ") for v in values)

            # What a route can actually supply is recorded in databank_access_scope:
            # reachable_products, coverage notes and fetch modes. Without them the source
            # map alone is a label and a few capability tags, and a need phrased in
            # research language matched nothing.
            blob = " ".join(
                part
                for part in (
                    route_id.replace("_", " "),
                    str(route.get("label") or ""),
                    str(route.get("provider") or ""),
                    _words(route.get("capabilities")),
                    _words(route.get("geographies")),
                    _words(route.get("reachable_products")),
                    _words(route.get("coverage_notes")),
                    _words(route.get("fetch_modes")),
                    str(route.get("notes") or ""),
                    str(route.get("access_mode") or "").replace("_", " "),
                )
                if part
            )
            docs.append(
                {
                    "id": route_id,
                    "kind": "source_route",
                    "text": blob,
                    "metadata": {
                        "source_id": route_id,
                        "title": route.get("label") or route_id,
                        "provider": route.get("provider") or "",
                        "access_mode": route.get("access_mode") or "",
                        "capabilities": list(route.get("capabilities") or []),
                        "status": route.get("status") or "",
                    },
                }
            )

        for task in gateway.orchestrator.queue_tasks(runnable_only=False):
            blob = f"{task.get('id','')} {task.get('title','')} {task.get('output_hint','')}"
            docs.append(
                {
                    "id": task["id"],
                    "kind": "queue_task",
                    "text": blob,
                    "metadata": {
                        "title": task.get("title") or task.get("id"),
                        "description": task.get("output_hint") or "",
                    },
                }
            )

        self._docs = docs
        self._df = Counter()
        for doc in docs:
            self._df.update(set(_tokenize(doc["text"])))
        self._built = True

    def snapshot(self) -> dict[str, Any]:
        return {
            "docs": self._docs,
            "df": dict(self._df),
            "built": self._built,
            "embeddings": self._embeddings,
            "embedding_model": self._embedding_model,
        }

    def load_snapshot(self, data: dict[str, Any]) -> None:
        self._docs = list(data.get("docs") or [])
        self._df = Counter(data.get("df") or {})
        self._built = bool(data.get("built"))
        self._embeddings = data.get("embeddings") or None
        self._embedding_model = str(data.get("embedding_model") or "")

    @staticmethod
    def _embedding_model_instance(model_name: str) -> Any:
        if model_name not in _EMBEDDING_MODELS:
            try:
                from sentence_transformers import SentenceTransformer
            except ModuleNotFoundError:
                # The desk service uses an isolated venv on this workstation while
                # the already-provisioned embedding runtime lives in the user site.
                # A normal deployment should install the declared project dependency.
                user_site = site.getusersitepackages()
                if user_site and user_site not in sys.path:
                    sys.path.append(user_site)
                from sentence_transformers import SentenceTransformer

            _EMBEDDING_MODELS[model_name] = SentenceTransformer(model_name)
        return _EMBEDDING_MODELS[model_name]

    def _ensure_embeddings(self, *, model_name: str = DEFAULT_EMBEDDING_MODEL) -> None:
        if self._embeddings is not None and self._embedding_model == model_name and len(self._embeddings) == len(self._docs):
            return
        model = self._embedding_model_instance(model_name)
        values = model.encode(
            [str(doc.get("text") or "") for doc in self._docs],
            normalize_embeddings=True,
            show_progress_bar=False,
            convert_to_numpy=True,
        )
        self._embeddings = values.tolist()
        self._embedding_model = model_name

    def embeddings_ready(self, *, model_name: str = DEFAULT_EMBEDDING_MODEL) -> bool:
        return bool(
            model_name in _EMBEDDING_MODELS
            and self._embeddings is not None
            and self._embedding_model == model_name
            and len(self._embeddings) == len(self._docs)
        )

    def warm_embeddings(self, *, model_name: str = DEFAULT_EMBEDDING_MODEL) -> bool:
        """Build the registry vectors only from the startup warmup thread."""
        try:
            self._ensure_embeddings(model_name=model_name)
            return self.embeddings_ready(model_name=model_name)
        except Exception:
            return False

    def _score(self, query_tokens: list[str], doc_tokens: list[str]) -> float:
        if not query_tokens or not doc_tokens:
            return 0.0
        doc_tf = Counter(doc_tokens)
        score = 0.0
        for token in query_tokens:
            if token not in doc_tf:
                continue
            idf = math.log(1 + len(self._docs) / (1 + self._df.get(token, 0)))
            score += (1 + math.log(1 + doc_tf[token])) * idf
        return score

    def search(self, query: str, *, limit: int = 8) -> list[dict[str, Any]]:
        if not self._built:
            return []
        q_tokens = _tokenize(query)
        ranked: list[tuple[float, dict[str, Any]]] = []
        for doc in self._docs:
            score = self._score(q_tokens, _tokenize(doc["text"]))
            if score > 0:
                ranked.append((score, {"id": doc["id"], "kind": doc["kind"], "score": round(score, 3)}))
        ranked.sort(key=lambda pair: pair[0], reverse=True)
        return [item for _score, item in ranked[:limit]]

    def subject_search(
        self,
        query: str,
        *,
        limit: int = 12,
        kinds: set[str] | None = None,
        floor: float = 0.0,
    ) -> list[dict[str, Any]]:
        """Rank by whether the document actually carries the query's subject.

        Cosine is the wrong primary retriever for a research question: it ranks
        by resemblance, so a monthly environmental panel outranks nothing at all
        for "forest fire and economic changes". Subject overlap is scored over
        every document rather than over cosine's shortlist, so a dataset that
        genuinely holds the subject can be surfaced even when the encoder never
        shortlisted it.
        """
        if not self._built or not str(query or "").strip():
            return []
        ranked: list[tuple[float, dict[str, Any]]] = []
        for index, doc in enumerate(self._docs):
            if kinds and str(doc.get("kind")) not in kinds:
                continue
            score = self.subject_overlap(query, index)
            if score < floor or score <= 0.0:
                continue
            ranked.append(
                (
                    score,
                    {
                        "id": doc.get("id"),
                        "kind": doc.get("kind"),
                        "subject_score": round(score, 4),
                        "metadata": dict(doc.get("metadata") or {}),
                    },
                )
            )
        ranked.sort(key=lambda pair: pair[0], reverse=True)
        return [item for _score, item in ranked[:limit]]

    def doc_index_for(self, dataset_id: str) -> int | None:
        target = str(dataset_id or "")
        for i, doc in enumerate(self._docs):
            if str(doc.get("id") or "") == target:
                return i
        return None

    def subject_overlap(self, query: str, doc_index: int) -> float:
        """How much rare query vocabulary the document actually contains.

        Embeddings match form as readily as subject: "forest fire and economic
        changes" pulled Mauna Loa CO2 and an earthquake catalog because a
        monthly environmental panel *looks* like the answer. A shared rare word
        is evidence the subject is really present; a shared common one is not,
        so each term is weighted by how few documents carry it.
        """
        doc = self._docs[doc_index] if 0 <= doc_index < len(self._docs) else None
        if not doc:
            return 0.0
        terms = set(_tokenize(query))
        if not terms:
            return 0.0
        text = set(_tokenize(str(doc.get("text") or "")))
        total = max(1, len(self._docs))
        score = 0.0
        for term in terms:
            if term not in text:
                continue
            seen = self._df.get(term, 0)
            # rarity in [0, 1]: a term in every document contributes nothing
            score += 1.0 - (min(seen, total) / total)
        return score / len(terms)

    def semantic_search(
        self,
        query: str,
        *,
        limit: int = 8,
        kinds: set[str] | None = None,
        model_name: str = DEFAULT_EMBEDDING_MODEL,
        require_ready: bool = True,
    ) -> list[dict[str, Any]]:
        """Embedding retrieval for research questions, distinct from token catalog lookup."""
        if not self._built or not query.strip():
            return []
        if require_ready and _require_resident_embedding_model() and not self.embeddings_ready(model_name=model_name):
            # The encoder can become resident several seconds before the corpus
            # vectors finish. Treat the pair as one readiness boundary so a user
            # request never races the warmup by building the same corpus again.
            return []
        self._ensure_embeddings(model_name=model_name)
        model = self._embedding_model_instance(model_name)
        vector = model.encode(query, normalize_embeddings=True, show_progress_bar=False, convert_to_numpy=True)
        ranked: list[tuple[float, dict[str, Any]]] = []
        for index, doc in enumerate(self._docs):
            if kinds and str(doc.get("kind")) not in kinds:
                continue
            embedding = self._embeddings[index]
            score = sum(float(left) * float(right) for left, right in zip(vector, embedding))
            ranked.append(
                (
                    score,
                    {
                        "id": doc.get("id"),
                        "kind": doc.get("kind"),
                        "score": round(score, 4),
                        "metadata": dict(doc.get("metadata") or {}),
                    },
                )
            )
        ranked.sort(key=lambda pair: pair[0], reverse=True)
        if not ranked:
            return []
        # Nearest-neighbour retrieval always returns its top-k, even for random
        # text.  An absolute score alone is not sufficient: the live corpus
        # scored ``zzqvjjk plmxxc`` at 0.2725, above the old 0.25 boundary.
        # Require a subject signal in the original query, then keep only the
        # coherent neighbourhood around the best result instead of presenting
        # the unrelated tail as additional evidence.
        top_score = ranked[0][0]
        floor = _semantic_relevance_floor()
        if top_score < floor or not _query_has_subject_signal(query, set(self._df)):
            return []
        row_floor = max(floor - 0.05, top_score - _semantic_tail_drop())
        return [item for score, item in ranked if score >= row_floor][:limit]

    def confidence(self, query: str, top: dict[str, Any] | None) -> str:
        if not top:
            return "none"
        hits = self.search(query, limit=1)
        if not hits:
            return "none"
        score = hits[0].get("score", 0)
        if score >= 8.0:
            return "high"
        if score >= 3.5:
            return "medium"
        return "low"


INDEX_SCHEMA_VERSION = "2-access-shape"


def get_semantic_index(gateway: Any, *, ttl_hours: float = 168) -> SemanticCatalogIndex:
    """Shared semantic index with disk cache invalidated on catalog fingerprint change."""
    repo_root = Path(gateway.repo_root).resolve()
    # The fingerprint tracks the catalog, not the code that indexes it, so a
    # change to what each document carries — a new metadata field, a different
    # text blob — silently reused a stale snapshot forever. Bump this whenever
    # build() changes what it stores.
    fp = f"{catalog_fingerprint(repo_root, gateway.registry_path)}:{INDEX_SCHEMA_VERSION}"
    cache_key = f"{fp}"
    if cache_key in _INDEX_SINGLETON:
        return _INDEX_SINGLETON[cache_key]

    cache = ProcurementCache(repo_root)
    cached = cache.get("semantic_index", "catalog", fingerprint=fp, ttl_hours=ttl_hours)
    index = SemanticCatalogIndex(repo_root)
    if cached:
        index.load_snapshot(cached)
    else:
        index.build(gateway)
        cache.set("semantic_index", "catalog", index.snapshot(), fingerprint=fp, ttl_hours=ttl_hours)

    _INDEX_SINGLETON[cache_key] = index
    return index


def warm_semantic_index(gateway: Any, *, model_name: str = DEFAULT_EMBEDDING_MODEL) -> bool:
    """Make the registry semantic index resident before it is used by traffic."""
    return get_semantic_index(gateway).warm_embeddings(model_name=model_name)


def invalidate_semantic_index() -> None:
    _INDEX_SINGLETON.clear()
