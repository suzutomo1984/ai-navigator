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
    payload = {"contents": [{"parts": [{"text": prompt + ("\n\n修正指示: " + refinement if refinement else "") + "\n\n" + body}]}],
               "generationConfig": {"temperature": 0.2, "responseMimeType": "application/json"}}
    for attempt in range(2):
        try:
            response = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent?key={key}",
                json=payload, timeout=300,
            )
            break
        except requests.Timeout:
            if attempt == 1:
                raise
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


def issue_rows(editions: list[dict]) -> list[dict]:
    """Return unique, valid issues in newest-first order."""
    rows = {}
    for row in editions:
        issue_date = str(row.get("date", ""))
        issue_type = str(row.get("edition", ""))
        if issue_type not in {"am", "pm"}:
            continue
        try:
            date.fromisoformat(issue_date)
        except ValueError:
            continue
        rows[(issue_date, issue_type)] = row
    return sorted(rows.values(), key=lambda row: (row["date"], row["edition"]), reverse=True)


def issue_title(row: dict) -> str:
    day_names = "月火水木金土日"
    issue_day = date.fromisoformat(row["date"])
    label = "朝刊" if row["edition"] == "am" else "夕刊"
    return f"{issue_day.year}年{issue_day.month}月{issue_day.day}日（{day_names[issue_day.weekday()]}）{label}"


SITE_ORIGIN = "https://ai-navigator.dev"
BRAND = "AI Navigator"
ARCHIVE_CANONICAL = f"{SITE_ORIGIN}/daily/"
ARCHIVE_TITLE = f"AIニュースの朝刊・夕刊バックナンバー｜{BRAND}"
# ブランド名の手前。全角1・半角0.5で数え、検索結果で日付だけが残らない範囲に収める。
TITLE_PRE_BRAND_MAX = 35.0
DESC_MIN = 80
DESC_MAX = 120
SEO_META_RE = re.compile(r"<!-- SEO_META:start -->.*?<!-- SEO_META:end -->", re.DOTALL)
TITLE_RE = re.compile(r"<title>.*?</title>", re.DOTALL)
ISSUE_HREF_RE = re.compile(r'href="(\d{4}-\d{2}-\d{2}-(?:am|pm))\.html(#[^"]*)?"')
ARCHIVE_BODY = "AIニュースの朝刊・夕刊を日付順に並べたバックナンバーです。各号には、その日の30秒要約と、選んだ記事の見出しを掲載しています。"
ARCHIVE_TAIL = "過去の号も、同じ構成のまま読めます。"


def display_width(text: str) -> float:
    """Full-width characters count as 1, ASCII as 0.5."""
    return sum(0.5 if ord(ch) < 128 else 1.0 for ch in text)


def clean_topic(text: str) -> str:
    text = html.unescape(str(text or ""))
    text = re.sub(r"\s+", " ", text).strip()
    stripped = re.sub(r"^(?:【[^】]{1,16}】\s*)+", "", text).strip()
    return stripped or text


def cut_to_width(text: str, limit: float) -> str:
    kept = []
    width = 0.0
    for ch in text:
        char_width = 0.5 if ord(ch) < 128 else 1.0
        if width + char_width > limit:
            break
        kept.append(ch)
        width += char_width
    return "".join(kept).rstrip(" 　、。・｜|—–-:：/／")


def natural_head(text: str, budget: float) -> str:
    for sep in ("｜", "|", "—", "–", "：", ":"):
        if sep not in text:
            continue
        head = text.split(sep, 1)[0].strip(" 　")
        if 8 <= display_width(head) <= budget:
            return head
    return ""


def truncate_topic(text: str, budget: float) -> str:
    marker = "ほか"
    head = cut_to_width(text, budget - display_width(marker))
    if display_width(head) < 8:
        return cut_to_width(text, budget)
    return head + marker


def choose_topic(titles: list[str], lead: str, budget: float) -> str:
    """Prefer the first 目次 title. The 15–25 character headline is the fallback.

    A complete first title wins. If it is too long, keep the clause before a
    separator such as ｜ or ：. The second title is used only when the first
    still does not fit. ほか is the last resort.
    """
    options = []
    for title in titles[:2]:
        cleaned = clean_topic(title)
        if cleaned:
            options.append(cleaned)
    if options and display_width(options[0]) <= budget:
        return options[0]
    if options:
        head = natural_head(options[0], budget)
        if head:
            return head
    for text in options[1:]:
        if display_width(text) <= budget:
            return text
    if options:
        return truncate_topic(options[0], budget)
    lead_clean = clean_topic(lead)
    if not lead_clean:
        return ""
    if display_width(lead_clean) <= budget:
        return lead_clean
    return truncate_topic(lead_clean, budget)


def edition_label(edition: str) -> str:
    return "朝刊" if edition == "am" else "夕刊"


