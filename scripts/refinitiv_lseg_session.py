#!/usr/bin/env python3
"""Shared LSEG platform session helpers for Refinitiv harvest scripts."""

from __future__ import annotations

import json
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from dotenv import load_dotenv

REPO = Path(__file__).resolve().parents[1]


def load_env(env_path: str | Path | None = ".env") -> Path | None:
    """Load dotenv from *env_path* when present; fall back to process env."""
    if env_path is None:
        load_dotenv()
        return None
    path = Path(env_path)
    if not path.is_absolute():
        path = REPO / path
    if path.exists():
        load_dotenv(path)
        return path
    load_dotenv()
    return None


def lseg_credentials() -> tuple[str | None, str | None, str | None]:
    user = os.getenv("LSEG_USERNAME") or os.getenv("REFINITIV_LOGIN_ID") or os.getenv("refinitiv-LOGIN_ID")
    password = os.getenv("LSEG_PASSWORD") or os.getenv("REFINITIV_PASSWORD") or os.getenv("refinitiv-PASSWORD")
    app_key = os.getenv("LSEG_EDP_APP_KEY") or os.getenv("LSEG_PLATFORM_APP_KEY")
    return user, password, app_key


def platform_config_path() -> str:
    """Write a temporary platform session config and return its path."""
    user, password, app_key = lseg_credentials()
    if not app_key:
        raise ValueError("LSEG_EDP_APP_KEY is required for platform mode.")
    if not user or not password:
        raise ValueError("LSEG_USERNAME and LSEG_PASSWORD are required for platform mode.")

    cfg = {
        "sessions": {
            "default": "platform.ldp",
            "platform": {
                "ldp": {
                    "app-key": app_key,
                    "username": user,
                    "password": password,
                    "signon_control": True,
                }
            },
        },
        "logs": {"level": "warning", "transports": {"console": {"enabled": False}}},
    }
    path = Path(tempfile.gettempdir()) / "lseg-platform-session.config.json"
    path.write_text(json.dumps(cfg), encoding="utf-8")
    return str(path)


@contextmanager
def platform_session(session_name: str | None = None) -> Iterator[object]:
    """Open and close an LSEG platform session using LSEG_EDP_APP_KEY credentials."""
    import lseg.data as ld

    config_path = os.getenv("LSEG_CONFIG_PATH") or platform_config_path()
    name = session_name or os.getenv("LSEG_SESSION_NAME") or "platform.ldp"
    ld.open_session(name=name, config_name=config_path)
    try:
        yield ld
    finally:
        try:
            ld.close_session()
        except Exception:
            pass
