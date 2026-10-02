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


def crawl_body(article: dict) -> tuple[str, str]:
    url = article["url"]
    response = requests.get(url, headers={"User-Agent": "Mozilla/5.0 AI-Navigator-MorningEdition/1.0"}, timeout=25)
    if response.ok:
        soup = BeautifulSoup(response.text, "html.parser")
        for node in soup.select("script,style,noscript,header,footer,nav,aside,form,svg"):
            node.decompose()
        nodes = soup.select("article, main, [itemprop='articleBody'], .article-body, .entry-content, .post-content")
        text = max((node.get_text(" ", strip=True) for node in nodes), key=len, default=soup.get_text(" ", strip=True))
        text = re.sub(r"\s+", " ", text).strip()[:14000]
        if len(text) >= 300:
            return text, "article page"
    if "note.com/" in url:
        note_key = url.rstrip("/").split("/")[-1].removeprefix("n/")
        note = requests.get(f"https://note.com/api/v3/notes/{note_key}", timeout=25)
        note.raise_for_status()
        payload = note.json().get("data") or {}
        body = BeautifulSoup(payload.get("body") or "", "html.parser")
        text = re.sub(r"\s+", " ", body.get_text(" ", strip=True)).strip()[:14000]
        if len(text) >= 300:
            return text, "note public API body"
        if payload.get("can_read") is False:
            raise ValueError(f"有料記事のため本文を取得できません ({article.get('id', 'unknown')})")
    response.raise_for_status()
    raise ValueError(f"記事本文を取得できません ({article.get('id', 'unknown')})")


def collect_readable_bodies(ranked_on_topic: list[dict], needed: int = 5) -> tuple[list[dict], list[str], list[dict], list[dict]]:
    """順位順に本文を読み、必要な本数まで集める。1本の失敗では止めない。"""
    readable: list[dict] = []
    bodies: list[str] = []
    crawl: list[dict] = []
    skipped: list[dict] = []
    for article in ranked_on_topic:
        if len(readable) >= needed:
            break
        try:
            body, method = crawl_body(article)
        except (requests.RequestException, ValueError, KeyError) as exc:
            skipped.append({"id": article.get("id"), "url": article.get("url"), "error": type(exc).__name__})
            print(f"記事本文をスキップ: {article.get('id')} ({type(exc).__name__})", file=sys.stderr)
            continue
        readable.append(article)
        bodies.append(body)
        crawl.append({
            "index": len(readable),
            "id": article.get("id"),
            "url": article.get("url"),
            "chars": len(body),
            "method": method,
        })
    return readable, bodies, crawl, skipped


def edition_selection(ranked_on_topic: list[dict], body_articles: list[dict], limit: int = 10) -> list[dict]:
    """掲載は Jev 順を保つ。本文の根拠が上位10本の外なら、その記事を掲載に含める。"""
    selected = list(ranked_on_topic[:limit])
    selected_keys = {str(article.get("id") or article.get("url")) for article in selected}
    missing = [article for article in body_articles if str(article.get("id") or article.get("url")) not in selected_keys]
    if not missing:
        return selected
    merged: list[dict] = []
    seen: set[str] = set()
    for article in body_articles + selected:
        key = str(article.get("id") or article.get("url"))
        if key in seen:
            continue
        seen.add(key)
        merged.append(article)
        if len(merged) >= limit:
            break
    return merged