def short_issue_label(issue_day: date, edition: str) -> str:
    return f"{issue_day.month}/{issue_day.day}{edition_label(edition)}"


def build_issue_title(issue_day: date, edition: str, lead: str, titles: list[str]) -> str:
    label = short_issue_label(issue_day, edition)
    suffix = f"｜{label}"
    budget = TITLE_PRE_BRAND_MAX - display_width(suffix)
    topic = choose_topic(titles, lead, budget)
    if not topic:
        return f"{label}｜{BRAND}"
    pre = f"{topic}{suffix}"
    if display_width(pre) > TITLE_PRE_BRAND_MAX:
        topic = truncate_topic(topic, budget)
        pre = f"{topic}{suffix}"
    return f"{pre}｜{BRAND}"


def clamp_description(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= DESC_MAX:
        return text
    window = text[:DESC_MAX]
    period = window.rfind("。")
    if period >= DESC_MIN - 1:
        return window[: period + 1]
    comma = window.rfind("、")
    if comma >= DESC_MIN - 1:
        return window[:comma] + "。"
    return window[: DESC_MAX - 1] + "…"


def dated_issue_fallback(issue_day: date, edition: str) -> str:
    kind = edition_label(edition)
    return (
        f"{issue_day.year}年{issue_day.month}月{issue_day.day}日の{kind}です。"
        "その日のAIニュースから選んだ記事の見出しと、30秒で読める要約を掲載しています。"
        "目次の各項目から、記事ごとの要約へ移動できます。"
    )


def build_issue_description(summary: str, titles: list[str], issue_day: date, edition: str) -> str:
    text = re.sub(r"\s+", " ", (summary or "").replace("ここまで読めば今日はOK。", "")).strip()
    chosen = ""
    for part in re.findall(r"[^。]*。", text):
        part = part.strip()
        if not part:
            continue
        if not chosen:
            chosen = part
        elif len(chosen) + len(part) <= DESC_MAX:
            chosen += part
        else:
            break
        if len(chosen) >= DESC_MIN:
            break
    if len(chosen) > DESC_MAX:
        chosen = clamp_description(chosen)
    if DESC_MIN <= len(chosen) <= DESC_MAX:
        return chosen
    names = [clean_topic(title) for title in titles[:2]]
    names = [name for name in names if name]
    if names:
        listed = "」「".join(names)
        supplement = f"{issue_day.month}月{issue_day.day}日の{edition_label(edition)}では「{listed}」を取り上げています。"
    else:
        supplement = dated_issue_fallback(issue_day, edition)
    merged = f"{chosen}{supplement}" if chosen else supplement
    if len(merged) < DESC_MIN:
        merged += "各記事の要約は、その号のページに掲載しています。"
    return clamp_description(merged)


def schema_datetime(value: str) -> str:
    if not value:
        return ""
    raw = str(value).strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        try:
            return date.fromisoformat(raw[:10]).isoformat()
        except ValueError:
            return ""
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=JST)
    return parsed.isoformat(timespec="seconds")


def issue_canonical(issue_day: date, edition: str) -> str:
    return f"{SITE_ORIGIN}/daily/{issue_day.isoformat()}-{edition}"


def json_ld_script(payload: dict) -> str:
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")
    return f'<script type="application/ld+json">{raw}</script>'


def seo_meta_block(title: str, description: str, canonical: str, og_type: str, payload: dict) -> str:
    return (
        "<!-- SEO_META:start -->"
        f'<meta name="description" content="{esc(description)}">'
        f'<link rel="canonical" href="{esc(canonical)}">'
        f'<meta property="og:title" content="{esc(title)}">'
        f'<meta property="og:description" content="{esc(description)}">'
        f'<meta property="og:url" content="{esc(canonical)}">'
        f'<meta property="og:type" content="{esc(og_type)}">'
        f"{json_ld_script(payload)}"
        "<!-- SEO_META:end -->"
    )


def issue_structured_data(title: str, description: str, canonical: str, batch_at: str, generated_at: str, issue_day: date) -> dict:
    headline = title[: -(len(BRAND) + 1)] if title.endswith(f"｜{BRAND}") else title
    published = schema_datetime(batch_at) or issue_day.isoformat()
    payload = {
        "@context": "https://schema.org",
        "@type": "NewsArticle",
        "headline": headline,
        "datePublished": published,
        "description": description,
        "inLanguage": "ja",
        "mainEntityOfPage": canonical,
        "url": canonical,
        "publisher": {"@type": "Organization", "name": BRAND, "url": f"{SITE_ORIGIN}/"},
    }
    modified = schema_datetime(generated_at)
    if modified:
        payload["dateModified"] = modified
    return payload


