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


class SemanticCatalogIndex:
    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root
        self._docs: list[dict[str, Any]] = []
        self._df: Counter[str] = Counter()
        self._built = False
        self._embeddings: list[list[float]] | None = None
        self._embedding_model = ""

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

    def semantic_search(
        self,
        query: str,
        *,
        limit: int = 8,
        kinds: set[str] | None = None,
        model_name: str = DEFAULT_EMBEDDING_MODEL,
    ) -> list[dict[str, Any]]:
        """Embedding retrieval for research questions, distinct from token catalog lookup."""
        if not self._built or not query.strip():
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
        return [item for _score, item in ranked[:limit]]

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


def get_semantic_index(gateway: Any, *, ttl_hours: float = 168) -> SemanticCatalogIndex:
    """Shared semantic index with disk cache invalidated on catalog fingerprint change."""
    repo_root = Path(gateway.repo_root).resolve()
    fp = catalog_fingerprint(repo_root, gateway.registry_path)
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


def invalidate_semantic_index() -> None:
    _INDEX_SINGLETON.clear()
