#!/usr/bin/env python3
"""Fetch production data, generate today's (or latest available) morning issue and start a local preview."""
from __future__ import annotations
import argparse
import json
import shutil
import socket
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
import requests

ROOT = Path(__file__).resolve().parents[1]
SCRATCH = ROOT.parent / "scratch" / "2026-09-28_morning_edition"
URL = "https://ai-navigator.dev/articles.json"

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8799)
    args = parser.parse_args()
    SCRATCH.mkdir(parents=True, exist_ok=True)
    articles_path = SCRATCH / "articles.prod.json"
    response = requests.get(URL, timeout=45)
    response.raise_for_status()
    articles_path.write_text(response.text, encoding="utf-8")
    data = response.json()
    today = datetime.now(ZoneInfo("Asia/Tokyo")).date()
    available = set()
    for article in data.get("articles", []):
        try:
            stamp = datetime.fromisoformat(str(article.get("addedAt", "")).replace("Z", "+00:00"))
            if stamp.tzinfo is None: stamp = stamp.replace(tzinfo=ZoneInfo("Asia/Tokyo"))
            if stamp.astimezone(ZoneInfo("Asia/Tokyo")).hour < 12 and article.get("url"):
                available.add(stamp.astimezone(ZoneInfo("Asia/Tokyo")).date().isoformat())
        except ValueError:
            continue
    target = today if today.isoformat() in available else today - timedelta(days=1)
    if target.isoformat() not in available:
        raise SystemExit(f"{target.isoformat()} の朝バッチがありません")
    generation = subprocess.run(
        [sys.executable, str(ROOT / "daily" / "morning_edition.py"), "--articles", str(articles_path), "--date", target.isoformat(), "--edition", "am"],
        cwd=ROOT, capture_output=True, text=True,
    )
    if generation.returncode != 0:
        reason = (generation.stderr.strip() or generation.stdout.strip() or "朝刊生成に失敗しました").replace("\r", " ").replace("\n", " ")[:400]
        print(reason, file=sys.stderr)
        raise SystemExit(generation.returncode)
    if generation.stdout.strip():
        print(generation.stdout.strip())
    site = SCRATCH / "site"
    site.mkdir(parents=True, exist_ok=True)
    for name in ("index.html", "news.html", "official.html", "about.html", "app.js", "official.js", "ai-consult.js", "style.css", "_headers", "_redirects"):
        source = ROOT / name
        if source.is_file(): shutil.copy2(source, site / name)
    shutil.copy2(articles_path, site / "articles.json")
    shutil.copytree(ROOT / "assets", site / "assets", dirs_exist_ok=True)
    shutil.copytree(ROOT / "daily", site / "daily", dirs_exist_ok=True, ignore=shutil.ignore_patterns("*.py", "*.pyc", "*.mjs", "__pycache__"))
    if not (site / "daily" / f"{target.isoformat()}-am.html").exists():
        raise SystemExit("生成号がプレビュー用フォルダにありません")
    pid_file = SCRATCH / "server.pid"
    existing_pid = int(pid_file.read_text(encoding="utf-8")) if pid_file.exists() else None
    with socket.socket() as sock:
        port_in_use = sock.connect_ex(("127.0.0.1", args.port)) == 0
    if port_in_use:
        if not existing_pid:
            raise SystemExit(f"ポート {args.port} は別プロセスが使用中です")
        pid = existing_pid
    else:
        log = (SCRATCH / "server.log").open("w", encoding="utf-8")
        proc = subprocess.Popen([sys.executable, str(ROOT / "daily" / "preview_server.py"), "--root", str(site), "--port", str(args.port)], cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), close_fds=True)
        pid = proc.pid
        pid_file.write_text(str(pid), encoding="utf-8")
    print(json.dumps({"date": target.isoformat(), "url": f"http://127.0.0.1:{args.port}/", "issue": f"http://127.0.0.1:{args.port}/daily/{target.isoformat()}-am", "pid": pid, "site": str(site)}, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
