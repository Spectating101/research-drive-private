#!/usr/bin/env python3
"""Bounded HTTP-manifest collector used by local and remote YZU workers.

The collector accepts a JSON manifest containing ``items`` with at least a
public HTTP(S) ``url``. Successful responses are written under ``raw/`` in one
ZIP artifact. Exit status is 0 when every item succeeds, 2 when at least one
item succeeds and at least one fails, and 1 when no usable artifact can be
produced.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import tempfile
import threading
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

try:
    from .network_policy import open_pinned_public_url, validate_public_http_url
except ImportError:  # pragma: no cover - direct script execution
    from network_policy import open_pinned_public_url, validate_public_http_url

CHUNK_SIZE = 1024 * 1024
DEFAULT_MAX_ITEM_BYTES = 512 * 1024 * 1024
SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _bounded_int(value: Any, *, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(parsed, maximum))


def _safe_name(item: dict[str, Any], index: int, seen: set[str]) -> str:
    raw = str(item.get("name") or "").strip()
    if not raw:
        raw = Path(urlsplit(str(item.get("url") or "")).path).name
    raw = Path(raw).name or f"item-{index + 1}.bin"
    clean = SAFE_NAME_RE.sub("_", raw).strip("._") or f"item-{index + 1}.bin"
    candidate = clean
    stem, suffix = Path(clean).stem, Path(clean).suffix
    serial = 2
    while candidate.casefold() in seen:
        candidate = f"{stem}-{serial}{suffix}"
        serial += 1
    seen.add(candidate.casefold())
    return candidate


class RateLimiter:
    def __init__(self, delay_seconds: float) -> None:
        self.delay_seconds = max(0.0, float(delay_seconds))
        self._lock = threading.Lock()
        self._next_at = 0.0

    def wait(self) -> None:
        if self.delay_seconds <= 0:
            return
        with self._lock:
            now = time.monotonic()
            wait_for = max(0.0, self._next_at - now)
            self._next_at = max(now, self._next_at) + self.delay_seconds
        if wait_for:
            time.sleep(wait_for)


@dataclass
class ItemResult:
    index: int
    url: str
    name: str
    ok: bool
    attempts: int
    bytes: int = 0
    sha256: str = ""
    content_type: str = ""
    status: int | None = None
    error: str = ""
    local_path: str = ""
    final_url: str = ""
    resolved_addresses: tuple[str, ...] = ()


def _validate_url(url: str) -> dict[str, Any]:
    return validate_public_http_url(url)


class PublicOnlyRedirectHandler(HTTPRedirectHandler):
    """Reject a redirect before urllib follows it into an internal network."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[override]
        _validate_url(str(newurl or ""))
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _download_item(
    item: dict[str, Any],
    *,
    index: int,
    name: str,
    output_dir: Path,
    timeout: int,
    retries: int,
    limiter: RateLimiter,
    default_max_bytes: int,
) -> ItemResult:
    url = str(item.get("url") or "").strip()
    try:
        _validate_url(url)
    except ValueError as exc:
        return ItemResult(index=index, url=url, name=name, ok=False, attempts=0, error=str(exc))

    headers = {"User-Agent": "ResearchDrive-YZU-Worker/1.0", "Accept": "*/*"}
    supplied_headers = item.get("headers")
    if isinstance(supplied_headers, dict):
        for key, value in supplied_headers.items():
            key_text = str(key).strip()
            if key_text and key_text.lower() not in {"host", "content-length"}:
                headers[key_text] = str(value)

    max_bytes = _bounded_int(
        item.get("max_bytes"),
        default=default_max_bytes,
        minimum=1,
        maximum=4 * 1024 * 1024 * 1024,
    )
    expected_sha256 = str(item.get("sha256") or "").strip().lower()
    destination = output_dir / name
    temporary = destination.with_suffix(destination.suffix + ".part")
    last_error = ""

    for attempt in range(1, retries + 2):
        temporary.unlink(missing_ok=True)
        limiter.wait()
        digest = hashlib.sha256()
        total = 0
        current_url = url
        try:
            # Manual redirect loop with pin+validate on every hop (no DNS rebind window).
            for _hop in range(8):
                evidence = _validate_url(current_url)
                with open_pinned_public_url(current_url, headers=headers, timeout=timeout) as response:
                    status = int(response.status)
                    if status in {301, 302, 303, 307, 308}:
                        location = str(response.headers.get("Location") or "").strip()
                        if not location:
                            raise RuntimeError(f"HTTP {status} without Location")
                        from urllib.parse import urljoin

                        next_url = urljoin(current_url, location)
                        _validate_url(next_url)
                        current_url = next_url
                        continue
                    if status < 200 or status >= 300:
                        raise RuntimeError(f"HTTP {status}")
                    final_url = current_url
                    final_evidence = evidence
                    pinned = getattr(response, "evidence", {}) or {}
                    length_header = response.headers.get("Content-Length")
                    if length_header:
                        declared = int(length_header)
                        if declared > max_bytes:
                            raise ValueError(f"response exceeds {max_bytes} byte limit")
                    with temporary.open("wb") as handle:
                        while True:
                            chunk = response.read(CHUNK_SIZE)
                            if not chunk:
                                break
                            total += len(chunk)
                            if total > max_bytes:
                                raise ValueError(f"response exceeds {max_bytes} byte limit")
                            digest.update(chunk)
                            handle.write(chunk)
                        handle.flush()
                        os.fsync(handle.fileno())
                    if total < 1:
                        raise ValueError("response body is empty")
                    actual_sha256 = digest.hexdigest()
                    if expected_sha256 and actual_sha256 != expected_sha256:
                        raise ValueError("response sha256 does not match manifest proof")
                    os.replace(temporary, destination)
                    return ItemResult(
                        index=index,
                        url=url,
                        name=name,
                        ok=True,
                        attempts=attempt,
                        bytes=total,
                        sha256=actual_sha256,
                        content_type=str(response.headers.get("Content-Type") or ""),
                        status=status,
                        local_path=str(destination),
                        final_url=final_url,
                        resolved_addresses=tuple(
                            pinned.get("resolved_addresses")
                            or final_evidence.get("resolved_addresses")
                            or ()
                        ),
                    )
            raise RuntimeError("too many redirects")
        except HTTPError as exc:
            last_error = f"HTTP {exc.code}"
        except (URLError, TimeoutError, OSError, RuntimeError, ValueError) as exc:
            last_error = str(exc)
        finally:
            temporary.unlink(missing_ok=True)
        if attempt <= retries:
            time.sleep(min(5.0, 0.25 * (2 ** (attempt - 1))))

    return ItemResult(
        index=index,
        url=url,
        name=name,
        ok=False,
        attempts=retries + 1,
        error=last_error or "download failed",
    )


