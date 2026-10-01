#!/usr/bin/env python3
"""Generate a source-checked morning edition from an articles.json snapshot."""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
DAILY = Path(__file__).resolve().parent
RANKER = DAILY / "rank_with_jev.mjs"
MODEL = "gemini-3-flash-preview"
JST = ZoneInfo("Asia/Tokyo")
GTM_HEAD = '''  <!-- Google Tag Manager -->
  <script>(function(w,d,s,l,i){w[l]=w[l]||[];w[l].push({'gtm.start':
  new Date().getTime(),event:'gtm.js'});var f=d.getElementsByTagName(s)[0],
  j=d.createElement(s),dl=l!='dataLayer'?'&l='+l:'';j.async=true;j.src=
  'https://www.googletagmanager.com/gtm.js?id='+i+dl;f.parentNode.insertBefore(j,f);
  })(window,document,'script','dataLayer','GTM-NNQDZVDZ');</script>
  <!-- End Google Tag Manager -->
  <script>
    // GTM移行後もJS側の gtag(...) 呼び出しを生かすためのスタブ。
    // 実体は dataLayer.push なので、GTM がそのまま受け取る。
    // ⚠️ これを消すと app.js の typeof ガードが false になり
    //    select_content / select_item が静かに停止する（JSエラーは出ない）。
    window.dataLayer = window.dataLayer || [];
    function gtag(){dataLayer.push(arguments);}
  </script>'''
GTM_NOSCRIPT = '''  <!-- Google Tag Manager (noscript) -->
  <noscript><iframe src="https://www.googletagmanager.com/ns.html?id=GTM-NNQDZVDZ"
  height="0" width="0" style="display:none;visibility:hidden"></iframe></noscript>
  <!-- End Google Tag Manager (noscript) -->'''
LATIN_TERM = re.compile(r"(?<![A-Za-z])[A-Z][A-Za-z0-9.+#_-]*(?:\s+[A-Z][A-Za-z0-9.+#_-]*)*")
NUMBER_TERM = re.compile(r"\d[\d,]*(?:\.\d+)?\s?(?:%|％|円|ドル|件|本|人|個|倍|年|月|日|時間|分|秒)?")


def fail(message: str) -> "NoReturn":
    print(message.replace("\n", " "), file=sys.stderr)
    raise SystemExit(1)


def filter_candidates(articles: list[dict], target: date, edition: str) -> list[dict]:
    """Keep URL-bearing items added in the requested JST batch and dated within 3 days."""
    candidates = []
    for article in articles:
        added = article.get("addedAt")
        try:
            added_dt = datetime.fromisoformat(str(added).replace("Z", "+00:00"))
            if added_dt.tzinfo is None:
                added_dt = added_dt.replace(tzinfo=JST)
            added_day = added_dt.astimezone(JST).date()
        except (TypeError, ValueError):
            continue
        if added_day != target:
            continue
        hour = added_dt.astimezone(JST).hour
        if (edition == "am" and hour >= 12) or (edition == "pm" and hour < 12):
            continue
        url = str(article.get("url") or "")
        if urlparse(url).scheme not in {"http", "https"} or not urlparse(url).netloc:
            continue
        try:
            published = date.fromisoformat(str(article.get("date", ""))[:10])
        except ValueError:
            continue
        age = (target - published).days
        if not 0 <= age <= 3:
            continue
        candidates.append(article)
    return candidates


def score_candidate(actionable: float, plain: float, needs_coding: float, is_promo: float) -> float:
    return (0.4 * actionable + 0.25 * plain + 0.35 * (1 - needs_coding)) * (1 - 0.5 * is_promo)


def run_jev(candidates: list[dict]) -> list[dict]:
    if not candidates:
        fail("朝刊候補が0件です")
    with tempfile.TemporaryDirectory(prefix="morning-edition-") as temp:
        in_path = Path(temp) / "candidates.json"
        out_path = Path(temp) / "ranked.json"
        in_path.write_text(json.dumps(candidates, ensure_ascii=False), encoding="utf-8")
        result = subprocess.run(
            ["node", str(RANKER), str(in_path), str(out_path)],
            cwd=ROOT, capture_output=True, text=True, timeout=600,
        )
        if result.returncode != 0:
            fail("Jev選定に失敗しました: " + (result.stderr.strip() or result.stdout.strip() or "node error"))
        try:
            ranked = json.loads(out_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            fail(f"Jev選定結果を読めません: {exc}")
    if ranked.get("failed_batches"):
        fail("Jev選定に失敗しました: 1つ以上の評価バッチが失敗")
    return ranked["results"]
