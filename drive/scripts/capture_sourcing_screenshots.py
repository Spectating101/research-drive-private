#!/usr/bin/env python3
"""Capture sourcing UI screenshots via Playwright (one-shot, long timeout)."""
from __future__ import annotations

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/status/generated"
EMAIL = "drkong@saturn.yzu.edu.tw"
BASE = "http://127.0.0.1:8765"


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.goto(BASE, wait_until="domcontentloaded", timeout=45_000)
        page.get_by_role("heading", name="Home").wait_for(timeout=30_000)
        page.locator(".rd-home-drive .rd-catalog-table").wait_for(timeout=30_000)

        # Sign in
        page.locator(".yzu-account-btn").click()
        page.get_by_placeholder("you@saturn.yzu.edu.tw").fill(EMAIL)
        page.get_by_role("button", name="Continue").click()
        page.wait_for_function(
            """() => {
              const s = document.querySelector('.yzu-account-copy strong');
              return s && !/sign in/i.test(s.textContent || '');
            }""",
            timeout=25_000,
        )

        def ask(prompt: str, shot: str) -> str:
            page.get_by_role("tab", name="Assistant").click()
            ta = page.locator("aside .yzu-composer textarea")
            ta.fill(prompt)
            page.locator("aside .yzu-composer button.primary").click()
            page.wait_for_function(
                """() => {
                  const arts = [...document.querySelectorAll('aside article.assistant')];
                  const last = arts[arts.length - 1];
                  return last && !last.textContent.includes('…') && last.textContent.trim().length > 30;
                }""",
                timeout=150_000,
            )
            page.screenshot(path=str(OUT / shot), full_page=False)
            return page.locator("aside .yzu-chat-card").inner_text()

        t1 = ask(
            "Find replication datasets on DataCite for Taiwan equity markets",
            "sourcing-01-datacite-ask.png",
        )
        print("--- DataCite ask (snippet) ---")
        print(t1[:600])

        t2 = ask(
            "Source SEC company tickers through spectator engine scrape on windows_lab",
            "sourcing-02-spectator-ask.png",
        )
        print("--- Spectator ask (snippet) ---")
        print(t2[:600])

        page.locator("aside.yzu-sidebar > nav").get_by_role("button", name="Discover").click()
        page.get_by_role("heading", name="Discover").wait_for()
        page.wait_for_function(
            "() => !document.body.textContent.includes('Loading recommendations')",
            timeout=30_000,
        )
        page.screenshot(path=str(OUT / "sourcing-03-recommended-datacite.png", full_page=False))

        browser.close()
    print(f"screenshots → {OUT}/sourcing-*.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
