#!/usr/bin/env python3
"""BigQuery helpers — shared by MCP and HTTP extension routes."""

from __future__ import annotations

import json
import os
import re
from datetime import date, datetime, time
from decimal import Decimal
from pathlib import Path
from typing import Any


DEFAULT_MAX_BYTES = int(os.getenv("RESEARCH_MCP_BIGQUERY_MAX_BYTES", str(10 * 1024**3)))
HARD_MAX_BYTES = int(os.getenv("RESEARCH_MCP_BIGQUERY_HARD_MAX_BYTES", str(100 * 1024**3)))
MAX_QUERY_ROWS = int(os.getenv("RESEARCH_MCP_BIGQUERY_MAX_ROWS", "5000"))


def json_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (datetime, date, time, Decimal)):
        return str(value)
    if isinstance(value, bytes):
        return value.hex()
    if isinstance(value, dict):
        return {str(key): json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_value(item) for item in value]
    return str(value)


def _strip_leading_comments(sql: str) -> str:
    lines = []
    for line in sql.splitlines():
        if line.strip().startswith("--"):
            continue
        lines.append(line)
    return "\n".join(lines).strip()


def read_only_sql(sql: str) -> str:
    clean = _strip_leading_comments(sql).strip().rstrip(";").strip()
    blocked = re.compile(
        r"\b(INSERT|UPDATE|DELETE|MERGE|CREATE|DROP|ALTER|TRUNCATE|CALL|EXPORT\s+DATA|LOAD\s+DATA|EXECUTE\s+IMMEDIATE|GRANT|REVOKE)\b",
        re.I,
    )
    if blocked.search(clean):
        raise ValueError("Mutation, scripting, export, and multi-statement SQL are blocked")
    if re.match(r"^DECLARE\b", clean, re.I):
        if not re.search(r"\b(SELECT|WITH)\b", clean, re.I):
            raise ValueError("DECLARE scripts must include SELECT or WITH")
        return clean
    if not re.match(r"^(SELECT|WITH)\b", clean, re.I):
        raise ValueError("Only SELECT or WITH queries are allowed")
    if ";" in clean:
        raise ValueError("Mutation, scripting, export, and multi-statement SQL are blocked")
    return clean


def bounded_bytes(value: int) -> int:
    selected = int(value or DEFAULT_MAX_BYTES)
    if selected <= 0 or selected > HARD_MAX_BYTES:
        raise ValueError(f"max_bytes_billed must be between 1 and {HARD_MAX_BYTES}")
    return selected


def _configured_project(project: str = "") -> str:
    return (
        project.strip()
        or os.getenv("GOOGLE_CLOUD_PROJECT", "").strip()
        or os.getenv("GCLOUD_PROJECT", "").strip()
        or os.getenv("GOOGLE_PROJECT", "").strip()
    )


def _adc_quota_project() -> str:
    adc_path = Path(os.getenv("CLOUDSDK_CONFIG", Path.home() / ".config" / "gcloud")) / "application_default_credentials.json"
    if adc_path.is_file():
        try:
            payload = json.loads(adc_path.read_text(encoding="utf-8"))
            return str(payload.get("quota_project_id") or "").strip()
        except Exception:
            pass
    return ""


def resolve_project(project: str = "") -> str:
    selected = _configured_project(project)
    if selected:
        return selected
    try:
        import google.auth

        _, detected = google.auth.default(scopes=["https://www.googleapis.com/auth/bigquery"])
        if detected:
            return str(detected).strip()
    except Exception:
        pass
    return _adc_quota_project()


def bq_client(project: str, location: str):
    from google.cloud import bigquery

    selected = resolve_project(project)
    if not selected:
        raise ValueError("BigQuery project is required. Set GOOGLE_CLOUD_PROJECT or pass project.")
    return bigquery.Client(project=selected, location=location), selected


def dry_run(sql: str, project: str, location: str, max_bytes_billed: int) -> tuple[Any, Any, str, int]:
    from google.cloud import bigquery

    clean = read_only_sql(sql)
    maximum = bounded_bytes(max_bytes_billed)
    client, selected = bq_client(project, location)
    config = bigquery.QueryJobConfig(dry_run=True, use_query_cache=False)
    job = client.query(clean, job_config=config, location=location)
    processed = int(job.total_bytes_processed or 0)
    return client, job, selected, maximum


