#!/usr/bin/env python3
"""Faculty-facing labels for procured / synthesis registry rows.

dataset_id stays stable and opaque. title / display_name / recommended_use must
read as research language — never the raw objective dump or "Custom collect · host".
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse, unquote

_OPS_PREFIX_RE = re.compile(
    r"^(?:Custom collect|Route prove|Synthesis)\s*[·:\-—]\s*",
    re.IGNORECASE,
)
_BUILD_PHRASE_RE = re.compile(
    r"(?:build|derive|construct|compute|create|make)\s+(?:a|an|the)\s+(.+?)(?:\.|$)",
    re.IGNORECASE | re.DOTALL,
)
_HEX_TAIL_RE = re.compile(r"_[0-9a-f]{6,12}$", re.IGNORECASE)
_VERSION_TAIL_RE = re.compile(r"_v\d+$", re.IGNORECASE)
_CRAFT_PREFIX_RE = re.compile(r"^craft_(?:raw_|openapi_|http_)?", re.IGNORECASE)
_SYNTH_PREFIX_RE = re.compile(r"^synthesis_", re.IGNORECASE)
_STOP_TOKENS = {
    "the",
    "a",
    "an",
    "and",
    "or",
    "of",
    "for",
    "to",
    "from",
    "with",
    "using",
    "library",
    "asset",
    "custom",
    "collect",
    "dataset",
    "id",
    "via",
}


def is_ops_label(text: str) -> bool:
    """True when a string is machine/ops dialect, not faculty language."""
    s = str(text or "").strip()
    if not s:
        return True
    if _OPS_PREFIX_RE.match(s):
        return True
    if s.lower().startswith("synthesis:"):
        return True
    if "dataset_id" in s.lower() and "craft_" in s.lower():
        return True
    if s.startswith("data_lake/") or "Inspect files under" in s:
        return True
    if len(s) > 96:
        return True
    return False


def humanize_dataset_id(dataset_id: str) -> str:
    """synthesis_keeling_accel_monthly_v1 → Keeling accel monthly."""
    raw = str(dataset_id or "").strip()
    if not raw:
        return "Dataset"
    s = _SYNTH_PREFIX_RE.sub("", raw)
    s = _CRAFT_PREFIX_RE.sub("", s)
    s = _HEX_TAIL_RE.sub("", s)
    s = _VERSION_TAIL_RE.sub("", s)
    # Drop host-ish craft fragments (twse_com_tw leftover after openapi strip).
    parts = [p for p in s.split("_") if p and p.lower() not in {"com", "tw", "www", "raw"}]
    if not parts:
        parts = [p for p in raw.split("_") if p][-4:]
    words: list[str] = []
    for part in parts:
        if part.isupper() and len(part) <= 6:
            words.append(part)
        elif part.lower() in {"co2", "ppm", "twse", "bwibbu", "mlo"}:
            words.append(part.upper() if part.lower() != "bwibbu" else "BWIBBU")
        else:
            words.append(part.replace("-", " "))
    title = " ".join(words).strip()
    title = re.sub(r"\s+", " ", title)
    if title:
        title = title[0].upper() + title[1:]
    return title[:80] or raw


def short_title_from_objective(objective: str, *, max_len: int = 72) -> str:
    """Pull a research phrase from a long synthesis objective."""
    text = re.sub(r"\s+", " ", str(objective or "").strip())
    if not text:
        return ""
    # Prefer "build a <phrase>"
    m = _BUILD_PHRASE_RE.search(text)
    if m:
        phrase = m.group(1).strip()
        # Cut at secondary clauses
        phrase = re.split(r"\b(?:Derive|Keep|Mark|State|Using)\b", phrase, maxsplit=1)[0].strip(" ,;")
        phrase = _strip_library_asset_preamble(phrase)
        if phrase and not is_ops_label(phrase):
            return _title_case_phrase(phrase)[:max_len]
    # First sentence if short enough
    first = re.split(r"(?<=[.!?])\s+", text, maxsplit=1)[0].strip()
    first = _strip_library_asset_preamble(first)
    if first and len(first) <= max_len and not is_ops_label(first):
        return _title_case_phrase(first)
    return ""


def _strip_library_asset_preamble(text: str) -> str:
    s = str(text or "").strip()
    s = re.sub(
        r"^Using the Library asset .+?(?:\(dataset_id [^)]+\)),\s*",
        "",
        s,
        flags=re.IGNORECASE,
    )
    s = re.sub(r"^Using .+?,\s*(?=build|derive|construct)", "", s, flags=re.IGNORECASE)
    return s.strip(" ,;")


def _title_case_phrase(phrase: str) -> str:
    s = phrase.strip()
    if not s:
        return s
    # Keep existing internal caps (CO₂, BWIBBU); only fix leading lower.
    if s[0].islower():
        s = s[0].upper() + s[1:]
    return s.rstrip(".")


def title_from_url(url: str) -> str:
    """https://…/co2-mm-mlo.csv → CO2 mm MLO CSV."""
    raw = str(url or "").strip()
    if not raw:
        return ""
    try:
        path = unquote(urlparse(raw).path or "")
    except Exception:  # noqa: BLE001
        path = raw
    base = path.rsplit("/", 1)[-1] if path else ""
    if not base or base in {".", "/"}:
        host = urlparse(raw).netloc or ""
        return host.split(":")[0][:60]
    stem = base.rsplit(".", 1)[0] if "." in base else base
    stem = stem.replace("-", " ").replace("_", " ")
    words = []
    for w in stem.split():
        if w.lower() in {"co2", "mlo", "twse", "csv", "json"}:
            words.append(w.upper())
        elif w.isupper():
            words.append(w)
        else:
            words.append(w.capitalize())
    return " ".join(words)[:72]


