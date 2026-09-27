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
        body = BeautifulSoup(note.json().get("data", {}).get("body", ""), "html.parser")
        text = re.sub(r"\s+", " ", body.get_text(" ", strip=True)).strip()[:14000]
        if len(text) >= 300:
            return text, "note public API body"
    response.raise_for_status()
    raise ValueError(f"記事本文を取得できません ({article.get('id', 'unknown')})")


def generate_copy(selected: list[dict], bodies: list[str], refinement: str = "") -> dict:
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        fail("GEMINI_API_KEY が設定されていません")
    prompt = """あなたは中小企業の非エンジニア実務者向け朝刊の編集者です。渡した上位5本の記事本文だけを根拠に文章を作成してください。
最重要: 渡した本文の範囲を超えて書くな。外部知識、推測、一般論、因果関係、予測、助言を追加しない。
JSONのみ。各文章を文単位に分け、各文に根拠記事番号 sources と、本文から逐語で抜いた固有名詞・数値の evidence_terms を付ける。
形式: {"lead_line":{"text":"15〜25字","sources":[1],"evidence_terms":[]},"summary":[{"text":"...","sources":[1],"evidence_terms":[]}],"deep_topics":[{"heading":"◆...","sentences":[{"text":"...","sources":[1],"evidence_terms":[]}]}]}
文字数はPythonのlen相当で数える。要点は350〜450字（7〜9文、各文45〜60字を目安）。「ここまで読めば今日はOK。」はHTML側で加える固定文なので要点には含めない。深掘りは3トピック、合計800〜1200字（各トピック4〜5文を目安）。短すぎないよう文字数を満たすこと。根拠語は本文と完全一致する表記にする。
"""
    body = "\n\n".join(
        f"【記事{i}】\n題名: {a.get('title','')}\n媒体: {a.get('source','')}\n本文:\n{text}"
        for i, (a, text) in enumerate(zip(selected[:5], bodies), 1)
    )
    response = requests.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent?key={key}",
        json={"contents": [{"parts": [{"text": prompt + ("\n\n修正指示: " + refinement if refinement else "") + "\n\n" + body}]}],
              "generationConfig": {"temperature": 0.2, "responseMimeType": "application/json"}}, timeout=120,
    )
    response.raise_for_status()
    return json.loads(response.json()["candidates"][0]["content"]["parts"][0]["text"])


def _sentence(text: str, sources: list[int], evidence_terms: list[str], source_text: str) -> tuple[bool, list[dict]]:
    terms = set(evidence_terms or [])
    terms.update(LATIN_TERM.findall(text))
    terms.update(NUMBER_TERM.findall(text))
    checks = [{"term": t, "found": bool(t) and t.casefold() in source_text.casefold()} for t in sorted(terms) if t.strip()]
    return bool(sources) and all(1 <= n <= 5 for n in sources) and all(item["found"] for item in checks), checks


def verify_and_filter(content: dict, bodies: list[str]) -> tuple[dict, dict]:
    source_text = "\n".join(bodies)
    dropped, checked = [], []
    def retain(item: dict, label: str) -> str:
        text = str(item.get("text", "")).strip()
        ok, terms = _sentence(text, item.get("sources", []), item.get("evidence_terms", []), source_text)
        checked.append({"section": label, "text": text, "terms": terms, "verified": ok})
        if not ok:
            dropped.append({"section": label, "text": text, "unsupported_terms": [t["term"] for t in terms if not t["found"]]})
            return ""
        return text
    lead = retain(content.get("lead_line", {}), "lead_line")
    summary = [s for s in (retain(x, "summary") for x in content.get("summary", [])) if s]
    topics = []
    for index, topic in enumerate(content.get("deep_topics", []), 1):
        sentences = [s for s in (retain(x, f"deep_topics[{index}]") for x in topic.get("sentences", [])) if s]
        if sentences:
            topics.append({"heading": topic.get("heading", ""), "text": "".join(sentences)})
    if not lead or len(topics) != 3 or not summary:
        raise ValueError("照合後に必須の朝刊文章が残りませんでした")
    return {"lead_line": lead, "summary": "".join(summary), "deep_topics": topics}, {
        "model": MODEL, "checked_sentence_count": len(checked), "dropped_sentences": dropped, "checks": checked,
    }


