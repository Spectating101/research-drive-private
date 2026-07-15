"""Structured schedule specs for Discover refresh subscriptions.

Cadence (manual|daily|weekly|monthly) remains a coarse classification.
Execution uses schedule_spec.cron + timezone via the Discover refresh runner —
never natural-language alone.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

DEFAULT_TIMEZONE = "Asia/Taipei"

_MON = re.compile(r"\bmon(?:day)?\b", re.I)
_TUE = re.compile(r"\btue(?:sday)?\b", re.I)
_WED = re.compile(r"\bwed(?:nesday)?\b", re.I)
_THU = re.compile(r"\bthu(?:rsday)?\b", re.I)
_FRI = re.compile(r"\bfri(?:day)?\b", re.I)
_SAT = re.compile(r"\bsat(?:urday)?\b", re.I)
_SUN = re.compile(r"\bsun(?:day)?\b", re.I)
_TIME = re.compile(r"\b([01]?\d|2[0-3])(?::([0-5]\d))?\s*(am|pm)?\b", re.I)
_CRON_RE = re.compile(
    r"^\s*(\d{1,2})\s+(\d{1,2})\s+(\*|\d{1,2})\s+\*\s+(\*|[0-7])\s*$"
)


def _dow_from_text(text: str) -> int | None:
    """Cron DOW: 0=Sunday … 6=Saturday."""
    if _MON.search(text):
        return 1
    if _TUE.search(text):
        return 2
    if _WED.search(text):
        return 3
    if _THU.search(text):
        return 4
    if _FRI.search(text):
        return 5
    if _SAT.search(text):
        return 6
    if _SUN.search(text):
        return 0
    return None


def _hour_minute(text: str) -> tuple[int, int]:
    match = _TIME.search(text)
    if not match:
        return 10, 0
    hour = int(match.group(1))
    minute = int(match.group(2) or 0)
    ampm = (match.group(3) or "").lower()
    if ampm == "pm" and hour < 12:
        hour += 12
    if ampm == "am" and hour == 12:
        hour = 0
    return hour, minute


def infer_cadence(text: str, fallback: str = "weekly") -> str:
    lowered = (text or "").lower()
    if re.search(r"\bevery\s+day\b|\bdaily\b", lowered):
        return "daily"
    if re.search(r"\bmonthly\b|\bevery\s+month\b", lowered):
        return "monthly"
    if re.search(r"\bmanual\b", lowered):
        return "manual"
    if _dow_from_text(lowered) is not None or re.search(r"\bweekly\b|\bevery\s+week\b", lowered):
        return "weekly"
    return fallback if fallback in {"manual", "daily", "weekly", "monthly"} else "weekly"


def build_schedule_spec(
    *,
    requested_schedule: str = "",
    cadence: str = "weekly",
    timezone: str = DEFAULT_TIMEZONE,
    explicit: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a structured schedule_spec dict (executable when cron is present)."""
    if isinstance(explicit, dict) and explicit.get("cron"):
        cron = str(explicit.get("cron"))[:64]
        return {
            "schedule_type": str(explicit.get("schedule_type") or "cron"),
            "timezone": str(explicit.get("timezone") or timezone or DEFAULT_TIMEZONE)[:64],
            "cron": cron,
            "requested_schedule": str(explicit.get("requested_schedule") or requested_schedule or "")[:240],
            "inferred": False,
            "executable": bool(cron.strip()),
            "note": "Discover refresh runner executes this cron when the subscription is active.",
        }

    text = str(requested_schedule or "").strip()
    cad = str(cadence or infer_cadence(text) or "weekly").lower()
    hour, minute = _hour_minute(text) if text else (10, 0)
    dow = _dow_from_text(text)

    if cad == "daily":
        cron = f"{minute} {hour} * * *"
    elif cad == "monthly":
        cron = f"{minute} {hour} 1 * *"
    elif cad == "manual":
        cron = ""
    else:
        cron = f"{minute} {hour} * * {1 if dow is None else dow}"

    return {
        "schedule_type": "cron" if cron else "manual",
        "timezone": str(timezone or DEFAULT_TIMEZONE)[:64],
        "cron": cron,
        "requested_schedule": text[:240],
        "inferred": True,
        "executable": bool(cron),
        "note": (
            "Discover refresh runner executes this cron when the subscription is active."
            if cron
            else "Manual cadence — no automatic next run."
        ),
    }


def _tz(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(str(name or DEFAULT_TIMEZONE))
    except Exception:  # noqa: BLE001
        return ZoneInfo(DEFAULT_TIMEZONE)


def parse_simple_cron(cron: str) -> dict[str, Any] | None:
    """Parse the limited cron forms we emit: m h dom * dow."""
    match = _CRON_RE.match(str(cron or "").strip())
    if not match:
        return None
    minute, hour, dom, dow = match.groups()
    return {
        "minute": int(minute),
        "hour": int(hour),
        "dom": None if dom == "*" else int(dom),
        "dow": None if dow == "*" else (0 if int(dow) == 7 else int(dow)),
    }


def compute_next_run_at(
    spec: dict[str, Any] | None,
    *,
    after: datetime | None = None,
) -> str | None:
    """Next UTC ISO timestamp for schedule_spec.cron, or None if manual/unparseable."""
    if not isinstance(spec, dict):
        return None
    cron = str(spec.get("cron") or "").strip()
    if not cron:
        return None
    parsed = parse_simple_cron(cron)
    if not parsed:
        return None
    tz = _tz(str(spec.get("timezone") or DEFAULT_TIMEZONE))
    base = after.astimezone(tz) if after else datetime.now(tz)
    # Start searching from the next minute
    cursor = base.replace(second=0, microsecond=0) + timedelta(minutes=1)
    target_h = parsed["hour"]
    target_m = parsed["minute"]
    for _ in range(366 * 24 * 60):
        ok_time = cursor.hour == target_h and cursor.minute == target_m
        ok_dom = parsed["dom"] is None or cursor.day == parsed["dom"]
        # Python weekday: Mon=0 … Sun=6; cron: Sun=0 … Sat=6
        cron_dow = (cursor.weekday() + 1) % 7
        ok_dow = parsed["dow"] is None or cron_dow == parsed["dow"]
        if ok_time and ok_dom and ok_dow:
            return cursor.astimezone(UTC).replace(microsecond=0).isoformat()
        cursor += timedelta(minutes=1)
    return None
