#!/usr/bin/env python3
"""Issue one invite-only Research Drive public-member access code.

The registry stores only a SHA-256 digest. A raw code is printed exactly once
to the operator terminal after an explicit ``--write``; it is never written to
the repository, environment, or a secondary file.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import sys
import tempfile
from pathlib import Path


def _clean_id(value: str) -> str:
    cleaned = "".join(ch for ch in str(value).strip() if ch.isalnum() or ch in "._-")[:96]
    if not cleaned:
        raise ValueError("principal id must contain letters, digits, '.', '_' or '-'")
    return cleaned


def _read_registry(path: Path) -> tuple[dict, list[dict]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        payload = {"principals": []}
    except (OSError, ValueError, TypeError) as exc:
        raise ValueError(f"cannot read principal registry: {exc}") from exc
    if isinstance(payload, list):
        payload = {"principals": payload}
    if not isinstance(payload, dict) or not isinstance(payload.get("principals", []), list):
        raise ValueError("principal registry must be an object with a principals list")
    rows = payload.setdefault("principals", [])
    if not all(isinstance(row, dict) for row in rows):
        raise ValueError("principal registry contains a non-object principal")
    return payload, rows


def _atomic_write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent, text=True)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(temp_name, path)
        path.chmod(0o600)
    except BaseException:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", required=True, type=Path, help="private DESK_PRINCIPALS_FILE path")
    parser.add_argument("--principal-id", required=True)
    parser.add_argument("--display-name", required=True)
    parser.add_argument("--email", required=True)
    parser.add_argument("--write", action="store_true", help="create the code and update the registry")
    args = parser.parse_args(argv)

    try:
        principal_id = _clean_id(args.principal_id)
        payload, rows = _read_registry(args.file.expanduser())
        if any(str(row.get("id") or row.get("principal_id") or "").strip() == principal_id for row in rows):
            raise ValueError(f"principal id already exists: {principal_id}")
        if not args.write:
            print(f"DRY RUN: would issue one public_member code for {principal_id}; re-run with --write")
            return 0
        code = f"rdm_{secrets.token_urlsafe(32)}"
        rows.append(
            {
                "id": principal_id,
                "email": str(args.email).strip().lower()[:320],
                "display_name": str(args.display_name).strip()[:160],
                "role": "public_member",
                "token_sha256": hashlib.sha256(code.encode("utf-8")).hexdigest(),
            }
        )
        _atomic_write(args.file.expanduser(), payload)
    except ValueError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2

    print("Issued one public-member access code. Deliver it through a private channel; it will not be shown again.")
    print(code)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
