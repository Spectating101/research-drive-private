#!/usr/bin/env python3
"""Probe CRSP MOVEit, WRDS, and Capital IQ credentials from .env.local (no secret output)."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

REPO = Path(__file__).resolve().parents[1]


def _load_env_local() -> dict[str, str]:
    path = REPO / ".env.local"
    if not path.is_file():
        return {}
    out: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        v = v.strip().strip("'").strip('"')
        out[k.strip()] = v
    return out


def _probe_crsp_moveit(user: str, password: str) -> dict[str, Any]:
    import requests

    base = "https://crsp.moveitcloud.com/"
    sess = requests.Session()
    sess.headers.update({"User-Agent": "SharpeRenaissance-CredentialProbe/1.0"})
    try:
        r0 = sess.get(base, timeout=30)
        r0.raise_for_status()
    except Exception as exc:
        return {"service": "crsp_moveit", "reachable": False, "error": str(exc)[:200]}

    m = re.search(r'<form[^>]+name="form_signon"[^>]+action="([^"]+)"', r0.text)
    if not m:
        return {"service": "crsp_moveit", "reachable": True, "login": "unknown_form"}

    action = urljoin(base, m.group(1))
    hidden = dict(re.findall(r'<input type="hidden" name="([^"]+)" value="([^"]*)"', r0.text))
    payload = {
        **hidden,
        "transaction": "signon",
        "fromsignon": "1",
        "Username": user,
        "Password": password,
    }
    try:
        r1 = sess.post(action, data=payload, timeout=30, allow_redirects=True)
    except Exception as exc:
        return {"service": "crsp_moveit", "reachable": True, "login": "post_failed", "error": str(exc)[:200]}

    text = r1.text.lower()
    ok_markers = ("sign out", "signoff", "logout", "my folders", "welcome", "file transfer")
    fail_markers = ("invalid", "incorrect", "failed", "sign on", "formsignon", "forgot password")
    logged_in = any(x in text for x in ok_markers) and r1.url != r0.url
    if not logged_in:
        logged_in = "signon" not in r1.url.lower() and "human.aspx" in r1.url.lower() and "invalid" not in text

    listing_hint = None
    if logged_in:
        if "stock" in text or "crsp" in text:
            listing_hint = "folder_listing_likely"
        # try common folder path hints in page
        folders = re.findall(r'>([^<]{3,60}(?:stock|daily|ccm|index)[^<]{0,40})<', r1.text, re.I)
        if folders:
            listing_hint = folders[:5]

    return {
        "service": "crsp_moveit",
        "url": base,
        "reachable": True,
        "login_attempted": True,
        "authenticated": bool(logged_in),
        "final_url": r1.url[:120],
        "http_status": r1.status_code,
        "listing_hint": listing_hint,
        "note": "CRSP US Stock Database bulk delivery via MOVEit Cloud",
    }


def _probe_wrds(user: str, password: str) -> dict[str, Any]:
    import requests

    base = "https://wrds-www.wharton.upenn.edu"
    login_url = f"{base}/login/"
    sess = requests.Session()
    sess.headers.update({"User-Agent": "SharpeRenaissance-CredentialProbe/1.0"})
    try:
        r0 = sess.get(login_url, timeout=30)
        r0.raise_for_status()
    except Exception as exc:
        return {"service": "wrds", "reachable": False, "error": str(exc)[:200]}

    csrf = sess.cookies.get("csrftoken", "")
    payload = {
        "username": user,
        "password": password,
        "csrfmiddlewaretoken": csrf,
    }
    headers = {"Referer": login_url}
    try:
        r1 = sess.post(login_url, data=payload, headers=headers, timeout=30, allow_redirects=True)
    except Exception as exc:
        return {"service": "wrds", "reachable": True, "login": "post_failed", "error": str(exc)[:200]}

    logged_in = '"logged_in": true' in r1.text or "logged_in': true" in r1.text
    if not logged_in:
        logged_in = "logout" in r1.text.lower() or "/account/" in r1.url

    products: list[str] = []
    if logged_in:
        try:
            r2 = sess.get(f"{base}/pages/get-data/", timeout=30)
            for name in ("CRSP", "Compustat", "CCM", "IBES"):
                if name.lower() in r2.text.lower():
                    products.append(name)
        except Exception:
            pass

    return {
        "service": "wrds",
        "url": base,
        "reachable": True,
        "login_attempted": True,
        "authenticated": bool(logged_in),
        "final_url": r1.url[:120],
        "http_status": r1.status_code,
        "data_vendors_mentioned": products,
        "note": "Wharton WRDS — SQL/web access to CRSP, Compustat, etc.",
    }


def _probe_capital_iq(email: str, password: str) -> dict[str, Any]:
    """Capital IQ uses Okta/SSO — probe login entrypoints; full auth may need browser MFA."""
    import requests

    candidates = [
        "https://www.capitaliq.com/CIQDotNet/login.aspx",
        "https://www.capitaliq.spglobal.com/web/client?auth=inherit",
        "https://login.spglobal.com/",
    ]
    sess = requests.Session()
    sess.headers.update({"User-Agent": "SharpeRenaissance-CredentialProbe/1.0"})
    results: list[dict[str, Any]] = []

    for url in candidates:
        try:
            r = sess.get(url, timeout=30, allow_redirects=True)
            results.append(
                {
                    "url": url,
                    "status": r.status_code,
                    "final_url": r.url[:140],
                    "title_hint": (re.search(r"<title>([^<]+)</title>", r.text, re.I) or [None, ""])[1][:80],
                    "has_login_form": bool(re.search(r'type=["\']password["\']', r.text, re.I)),
                    "okta_hint": "okta" in r.text.lower() or "okta" in r.url.lower(),
                }
            )
        except Exception as exc:
            results.append({"url": url, "error": str(exc)[:120]})

    # Try legacy Capital IQ form if present on capitaliq.com
    auth_result = "not_attempted"
    try:
        r0 = sess.get("https://www.capitaliq.com/", timeout=30, allow_redirects=True)
        # Some tenants use POST to login.aspx with UserName/Password
        if "password" in r0.text.lower():
            action = re.search(r'<form[^>]+action="([^"]+)"', r0.text, re.I)
            if action:
                post_url = urljoin(r0.url, action.group(1))
                payload = {"UserName": email, "Password": password, "username": email, "password": password}
                r1 = sess.post(post_url, data=payload, timeout=30, allow_redirects=True)
                ok = "logout" in r1.text.lower() or "dashboard" in r1.url.lower()
                auth_result = "authenticated" if ok else "rejected_or_sso_redirect"
    except Exception as exc:
        auth_result = f"error:{str(exc)[:80]}"

    return {
        "service": "capital_iq",
        "reachable": True,
        "login_id_format": "email" if "@" in email else "username",
        "entrypoints": results,
        "http_login_attempt": auth_result,
        "note": "S&P Capital IQ / Market Intelligence — Compustat fundamentals often here; may require Okta/MFA in browser",
    }


def main() -> int:
    env = _load_env_local()
    crsp_user = env.get("CRSP_ID", "")
    crsp_pass = env.get("CRSP_PASSWORD", "")
    ci_user = env.get("Capital_IQ_Login_ID", "")
    ci_pass = env.get("Capital_IQ_PASSWORD", "")

    report: dict[str, Any] = {
        "probe": "vendor_credentials",
        "credentials_present": {
            "crsp_moveit": bool(crsp_user and crsp_pass),
            "wrds_same_as_crsp_id": bool(crsp_user),
            "capital_iq": bool(ci_user and ci_pass),
        },
        "results": [],
    }

    if crsp_user and crsp_pass:
        report["results"].append(_probe_crsp_moveit(crsp_user, crsp_pass))
        report["results"].append(_probe_wrds(crsp_user, crsp_pass))
    else:
        report["results"].append({"service": "crsp_moveit", "skipped": "CRSP_ID/CRSP_PASSWORD missing"})

    if ci_user and ci_pass:
        report["results"].append(_probe_capital_iq(ci_user, ci_pass))
    else:
        report["results"].append({"service": "capital_iq", "skipped": "Capital_IQ_* missing"})

    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