def collect_manifest(
    manifest_path: Path,
    artifact_path: Path,
    *,
    workers: int = 2,
    timeout: int = 90,
    retries: int = 3,
    delay: float = 0.25,
) -> tuple[int, dict[str, Any]]:
    document = json.loads(manifest_path.read_text(encoding="utf-8"))
    items = document.get("items")
    if not isinstance(items, list) or not items:
        raise ValueError("manifest must contain a non-empty items list")
    if not all(isinstance(item, dict) for item in items):
        raise ValueError("every manifest item must be an object")

    worker_count = _bounded_int(workers, default=2, minimum=1, maximum=16)
    timeout_seconds = _bounded_int(timeout, default=90, minimum=1, maximum=300)
    retry_count = _bounded_int(retries, default=3, minimum=0, maximum=5)
    default_max_bytes = _bounded_int(
        os.environ.get("YZU_REMOTE_COLLECT_MAX_ITEM_BYTES"),
        default=DEFAULT_MAX_ITEM_BYTES,
        minimum=1,
        maximum=4 * 1024 * 1024 * 1024,
    )
    limiter = RateLimiter(delay)
    seen: set[str] = set()
    names = [_safe_name(item, index, seen) for index, item in enumerate(items)]

    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_tmp = artifact_path.with_suffix(artifact_path.suffix + ".part")
    artifact_tmp.unlink(missing_ok=True)

    with tempfile.TemporaryDirectory(prefix="yzu-remote-collect-") as temporary_root:
        output_dir = Path(temporary_root) / "raw"
        output_dir.mkdir(parents=True)
        results: list[ItemResult] = []
        with ThreadPoolExecutor(max_workers=worker_count, thread_name_prefix="yzu-http") as pool:
            futures = {
                pool.submit(
                    _download_item,
                    item,
                    index=index,
                    name=names[index],
                    output_dir=output_dir,
                    timeout=timeout_seconds,
                    retries=retry_count,
                    limiter=limiter,
                    default_max_bytes=default_max_bytes,
                ): index
                for index, item in enumerate(items)
            }
            for future in as_completed(futures):
                results.append(future.result())
        results.sort(key=lambda row: row.index)

        successful = [row for row in results if row.ok]
        failed = [row for row in results if not row.ok]
        report = {
            "job_id": str(document.get("job_id") or ""),
            "shard": document.get("shard", 0),
            "created_at": _now(),
            "total": len(results),
            "succeeded": len(successful),
            "failed": len(failed),
            "items": [asdict(row) | {"local_path": ""} for row in results],
        }

        if not successful:
            artifact_path.unlink(missing_ok=True)
            return 1, report

        try:
            with zipfile.ZipFile(artifact_tmp, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
                archive.writestr("manifest.json", json.dumps(document, indent=2, ensure_ascii=False) + "\n")
                archive.writestr("collect_report.json", json.dumps(report, indent=2, ensure_ascii=False) + "\n")
                for row in successful:
                    archive.write(Path(row.local_path), arcname=f"raw/{row.name}")
            os.replace(artifact_tmp, artifact_path)
        finally:
            artifact_tmp.unlink(missing_ok=True)

    return (0 if not failed else 2), report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Collect a bounded HTTP manifest into a worker artifact ZIP")
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--artifact", required=True, type=Path)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--timeout", type=int, default=90)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--delay", type=float, default=0.25)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        code, report = collect_manifest(
            args.manifest,
            args.artifact,
            workers=args.workers,
            timeout=args.timeout,
            retries=args.retries,
            delay=args.delay,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps({"ok": code == 0, **report}, ensure_ascii=False))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
