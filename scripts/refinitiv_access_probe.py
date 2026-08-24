#!/usr/bin/env python3
"""Smoke-test local LSEG/Refinitiv access without storing secrets in code.

Run with the Refinitiv Python 3.11 environment:

    # Web / university login (no desktop) — EDP API app key + username/password
    .venv-refinitiv/bin/python scripts/refinitiv_access_probe.py --mode platform --env .env.local

    # Desktop Workspace/Eikon on same machine — Eikon Data API app key
    .venv-refinitiv/bin/python scripts/refinitiv_access_probe.py --mode desktop --ric BBCA.JK

Credentials: .env.local (LSEG_EDP_APP_KEY + LSEG_USERNAME + LSEG_PASSWORD for web;
LSEG_APP_KEY + running Workspace for desktop). Keep secrets out of git.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

from dotenv import load_dotenv


def _print_frame(label: str, frame) -> None:
    print(f"\n[{label}]")
    if frame is None:
        print("No dataframe returned.")
        return
    try:
        print(frame.head(20).to_string())
    except Exception:
        print(frame)


def _lseg_credentials() -> tuple[str | None, str | None, str | None]:
    user = os.getenv("LSEG_USERNAME") or os.getenv("REFINITIV_LOGIN_ID") or os.getenv("refinitiv-LOGIN_ID")
    password = os.getenv("LSEG_PASSWORD") or os.getenv("REFINITIV_PASSWORD") or os.getenv("refinitiv-PASSWORD")
    return user, password, os.getenv("LSEG_EDP_APP_KEY") or os.getenv("LSEG_PLATFORM_APP_KEY")


def _platform_config_path() -> str:
    user, password, app_key = _lseg_credentials()
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


def probe_platform(rics: list[str], fields: list[str]) -> int:
    import lseg.data as ld

    config_path = os.getenv("LSEG_CONFIG_PATH") or _platform_config_path()
    session_name = os.getenv("LSEG_SESSION_NAME") or "platform.ldp"
    user, _, app_key = _lseg_credentials()

    print("Opening LSEG platform session (web / EDP API)...")
    print(f"  session_name={session_name}")
    print(f"  username={user}")
    print(f"  edp_app_key={'set' if app_key else 'missing'}")

    try:
        ld.open_session(name=session_name, config_name=config_path)
        frame = ld.get_data(universe=rics, fields=fields)
        _print_frame("LSEG platform get_data", frame)
    finally:
        try:
            ld.close_session()
        except Exception:
            pass
    return 0


def probe_desktop(rics: list[str], fields: list[str]) -> int:
    import lseg.data as ld

    app_key = os.getenv("LSEG_APP_KEY") or None
    session_name = os.getenv("LSEG_SESSION_NAME") or "desktop.workspace"
    config_path = os.getenv("LSEG_CONFIG_PATH") or None

    kwargs = {}
    if app_key:
        kwargs["app_key"] = app_key
    if session_name:
        kwargs["name"] = session_name
    if config_path:
        kwargs["config_name"] = config_path

    print("Opening LSEG session...")
    print(f"  session_name={session_name or '<library default>'}")
    print(f"  config_path={config_path or '<library/default search>'}")
    print(f"  app_key={'set' if app_key else 'not set, relying on desktop/config'}")

    try:
        ld.open_session(**kwargs)
        frame = ld.get_data(universe=rics, fields=fields)
        _print_frame("LSEG get_data", frame)
    finally:
        try:
            ld.close_session()
        except Exception:
            pass
    return 0


def probe_eikon(rics: list[str], fields: list[str]) -> int:
    import eikon as ek

    app_key = os.getenv("EIKON_APP_KEY") or os.getenv("LSEG_APP_KEY")
    if not app_key:
        print("EIKON_APP_KEY or LSEG_APP_KEY is required for legacy eikon mode.", file=sys.stderr)
        return 2

    print("Opening legacy Eikon Data API session via desktop API proxy...")
    ek.set_app_key(app_key)
    frame, err = ek.get_data(rics, fields)
    if err:
        print(f"Eikon returned error: {err}", file=sys.stderr)
        return 1
    _print_frame("Eikon get_data", frame)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--mode",
        choices=["platform", "desktop", "eikon", "lseg"],
        default="platform",
        help="platform=web/EDP (default); desktop/lseg=Workspace on localhost; eikon=legacy",
    )
    ap.add_argument("--ric", action="append", default=["BBCA.JK"])
    ap.add_argument(
        "--field",
        action="append",
        default=["TR.CommonName", "TR.PriceClose", "TR.Volume"],
    )
    ap.add_argument("--env", default=".env", help="Local env file. Default: .env")
    args = ap.parse_args()

    env_path = Path(args.env)
    if env_path.exists():
        load_dotenv(env_path)
    else:
        load_dotenv()

    try:
        if args.mode in ("platform",):
            return probe_platform(args.ric, args.field)
        if args.mode in ("desktop", "lseg"):
            return probe_desktop(args.ric, args.field)
        return probe_eikon(args.ric, args.field)
    except Exception as exc:
        print("\nAccess probe failed.", file=sys.stderr)
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        if args.mode == "platform":
            print(
                "\nWeb access needs LSEG_EDP_APP_KEY (EDP API type, not Eikon Data API), "
                "plus LSEG_USERNAME / LSEG_PASSWORD in .env.local. "
                "Close other Workspace web sessions if you see session quota errors.",
                file=sys.stderr,
            )
        else:
            print(
                "\nDesktop mode needs LSEG Workspace/Eikon running on this machine "
                "and LSEG_APP_KEY (Eikon Data API type).",
                file=sys.stderr,
            )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