def copy_length_problem(content: dict) -> str | None:
    lead_len = len(content["lead_line"])
    summary_len = len(content["summary"])
    deep_len = sum(len(topic["text"]) for topic in content["deep_topics"])
    issues = []
    if not 15 <= lead_len <= 25: issues.append(f"今日の一言は{lead_len}字（15〜25字に調整）")
    if not 350 <= summary_len <= 450: issues.append(f"要点は{summary_len}字（350〜450字に調整）")
    if not 800 <= deep_len <= 1200: issues.append(f"深掘りは{deep_len}字（800〜1200字に調整）")
    return "。".join(issues) if issues else None


def esc(value: object) -> str:
    return html.escape(str(value or ""), quote=True)


def render_html(target: date, edition: str, candidates: list[dict], selected: list[dict], content: dict, generated_at: str, editions: list[dict]) -> str:
    day_names = "月火水木金土日"
    weekday = day_names[target.weekday()]
    stories = []
    toc = []
    for i, a in enumerate(selected, 1):
        summary = esc(a.get("summary", ""))
        thumb = f'<img class="thumb" src="{esc(a["thumbnail"])}" alt="" loading="lazy">' if a.get("thumbnail") else ""
        source = esc(a.get("source") or urlparse(a["url"]).netloc)
        stories.append(f'<article class="story" id="story-{i}"><div class="story-copy"><p class="story-kicker">ARTICLE {i:02d}</p><h3>{esc(a.get("title"))}</h3><p class="story-summary">{summary}</p><p class="source">{source}</p><a class="read-link" href="{esc(a["url"])}" target="_blank" rel="nofollow noopener">元記事を読む →</a></div>{thumb}</article>')
        toc.append(f'<a href="#story-{i}"><span>{i:02d}</span>{esc(a.get("title"))}</a>')
    topic_html = "".join(f'<article class="topic"><h3>{esc(t["heading"])}</h3><p>{esc(t["text"])}</p></article>' for t in content["deep_topics"])
    week = []
    week_map = {(row.get("date"), row.get("edition")): row for row in editions}
    week_start = target - timedelta(days=target.weekday())
    for day_offset in range(7):
        issue_day = week_start + timedelta(days=day_offset)
        day_text = issue_day.isoformat()
        label = f'{issue_day.month}/{issue_day.day} ({day_names[issue_day.weekday()]})'
        for issue_type in ("am", "pm"):
            row = week_map.get((day_text, issue_type))
            title = "朝刊" if issue_type == "am" else "夕刊"
            this_issue = day_text == target.isoformat() and issue_type == edition
            name = title + ("（この号）" if this_issue else "")
            if row:
                cell = f'<a class="{"current" if this_issue else ""}" href="{esc(issue_day.isoformat())}-{issue_type}.html">{name}</a>'
                count = f'{len(row.get("selectedIds", []))}本'
            else:
                cell = f'<span class="muted">{name}</span>'
                count = "—"
            week.append(f'<div class="week-day"><b>{label}</b>{cell}<span>{count}</span></div>')
    summary = esc(content["summary"])
    time_label = datetime.fromisoformat(generated_at).astimezone(JST).strftime("%H:%M")
    return f'''<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><meta name="color-scheme" content="light"><title>{target.year}年{target.month}月{target.day}日（{weekday}）朝刊｜AI Navigator</title><link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin><link href="https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@400;500;600;700&family=Noto+Serif+JP:wght@500;600;700;800&display=swap" rel="stylesheet"><style>
:root{{--paper:#f7f3e8;--ink:#25231f;--soft:#5c574f;--red:#ff335f;--rule:#d8d0c1;--card:#fffdf7;--serif:"Noto Serif JP","Yu Mincho",serif;--sans:"Noto Sans JP",sans-serif}}*{{box-sizing:border-box}}html{{scroll-behavior:smooth;scroll-padding-top:18px}}body{{margin:0;background:var(--paper);color:var(--ink);font:16px/1.8 var(--sans)}}a{{color:inherit}}.page{{width:min(100% - 32px,680px);margin:auto}}.site-header{{position:fixed;z-index:10;top:0;left:0;right:0;height:58px;display:flex;align-items:center;gap:18px;padding:0 20px;background:#1e2440;color:#f3f2f1;font:14px/1.4 Inter,sans-serif}}.site-logo{{font-weight:700;text-decoration:none}}.site-tabs{{display:flex;gap:18px;margin:auto}}.site-tabs a{{color:#a9b0cf;text-decoration:none}}.site-tabs a.active{{color:#fff}}.site-bottom-nav{{display:none}}.page{{padding-top:76px;padding-bottom:30px}}.masthead{{border-bottom:1px solid var(--ink);padding:14px 0;font-size:12px;letter-spacing:.1em}}.hero{{padding:22px 0 13px}}h1{{font:800 clamp(29px,8vw,43px)/1.28 var(--serif);margin:0 0 10px}}.stats{{margin:0;color:var(--soft);font-size:13px}}.updated{{display:block;color:var(--soft);font-size:12px}}.brief{{margin:12px 0 30px;padding:14px 17px 18px;background:var(--card);border:1px solid var(--rule);border-left:4px solid var(--red)}}.brief-label{{font-size:11px;color:var(--red);font-weight:700}}.brief h2{{font:700 20px/1.55 var(--serif);margin:0 0 8px}}.brief p{{margin:0 0 13px;font-size:16px;line-height:1.8}}.brief-end{{border-top:1px solid var(--rule);padding-top:8px;font-weight:700;font-size:14px}}.section-title{{font:700 22px/1.5 var(--serif);margin:38px 0 12px}}.toc,.week{{border:1px solid var(--rule);background:#fbf8f0;padding:5px 15px}}.toc a{{display:grid;grid-template-columns:34px 1fr;gap:8px;padding:9px 0;border-bottom:1px solid var(--rule);text-decoration:none;font-size:14px;line-height:1.55}}.toc a:last-child{{border:0}}.toc a span{{color:var(--red);font-weight:700}}.deep-head{{display:flex;justify-content:space-between;align-items:baseline;gap:8px}}.deep-head .section-title{{margin-bottom:4px}}.readtime{{font-size:12px;color:var(--soft);white-space:nowrap}}.topic{{padding:12px 0 17px;border-bottom:1px solid var(--rule)}}.topic h3,.story h3{{font:700 18px/1.55 var(--serif);margin:0 0 6px}}.topic p{{margin:0;line-height:1.85}}.story-list{{border-top:1px solid var(--ink)}}.story{{scroll-margin-top:20px;display:flex;gap:12px;padding:16px 0;border-bottom:1px solid var(--rule)}}.story-copy{{min-width:0;flex:1}}.story-kicker{{font-size:10px;color:var(--red);font-weight:700;margin:0}}.story-summary{{font-size:14px;line-height:1.75;color:var(--soft);margin:0 0 6px}}.source{{font-size:11px;color:#777067;margin:0}}.read-link{{display:inline-block;margin-top:5px;font-size:12px;text-decoration-color:var(--red)}}.thumb{{width:78px;height:62px;object-fit:cover;border:1px solid var(--rule);flex:none;margin-top:14px}}.week-day{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:5px;padding:9px 0;border-bottom:1px solid var(--rule);font-size:12px}}.week-day:last-child{{border:0}}.week-day a{{text-decoration:none}}.current{{color:var(--red);font-weight:700}}.muted{{color:#a9a297}}.next{{margin:32px 0;padding:12px 14px;border:1px solid var(--rule);font-size:13px;color:var(--soft)}}footer{{border-top:1px solid var(--ink);padding:18px 0 36px;margin-top:36px;font-size:12px;color:var(--soft)}}footer p{{margin:4px 0}}@media(max-width:768px){{.site-header{{height:52px;padding:0 12px}}.site-tabs{{display:none}}.page{{padding-top:65px;padding-bottom:78px}}.site-bottom-nav{{position:fixed;z-index:11;bottom:0;left:0;right:0;display:flex;height:56px;background:#1e2440}}.site-bottom-nav a{{flex:1;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:3px;color:#6b7299;font:500 10px/1 Inter,sans-serif;text-decoration:none}}.site-bottom-nav a.active{{color:#ff6680}}.nav-icon{{font-size:19px}}.hero{{padding-top:18px}}.brief{{padding:12px 14px 15px}}.section-title{{font-size:20px}}.story{{gap:9px}}.thumb{{width:68px;height:58px}}}}
</style></head><body><header class="site-header"><a class="site-logo" href="../index.html">AI Navigator</a><nav class="site-tabs"><a href="../index.html">🏠 TOP</a><a href="../news.html">📰 ニュース</a><a class="active" href="./{target.isoformat()}-{edition}.html">🌅 朝刊</a><a href="../official.html">📦 リリース</a><a href="../about.html">🛠️ 作り方</a></nav></header><nav class="site-bottom-nav"><a href="../index.html"><span class="nav-icon">🏠</span>TOP</a><a href="../news.html"><span class="nav-icon">📰</span>ニュース</a><a class="active" href="./{target.isoformat()}-{edition}.html"><span class="nav-icon">🌅</span>朝刊</a><a href="../official.html"><span class="nav-icon">📦</span>リリース</a><a href="../about.html"><span class="nav-icon">🛠️</span>作り方</a></nav><main class="page"><div class="masthead">AI NAVIGATOR <span> / MORNING EDITION</span></div><header class="hero"><h1>{target.year}年{target.month}月{target.day}日（{weekday}）朝刊</h1><p class="stats">毎日2回、<b>{len(candidates)}本</b>を集めて、<b>{len(selected)}本</b>を選びました。</p><span class="updated">更新 {time_label}</span></header><section class="brief"><p class="brief-label">30秒でわかる</p><h2>{esc(content['lead_line'])}</h2><p>{summary}</p><div class="brief-end">ここまで読めば今日はOK。</div></section><h2 class="section-title">今日の目次</h2><nav class="toc">{"".join(toc)}</nav><section><div class="deep-head"><h2 class="section-title">読みたい人だけ</h2><span class="readtime">約3分</span></div>{topic_html}</section><section><h2 class="section-title">選んだ記事 {len(selected)}本</h2><div class="story-list">{"".join(stories)}</div></section><section><h2 class="section-title">今週の朝刊・夕刊</h2><div class="week">{"".join(week)}</div></section><aside class="next">次の夕刊は <b>19時ごろ</b> の予定です。</aside><footer><p><a href="../index.html">AI Navigator トップへ</a></p><p>このサイトは非エンジニアがAIで全自動化して作っています。<a href="../about.html">作り方を見る</a></p></footer></main></body></html>'''


def atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def upsert_edition(rows: list[dict], row: dict) -> list[dict]:
    updated = [x for x in rows if not (x.get("date") == row["date"] and x.get("edition") == row["edition"])]
    updated.append(row)
    return sorted(updated, key=lambda x: (x.get("date", ""), x.get("edition", "")), reverse=True)


def generate(articles_path: Path, target: date, edition: str, output_dir: Path) -> dict:
    data = json.loads(articles_path.read_text(encoding="utf-8-sig"))
    candidates = filter_candidates(data.get("articles", []), target, edition)
    ranked = run_jev(candidates)
    selected = [row for row in ranked if row.get("on_topic", 0) >= 0.5][:10]
    if not selected:
        fail("Jevで対象記事を選べませんでした")
    body_rows, crawl = [], []
    for index, article in enumerate(selected[:5], 1):
        try:
            body, method = crawl_body(article)
        except (requests.RequestException, ValueError, KeyError) as exc:
            fail(f"上位5本の記事本文を取得できません: {article.get('id')} ({type(exc).__name__})")
        body_rows.append(body)
        crawl.append({"index": index, "id": article.get("id"), "url": article.get("url"), "chars": len(body), "method": method})
    copy = None
    claim_check = None
    refinement = ""
    gemini_calls = 0
    for _ in range(6):
        try:
            raw_copy = generate_copy(selected, body_rows, refinement)
            gemini_calls += 1
            copy, claim_check = verify_and_filter(raw_copy, body_rows)
            refinement = copy_length_problem(copy) or ""
            if not refinement:
                break
        except (requests.RequestException, KeyError, ValueError, json.JSONDecodeError) as exc:
            fail(f"Gemini文章生成または照合に失敗しました: {type(exc).__name__}: {str(exc)[:160]}")
    if refinement or copy is None or claim_check is None:
        fail("Gemini文章生成の文字数条件を6回以内に満たせませんでした: " + refinement)
    generated_at = datetime.now(JST).isoformat(timespec="seconds")
    edition_rows = []
    editions_path = output_dir / "editions.json"
    if editions_path.exists():
        try:
            edition_rows = json.loads(editions_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            fail("既存の editions.json を読み込めません")
    row = {"date": target.isoformat(), "edition": edition, "url": f"daily/{target.isoformat()}-{edition}.html", "candidateCount": len(candidates), "selectedCount": len(selected), "selectedIds": [x.get("id") for x in selected], "leadLine": copy["lead_line"], "summaryExcerpt": copy["summary"][:140], "generatedAt": generated_at}
    edition_rows = upsert_edition(edition_rows, row)
    page_path = output_dir / f"{target.isoformat()}-{edition}.html"
    html_text = render_html(target, edition, candidates, selected, copy, generated_at, edition_rows)
    page_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_page = page_path.with_suffix(".html.tmp")
    tmp_page.write_text(html_text, encoding="utf-8")
    claim_check.update({"crawl": crawl, "selectedIds": [x.get("id") for x in selected], "gemini_calls": gemini_calls})
    tmp_claim = output_dir / f"{target.isoformat()}-{edition}.claim_check.json.tmp"
    tmp_claim.write_text(json.dumps(claim_check, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_page.replace(page_path)
    tmp_claim.replace(output_dir / f"{target.isoformat()}-{edition}.claim_check.json")
    atomic_json(editions_path, edition_rows)
    latest = edition_rows[0]
    index_html = f'''<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><meta http-equiv="refresh" content="0; url={esc(latest["date"])}-{esc(latest["edition"])}.html"><title>AI Navigator 朝刊・夕刊</title></head><body><p><a href="{esc(latest["date"])}-{esc(latest["edition"])}.html">最新号を読む</a></p></body></html>'''
    (output_dir / "index.html").write_text(index_html, encoding="utf-8")
    return {"page": str(page_path), "editions": str(editions_path), "candidate_count": len(candidates), "selected": selected, "dropped_sentences": claim_check["dropped_sentences"], "generated_at": generated_at, "claim_check": str(output_dir / f"{target.isoformat()}-{edition}.claim_check.json")}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--articles", type=Path, required=True)
    parser.add_argument("--date", type=date.fromisoformat, required=True)
    parser.add_argument("--edition", choices=("am", "pm"), default="am")
    parser.add_argument("--output-dir", type=Path, default=DAILY)
    args = parser.parse_args()
    try:
        result = generate(args.articles, args.date, args.edition, args.output_dir)
    except SystemExit:
        raise
    except Exception as exc:
        fail(f"朝刊を生成できません: {type(exc).__name__}: {str(exc)[:180]}")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
