"""
AI NEWS HUB パーサー
自動ニュース配信/ フォルダのMDファイルを articles.json に変換する
"""

import io
import json
import os
import re
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

# ============================================================
# 設定
# ============================================================

JST = timezone(timedelta(hours=9))
VAULT_ROOT = Path(__file__).parent.parent
NEWS_DIR = VAULT_ROOT / "自動ニュース配信"
OUTPUT_FILE = Path(__file__).parent / "articles.json"
AUDIT_FILE = Path(__file__).parent / "audit_report.txt"
# SEO基礎工事の出力先と公開URL（作品として正しく存在するための自動生成物）
SITEMAP_FILE = Path(__file__).parent / "sitemap.xml"
ROBOTS_FILE = Path(__file__).parent / "robots.txt"
INDEX_FILE = Path(__file__).parent / "index.html"
ABOUT_FILE = Path(__file__).parent / "about.html"
BASE_URL = "https://ai-news-eev.pages.dev"

# 記事データからは算出できない運用方針の固定値。
# トップの指標バー／数字グリッド（および about.html）は必ずここから生成し、
# HTMLへ同じ値を重複して直書きしない。
TOP_STATS_FIXED = (
    {
        "value": "1日2回",
        "unit": "",
        "label": "更新頻度",
        "about_label": "更新頻度（全自動）",
        "detail": "JST 5:45 / 15:45",
    },
    {"value": "0", "unit": "分/日", "label": "人の運用作業", "detail": ""},
    {"value": "0", "unit": "円/月", "label": "運営コスト", "detail": ""},
    {"value": "ほぼ0", "unit": "行", "label": "手書きしたコード", "detail": ""},
)

# 基準日（直近7日ボーナス判定用）
NOW = datetime.now(JST)
SEVEN_DAYS_AGO = (NOW - timedelta(days=7)).strftime("%Y-%m-%d")

# カテゴリ正規化マッピング（優先順位順）
CATEGORY_MAP = [
    ("official",        "リリースノート",    "📦", ["📦", "リリースノート", "公式リリース", "AI企業アップデート"]),
    ("sales-marketing", "営業・マーケ",      "📈", ["📈", "営業", "マーケ", "SEO", "広告", "SNS", "集客", "CRM", "Webマーケティング"]),
    ("back-office",     "経理・総務・管理",  "📋", ["📋", "経理", "総務", "人事", "HR", "採用", "法務", "バックオフィス", "会計"]),
    ("productivity",    "業務効率化",        "⚡", ["⚡", "業務効率化", "DX", "時短", "自動化", "ノーコード", "作業効率"]),
    ("strategy",        "経営・戦略",        "🏢", ["🏢", "経営", "戦略", "AI導入", "コスト削減", "投資", "ビジネスモデル", "新規事業", "💡", "トレンド", "教養", "動向", "解説", "入門", "まとめ"]),
    ("info-mgmt",       "情報管理・ナレッジ","🧠", ["🧠", "知識管理", "情報整理", "ナレッジ", "ドキュメント", "社内共有", "Obsidian", "PKM"]),
    ("ai-tech",         "AI技術・ツール",    "🔧", ["🔧", "AI技術", "AIツール", "エージェント", "MCP", "LLM", "モデル", "API"]),
    ("side-business",   "副業・フリーランス","💰", ["💰", "副業", "フリーランス", "複業", "個人開発", "案件獲得"]),
]

# スキップと見なす固定セクションのキーワード
SKIP_SECTIONS = ["今日のサマリー", "GitHub Trending", "その他の注目ニュース", "収集ソース"]

# リリースノート判定リスト（isOfficial: True をセットするソース名）
# 2026-06-27 再設計: 公式ブログ（読み物）はここから除外し、用途カテゴリへ振り分ける。
# このリストはツールの更新通知（リリースノート）のみ。category="official"（ラベル=リリースノート）に集約する。
OFFICIAL_SOURCES = [
    "Claude Code Releases",
    "Anthropic SDK Releases",
    "OpenAI SDK Releases",
    "Google GenAI SDK Releases",
    "Anthropic TypeScript SDK Releases",
    "OpenAI Node.js SDK Releases",
    "MCP Specification Releases",
    "MCP Python SDK Releases",
    "LangChain Releases",
    "LlamaIndex Releases",
    "Ollama Releases",
    "vLLM Releases",
    "LiteLLM Releases",
    "CrewAI Releases",
    "Dify Releases",
    "Flowise Releases",
    "Gemini CLI Releases",
    "Codex CLI Releases",
]

# 公式ブログ（読み物）ソース。isOfficial=False とし、内容に応じて用途カテゴリへ振り分ける対象。
# 既存データのルールベース再振り分け・分類プロンプトの判定に使う。
OFFICIAL_BLOG_SOURCES = [
    "OpenAI Blog",
    "Google AI Blog",
    "Google DeepMind Blog",
    "Gemini Blog",
    "Microsoft Foundry Blog",
    "Hugging Face Blog",
    "Anthropic News",
    "Anthropic Research",
    "Claude News",
]

# 要約生成スキップ判定（ファイルがほぼ空）
SKIP_THRESHOLD = 200  # バイト



# ============================================================
# カテゴリ正規化
# ============================================================

def normalize_category(h2_text: str) -> tuple[str, str, str]:
    """H2カテゴリ名を正規化ID・ラベル・絵文字に変換する"""
    # サブタイトル（/ 以降）を除去してチェック
    base = h2_text.split("/")[0].strip()

    for cat_id, label, emoji, keywords in CATEGORY_MAP:
        for kw in keywords:
            if kw in base:
                return cat_id, label, emoji

    # フォールバック: その他
    return "other", "その他", "📰"


def is_skip_section(h2_text: str) -> bool:
    """固定セクション（サマリー等）かどうか判定"""
    for skip in SKIP_SECTIONS:
        if skip in h2_text:
            return True
    return False


