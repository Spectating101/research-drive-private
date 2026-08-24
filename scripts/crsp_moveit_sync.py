#!/usr/bin/env python3
"""Download priority CRSP MOVEit products into data_lake/crsp/raw/."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO / "kernel") not in sys.path:
    sys.path.insert(0, str(REPO / "kernel"))

from sharpe_kernel.paths import repo_root_from_file

ROOT = repo_root_from_file(__file__)
CATALOG = ROOT / "config/crsp_moveit_catalog.json"
RAW_ROOT = ROOT / "data_lake/crsp/raw"
SYNC_MANIFEST = ROOT / "data_lake/crsp/sync_latest.json"

TIER_PRODUCTS = {
    "smoke": [],
    "index": ["stock_index_1925_annsub"],
    "stock": ["stock_25i_si_ascii_annual"],
    "us_core": ["stock_index_1925_annsub", "stock_25i_si_ascii_annual"],
    "index_quarterly": ["index_history_qtrrel"],
    "all": None,
}


def _load_catalog() -> dict:
    return json.loads(CATALOG.read_text(encoding="utf-8"))


def _pick_files(files: list, *, pattern: str | None, max_mb: float | None):
    rows = sorted(files, key=lambda f: f.name)
    if pattern:
        import fnmatch

        rows = [f for f in rows if fnmatch.fnmatch(f.name.lower(), pattern.lower())]
    if max_mb is not None:
        cap = int(max_mb * 1024 * 1024)
        rows = [f for f in rows if f.size_bytes <= cap]
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true", help="List downloads without fetching bytes")
    ap.add_argument("--tier", choices=sorted(TIER_PRODUCTS), default="index",
                    help="index=Stock_Index_1925 (~2GB); stock=STOCK_25i_SI (~4GB); smoke=tiny test file")
    ap.add_argument("--product", action="append", dest="products", help="Catalog product id (repeatable)")
    ap.add_argument("--pattern", default=None, help="Glob filter on remote filename, e.g. '*_ascii.zip'")
    ap.add_argument("--max-mb", type=float, default=None, help="Skip remote files larger than this")
    ap.add_argument("--force", action="store_true", help="Re-download even if local file exists")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    from scripts.crsp_moveit_lib import (
        crsp_credentials,
        download_moveit_file,
        folder_list_url,
        folder_tree_from_html,
        list_folder_contents,
        load_env_local,
        make_session_factory,
        moveit_login_session,
        parse_r_token,
        resolve_product_folder,
    )

    session_factory = make_session_factory(ROOT)

    catalog = _load_catalog()
    products = catalog.get("priority_products") or []
    by_id = {p["id"]: p for p in products}

    if args.products:
        selected = [by_id[pid] for pid in args.products]
    elif args.tier == "smoke":
        selected = []
    else:
        tier_ids = TIER_PRODUCTS[args.tier]
        selected = products if tier_ids is None else [by_id[i] for i in tier_ids if i in by_id]

    env = load_env_local(ROOT)
    user, password = crsp_credentials(env)
    sess = moveit_login_session(user, password)
    home = sess.get("https://crsp.moveitcloud.com/", timeout=60)
    home.raise_for_status()
    r_token = parse_r_token(home.text)
    tree = folder_tree_from_html(home.text)

    plan: list[dict] = []
    downloaded: list[dict] = []
    skipped: list[dict] = []

    def _plan_product(prod: dict, folder_id: str, referer: str):
        files, _ = list_folder_contents(sess, r_token, folder_id)
        picks = _pick_files(files, pattern=args.pattern, max_mb=args.max_mb)
        if not picks and files:
            skipped.append({"product_id": prod["id"], "reason": "max_mb_filter", "remote_files": len(files)})
            return
        for f in picks:
            dest = RAW_ROOT / prod["id"] / f.name
            entry = {
                "product_id": prod["id"],
                "moveit_label": prod.get("moveit_label"),
                "folder_id": folder_id,
                "remote_name": f.name,
                "size_bytes": f.size_bytes,
                "local_path": str(dest.relative_to(ROOT)),
            }
            plan.append(entry)
            if dest.is_file() and not args.force:
                on_disk = dest.stat().st_size
                if f.size_bytes > 0 and on_disk >= f.size_bytes * 0.99:
                    skipped.append({**entry, "reason": "exists"})
                    continue
            if args.dry_run:
                continue

            def _progress(written: int, total: int, _entry=entry) -> None:
                pct = round(100.0 * written / max(total, 1), 1)
                line = f"{_entry['remote_name']}: {written // (1024*1024)} MB / {total // (1024*1024)} MB ({pct}%)"
                print(line, flush=True)
                progress_path = ROOT / "data_lake/crsp/download_progress.json"
                progress_path.write_text(
                    json.dumps(
                        {
                            "updated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
                            "file": _entry["remote_name"],
                            "written_bytes": written,
                            "total_bytes": total,
                            "pct": pct,
                        },
                        indent=2,
                    )
                    + "\n",
                    encoding="utf-8",
                )

            download_moveit_file(
                sess,
                file=f,
                folder_id=folder_id,
                dest=dest,
                referer=referer,
                on_progress=_progress,
                session_factory=session_factory,
            )
            downloaded.append({**entry, "bytes_on_disk": dest.stat().st_size})

    if args.tier == "smoke":
        notif = tree.get("/Product_Downloads/Notifications")
        if not notif:
            print("Notifications folder not found", file=sys.stderr)
            return 1
        referer = folder_list_url(r_token, notif.folder_id)
        files, _ = list_folder_contents(sess, r_token, notif.folder_id)
        picks = sorted(files, key=lambda f: f.size_bytes)[:1]
        for f in picks:
            dest = RAW_ROOT / "_smoke" / f.name
            entry = {
                "product_id": "smoke",
                "folder_id": notif.folder_id,
                "remote_name": f.name,
                "size_bytes": f.size_bytes,
                "local_path": str(dest.relative_to(ROOT)),
            }
            plan.append(entry)
            if dest.is_file() and not args.force and dest.stat().st_size > 0:
                skipped.append({**entry, "reason": "exists"})
                continue
            if not args.dry_run:
                download_moveit_file(sess, file=f, folder_id=notif.folder_id, dest=dest, referer=referer)
                downloaded.append({**entry, "bytes_on_disk": dest.stat().st_size})
    else:
        for prod in selected:
            folder = resolve_product_folder(tree, prod["moveit_label"])
            if not folder:
                skipped.append({"product_id": prod["id"], "reason": "folder_not_found"})
                continue
            referer = folder_list_url(r_token, folder.folder_id)
            _plan_product(prod, folder.folder_id, referer)

    out = {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "dry_run": args.dry_run,
        "tier": args.tier,
        "planned": plan,
        "downloaded": downloaded,
        "skipped": skipped,
    }
    if not args.dry_run:
        SYNC_MANIFEST.parent.mkdir(parents=True, exist_ok=True)
        SYNC_MANIFEST.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")

    if args.json or args.dry_run:
        print(json.dumps(out, indent=2))
    else:
        print(json.dumps({"downloaded": len(downloaded), "skipped": len(skipped), "manifest": str(SYNC_MANIFEST.relative_to(ROOT))}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
