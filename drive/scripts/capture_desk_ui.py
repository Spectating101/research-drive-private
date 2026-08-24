#!/usr/bin/env python3
"""Capture desk UI screenshots for QA / faculty preview."""

from __future__ import annotations

from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/status/generated"
BASE = "http://127.0.0.1:8765"
EMAIL = "drkong@saturn.yzu.edu.tw"


def sign_in(page) -> None:
    page.goto(f"{BASE}/")
    page.evaluate("localStorage.clear()")
    page.reload()
    page.get_by_placeholder("you@saturn.yzu.edu.tw").fill(EMAIL)
    page.get_by_role("button", name="Continue").click()
    page.get_by_text("Asst. Prof. Kong · desk").wait_for(timeout=20_000)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()

        desktop = browser.new_page(viewport={"width": 1440, "height": 900})
        desktop.goto(f"{BASE}/")
        desktop.evaluate("localStorage.clear()")
        desktop.reload()
        desktop.screenshot(path=str(OUT / "desk-ui-login-desktop.png"), full_page=True)

        sign_in(desktop)
        desktop.screenshot(path=str(OUT / "desk-ui-home-desktop.png"), full_page=True)

        desktop.get_by_role("button", name="Lab").click()
        desktop.screenshot(path=str(OUT / "desk-ui-lab-rail-desktop.png"), full_page=True)

        desktop.get_by_role("button", name="TWSE listed firm daily prices").click()
        desktop.locator("article.assistant").last.wait_for(state="visible", timeout=90_000)
        desktop.locator("article.assistant").last.filter(has_not_text="…").wait_for(timeout=90_000)
        desktop.screenshot(path=str(OUT / "desk-ui-chat-reply-desktop.png"), full_page=True)

        desktop.get_by_role("button", name="Jobs").click()
        desktop.get_by_role("heading", name="Procurement jobs").wait_for()
        desktop.screenshot(path=str(OUT / "desk-ui-jobs-desktop.png"), full_page=True)

        desktop.get_by_role("button", name="Vault").click()
        desktop.get_by_role("heading", name="Credential vault").wait_for()
        desktop.screenshot(path=str(OUT / "desk-ui-vault-desktop.png"), full_page=True)

        mobile = browser.new_page(viewport={"width": 390, "height": 844})
        sign_in(mobile)
        mobile.screenshot(path=str(OUT / "desk-ui-home-mobile.png"), full_page=True)

        browser.close()
    print(f"Wrote screenshots to {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