# ============================================================
# テックニュース.md パーサー
# ============================================================

def parse_tech_news(filepath: Path, date_str: str) -> list[dict]:
    """テックニュースMDから記事リストを抽出する"""
    content = filepath.read_text(encoding="utf-8")
    articles = []

    current_category_id = "other"
    current_category_label = "その他"
    current_category_emoji = "📰"
    current_section = "main"
    article_num = 0

    lines = content.split("\n")
    i = 0

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # H2: カテゴリ判定
        h2_match = re.match(r"^##\s+(.+)", stripped)
        if h2_match and not stripped.startswith("###"):
            h2_text = h2_match.group(1).strip()

            if is_skip_section(h2_text):
                # 固定セクションはスキップ（Trendingは別処理）
                if "Trending" in h2_text:
                    current_section = "trending"
                elif "その他" in h2_text:
                    current_section = "other_news"
                elif "収集ソース" in h2_text:
                    current_section = "sources"
                else:
                    current_section = "skip"
            else:
                current_section = "main"
                cat_id, cat_label, cat_emoji = normalize_category(h2_text)
                current_category_id = cat_id
                current_category_label = cat_label
                current_category_emoji = cat_emoji

            i += 1
            continue

        # H3: 番号付き記事（### N. タイトル）
        art_match = re.match(r"^###\s+(\d+)\.\s+(.+)", stripped)
        if art_match and current_section == "main":
            title = art_match.group(2).strip()
            # タイトルから Markdown リンクを除去
            title = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", title)
            # 絵文字タイトルヘッダーを除去（例: 💎 今日のイチオシ）
            if re.match(r"^[^\w\s].*", title) and len(title) < 20:
                i += 1
                continue

            source = ""
            url = ""
            summary = ""

            j = i + 1
            while j < len(lines) and not lines[j].strip().startswith("##"):
                sline = lines[j].strip()

                # ソース行: - ソース: [名前](URL)
                src_match = re.match(r"^-\s*ソース:\s*\[(.+?)\]\((.+?)\)", sline)
                if src_match:
                    source = src_match.group(1)
                    url = src_match.group(2)

                # 要約行: - 要約・ポイント: テキスト
                sum_match = re.match(r"^-\s*(?:要約・ポイント|要約|ポイント):\s*(.+)", sline)
                if sum_match:
                    summary = sum_match.group(1)

                j += 1

            is_official = source in OFFICIAL_SOURCES
            # カテゴリ決定（2026-06-28 「公式」再設計）。
            # - リリースノート枠（category="official", ラベル=リリースノート）に入れて良いのは
            #   OFFICIAL_SOURCES（ツールの更新通知）の記事だけ。
            # - 公式ブログ（OFFICIAL_BLOG_SOURCES）や一般記事（Zenn/ITmedia等）が、過去mdで
            #   「📢 公式リリース」セクションに置かれていた名残で current_category_id="official" に
            #   正規化されることがあるが、それは誤り。リリースノート枠から弾いて用途カテゴリへ戻す。
            #   用途カテゴリが判別できない（official落ち）ものは一律 ai-tech にフォールバック。
            if is_official:
                category = "official"
            elif current_category_id == "official":
                # OFFICIAL_SOURCES以外がリリースノート枠に落ちたら再振り分け
                category = "ai-tech"
            else:
                category = current_category_id
            article_num += 1
            articles.append({
                "id": f"{date_str}_{article_num}",
                "date": date_str,
                "title": title,
                "url": url,
                "source": source,
                "category": category,
                "summary": summary,
                "section": "main",
                "isPick": False,
                "pickPriority": None,
                "rankingTier": 3,
                "rankingScore": 0,
                "isOfficial": is_official,
                "addedAt": NOW.isoformat(),
            })
            i = j
            continue

        i += 1

    return articles


# ============================================================
# パーソナルピック.md パーサー
# ============================================================

def parse_personal_pick(filepath: Path) -> list[dict]:
    """パーソナルピックMDからPICK情報を抽出する"""
    content = filepath.read_text(encoding="utf-8")
    picks = []

    current_priority = None

    lines = content.split("\n")
    i = 0

    while i < len(lines):
        stripped = lines[i].strip()

        # 優先度セクション判定
        if "必読" in stripped and stripped.startswith("##"):
            current_priority = "must-read"
        elif "チェック推奨" in stripped and stripped.startswith("##"):
            current_priority = "worth-checking"
        elif "参考情報" in stripped and stripped.startswith("##"):
            current_priority = "fyi"
        elif stripped.startswith("## ") and current_priority:
            # 他のH2が来たらリセット
            if "選定" not in stripped and "つながり" not in stripped and "連鎖" not in stripped:
                current_priority = None

        # 記事エントリ: ### N. [タイトル](URL)
        if current_priority and stripped.startswith("###"):
            link_match = re.match(r"^###\s+\d+\.\s+\[(.+?)\]\((.+?)\)", stripped)
            if link_match:
                title = link_match.group(1).strip()
                url = link_match.group(2).strip()
                picks.append({
                    "title": title,
                    "url": url,
                    "priority": current_priority,
                })

        i += 1

    return picks


# ============================================================
# PICK統合
# ============================================================

def merge_picks(articles: list[dict], picks: list[dict]) -> list[dict]:
    """テックニュース記事にPICK情報を統合する"""
    # URLで高速マッチング用辞書
    url_to_pick = {p["url"]: p for p in picks if p["url"]}

    for article in articles:
        # URLマッチ（第一優先）
        if article["url"] and article["url"] in url_to_pick:
            pick = url_to_pick[article["url"]]
            article["isPick"] = True
            article["pickPriority"] = pick["priority"]
            continue

        # タイトル部分一致（フォールバック）
        for pick in picks:
            if pick["title"] and pick["title"][:20] in article["title"]:
                article["isPick"] = True
                article["pickPriority"] = pick["priority"]
                break

    return articles