def status(project: str = "", location: str = "US") -> dict[str, Any]:
    selected = _configured_project(project) or _adc_quota_project()
    try:
        import google.auth
        from google.cloud import bigquery  # noqa: F401

        credentials, detected_project = google.auth.default(scopes=["https://www.googleapis.com/auth/bigquery"])
        resolved = selected or (str(detected_project).strip() if detected_project else "")
        return {
            "dependency": "installed",
            "credentials": "available",
            "project": resolved or None,
            "location": location,
            "credential_type": type(credentials).__name__,
            "default_max_bytes_billed": DEFAULT_MAX_BYTES,
            "hard_max_bytes_billed": HARD_MAX_BYTES,
        }
    except Exception as exc:
        return {
            "dependency": "installed",
            "credentials": "missing",
            "project": selected or None,
            "location": location,
            "fix": "Run gcloud auth application-default login and set GOOGLE_CLOUD_PROJECT, or set GOOGLE_APPLICATION_CREDENTIALS.",
            "detail": str(exc),
        }


def list_datasets(project: str = "", location: str = "US", limit: int = 100) -> dict[str, Any]:
    client, selected = bq_client(project, location)
    rows = []
    for dataset in client.list_datasets(project=selected, max_results=min(max(limit, 1), 500)):
        rows.append({"dataset_id": dataset.dataset_id, "full_dataset_id": dataset.full_dataset_id, "friendly_name": dataset.friendly_name})
    return {"project": selected, "datasets": rows, "returned": len(rows)}


def list_tables(dataset: str, project: str = "", location: str = "US", limit: int = 100) -> dict[str, Any]:
    client, selected = bq_client(project, location)
    reference = dataset if "." in dataset else f"{selected}.{dataset}"
    rows = []
    for table in client.list_tables(reference, max_results=min(max(limit, 1), 500)):
        rows.append({"table_id": table.table_id, "full_table_id": table.full_table_id, "table_type": table.table_type})
    return {"dataset": reference, "tables": rows, "returned": len(rows)}


def table_schema(table: str, project: str = "", location: str = "US") -> dict[str, Any]:
    client, selected = bq_client(project, location)
    reference = table if table.count(".") >= 2 else f"{selected}.{table}"
    obj = client.get_table(reference)
    fields = [{"name": field.name, "type": field.field_type, "mode": field.mode, "description": field.description} for field in obj.schema]
    return {
        "table": reference,
        "rows": obj.num_rows,
        "bytes": obj.num_bytes,
        "partitioning": str(obj.time_partitioning) if obj.time_partitioning else None,
        "clustering_fields": obj.clustering_fields,
        "schema": fields,
    }


def dry_run_query(sql: str, project: str = "", location: str = "US", max_bytes_billed: int = DEFAULT_MAX_BYTES) -> dict[str, Any]:
    _, job, selected, maximum = dry_run(sql, project, location, max_bytes_billed)
    processed = int(job.total_bytes_processed or 0)
    try:
        from scripts.research_data_mcp.desk_activity import record_activity
        from scripts.research_data_mcp.desk_usage import record_bq_bytes

        record_bq_bytes(processed)
        record_activity(
            "bq_dry_run",
            sql[:200],
            bq_gib=processed / 1024**3,
        )
    except Exception:
        pass
    return {
        "project": selected,
        "location": location,
        "total_bytes_processed": processed,
        "estimated_gib": round(processed / 1024**3, 4),
        "maximum_bytes_billed": maximum,
        "within_guard": processed <= maximum,
        "execution": "not_run",
    }


def read_query(
    sql: str,
    project: str = "",
    location: str = "US",
    max_bytes_billed: int = DEFAULT_MAX_BYTES,
    max_rows: int = 1000,
    confirm: str = "",
) -> dict[str, Any]:
    from google.cloud import bigquery

    if confirm != "EXECUTE_READ_ONLY":
        raise ValueError("execution requires confirm=EXECUTE_READ_ONLY")
    clean = read_only_sql(sql)
    client, dry_job, selected, maximum = dry_run(clean, project, location, max_bytes_billed)
    processed = int(dry_job.total_bytes_processed or 0)
    if processed > maximum:
        raise ValueError(f"dry run estimates {processed} bytes, above maximum_bytes_billed={maximum}")
    row_limit = min(max(int(max_rows), 1), MAX_QUERY_ROWS)
    config = bigquery.QueryJobConfig(use_query_cache=True, maximum_bytes_billed=maximum)
    job = client.query(clean, job_config=config, location=location)
    rows = [{key: json_value(value) for key, value in dict(row).items()} for row in job.result(max_results=row_limit)]
    billed = int(job.total_bytes_processed or 0)
    try:
        from scripts.research_data_mcp.desk_activity import record_activity
        from scripts.research_data_mcp.desk_usage import record_bq_bytes

        record_bq_bytes(billed)
        record_activity(
            "bq_read",
            sql[:200],
            bq_gib=billed / 1024**3,
        )
    except Exception:
        pass
    return {
        "project": selected,
        "location": location,
        "job_id": job.job_id,
        "total_bytes_processed": billed,
        "returned": len(rows),
        "max_rows": row_limit,
        "rows": rows,
    }
