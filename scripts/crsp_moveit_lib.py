"""Shared CRSP MOVEit session helpers (credentials from .env.local)."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urljoin

import requests


@dataclass(frozen=True)
class MoveitFile:
    file_id: str
    name: str
    size_bytes: int
    item_id: str

    @classmethod
    def from_html(cls, file_id: str, name: str, size_bytes: int) -> MoveitFile:
        return cls(file_id=file_id, name=name, size_bytes=size_bytes, item_id=f"file{file_id}")


@dataclass(frozen=True)
class MoveitFolder:
    folder_id: str
    name: str
    path: str


SessionFactory = Callable[[], requests.Session]


def load_env_local(repo_root: Path) -> dict[str, str]:
    path = repo_root / ".env.local"
    if not path.is_file():
        return {}
    out: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        out[k.strip()] = v.strip().strip("'\"").strip('"')
    return out


def crsp_credentials(env: dict[str, str]) -> tuple[str, str]:
    user = env.get("CRSP_ID", "").strip()
    password = env.get("CRSP_PASSWORD", "").strip()
    if not user or not password:
        raise RuntimeError("CRSP_ID and CRSP_PASSWORD required in .env.local")
    return user, password


def make_session_factory(repo_root: Path) -> SessionFactory:
    env = load_env_local(repo_root)
    user, password = crsp_credentials(env)

    def _factory() -> requests.Session:
        return moveit_login_session(user, password)

    return _factory


def moveit_login_session(user: str, password: str) -> requests.Session:
    base = "https://crsp.moveitcloud.com/"
    sess = requests.Session()
    sess.headers.update({"User-Agent": "SharpeRenaissance-CRSP/1.0"})
    r0 = sess.get(base, timeout=60)
    r0.raise_for_status()
    m = re.search(r'<form[^>]+name="form_signon"[^>]+action="([^"]+)"', r0.text)
    if not m:
        raise RuntimeError("CRSP MOVEit signon form not found")
    action = urljoin(base, m.group(1))
    hidden = dict(re.findall(r'<input type="hidden" name="([^"]+)" value="([^"]*)"', r0.text))
    payload = {**hidden, "transaction": "signon", "fromsignon": "1", "Username": user, "Password": password}
    r1 = sess.post(action, data=payload, timeout=60, allow_redirects=True)
    text = r1.text.lower()
    if "invalid" in text and "password" in text:
        raise RuntimeError("CRSP MOVEit authentication failed")
    if "formsignon" in r1.url.lower() and "sign on" in text:
        raise RuntimeError("CRSP MOVEit authentication failed (still on signon)")
    return sess


def parse_r_token(html: str) -> str:
    m = re.search(r'name="filelistform"[^>]*action="[^"]*\?r=(\d+)"', html)
    if m:
        return m.group(1)
    m = re.search(r'human\.aspx\?r=(\d+)', html)
    if not m:
        raise RuntimeError("MOVEit session token (r=) not found")
    return m.group(1)


def folder_tree_from_html(html: str) -> dict[str, MoveitFolder]:
    out: dict[str, MoveitFolder] = {}
    for path, folder_id in re.findall(r'<option title="([^"]+)" value="(\d+)">', html):
        norm = path.strip().rstrip("/")
        if not norm.startswith("/"):
            norm = f"/{norm}"
        out[norm] = MoveitFolder(folder_id=folder_id, name=norm.rsplit("/", 1)[-1], path=norm)
    return out


def list_moveit_folders(html: str) -> list[dict[str, Any]]:
    labels = re.findall(r'>([^<]{3,140})<', html)
    cleaned: list[str] = []
    for raw in labels:
        s = re.sub(r"\s+", " ", raw.replace("&nbsp;", " ")).strip(" /")
        if not s or s.lower() in {"size", "contents", "name"}:
            continue
        if any(k in s.upper() for k in ("PRODUCT", "STOCK", "INDEX", "CCM", "NOTIFICATION")):
            cleaned.append(s)
    seen: set[str] = set()
    rows: list[dict[str, Any]] = []
    for label in cleaned:
        if label in seen:
            continue
        seen.add(label)
        rows.append({"label": label, "path": label})
    return rows


def folder_list_url(r_token: str, folder_id: str) -> str:
    return f"https://crsp.moveitcloud.com/human.aspx?r={r_token}&arg06={folder_id}&arg12=filelist"


def list_folder_contents(sess: requests.Session, r_token: str, folder_id: str) -> tuple[list[MoveitFile], list[MoveitFolder]]:
    url = folder_list_url(r_token, folder_id)
    r = sess.get(url, timeout=120)
    r.raise_for_status()
    text = r.text
    files: list[MoveitFile] = []
    for m in re.finditer(r'name="filename_(\d+)" value="([^"]+)"', text):
        fid, fname = m.group(1), m.group(2)
        sm = re.search(rf'name="filesize_{fid}" value="(\d+)"', text)
        size = int(sm.group(1)) if sm else 0
        files.append(MoveitFile.from_html(fid, fname, size))
    folders: list[MoveitFolder] = []
    for m in re.finditer(r'name="foldername_(\d+)" value="([^"]+)"', text):
        folders.append(MoveitFolder(folder_id=m.group(1), name=m.group(2), path=m.group(2)))
    return files, folders


def _is_zip_prefix(data: bytes) -> bool:
    return data[:2] == b"PK"


def _finalize_part(part: Path, dest: Path, expected: int) -> Path:
    on_disk = part.stat().st_size
    if expected > 0 and on_disk < expected * 0.99:
        raise RuntimeError(f"Incomplete download for {dest.name}: {on_disk} of {expected} bytes")
    if on_disk == 0:
        raise RuntimeError(f"Downloaded zero bytes for {dest.name}")
    if dest.is_file():
        dest.unlink()
    part.replace(dest)
    return dest


def _consolidate_partials(part: Path) -> int:
    """Keep the largest valid zip partial between .part and .part.tmp."""
    tmp = part.with_suffix(part.suffix + ".tmp")
    best_size = 0
    for candidate in (part, tmp):
        if not candidate.is_file():
            continue
        size = candidate.stat().st_size
        if size <= 0:
            continue
        try:
            head = candidate.read_bytes()[:4]
        except OSError:
            continue
        if not _is_zip_prefix(head):
            candidate.unlink(missing_ok=True)
            continue
        if size > best_size:
            best_size = size
            if candidate is not part:
                candidate.replace(part)
    return part.stat().st_size if part.is_file() else 0


def download_moveit_file(
    sess: requests.Session,
    *,
    file: MoveitFile,
    folder_id: str,
    dest: Path,
    referer: str | None = None,
    chunk_size: int = 1024 * 1024,
    max_attempts: int = 12,
    read_timeout_s: int = 3600,
    on_progress: Callable[[int, int], None] | None = None,
    session_factory: SessionFactory | None = None,
) -> Path:
    """Download with fresh MOVEit login on each retry; keep best partial on disk."""
    import time

    from requests.exceptions import ConnectionError as ReqConnectionError

    part = dest.with_suffix(dest.suffix + ".part")
    _consolidate_partials(part)
    best_bytes = part.stat().st_size if part.is_file() else 0

    if dest.is_file() and file.size_bytes > 0 and dest.stat().st_size >= file.size_bytes * 0.99:
        return dest
    if best_bytes > 0 and file.size_bytes > 0 and best_bytes >= file.size_bytes * 0.99:
        return _finalize_part(part, dest, file.size_bytes)

    last_err: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        active = session_factory() if session_factory else sess
        active_referer = referer
        if session_factory:
            home = active.get("https://crsp.moveitcloud.com/", timeout=60)
            home.raise_for_status()
            r_token = parse_r_token(home.text)
            active_referer = folder_list_url(r_token, folder_id)
            active.get(active_referer, timeout=120)

        tmp = part.with_suffix(part.suffix + ".tmp")
        try:
            if best_bytes > 0:
                target = part
                resume = best_bytes
            else:
                target = tmp
                resume = 0
            _download_moveit_file_once(
                active,
                file=file,
                folder_id=folder_id,
                dest=target,
                referer=active_referer,
                chunk_size=chunk_size,
                read_timeout_s=read_timeout_s,
                on_progress=on_progress,
                resume_from=resume,
            )
            if tmp.is_file():
                if not part.is_file() or tmp.stat().st_size > part.stat().st_size:
                    tmp.replace(part)
                else:
                    tmp.unlink(missing_ok=True)
            best_bytes = part.stat().st_size if part.is_file() else 0
            if file.size_bytes > 0 and best_bytes >= file.size_bytes * 0.99:
                return _finalize_part(part, dest, file.size_bytes)
        except (ReqConnectionError, TimeoutError, RuntimeError) as exc:
            last_err = exc
            if tmp.is_file():
                tmp_size = tmp.stat().st_size
                if tmp_size > best_bytes and _is_zip_prefix(tmp.read_bytes()[:4]):
                    tmp.replace(part)
                    best_bytes = tmp_size
                else:
                    tmp.unlink(missing_ok=True)
            if attempt >= max_attempts:
                break
            time.sleep(min(45 * attempt, 300))

    if part.is_file() and best_bytes > 0:
        raise RuntimeError(
            f"MOVEit download incomplete for {file.name} after {max_attempts} attempts "
            f"({best_bytes} bytes kept at {part}): {last_err}"
        )
    raise RuntimeError(f"MOVEit download failed for {file.name} after {max_attempts} attempts: {last_err}")


def _download_moveit_file_once(
    sess: requests.Session,
    *,
    file: MoveitFile,
    folder_id: str,
    dest: Path,
    referer: str | None,
    chunk_size: int,
    read_timeout_s: int,
    on_progress: Callable[[int, int], None] | None,
    resume_from: int = 0,
) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if resume_from <= 0 and dest.is_file():
        dest.unlink()
    download_id = uuid.uuid4().hex
    url = (
        f"https://crsp.moveitcloud.com/download?arg01={file.item_id}"
        f"&arg02={folder_id}&arg03={download_id}"
    )
    headers: dict[str, str] = {}
    if referer:
        headers["Referer"] = referer
    if resume_from > 0:
        headers["Range"] = f"bytes={resume_from}-"

    written = resume_from
    next_log = ((written // (100 * 1024 * 1024)) + 1) * 100 * 1024 * 1024
    mode = "ab" if resume_from > 0 else "wb"
    with sess.get(url, timeout=(30, read_timeout_s), stream=True, headers=headers) as r:
        if resume_from > 0 and r.status_code == 416:
            return dest
        if resume_from > 0 and r.status_code not in (200, 206):
            raise RuntimeError(f"MOVEit resume failed HTTP {r.status_code} for {file.name}")
        if resume_from == 0:
            r.raise_for_status()
        ct = (r.headers.get("content-type") or "").lower()
        with dest.open(mode) as fh:
            first: bytes | None = None
            for chunk in r.iter_content(chunk_size=chunk_size):
                if not chunk:
                    continue
                if first is None and resume_from == 0:
                    first = chunk[:8]
                    if "html" in ct or first.startswith(b"<"):
                        raise RuntimeError(f"MOVEit download returned HTML for {file.name}")
                    if not _is_zip_prefix(first) and file.name.lower().endswith(".zip"):
                        raise RuntimeError(f"MOVEit download not a zip for {file.name}")
                fh.write(chunk)
                written += len(chunk)
                if on_progress and written >= next_log:
                    on_progress(written, file.size_bytes)
                    next_log += 100 * 1024 * 1024
    if on_progress:
        on_progress(written, file.size_bytes)
    return dest


def resolve_product_folder(tree: dict[str, MoveitFolder], moveit_label: str) -> MoveitFolder | None:
    candidates = [
        f"/Product_Downloads/{moveit_label}",
        f"/{moveit_label}",
    ]
    for path in candidates:
        if path in tree:
            return tree[path]
    for path, folder in tree.items():
        if path.endswith(f"/{moveit_label}"):
            return folder
    return None