def issue_seo_markup(issue_day: date, edition: str, lead: str, summary: str, titles: list[str], batch_at: str = "", generated_at: str = "") -> tuple[str, str]:
    title = build_issue_title(issue_day, edition, lead, titles)
    description = build_issue_description(summary, titles, issue_day, edition)
    canonical = issue_canonical(issue_day, edition)
    payload = issue_structured_data(title, description, canonical, batch_at, generated_at, issue_day)
    return title, seo_meta_block(title, description, canonical, "article", payload)


def archive_description(editions: list[dict]) -> str:
    rows = issue_rows(editions)
    if not rows:
        return ARCHIVE_BODY + ARCHIVE_TAIL
    latest = rows[0]
    issue_day = date.fromisoformat(latest["date"])
    lead = clean_topic(str(latest.get("leadLine") or ""))
    kind = edition_label(str(latest.get("edition") or "am"))
    if lead:
        open_quote, close_quote = ("『", "』") if ("「" in lead or "」" in lead) else ("「", "」")
        prefix = f"最新号は{issue_day.month}月{issue_day.day}日{kind}{open_quote}{lead}{close_quote}。"
    else:
        prefix = f"最新号は{issue_day.month}月{issue_day.day}日{kind}です。"
    return clamp_description(prefix + ARCHIVE_BODY)


def archive_seo_markup(editions: list[dict]) -> tuple[str, str]:
    description = archive_description(editions)
    payload = {
        "@context": "https://schema.org",
        "@type": "CollectionPage",
        "name": "AIニュースの朝刊・夕刊バックナンバー",
        "description": description,
        "url": ARCHIVE_CANONICAL,
        "inLanguage": "ja",
        "isPartOf": {"@type": "WebSite", "name": BRAND, "url": f"{SITE_ORIGIN}/"},
    }
    return ARCHIVE_TITLE, seo_meta_block(ARCHIVE_TITLE, description, ARCHIVE_CANONICAL, "website", payload)