def _transform_hint(execution_spec: dict[str, Any] | None) -> str:
    spec = execution_spec if isinstance(execution_spec, dict) else {}
    transforms = spec.get("transforms") or []
    if not isinstance(transforms, list):
        return ""
    diffs = [t for t in transforms if isinstance(t, dict) and t.get("op") == "diff"]
    if len(diffs) >= 2:
        p0 = diffs[0].get("periods")
        p1 = diffs[1].get("periods")
        if p0 and p1:
            return f"{p0}-month rate → {p1}-month acceleration"
        return "rate and acceleration transforms"
    if len(diffs) == 1:
        p = diffs[0].get("periods")
        return f"{p}-period change" if p else "difference transform"
    return ""


def _faculty_recommended_use(
    *,
    kind: str,
    title: str,
    objective: str,
    url: str,
    transform_hint: str,
    input_id: str,
) -> str:
    if kind == "synthesis":
        bits = [f"Use for {title[0].lower() + title[1:]}" if title else "Use as a derived research panel"]
        if transform_hint:
            bits.append(f"({transform_hint})")
        if input_id:
            bits.append(f"Derived from `{input_id}`.")
        # One clean sentence from objective if short
        short = short_title_from_objective(objective, max_len=100)
        if short and short.lower() not in title.lower():
            bits.append(short + ".")
        return " ".join(bits)[:280]
    if url:
        return f"Acquired snapshot from {url}. Preview or query after smoke proves readiness."[:280]
    return f"Library holding: {title}."[:280]


