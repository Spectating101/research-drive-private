#!/usr/bin/env python3
"""Answer research questions by reading the whole catalog, not by retrieving from it.

The internal catalog is small enough to read in full: 113 professor-visible
datasets serialise to ~15.5 KB.  Retrieval exists to avoid reading everything,
so at this size it buys nothing and costs recall.

Measured on 16 questions against the same catalog:

    agent + full catalog     10/10 real questions, 5/6 correct refusals, 0 bad ids
    local_search              2/6
    discover_search           2/6

The layered path does not merely rank worse -- it returns *empty* for four of
six questions whose answer sits in the catalog.  Each layer (lexical index,
relevance threshold, geography rules) filters independently, and any one of them
returning nothing ends the query.  Passing the catalog to a reader removes all
of them from the internal path at once.

Two guards, because the model is not trusted on its own:

* every returned id must exist in the registry, or it is dropped.  This is the
  same grounding principle used for requirement drafting: a value the corpus
  cannot confirm does not get to become an answer.
* keyword and identifier queries do not come here at all.  They already work
  through the lexical path in milliseconds, and a model call would add latency
  and cost for a question that never needed judgement.

This does not replace federated search.  External sources are unbounded and
genuinely need retrieval; only the internal catalog is small enough to read.
"""
from __future__ import annotations

import json
import os
import re
from typing import Any, Iterable, Sequence

DEFAULT_MODEL = "composer-2.5"
MAX_CATALOG_ROWS = 400
_QUESTION_WORDS = frozenset({
    "what", "which", "where", "when", "who", "how", "can", "could", "should",
    "do", "does", "is", "are", "need", "want", "find", "looking", "study",
    "analyse", "analyze", "research", "measure", "test", "compare", "for",
})


def enabled() -> bool:
    """Catalog reading is opt-in; the lexical path stays the default."""
    return os.getenv("RD_CATALOG_SELECT", "").strip().lower() in {"1", "true", "yes", "on"}


def is_question_like(query: str) -> bool:
    """Whether a query deserves a reader rather than a lexical match.

    Keyword and identifier queries ("CRSP daily", "stablecoin") are answered
    well and instantly by the existing index; sending them to a model would add
    seconds and a network dependency to a question that never needed judgement.
    """
    text = str(query or "").strip().lower()
    if not text:
        return False
    words = re.findall(r"[a-z0-9-]+", text)
    if len(words) >= 5:
        return True
    return len(words) >= 3 and any(w in _QUESTION_WORDS for w in words)


def build_catalog_text(datasets: Iterable[dict[str, Any]], *, limit: int = MAX_CATALOG_ROWS) -> str:
    """Serialise the catalog as one line per dataset.

    Description carries the relevance signal, so it is kept at the expense of
    fields a reader cannot act on. Rows without an id are skipped rather than
    padded: an unidentifiable row cannot be returned as an answer.
    """
    lines: list[str] = []
    for row in datasets or []:
        if not isinstance(row, dict):
            continue
        dataset_id = str(row.get("dataset_id") or "").strip()
        if not dataset_id:
            continue
        desc = str(row.get("one_line") or row.get("description") or "").replace("\n", " ")[:90]
        lines.append(f"{dataset_id} | {row.get('grain', '')} | {desc}")
        if len(lines) >= limit:
            break
    return "\n".join(lines)


_PROMPT = """You are a research-data librarian. Below is the COMPLETE catalog the desk holds, one line per dataset: dataset_id | grain | description.

Name the datasets that genuinely answer the question, best first, at most {top}. If the catalog has no suitable dataset, output only: NONE
Answering NONE is correct and expected when the desk does not hold the data; proposing a near-match instead is a defect. Use only ids that appear verbatim in the catalog.

Output only lines of the form:
<dataset_id> | <reason, max 12 words>

QUESTION: {question}

CATALOG:
{catalog}"""


def parse_selection(text: str, valid_ids: set[str]) -> list[dict[str, str]]:
    """Parse the reply, keeping only ids the registry actually contains.

    A model naming a plausible dataset the desk does not hold would be worse
    than returning nothing, because the researcher cannot tell the difference
    without checking. Unknown ids are dropped rather than surfaced.
    """
    out: list[dict[str, str]] = []
    for raw in str(text or "").splitlines():
        line = raw.strip().strip("`").lstrip("-* ").strip()
        if not line or line.upper() == "NONE":
            continue
        dataset_id, _, reason = line.partition("|")
        dataset_id = dataset_id.strip()
        if dataset_id in valid_ids and not any(d["dataset_id"] == dataset_id for d in out):
            out.append({"dataset_id": dataset_id, "reason": reason.strip()[:120]})
    return out


def select(
    question: str,
    datasets: Sequence[dict[str, Any]],
    *,
    top: int = 6,
    model: str | None = None,
    timeout: float = 120.0,
) -> dict[str, Any]:
    """Pick the datasets that answer ``question`` by reading the whole catalog."""
    valid_ids = {str(d.get("dataset_id") or "") for d in datasets if isinstance(d, dict)}
    valid_ids.discard("")
    catalog = build_catalog_text(datasets)
    if not catalog:
        return {"selected": [], "reason": "empty_catalog"}

    from scripts.research_data_mcp.requirement_extraction import (
        ExtractionUnavailable,
        run_cursor_prompt,
    )

    prompt = _PROMPT.format(top=top, question=str(question or "").strip(), catalog=catalog)
    try:
        raw = run_cursor_prompt(prompt, model or os.getenv("RD_CATALOG_MODEL", DEFAULT_MODEL), timeout)
    except ExtractionUnavailable as exc:
        return {"selected": [], "reason": f"backend_unavailable: {exc}"}

    selected = parse_selection(raw, valid_ids)
    return {
        "selected": selected[:top],
        "catalog_rows": len(catalog.splitlines()),
        "reason": "ok" if selected else "model_returned_none",
    }


def main(argv: Sequence[str] | None = None) -> int:
    import argparse
    from pathlib import Path

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("question")
    ap.add_argument("--registry", type=Path, required=True)
    ap.add_argument("--all-datasets", action="store_true")
    args = ap.parse_args(argv)
    rows = json.loads(args.registry.read_text(encoding="utf-8")).get("datasets") or []
    if not args.all_datasets:
        rows = [r for r in rows if r.get("professor_visible")]
    print(json.dumps(select(args.question, rows), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