# ============================================================
# RANKINGスコア算出（tier + score方式）
# ============================================================

def calc_ranking(articles: list[dict]) -> list[dict]:
    """tier（1=must-read, 2=worth-checking, 3=none）とスコアを算出"""
    for article in articles:
        score = 0

        # セクションボーナス
        if article["section"] == "main":
            score += 3
        elif article["section"] == "trending":
            score += 2
        else:
            score += 1

        # カテゴリボーナス
        if article["category"] == "ai-agent":
            score += 2

        # 直近7日ボーナス
        if article["date"] >= SEVEN_DAYS_AGO:
            score += 1

        # tierの設定
        if article["isPick"] and article["pickPriority"] == "must-read":
            tier = 1
        elif article["isPick"] and article["pickPriority"] in ("worth-checking", "fyi"):
            tier = 2
        else:
            tier = 3

        article["rankingTier"] = tier
        article["rankingScore"] = score

    return articles


# ============================================================
# メイン処理
# ============================================================

def main():
    all_articles = []
    dates_meta = []
    audit_lines = ["=== AI NEWS HUB 監査レポート ===\n"]
    url_seen = {}  # URL重複検出用

    # 既存のthumbnailキャッシュを読み込む（article url → thumbnail URL）
    # addedAt も同時にキャッシュする（url → 初回登場時刻）。
    # これにより既出記事の addedAt は固定され、新規記事だけが今回の NOW を持つ。
    existing_thumbnails = {}
    existing_added_at = {}
    existing_data = {}
    if OUTPUT_FILE.exists():
        try:
            existing_data = json.loads(OUTPUT_FILE.read_text(encoding="utf-8"))
            for a in existing_data.get("articles", []):
                if a.get("thumbnail") and a.get("url"):
                    existing_thumbnails[a["url"]] = a["thumbnail"]
                if a.get("addedAt") and a.get("url"):
                    existing_added_at[a["url"]] = a["addedAt"]
        except Exception:
            pass

    # テックニュースファイルを日付順で処理
    tech_files = sorted(NEWS_DIR.glob("*_テックニュース.md"))

    for tech_path in tech_files:
        date_str = tech_path.name.split("_")[0]

        # ファイルサイズチェック（スキップ判定）
        file_size = tech_path.stat().st_size
        if file_size < SKIP_THRESHOLD:
            audit_lines.append(f"[SKIPPED] {date_str} - ファイル小さすぎ ({file_size}bytes)")
            dates_meta.append({
                "date": date_str,
                "dayOfWeek": get_day_of_week(date_str),
                "articleCount": 0,
                "status": "skipped",
                "dailySummary": "",
            })
            continue

        # 記事パース
        articles = parse_tech_news(tech_path, date_str)

        # パーソナルピック統合
        pick_path = NEWS_DIR / f"{date_str}_パーソナルピック.md"
        if pick_path.exists():
            picks = parse_personal_pick(pick_path)
            articles = merge_picks(articles, picks)

        # RANKINGスコア算出
        articles = calc_ranking(articles)

        # URL重複チェック
        for art in articles:
            if art["url"]:
                if art["url"] in url_seen:
                    audit_lines.append(
                        f"[DUPLICATE_URL] {date_str} '{art['title'][:30]}' "
                        f"→ 重複: {url_seen[art['url']]}"
                    )
                else:
                    url_seen[art["url"]] = date_str

        pick_count = sum(1 for a in articles if a["isPick"])
        audit_lines.append(
            f"[OK] {date_str} - {len(articles)}記事 (PICK: {pick_count}件)"
        )

        # デイリーサマリーを取得（📌 今日のサマリーセクション）
        daily_summary = extract_daily_summary(tech_path)

        dates_meta.append({
            "date": date_str,
            "dayOfWeek": get_day_of_week(date_str),
            "articleCount": len(articles),
            "status": "ok",
            "dailySummary": daily_summary,
        })

        all_articles.extend(articles)

    # カテゴリ集計
    category_counts = {}
    for art in all_articles:
        cat = art["category"]
        category_counts[cat] = category_counts.get(cat, 0) + 1

    categories = []
    for cat_id, label, emoji, _ in CATEGORY_MAP:
        categories.append({
            "id": cat_id,
            "label": label,
            "emoji": emoji,
            "articleCount": category_counts.get(cat_id, 0),
        })
    if category_counts.get("other", 0) > 0:
        categories.append({
            "id": "other", "label": "その他", "emoji": "📰",
            "articleCount": category_counts["other"],
        })

    # 日付範囲
    all_dates = [d["date"] for d in dates_meta if d["status"] == "ok"]
    date_from = min(all_dates) if all_dates else ""
    date_to = max(all_dates) if all_dates else ""

    # GitHub Trending RSS から今日分を取得（dailyのみ・毎日25件）
    today_str = datetime.now(JST).strftime("%Y-%m-%d")
    today_trending = fetch_github_trending(limit=25)
    existing_trending = existing_data.get("trending", [])

    if len(today_trending) < TRENDING_DISPLAY_COUNT:
        # 取得失敗時は当日分を先に除外しない。直前の表示スナップショットを
        # そのまま維持し、部分取得したデータでは置き換えない。
        all_trending, snapshot_status = select_trending_snapshot(
            today_trending, existing_trending, today_str
        )
        print(f"⚠️  GitHub Trending: {snapshot_status}")
    else:
        # GitHub APIキャッシュ（owner/repo→repo）を作成してレート制限と
        # Geminiの再呼び出しを避ける。当日分も含む既存値全体が対象。
        existing_trending_cache = build_trending_cache(existing_trending)

        # GitHub APIで今日分の詳細情報を補完（stars・language・description・summary）
        enrich_trending_with_github_api(today_trending, existing_trending_cache)

        # 画面に出す先頭5件だけを、英語descriptionから日本語要約する。
        translate_trending_descriptions(today_trending[:TRENDING_DISPLAY_COUNT])

        all_trending, snapshot_status = select_trending_snapshot(
            today_trending, existing_trending, today_str
        )
        print(f"📊 Trending合計: {len(all_trending)}件 ({snapshot_status})")

    # addedAt 固定化 + 最新配信バッチ判定
    # 既出URLは前回の addedAt を引き継ぎ（＝初回登場時刻で固定）、
    # 今回初登場のURLだけ NOW を持つ。NEW判定はこの「今回バッチ」を基準にする。
    new_count = 0
    for a in all_articles:
        url = a.get("url", "")
        if url and url in existing_added_at:
            a["addedAt"] = existing_added_at[url]
        else:
            a["addedAt"] = NOW.isoformat()
            new_count += 1

    # latestBatchAt = 今回の配信バッチ時刻。
    # 今回新規が1件でもあれば NOW、無ければ前回値を維持（NEW表示を消さない）。
    if new_count > 0:
        latest_batch_at = NOW.isoformat()
    else:
        latest_batch_at = existing_data.get("latestBatchAt", "")
    print(f"🆕 今回新規記事: {new_count}件 / latestBatchAt={latest_batch_at}")

    output = {
        "generatedAt": datetime.now(JST).isoformat(),
        "latestBatchAt": latest_batch_at,
        "batchNewCount": new_count,
        "totalArticles": len(all_articles),
        "officialCount": sum(1 for a in all_articles if a.get("isOfficial")),
        "trendingCount": len(all_trending),
        "dateRange": {"from": date_from, "to": date_to},
        "dates": sorted(dates_meta, key=lambda x: x["date"], reverse=True),
        "categories": categories,
        "articles": all_articles,
        "trending": all_trending,
    }

    # サムネイル付与（既存キャッシュ引き継ぎ + 新規のみ並列OGP取得）
    # 新規OGP取得はThreadPoolで並列化し、サムネを必ず全件埋める。
    # 一度取得したサムネはarticles.json経由でキャッシュされ、次回は引き継がれる。
    # 全体に時間上限(OGP_BUDGET_SEC, 既定600秒)を設け、超過分のみサムネ無しで残す。
    # OGP_BUDGET_SEC=0 で新規取得を完全停止（既存キャッシュのみ）。
    ogp_budget = float(os.environ.get("OGP_BUDGET_SEC", "600"))
    ogp_workers = int(os.environ.get("OGP_WORKERS", "20"))
    thumb_ok = 0
    thumb_new = 0
    thumb_skipped = 0

    # キャッシュヒット分を先に適用し、新規取得が必要な記事を集める
    pending = []
    for a in all_articles:
        url = a.get("url", "")
        if url and url in existing_thumbnails:
            a["thumbnail"] = existing_thumbnails[url]
            thumb_ok += 1
        elif url.startswith("http"):
            pending.append(a)

    if pending and ogp_budget > 0:
        ogp_start = time.monotonic()
        with ThreadPoolExecutor(max_workers=ogp_workers) as executor:
            future_to_article = {
                executor.submit(get_ogp_image, a["url"]): a for a in pending
            }
            for future in as_completed(future_to_article):
                if (time.monotonic() - ogp_start) > ogp_budget:
                    for f in future_to_article:
                        f.cancel()
                    break
                a = future_to_article[future]
                try:
                    thumb = future.result()
                except Exception:
                    thumb = None
                if thumb:
                    a["thumbnail"] = thumb
                    thumb_new += 1
        thumb_skipped = len(pending) - thumb_new
    else:
        thumb_skipped = len(pending)

    print(f"🖼️  サムネイル: 引き継ぎ{thumb_ok}件 / 新規取得{thumb_new}件 / 未取得{thumb_skipped}件")

    # 記事数の激減ガード（OGPタイムアウト等で生成が途中失敗した時の自己防衛）
    # 既存より大幅に減っていたら警告。FAIL_ON_SHRINK=1 で中断（古いjsonを上書きしない）。
    prev_count = len(existing_data.get("articles", [])) if existing_data else 0
    new_count = len(all_articles)
    if prev_count > 0 and new_count < prev_count * 0.7:
        msg = (
            f"⚠️ 記事数が激減しています: {prev_count} → {new_count}件 "
            f"(前回比 {round(new_count / prev_count * 100)}%)。"
            "OGP取得タイムアウトや収集失敗の可能性があります。AGENTS.md参照。"
        )
        print(msg)
        if os.environ.get("FAIL_ON_SHRINK") == "1":
            raise SystemExit(f"❌ 記事数激減のため中断（FAIL_ON_SHRINK=1）: {msg}")

    # JSON出力
    OUTPUT_FILE.write_text(
        json.dumps(output, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    # 監査レポート出力
    audit_lines.append(f"\n合計: {len(all_articles)}記事 / {len(dates_meta)}日分")
    audit_lines.append(f"PICK記事: {sum(1 for a in all_articles if a['isPick'])}件")
    AUDIT_FILE.write_text("\n".join(audit_lines), encoding="utf-8")

    print(f"✅ articles.json 生成完了: {len(all_articles)}記事 / {len(dates_meta)}日分")
    print(f"📋 監査レポート: {AUDIT_FILE}")

    # SEO基礎工事（robots.txt / sitemap.xml / 構造化データ）を自動生成
    generate_seo_assets(all_articles)

    # about.html の実測値ブロックを更新（「全自動」を謳うページの数字が
    # 手動更新では自己矛盾になるため、記事収集のたびに毎回上書きする）
    update_about_stats(output, dates_meta)

    # トップページの2か所にある統計も、同じ実測値・固定値から毎回生成する。
    update_top_stats(output, dates_meta)


def _format_stat_value(value: str, unit: str = "") -> str:
    """統計値と単位を、各統計ブロックで共通のHTMLへ整形する。"""
    return f"{value}<small>{unit}</small>" if unit else value


def _stats_context(meta: dict, dates_meta: list[dict]) -> tuple[int, int, int, str]:
    """動的統計値と正順の期間文字列を返す。"""
    total = int(meta.get("totalArticles", 0) or 0)
    official = int(meta.get("officialCount", 0) or 0)
    dates = meta.get("dates")
    if not isinstance(dates, list):
        dates = dates_meta
    days = len(dates)

    # dateRange.from/to が真実源。無い場合だけ日付群の min/max へ縮退する。
    all_dates = [d.get("date", "") for d in dates if isinstance(d, dict) and d.get("date")]
    fallback_from = min(all_dates) if all_dates else ""
    fallback_to = max(all_dates) if all_dates else ""
    date_range = meta.get("dateRange")
    if not isinstance(date_range, dict):
        date_range = {}
    date_from = date_range.get("from") or fallback_from
    date_to = date_range.get("to") or fallback_to

    def _short(d: str, with_year: bool) -> str:
        try:
            y, m, dd = d.split("-")
            return f"{y}/{int(m)}/{int(dd)}" if with_year else f"{int(m)}/{int(dd)}"
        except (AttributeError, ValueError):
            return d

    period = (
        f"{_short(date_from, True)}〜{_short(date_to, False)}"
        if date_from and date_to
        else ""
    )
    return total, official, days, period


def _replace_exact_marker_block(html: str, marker: str, content: str) -> str:
    """指定マーカーが開始・終了とも各1個のときだけ内側を置換する。"""
    start_marker = f"<!-- {marker}:start -->"
    end_marker = f"<!-- {marker}:end -->"
    start_count = html.count(start_marker)
    end_count = html.count(end_marker)
    if start_count != 1 or end_count != 1:
        raise RuntimeError(
            f"index.html の {marker} マーカー数が不正です "
            f"(start={start_count}, end={end_count})。開始・終了を各1個にしてください。"
        )

    start = html.index(start_marker) + len(start_marker)
    end = html.index(end_marker)
    if end < start:
        raise RuntimeError(f"index.html の {marker} マーカーの順序が不正です。")
    return html[:start] + "\n" + content + "\n" + html[end:]


def update_top_stats(meta: dict, dates_meta: list[dict]) -> None:
    """index.html の指標バーと数字グリッドを最新値で厳格に更新する。"""
    if not INDEX_FILE.exists():
        raise RuntimeError("index.html が無いためトップ統計を更新できません。")

    total, official, days, period = _stats_context(meta, dates_meta)
    dynamic = (
        {"value": f"{total:,}", "unit": "本", "label": "累計記事数", "detail": ""},
        {"value": f"{official:,}", "unit": "本", "label": "うち公式リリース", "detail": ""},
        {"value": str(days), "unit": "日分", "label": "カバー期間", "detail": period},
    )
    stats = dynamic + TOP_STATS_FIXED

    bar_lines = []
    grid_lines = []
    for index, stat in enumerate(stats):
        value_html = _format_stat_value(stat["value"], stat.get("unit", ""))
        detail = stat.get("detail", "")
        bar_detail = f"<br>{detail}" if detail and index >= len(dynamic) else ""
        grid_detail = f"<br>{detail}" if detail else ""
        bar_lines.append(
            f'        <div class="top-stat"><strong>{value_html}</strong>'
            f'<span>{stat["label"]}{bar_detail}</span></div>'
        )
        grid_lines.append(
            f'        <div class="top-number-card"><strong>{value_html}</strong>'
            f'<span>{stat["label"]}{grid_detail}</span></div>'
        )

    # サイト説明バーの記事数。ここを固定値のままにすると、指標バー・数字グリッドだけが
    # 更新され、同一ページに新旧2つの記事数が並ぶ（2026-08-05 レビュー指摘）。
    info_line = f"        <dd>{total:,}本</dd>"

    # 一部だけ更新された状態を作らないため、全ブロックを検証・置換してから1回だけ書く。
    html = INDEX_FILE.read_text(encoding="utf-8")
    updated = _replace_exact_marker_block(html, "TOP_STATS_BAR", "\n".join(bar_lines))
    updated = _replace_exact_marker_block(updated, "TOP_STATS_GRID", "\n".join(grid_lines))
    updated = _replace_exact_marker_block(updated, "TOP_STATS_COUNT", info_line)
    INDEX_FILE.write_text(updated, encoding="utf-8")
    print(f"✅ index.html の数字を更新: {total:,}本 / {official:,}本 / {days}日分")


def update_about_stats(meta: dict, dates_meta: list[dict]) -> None:
    """about.html の ABOUT_STATS マーカー間を最新の実測値で置き換える。

    数字はこのサイトの「全自動で動いている」という主張の裏付けなので、
    古い値が残ると主張そのものが嘘になる。マーカーが見つからない場合は
    黙って素通りせずFail loudさせる（静かに古い数字が残る方が有害）。
    """
    if not ABOUT_FILE.exists():
        print("⚠️ about.html が無いのでスキップ")
        return

    html = ABOUT_FILE.read_text(encoding="utf-8")
    start_marker = "<!-- ABOUT_STATS:start"
    end_marker = "<!-- ABOUT_STATS:end -->"
    start = html.find(start_marker)
    end = html.find(end_marker)
    if start == -1 or end == -1:
        raise RuntimeError(
            "about.html の ABOUT_STATS マーカーが見つかりません。"
            "マーカーを消すと数字が更新されず、実測値という主張が嘘になります。"
        )
    # マーカー行自体は残し、その内側だけ差し替える
    start_line_end = html.find("-->", start) + len("-->")

    total, official, days, period = _stats_context(meta, dates_meta)
    dynamic = (
        {"value": f"{total:,}", "unit": "本", "label": "累計記事数", "detail": ""},
        {"value": f"{official:,}", "unit": "本", "label": "うち公式リリース", "detail": ""},
        {
            "value": str(days),
            "unit": "日分",
            "label": "カバー期間",
            "detail": f"({period})" if period else "",
        },
    )
    card_lines = ['      <div class="stat-grid">']
    for stat in dynamic + TOP_STATS_FIXED:
        value_html = _format_stat_value(stat["value"], stat.get("unit", ""))
        label = stat.get("about_label", stat["label"])
        detail = f'<br>{stat["detail"]}' if stat.get("detail") else ""
        card_lines.extend((
            '        <div class="stat-card">',
            f'          <div class="stat-value">{value_html}</div>',
            f'          <div class="stat-label">{label}{detail}</div>',
            '        </div>',
        ))
    card_lines.append("      </div>")
    cards = "\n" + "\n".join(card_lines) + "\n      "

    ABOUT_FILE.write_text(html[:start_line_end] + cards + html[end:], encoding="utf-8")
    print(f"✅ about.html の数字を更新: {total:,}本 / {official:,}本 / {days}日分")


def generate_seo_assets(all_articles: list[dict]) -> None:
    """robots.txt・sitemap.xml を生成し、index.html に WebSite/CollectionPage の
    JSON-LD を埋め込む。記事収集のたびに毎回上書きされるため運用は完全自動。"""
    today = datetime.now(JST)
    lastmod = today.strftime("%Y-%m-%d")

    # --- robots.txt（全許可＋サイトマップ案内）---
    ROBOTS_FILE.write_text(
        f"User-agent: *\nAllow: /\nSitemap: {BASE_URL}/sitemap.xml\n",
        encoding="utf-8",
    )

    # --- sitemap.xml（個別記事URLは存在しないので固定ページのみ）---
    # about.html は毎日更新されないので changefreq を monthly にする。
    sitemap = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>{BASE_URL}/</loc>
    <lastmod>{lastmod}</lastmod>
    <changefreq>daily</changefreq>
    <priority>1.0</priority>
  </url>
  <url>
    <loc>{BASE_URL}/official.html</loc>
    <lastmod>{lastmod}</lastmod>
    <changefreq>daily</changefreq>
    <priority>0.8</priority>
  </url>
  <url>
    <loc>{BASE_URL}/about.html</loc>
    <lastmod>{lastmod}</lastmod>
    <changefreq>monthly</changefreq>
    <priority>0.6</priority>
  </url>
</urlset>"""
    SITEMAP_FILE.write_text(sitemap, encoding="utf-8")

    # --- 構造化データ（JSON-LD）を index.html に埋め込み ---
    # 個別記事URLが無いため NewsArticle ではなく WebSite + CollectionPage(ItemList)
    non_official = [a for a in all_articles if not a.get("isOfficial")]
    # 配列順は日付降順とは限らないため max() で最新日を確定する
    latest_date = max((a.get("date", "") for a in non_official), default="")
    latest = [a for a in non_official if a.get("date") == latest_date][:30]

    website_schema = {
        "@context": "https://schema.org",
        "@type": "WebSite",
        "name": "AI Navigator",
        "description": "中小企業の経営者・現場担当者向けAIビジネスニュース。",
        "url": BASE_URL + "/",
        "inLanguage": "ja",
    }
    collection_schema = {
        "@context": "https://schema.org",
        "@type": "CollectionPage",
        "name": f"AI Navigator — {latest_date} のAIニュース",
        "description": "AIビジネスニュースを毎日自動収集・要約配信。",
        "url": BASE_URL + "/",
        "dateModified": today.isoformat(),
        "mainEntity": {
            "@type": "ItemList",
            "itemListElement": [
                {
                    "@type": "ListItem",
                    "position": i,
                    "name": a.get("title", ""),
                    "url": a.get("url", BASE_URL),
                }
                for i, a in enumerate(latest, 1)
            ],
        },
    }
    json_ld = (
        '<script type="application/ld+json">\n'
        + json.dumps(website_schema, ensure_ascii=False)
        + "\n</script>\n"
        + '<script type="application/ld+json">\n'
        + json.dumps(collection_schema, ensure_ascii=False)
        + "\n</script>"
    )

    # マーカーで挟んだ区間を毎回置換する（冪等：何度実行してもマーカーが残る）
    block = (
        "<!-- JSON_LD:start -->\n" + json_ld + "\n<!-- JSON_LD:end -->"
    )
    if INDEX_FILE.exists():
        html = INDEX_FILE.read_text(encoding="utf-8")
        pattern = re.compile(
            r"<!-- JSON_LD:start -->.*?<!-- JSON_LD:end -->", re.DOTALL
        )
        if pattern.search(html):
            INDEX_FILE.write_text(pattern.sub(lambda _: block, html), encoding="utf-8")
        else:
            print("⚠️ index.html に JSON_LD マーカーが無いためJSON-LD未挿入")

    print("✅ SEO生成完了: robots.txt / sitemap.xml / JSON-LD")


def parse_trending(filepath: Path, date_str: str) -> list[dict]:
    """テックニュースMDのGitHub TrendingセクションからリポジトリリストをパースしてJSON化する"""
    content = filepath.read_text(encoding="utf-8")
    lines = content.split("\n")
    repos = []
    in_trending = False
    repo_num = 0

    i = 0
    while i < len(lines):
        stripped = lines[i].strip()

        # Trendingセクション開始
        if re.match(r"^##\s+.*Trending", stripped):
            in_trending = True
            i += 1
            continue

        # 別セクション開始でTrending終了
        if in_trending and re.match(r"^##\s+", stripped) and "Trending" not in stripped:
            break

        # リポジトリ行: - [owner/repo](url)
        if in_trending:
            repo_match = re.match(r"^-\s+\[([^\]]+)\]\((https://github\.com/[^)]+)\)", stripped)
            if repo_match:
                repo_name = repo_match.group(1)
                repo_url = repo_match.group(2)
                description = ""
                # 次行が説明文
                if i + 1 < len(lines):
                    next_line = lines[i + 1].strip()
                    if next_line and not next_line.startswith("-") and not next_line.startswith("#"):
                        description = next_line
                        i += 1
                repo_num += 1
                repos.append({
                    "id": f"{date_str}_trending_{repo_num}",
                    "date": date_str,
                    "title": repo_name,
                    "url": repo_url,
                    "source": "GitHub Trending",
                    "category": "trending",
                    "summary": description,
                    "isTrending": True,
                    "isPick": False,
                    "pickPriority": None,
                    "isOfficial": False,
                    "rankingTier": 3,
                    "rankingScore": 0,
                })
        i += 1

    return repos


TRENDING_DISPLAY_COUNT = 5


def github_repo_key(value: str) -> str:
    """GitHub URLまたはfull_nameを小文字のowner/repoキーへ正規化する。"""
    raw = str(value or "").strip()
    match = re.match(r"https://github\.com/([^/]+/[^/?#]+)", raw, flags=re.IGNORECASE)
    full_name = match.group(1) if match else raw
    parts = [part for part in full_name.strip("/").split("/") if part]
    if len(parts) != 2:
        return ""
    return "/".join(parts).lower()


def build_trending_cache(repos: list[dict]) -> dict[str, dict]:
    """既存Trendingを正規化したowner/repoキーでキャッシュする。"""
    cache = {}
    for repo in repos:
        key = github_repo_key(repo.get("url", "") or repo.get("title", ""))
        if key:
            # 入力は新しい順なので、同じリポジトリの最初（最新）を優先する。
            cache.setdefault(key, repo)
    return cache


def has_japanese_summary(repo: dict) -> bool:
    """画面表示可能な日本語要約（最大5行）があるか判定する。"""
    summary = str(repo.get("summary", "")).strip()
    return bool(summary) and len(summary.splitlines()) <= 5 and bool(
        re.search(r"[ぁ-んァ-ヶ一-龠々ー]", summary)
    )


def merge_trending_history(
    today_repos: list[dict], existing_repos: list[dict], today: str
) -> list[dict]:
    """今日のスナップショットを先頭にし、過去履歴を重複なく引き継ぐ。"""
    past_repos = [repo for repo in existing_repos if repo.get("date") != today]
    past_days: dict[str, int] = {}
    for repo in past_repos:
        key = github_repo_key(repo.get("url", "") or repo.get("title", ""))
        if key:
            past_days[key] = past_days.get(key, 0) + 1

    today_keys = set()
    for repo in today_repos:
        key = github_repo_key(repo.get("url", "") or repo.get("title", ""))
        repo["trendingDays"] = past_days.get(key, 0) + 1
        if key:
            today_keys.add(key)

    return today_repos + [
        repo for repo in past_repos
        if github_repo_key(repo.get("url", "") or repo.get("title", "")) not in today_keys
    ]


def select_trending_snapshot(
    today_repos: list[dict], existing_repos: list[dict], today: str
) -> tuple[list[dict], str]:
    """要約の成否に応じて新規・前回正常値・初回縮退値を選ぶ。"""
    if len(today_repos) < TRENDING_DISPLAY_COUNT:
        return (
            existing_repos,
            f"取得{len(today_repos)}件 (<{TRENDING_DISPLAY_COUNT})・前回値を維持",
        )

    merged = merge_trending_history(today_repos, existing_repos, today)
    current_five = today_repos[:TRENDING_DISPLAY_COUNT]
    if len(current_five) == TRENDING_DISPLAY_COUNT and all(
        has_japanese_summary(repo) for repo in current_five
    ):
        return merged, "新5件を採用"

    previous_five = existing_repos[:TRENDING_DISPLAY_COUNT]
    if len(previous_five) == TRENDING_DISPLAY_COUNT and all(
        has_japanese_summary(repo) for repo in previous_five
    ):
        return existing_repos, "要約不足のため前回正常値を維持"

    # 初回など正常値がまだ無い場合は、フロント側が空要約を
    # 「要約を準備中です」に置き換える。
    return merged, "正常値なし・準備中表示へ縮退"


def fetch_github_trending(limit: int = 25) -> list[dict]:
    """GitHub Trending RSS (daily/all) からリポジトリ一覧を取得する。"""
    feed_url = "https://mshibanami.github.io/GitHubTrendingRSS/daily/all.xml"
    today = datetime.now(JST).strftime("%Y-%m-%d")
    repos = []
    seen_names = set()

    def parse_feed(feed_url: str) -> list[tuple[str, str]]:
        """フィードからリポジトリの (full_name, url) リストを返す"""
        req = urllib.request.Request(feed_url, headers={"User-Agent": "ai-navigator/1.0"})
        with urllib.request.urlopen(req, timeout=15) as res:
            raw = res.read()
        root = ET.fromstring(raw)
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        entries = root.findall("atom:entry", ns) or root.findall(".//item")
        result = []
        for entry in entries:
            title_el = entry.find("atom:title", ns) or entry.find("title")
            link_el  = entry.find("atom:link",  ns) or entry.find("link")
            title = title_el.text.strip() if title_el is not None and title_el.text else ""
            if link_el is not None:
                url = link_el.get("href") or (link_el.text or "").strip()
            else:
                url = ""
            if not url.startswith("https://github.com/"):
                continue
            m = re.match(r"https://github\.com/([^/]+/[^/?#]+)", url)
            if not m:
                continue
            full_name = m.group(1).rstrip("/")
            result.append((full_name, f"https://github.com/{full_name}"))
        return result

    try:
        items = parse_feed(feed_url)
        for full_name, url in items:
            key = github_repo_key(full_name)
            if not key or key in seen_names:
                continue
            seen_names.add(key)
            idx = len(repos) + 1
            repos.append({
                "id": f"{today}_trending_{idx}",
                "date": today,
                "title": full_name,
                "url": url,
                "source": "GitHub Trending",
                "category": "trending",
                "summary": "",
                "isTrending": True,
                "isPick": False,
                "pickPriority": None,
                "isOfficial": False,
                "rankingTier": 3,
                "rankingScore": 0,
            })
            if len(repos) >= limit:
                break
        print(f"📡 RSS取得: +{len(repos)}件 (daily)")
    except Exception as e:
        print(f"⚠️  RSS取得失敗 (daily): {e}")

    print(f"📡 GitHub Trending 合計: {len(repos)}件")
    return repos


def enrich_trending_with_github_api(repos: list[dict], existing_cache: dict | None = None) -> None:
    """GitHub APIでリポジトリ詳細（stars・language・description）を補完する"""
    token = os.environ.get("GITHUB_TOKEN", "")
    headers = {"User-Agent": "ai-navigator/1.0"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    enriched = 0
    cached = 0
    for repo in repos:
        m = re.match(r"https://github\.com/([^/]+/[^/?#]+)", repo.get("url", ""))
        if not m:
            continue
        full_name = m.group(1).rstrip("/")
        cache_key = github_repo_key(full_name)

        # 既存キャッシュがあれば再利用（ローカルのレート制限対策）
        if existing_cache and cache_key in existing_cache:
            cached_repo = existing_cache[cache_key]
            repo["stars"] = cached_repo.get("stars")
            repo["forks"] = cached_repo.get("forks")
            repo["language"] = cached_repo.get("language", "")
            repo["githubDescription"] = cached_repo.get("githubDescription", "")
            repo["summary"] = cached_repo.get("summary", "")
            cached += 1
            if repo.get("githubDescription") and repo.get("stars") is not None:
                continue

        api_url = f"https://api.github.com/repos/{full_name}"
        try:
            req = urllib.request.Request(api_url, headers=headers)
            with urllib.request.urlopen(req, timeout=8) as res:
                data = json.loads(res.read())
            repo["stars"] = data.get("stargazers_count", 0)
            repo["forks"] = data.get("forks_count", 0)
            repo["language"] = data.get("language") or ""
            repo["githubDescription"] = data.get("description") or ""
            enriched += 1
        except Exception:
            pass

    print(f"🐙 GitHub API: 新規{enriched}件 / キャッシュ{cached}件 補完")


def translate_trending_descriptions(repos: list[dict]) -> None:
    """Gemini APIでGitHub Trendingの英語説明を日本語で要約する。"""
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        print("⚠️  GEMINI_API_KEY未設定 - 翻訳スキップ")
        return

    # 要約対象（githubDescriptionあり・日本語summaryなし）
    targets = [
        r for r in repos
        if r.get("githubDescription") and not has_japanese_summary(r)
    ]
    if not targets:
        print("🌐 翻訳対象なし（全件キャッシュ済み）")
        return

    # 一括要約プロンプト（入力はGitHub APIの英語1行descriptionのみ）
    lines = "\n".join(
        f"{i+1}. [{r['title']}] {r['githubDescription']}"
        for i, r in enumerate(targets)
    )
    prompt = f"""以下はGitHubリポジトリの英語の短い説明です。
各リポジトリが何をするものか、非エンジニアにも分かる日本語で要約してください。

## ルール
- 各要約は5行以内
- 誇張しない
- 入力から分からないことは書かない
- 英語説明の翻訳や言い換えに必要な範囲だけを書く
- 出力は番号付きリスト形式（例: 1. 要約）
- リポジトリ名は要約に含めない

{lines}"""

    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash:generateContent?key={api_key}"
        body = json.dumps({"contents": [{"parts": [{"text": prompt}]}]}).encode("utf-8")
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as res:
            result = json.loads(res.read())
        text = result["candidates"][0]["content"]["parts"][0]["text"]

        # 番号付きリストをパース: "1. 説明文" → index → summary
        for line in text.strip().splitlines():
            m = re.match(r"^(\d+)\.\s+(.+)", line.strip())
            if m:
                idx = int(m.group(1)) - 1
                if 0 <= idx < len(targets):
                    targets[idx]["summary"] = m.group(2).strip()

        translated = sum(1 for r in targets if r.get("summary"))
        print(f"🌐 Gemini翻訳: {translated}/{len(targets)}件")
    except Exception as e:
        print(f"⚠️  Gemini翻訳失敗: {e}")


def get_ogp_image(url: str) -> str | None:
    """URLからOGP画像URLを取得する（GitHubはOGP APIを直接利用）"""
    # GitHub releases/repo URL → opengraph.githubassets.com で直接取得
    gh_match = re.match(r"https://github\.com/([^/]+/[^/?#]+)", url)
    if gh_match:
        full_name = gh_match.group(1)
        return f"https://opengraph.githubassets.com/1/{full_name}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=8) as res:
            html = res.read().decode("utf-8", errors="ignore")
        m = re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']', html)
        if not m:
            m = re.search(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']', html)
        return m.group(1) if m else None
    except Exception:
        return None


def get_day_of_week(date_str: str) -> str:
    """YYYY-MM-DD から曜日（MON/TUE/.../SUN）を返す"""
    days = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        return days[dt.weekday()]
    except Exception:
        return ""


def extract_daily_summary(filepath: Path) -> str:
    """テックニュースMDから今日のサマリーテキストを抽出"""
    content = filepath.read_text(encoding="utf-8")
    match = re.search(
        r"##\s*(?:📌\s*)?今日のサマリー\s*\n(.*?)(?=\n##|\Z)",
        content,
        re.DOTALL
    )
    if match:
        text = match.group(1).strip()
        # 最初の段落のみ（改行2つで切る）
        first_para = text.split("\n\n")[0].strip()
        return first_para
    return ""


if __name__ == "__main__":
    main()