def apply_document_seo(page: str, title: str, block: str) -> str:
    page = SEO_META_RE.sub("", page)
    page = re.sub(r'<meta\b[^>]*\bname\s*=\s*["\']description["\'][^>]*>', "", page, flags=re.IGNORECASE)
    page = re.sub(r'<link\b[^>]*\brel\s*=\s*["\']canonical["\'][^>]*>', "", page, flags=re.IGNORECASE)
    page = re.sub(
        r'<meta\b[^>]*\bproperty\s*=\s*["\']og:(?:title|description|url|type)["\'][^>]*>',
        "",
        page,
        flags=re.IGNORECASE,
    )
    page = re.sub(
        r'<script\b[^>]*\btype\s*=\s*["\']application/ld\+json["\'][^>]*>.*?</script>',
        "",
        page,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not TITLE_RE.search(page):
        raise ValueError("titleがありません")
    return TITLE_RE.sub(f"<title>{esc(title)}</title>{block}", page, count=1)


def rewrite_issue_hrefs(page: str) -> str:
    """Point issue links at the extensionless path listed in the sitemap."""
    return ISSUE_HREF_RE.sub(lambda match: f'href="{match.group(1)}{match.group(2) or ""}"', page)


def extract_issue_copy(page: str) -> dict | None:
    brief = re.search(
        r'<section class="brief">\s*<p class="brief-label">.*?</p>\s*<h2>(.*?)</h2>\s*<p>(.*?)</p>',
        page,
        re.DOTALL,
    )
    if not brief:
        return None
    def visible(fragment: str) -> str:
        return html.unescape(re.sub(r"<[^>]+>", "", fragment)).strip()
    toc = re.search(r'<nav class="toc">(.*?)</nav>', page, re.DOTALL)
    titles = []
    if toc:
        for raw in re.findall(r"<a\b[^>]*>.*?</a>", toc.group(1), re.DOTALL):
            without_num = re.sub(r"<span>.*?</span>", "", raw, count=1, flags=re.DOTALL)
            text = visible(without_num)
            if text:
                titles.append(text)
    return {"lead": visible(brief.group(1)), "summary": visible(brief.group(2)), "titles": titles}


def sync_issue_seo(editions: list[dict], output_dir: Path) -> None:
    """Refresh <head> metadata on already generated issues. Body copy stays as published."""
    rows = {(row["date"], row["edition"]): row for row in issue_rows(editions)}
    for path in sorted(output_dir.glob("*.html")):
        match = re.fullmatch(r"(\d{4}-\d{2}-\d{2})-(am|pm)\.html", path.name)
        if not match:
            continue
        try:
            page = path.read_text(encoding="utf-8")
            updated = rewrite_issue_hrefs(page)
            issue_day = date.fromisoformat(match.group(1))
            edition_name = match.group(2)
            row = rows.get((match.group(1), edition_name), {})
            extracted = extract_issue_copy(updated) or {}
            lead = extracted.get("lead") or str(row.get("leadLine") or "")
            summary = extracted.get("summary") or str(row.get("summaryExcerpt") or "")
            titles = list(extracted.get("titles") or [])
            if lead or summary or titles:
                seo_title, block = issue_seo_markup(
                    issue_day,
                    edition_name,
                    lead,
                    summary,
                    titles,
                    str(row.get("batchAt") or ""),
                    str(row.get("generatedAt") or ""),
                )
                updated = apply_document_seo(updated, seo_title, block)
            if updated != page:
                path.write_text(updated, encoding="utf-8")
        except (OSError, ValueError) as exc:
            print(f"朝刊SEOの更新をスキップ: {path.name} ({exc})", file=sys.stderr)


def render_issue_navigation(current: dict, editions: list[dict]) -> str:
    """Render previous and next issue links as crawlable static HTML."""
    rows = issue_rows(editions)
    keys = [(row["date"], row["edition"]) for row in rows]
    current_key = (current["date"], current["edition"])
    if current_key not in keys:
        return ""
    index = keys.index(current_key)
    previous = rows[index + 1] if index + 1 < len(rows) else None
    following = rows[index - 1] if index > 0 else None
    links = []
    if previous:
        links.append(f'<a class="issue-nav-link" href="{esc(previous["date"])}-{esc(previous["edition"])}"><span>← 前の号</span><small>{esc(issue_title(previous))}</small></a>')
    if following:
        links.append(f'<a class="issue-nav-link issue-nav-link--next" href="{esc(following["date"])}-{esc(following["edition"])}"><span>次の号 →</span><small>{esc(issue_title(following))}</small></a>')
    if not links:
        return ""
    return """<!-- EDITION_NAV:start -->
<style>.issue-nav{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin:34px 0 10px;padding-top:18px;border-top:1px solid var(--rule)}.issue-nav-link{display:flex;flex-direction:column;gap:3px;padding:12px 14px;border:1px solid var(--rule);text-decoration:none;color:var(--ink)}.issue-nav-link span{font-weight:700;color:var(--brand-red)}.issue-nav-link small{font-size:11px;color:var(--ink-muted)}.issue-nav-link--next{text-align:right;grid-column:2}.issue-nav-link:hover{border-color:var(--brand-red)}@media(max-width:520px){.issue-nav{gap:8px}.issue-nav-link{padding:10px}.issue-nav-link small{font-size:10px}}</style>
<nav class="issue-nav" aria-label="号を移動">""" + "".join(links) + "</nav>\n<!-- EDITION_NAV:end -->"


def sync_issue_navigation(editions: list[dict], output_dir: Path) -> None:
    """Refresh navigation and add GTM to every already-generated issue page."""
    markers = re.compile(r"<!-- EDITION_NAV:start -->.*?<!-- EDITION_NAV:end -->", re.DOTALL)
    for row in issue_rows(editions):
        page_path = output_dir / f'{row["date"]}-{row["edition"]}.html'
        if not page_path.is_file():
            continue
        page = page_path.read_text(encoding="utf-8")
        navigation = render_issue_navigation(row, editions)
        if markers.search(page):
            updated = markers.sub(lambda _: navigation, page)
        elif navigation:
            footer = re.search(r"<footer\b", page, re.IGNORECASE)
            position = footer.start() if footer else page.lower().rfind("</body>")
            if position < 0:
                raise ValueError(f"号ナビゲーションを挿入できません: {page_path}")
            updated = page[:position] + navigation + page[position:]
        else:
            updated = page
        updated = ensure_issue_gtm(updated, page_path)
        if updated != page:
            page_path.write_text(updated, encoding="utf-8")


def ensure_issue_gtm(page: str, page_path: Path) -> str:
    """Add the shared GTM snippets to an existing issue page once."""
    if "GTM-NNQDZVDZ" in page:
        return page

    color_scheme = re.search(
        r'<meta\b(?=[^>]*\bname\s*=\s*["\']color-scheme["\'])[^>]*>',
        page,
        re.IGNORECASE,
    )
    if color_scheme:
        head_position = color_scheme.end()
    else:
        head_close = re.search(r"</head\s*>", page, re.IGNORECASE)
        if not head_close:
            raise ValueError(f"GTMを挿入できるheadがありません: {page_path}")
        head_position = head_close.start()

    body_open = re.search(r"<body\b[^>]*>", page, re.IGNORECASE)
    if not body_open:
        raise ValueError(f"GTMを挿入できるbodyがありません: {page_path}")

    updated = page[:head_position] + GTM_HEAD + page[head_position:]
    body_open = re.search(r"<body\b[^>]*>", updated, re.IGNORECASE)
    assert body_open is not None
    body_position = body_open.end()
    return updated[:body_position] + GTM_NOSCRIPT + updated[body_position:]


def render_archive_html(editions: list[dict]) -> str:
    """Render the back-issue list as a static, newest-first page."""
    cards = []
    for index, row in enumerate(issue_rows(editions)):
        issue_type = "朝刊" if row["edition"] == "am" else "夕刊"
        title = issue_title(row)
        href = f'{esc(row["date"])}-{esc(row["edition"])}'
        lead = esc(row.get("leadLine") or title)
        excerpt = esc(row.get("summaryExcerpt", ""))
        badge = '<span class="archive-latest">最新号</span>' if index == 0 else ""
        latest_class = " archive-card--latest" if index == 0 else ""
        cards.append(f'<article class="archive-card{latest_class}"><div class="archive-meta">{badge}<span>{esc(title)}</span><span class="archive-kind">{issue_type}</span></div><h2><a href="{href}">{lead}</a></h2><p>{excerpt}</p><a class="archive-read" href="{href}">この号を読む →</a></article>')
    empty = '<p class="archive-empty">朝刊を準備しています。</p>' if not cards else ""
    archive_title, archive_block = archive_seo_markup(editions)
    return f'''<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><meta name="color-scheme" content="light">{GTM_HEAD}<title>{esc(archive_title)}</title>{archive_block}<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin><link href="https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@400;500;600;700&family=Noto+Serif+JP:wght@500;600;700;800&display=swap" rel="stylesheet"><link rel="stylesheet" href="../style.css"><style>
.daily-archive{{width:min(100% - 32px,760px);margin:0 auto;padding:78px 0 40px;color:var(--ink)}}.archive-masthead{{border-bottom:1px solid var(--ink);padding:12px 0;font-size:11px;letter-spacing:.12em}}.archive-heading{{padding:24px 0 8px}}.archive-heading p{{margin:0;color:var(--ink-muted);font-size:14px}}.archive-heading h1{{font:800 clamp(30px,7vw,42px)/1.3 "Noto Serif JP","Yu Mincho",serif;margin:0 0 8px}}.archive-list{{display:grid;gap:14px;margin-top:22px}}.archive-card{{padding:18px 20px;border:1px solid var(--rule);background:var(--paper)}}.archive-card--latest{{border-left:4px solid var(--brand-red);padding-left:17px}}.archive-meta{{display:flex;align-items:center;gap:9px;flex-wrap:wrap;font-size:12px;color:var(--ink-muted)}}.archive-latest{{padding:2px 8px;background:var(--brand-red);color:var(--paper);font-weight:700}}.archive-kind{{padding-left:9px;border-left:1px solid var(--rule-strong)}}.archive-card h2{{font:700 clamp(19px,4vw,25px)/1.5 "Noto Serif JP","Yu Mincho",serif;margin:8px 0}}.archive-card h2 a{{text-decoration:none}}.archive-card h2 a:hover,.archive-read:hover{{color:var(--brand-red)}}.archive-card p{{margin:0 0 12px;color:var(--ink-muted);font-size:14px;line-height:1.8}}.archive-read{{display:inline-flex;font-size:13px;font-weight:700;color:var(--brand-red);text-decoration:none}}.archive-empty{{padding:24px 0;color:var(--ink-muted)}}.archive-footer{{width:min(100% - 32px,760px);margin:10px auto 0;padding:18px 0 38px;border-top:1px solid var(--ink);font-size:12px;color:var(--ink-muted)}}.archive-footer-links{{display:flex;gap:16px;flex-wrap:wrap;margin-top:8px}}.archive-footer a{{color:inherit}}@media(max-width:768px){{.daily-archive{{padding-top:66px;padding-bottom:24px}}.archive-card{{padding:15px}}.archive-card--latest{{padding-left:12px}}}}
</style></head><body>{GTM_NOSCRIPT}<header id="header"><a href="/" id="logo"><span id="logo-icon">Ai</span><span id="logo-group"><span id="logo-text">AI Navigator</span><span id="logo-tagline">AIニュースを、現場の言葉に。</span></span></a><nav id="tabbar"><a class="tab-btn" href="/">🏠 TOP</a><a class="tab-btn" href="/news">📰 AIニュース</a><a class="tab-btn active" href="/daily/">🌅 朝刊</a><a class="tab-btn" href="/official">📦 リリースノート</a><a class="tab-btn" href="/about">🛠️ 作り方</a></nav><span class="daily-header-spacer"></span></header><nav id="bottom-nav"><a class="bnav-item" href="/"><span class="bnav-icon">🏠</span><span class="bnav-label">TOP</span></a><a class="bnav-item" href="/news"><span class="bnav-icon">📰</span><span class="bnav-label">ニュース</span></a><a class="bnav-item active" href="/daily/"><span class="bnav-icon">🌅</span><span class="bnav-label">朝刊</span></a><a class="bnav-item" href="/official"><span class="bnav-icon">📦</span><span class="bnav-label">リリース</span></a><a class="bnav-item" href="/about"><span class="bnav-icon">🛠️</span><span class="bnav-label">作り方</span></a></nav><main class="daily-archive"><div class="archive-masthead">AI NAVIGATOR <span> / EDITION ARCHIVE</span></div><header class="archive-heading"><h1>朝刊・夕刊の一覧</h1><p>新しい号から順に掲載しています。</p></header><section class="archive-list" aria-label="朝刊・夕刊バックナンバー">{"".join(cards)}{empty}</section></main><footer class="archive-footer"><a href="/" class="footer-brand">AI Navigator</a><p>AIニュースを、現場の言葉に。</p><nav class="archive-footer-links"><a href="/">TOP</a><a href="/news">AIニュース</a><a href="/daily/">朝刊・夕刊</a><a href="/official">リリースノート</a><a href="/about">作り方</a></nav></footer></body></html>'''


def render_html(target: date, edition: str, candidates: list[dict], selected: list[dict], content: dict, batch_at: str, editions: list[dict], generated_at: str = "") -> str:
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
    week_start = target - timedelta(days=target.weekday())
    week_end = week_start + timedelta(days=6)
    existing_mornings = sorted(
        (row for row in editions if row.get("edition") == "am" and week_start.isoformat() <= row.get("date", "") <= week_end.isoformat()),
        key=lambda row: row["date"],
    )
    for row in existing_mornings:
        issue_day = date.fromisoformat(row["date"])
        this_issue = issue_day == target and edition == "am"
        label = f'{issue_day.month}/{issue_day.day} ({day_names[issue_day.weekday()]})'
        name = "朝刊（この号）" if this_issue else "朝刊"
        cell = f'<a class="{"current" if this_issue else ""}" href="{esc(issue_day.isoformat())}-am">{name}</a>'
        count = f'{row.get("selectedCount", len(row.get("selectedIds", [])))}本'
        week.append(f'<div class="week-day"><b>{label}</b>{cell}<span>{count}</span></div>')
    summary = esc(content["summary"])
    time_label = datetime.fromisoformat(batch_at).astimezone(JST).strftime("%H:%M") if batch_at else ""
    seo_title, seo_block = issue_seo_markup(
        target, edition, str(content.get("lead_line") or ""), str(content.get("summary") or ""),
        [str(article.get("title") or "") for article in selected], batch_at, generated_at,
    )
    return f'''<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><meta name="color-scheme" content="light">{GTM_HEAD}<title>{esc(seo_title)}</title>{seo_block}<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin><link href="https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@400;500;600;700&family=Noto+Serif+JP:wght@500;600;700;800&display=swap" rel="stylesheet"><style>
:root{{--soft:var(--ink-muted);--red:var(--brand-red);--card:var(--paper);--serif:"Noto Serif JP","Yu Mincho",serif;--sans:"Noto Sans JP",sans-serif}}*{{box-sizing:border-box}}html{{scroll-behavior:smooth;scroll-padding-top:18px}}body{{margin:0;background:var(--paper);color:var(--ink);font:16px/1.8 var(--sans)}}a{{color:inherit}}.page{{width:min(100% - 32px,680px);margin:auto}}.site-header{{position:fixed;z-index:10;top:0;left:0;right:0;height:58px;display:flex;align-items:center;gap:18px;padding:0 20px;background:var(--paper);color:var(--ink);font:14px/1.4 Inter,sans-serif}}.site-logo{{font-weight:700;text-decoration:none}}.site-tabs{{display:flex;gap:18px;margin:auto}}.site-tabs a{{color:var(--ink-muted);text-decoration:none}}.site-tabs a.active{{color:var(--brand-red)}}.site-bottom-nav{{display:none}}.page{{padding-top:76px;padding-bottom:30px}}.masthead{{border-bottom:1px solid var(--ink);padding:14px 0;font-size:12px;letter-spacing:.1em}}.hero{{padding:22px 0 13px}}h1{{font:800 clamp(29px,8vw,43px)/1.28 var(--serif);margin:0 0 10px}}.stats{{margin:0;color:var(--soft);font-size:13px}}.updated{{display:block;color:var(--soft);font-size:12px}}.brief{{margin:12px 0 30px;padding:14px 17px 18px;background:var(--card);border:1px solid var(--rule);border-left:4px solid var(--red)}}.brief-label{{font-size:11px;color:var(--red);font-weight:700}}.brief h2{{font:700 20px/1.55 var(--serif);margin:0 0 8px}}.brief p{{margin:0 0 13px;font-size:16px;line-height:1.8}}.brief-end{{border-top:1px solid var(--rule);padding-top:8px;font-weight:700;font-size:14px}}.section-title{{font:700 22px/1.5 var(--serif);margin:38px 0 12px}}.toc,.week{{border:1px solid var(--rule);background:var(--paper);padding:5px 15px}}.toc a{{display:grid;grid-template-columns:34px 1fr;gap:8px;padding:9px 0;border-bottom:1px solid var(--rule);text-decoration:none;font-size:14px;line-height:1.55}}.toc a:last-child{{border:0}}.toc a span{{color:var(--red);font-weight:700}}.deep-head{{display:flex;justify-content:space-between;align-items:baseline;gap:8px}}.deep-head .section-title{{margin-bottom:4px}}.readtime{{font-size:12px;color:var(--soft);white-space:nowrap}}.topic{{padding:12px 0 17px;border-bottom:1px solid var(--rule)}}.topic h3,.story h3{{font:700 18px/1.55 var(--serif);margin:0 0 6px}}.topic p{{margin:0;line-height:1.85}}.story-list{{border-top:1px solid var(--ink)}}.story{{scroll-margin-top:20px;display:flex;gap:12px;padding:16px 0;border-bottom:1px solid var(--rule)}}.story-copy{{min-width:0;flex:1}}.story-kicker{{font-size:10px;color:var(--red);font-weight:700;margin:0}}.story-summary{{font-size:14px;line-height:1.75;color:var(--soft);margin:0 0 6px}}.source{{font-size:11px;color:var(--ink-soft);margin:0}}.read-link{{display:inline-block;margin-top:5px;font-size:12px;text-decoration-color:var(--red)}}.thumb{{width:78px;height:62px;object-fit:cover;border:1px solid var(--rule);flex:none;margin-top:14px}}.week-day{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:5px;padding:9px 0;border-bottom:1px solid var(--rule);font-size:12px}}.week-day:last-child{{border:0}}.week-day a{{text-decoration:none}}.current{{color:var(--red);font-weight:700}}.muted{{color:var(--ink-muted)}}.next{{margin:32px 0;padding:12px 14px;border:1px solid var(--rule);font-size:13px;color:var(--soft)}}footer{{border-top:1px solid var(--ink);padding:18px 0 36px;margin-top:36px;font-size:12px;color:var(--soft)}}footer p{{margin:4px 0}}@media(max-width:768px){{.site-header{{height:52px;padding:0 12px}}.site-tabs{{display:none}}.page{{padding-top:65px;padding-bottom:78px}}.site-bottom-nav{{position:fixed;z-index:11;bottom:0;left:0;right:0;display:flex;height:56px;background:var(--paper)}}.site-bottom-nav a{{flex:1;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:3px;color:var(--ink-muted);font:500 10px/1 Inter,sans-serif;text-decoration:none}}.site-bottom-nav a.active{{color:var(--brand-red)}}.nav-icon{{font-size:19px}}.hero{{padding-top:18px}}.brief{{padding:12px 14px 15px}}.section-title{{font-size:20px}}.story{{gap:9px}}.thumb{{width:68px;height:58px}}}}
</style><link rel="stylesheet" href="../style.css"></head><body>{GTM_NOSCRIPT}<header id="header"><a href="../index.html" id="logo"><span id="logo-icon">Ai</span><span id="logo-group"><span id="logo-text">AI Navigator</span><span id="logo-tagline">AIニュースを、現場の言葉に。</span></span></a><nav id="tabbar"><a class="tab-btn" href="../index.html">🏠 TOP</a><a class="tab-btn" href="../news.html">📰 AIニュース</a><a class="tab-btn active" href="../daily/">🌅 朝刊</a><a class="tab-btn" href="../official.html">📦 リリースノート</a><a class="tab-btn" href="../about.html">🛠️ 作り方</a></nav><span class="daily-header-spacer"></span></header><nav id="bottom-nav"><a class="bnav-item" href="../index.html"><span class="bnav-icon">🏠</span><span class="bnav-label">TOP</span></a><a class="bnav-item" href="../news.html"><span class="bnav-icon">📰</span><span class="bnav-label">ニュース</span></a><a class="bnav-item active" href="../daily/"><span class="bnav-icon">🌅</span><span class="bnav-label">朝刊</span></a><a class="bnav-item" href="../official.html"><span class="bnav-icon">📦</span><span class="bnav-label">リリース</span></a><a class="bnav-item" href="../about.html"><span class="bnav-icon">🛠️</span><span class="bnav-label">作り方</span></a></nav><main class="page"><div class="masthead">AI NAVIGATOR <span> / MORNING EDITION</span></div><header class="hero"><h1>{target.year}年{target.month}月{target.day}日（{weekday}）朝刊</h1><p class="stats">毎日2回、<b>{len(candidates)}本</b>を集めて、<b>{len(selected)}本</b>を選びました。</p><span class="updated">更新 {time_label}</span></header><section class="brief"><p class="brief-label">30秒でわかる</p><h2>{esc(content['lead_line'])}</h2><p>{summary}</p><div class="brief-end">ここまで読めば今日はOK。</div></section><h2 class="section-title">今日の目次</h2><nav class="toc">{"".join(toc)}</nav><section><div class="deep-head"><h2 class="section-title">読みたい人だけ</h2><span class="readtime">約3分</span></div>{topic_html}</section><section><h2 class="section-title">選んだ記事 {len(selected)}本</h2><div class="story-list">{"".join(stories)}</div></section><section><h2 class="section-title">今週の朝刊</h2><div class="week">{"".join(week)}</div></section><aside class="next">次の朝刊は <b>明朝8時ごろ</b> の予定です。</aside><footer><p><a href="../index.html">AI Navigator トップへ</a></p><p>このサイトは非エンジニアがAIで全自動化して作っています。<a href="../about.html">作り方を見る</a></p></footer></main></body></html>'''


def atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def sns_post_payload(target: date, edition: str, content: dict) -> dict:
    """Expose only verified copy fields needed by the separate social post."""
    return {
        "date": target.isoformat(),
        "lead_line": content["lead_line"],
        "summary": content["summary"],
        "deep_topics": [
            {"heading": topic["heading"]}
            for topic in content["deep_topics"]
        ],
        "url": f"https://ai-navigator.dev/daily/{target.isoformat()}-{edition}",
    }


def upsert_edition(rows: list[dict], row: dict) -> list[dict]:
    updated = [x for x in rows if not (x.get("date") == row["date"] and x.get("edition") == row["edition"])]
    updated.append(row)
    return sorted(updated, key=lambda x: (x.get("date", ""), x.get("edition", "")), reverse=True)


def generate(articles_path: Path, target: date, edition: str, output_dir: Path) -> dict:
    data = json.loads(articles_path.read_text(encoding="utf-8-sig"))
    candidates = filter_candidates(data.get("articles", []), target, edition)
    ranked = run_jev(candidates)
    ranked_on_topic = [row for row in ranked if row.get("on_topic", 0) >= 0.5]
    if not ranked_on_topic:
        fail("Jevで対象記事を選べませんでした")
    body_articles, body_rows, crawl, skipped = collect_readable_bodies(ranked_on_topic, 5)
    if len(body_articles) < 5:
        failed = ", ".join(str(item.get("id")) for item in skipped) or "なし"
        fail(
            f"本文を取得できた記事が{len(body_articles)}本で、朝刊に必要な5本に足りません"
            f"（取得できなかった記事: {failed}）"
        )
    selected = edition_selection(ranked_on_topic, body_articles)
    copy = None
    claim_check = None
    refinement = ""
    gemini_calls = 0
    for _ in range(6):
        try:
            raw_copy = generate_copy(body_articles, body_rows, refinement)
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
    batch_at = data.get("latestBatchAt", "")
    row = {"date": target.isoformat(), "edition": edition, "url": f"daily/{target.isoformat()}-{edition}", "candidateCount": len(candidates), "selectedCount": len(selected), "selectedIds": [x.get("id") for x in selected], "leadLine": copy["lead_line"], "summaryExcerpt": copy["summary"][:140], "batchAt": batch_at, "generatedAt": generated_at}
    edition_rows = upsert_edition(edition_rows, row)
    page_path = output_dir / f"{target.isoformat()}-{edition}.html"
    html_text = render_html(target, edition, candidates, selected, copy, batch_at, edition_rows, generated_at)
    page_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_page = page_path.with_suffix(".html.tmp")
    tmp_page.write_text(html_text, encoding="utf-8")
    claim_check.update({
        "crawl": crawl,
        "skipped_bodies": skipped,
        "body_source_ids": [x.get("id") for x in body_articles],
        "selectedIds": [x.get("id") for x in selected],
        "gemini_calls": gemini_calls,
    })
    tmp_claim = output_dir / f"{target.isoformat()}-{edition}.claim_check.json.tmp"
    tmp_claim.write_text(json.dumps(claim_check, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_page.replace(page_path)
    tmp_claim.replace(output_dir / f"{target.isoformat()}-{edition}.claim_check.json")
    if edition == "am":
        atomic_json(
            output_dir / f"{target.isoformat()}-{edition}.sns.json",
            sns_post_payload(target, edition, copy),
        )
    atomic_json(editions_path, edition_rows)
    (output_dir / "index.html").write_text(render_archive_html(edition_rows), encoding="utf-8")
    sync_issue_navigation(edition_rows, output_dir)
    sync_issue_seo(edition_rows, output_dir)
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))  # 直接実行時は daily/ しか import パスに無い
    from parse_news import generate_sitemap
    generate_sitemap(editions_path=editions_path)
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