def faculty_labels_for_plan(
    plan: dict[str, Any],
    *,
    dataset_id: str = "",
    job: dict[str, Any] | None = None,
) -> dict[str, str]:
    """Derive faculty title/display_name/description/recommended_use/domain."""
    plan = plan if isinstance(plan, dict) else {}
    job = job if isinstance(job, dict) else {}
    did = str(
        dataset_id
        or plan.get("dataset_id")
        or (plan.get("execution_spec") or {}).get("output_dataset_id")
        or ""
    ).strip()
    job_type = str(plan.get("job_type") or "").strip()
    objective = str(plan.get("objective") or "").strip()
    url = str(plan.get("url") or "").strip()
    explicit = str(
        plan.get("faculty_title")
        or plan.get("display_name")
        or plan.get("faculty_label")
        or ""
    ).strip()
    plan_title = str(plan.get("title") or job.get("title") or "").strip()
    exec_spec = plan.get("execution_spec") if isinstance(plan.get("execution_spec"), dict) else {}
    input_id = str(exec_spec.get("input_dataset_id") or "").strip()
    transform_hint = _transform_hint(exec_spec)

    kind = "synthesis" if job_type == "synthesis_execute" or did.startswith("synthesis_") else "procure"

    title = ""
    if explicit and not is_ops_label(explicit):
        title = explicit[:80]
    elif kind == "synthesis":
        title = short_title_from_objective(objective) or humanize_dataset_id(did)
        if transform_hint and "accel" in did.lower() and "accel" not in title.lower():
            title = f"{title} ({transform_hint})"[:80]
    else:
        if plan_title and not is_ops_label(plan_title):
            title = plan_title[:80]
        else:
            stripped = _OPS_PREFIX_RE.sub("", plan_title).strip() if plan_title else ""
            from_url = title_from_url(url)
            if from_url:
                title = from_url
            elif stripped and not is_ops_label(stripped) and len(stripped) <= 80:
                title = stripped
            else:
                title = humanize_dataset_id(did)

    title = re.sub(r"\s+", " ", title).strip() or humanize_dataset_id(did) or did

    if kind == "synthesis":
        description = (
            f"Derived monthly panel: {title}."
            if "month" in (plan.get("grain") or did).lower()
            else f"Derived research panel: {title}."
        )
        if transform_hint:
            description = f"{description.rstrip('.')} — {transform_hint}."
        domain = "derived"
    else:
        host = ""
        try:
            host = urlparse(url).netloc.split(":")[0]
        except Exception:  # noqa: BLE001
            host = ""
        description = (
            f"Procured snapshot “{title}” from {host or url or 'web'}."
            if url
            else f"Procured Library snapshot: {title}."
        )
        domain = str(plan.get("domain") or "").strip() or (
            "asia_markets" if "twse" in (did + url + title).lower() else "acquired"
        )

    recommended = _faculty_recommended_use(
        kind=kind,
        title=title,
        objective=objective,
        url=url,
        transform_hint=transform_hint,
        input_id=input_id,
    )

    return {
        "title": title[:120],
        "display_name": title[:120],
        "name": title[:120],
        "description": description[:400],
        "recommended_use": recommended[:400],
        "domain": domain,
        "ops_title": plan_title[:240] if plan_title else "",
    }


def apply_faculty_labels(row: dict[str, Any], labels: dict[str, str]) -> dict[str, Any]:
    """Write faculty fields onto a registry row; keep dataset_id unchanged."""
    out = dict(row)
    for key in ("title", "display_name", "name", "description", "recommended_use", "domain"):
        val = str(labels.get(key) or "").strip()
        if val:
            out[key] = val
    ops = str(labels.get("ops_title") or "").strip()
    if ops and ops != out.get("name"):
        out["ops_title"] = ops
    return out


def relabel_registry_row(row: dict[str, Any], *, plan: dict[str, Any] | None = None) -> dict[str, Any]:
    """Relabel an existing registry row from itself + optional plan context."""
    row = dict(row or {})
    plan = dict(plan or {})
    if not plan.get("job_type"):
        if str(row.get("dataset_id") or "").startswith("synthesis_") or str(
            (row.get("lineage") or {}).get("derived_via") or ""
        ) == "synthesis_execute":
            plan["job_type"] = "synthesis_execute"
        else:
            plan["job_type"] = "http_manifest"
    if not plan.get("objective"):
        # Prefer prior objective-shaped recommended_use only if it looks like one
        rec = str(row.get("recommended_use") or "")
        if rec and ("build" in rec.lower() or "derive" in rec.lower()) and len(rec) > 80:
            plan["objective"] = rec
    if not plan.get("execution_spec") and isinstance(row.get("execution_spec"), dict):
        plan["execution_spec"] = row["execution_spec"]
    elif not plan.get("execution_spec"):
        up = (row.get("lineage") or {}).get("upstream_dataset_ids") or []
        if up:
            plan["execution_spec"] = {"input_dataset_id": up[0], "output_dataset_id": row.get("dataset_id")}
    if not plan.get("url"):
        # scrape from description
        m = re.search(r"https?://\S+", str(row.get("description") or ""))
        if m:
            plan["url"] = m.group(0).rstrip(".")
    if not plan.get("title"):
        plan["title"] = str(row.get("name") or row.get("title") or "")
    if not plan.get("grain"):
        plan["grain"] = str(row.get("grain") or "")
    if not plan.get("domain"):
        plan["domain"] = str(row.get("domain") or "")
    labels = faculty_labels_for_plan(plan, dataset_id=str(row.get("dataset_id") or ""))
    return apply_faculty_labels(row, labels)
