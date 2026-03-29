"""
AI NEWS HUB パーサー
自動ニュース配信/ フォルダのMDファイルを articles.json に変換する
"""

import io
import json
import os
import re
import sys
import urllib.request
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

# 基準日（直近7日ボーナス判定用）
NOW = datetime.now(JST)
SEVEN_DAYS_AGO = (NOW - timedelta(days=7)).strftime("%Y-%m-%d")

# カテゴリ正規化マッピング（優先順位順）
CATEGORY_MAP = [
    ("official",  "公式リリース", "📢", ["📢", "公式リリース", "AI企業アップデート"]),
    ("ai-agent",  "AI/エージェント", "🤖", ["🤖", "AIエージェント", "LLM", "Claude", "エージェント"]),
    ("dev-tools", "開発ツール",   "🛠️", ["🛠", "開発ツール", "AI駆動開発", "プログラミング", "AIコーディング"]),
    ("efficiency","業務効率化",   "⚡", ["⚡", "業務効率化", "DX", "ビジネス", "ノーコード", "Vibe Coding", "個人開発"]),
    ("ai-biz",    "AIビジネス",   "💼", ["💼", "AIビジネス", "Webマーケティング", "マーケティング", "個人開発マネタイズ", "収益化", "AI導入"]),
    ("pkm",       "知識管理",     "🧠", ["🧠", "知識管理", "PKM", "Obsidian", "ナレッジ", "情報整理", "NotionAI"]),
]

# スキップと見なす固定セクションのキーワード
SKIP_SECTIONS = ["今日のサマリー", "GitHub Trending", "その他の注目ニュース", "収集ソース"]

# 公式ソース判定リスト（isOfficial: True をセットするソース名）
OFFICIAL_SOURCES = [
    "OpenAI Blog",
    "Google AI Blog",
    "Claude Code Releases",
    "Anthropic SDK Releases",
    "Anthropic News",
    "OpenAI SDK Releases",
    "Google GenAI SDK Releases",
    "Google DeepMind Blog",
    "Gemini Blog",
    "Microsoft Foundry Blog",
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
            article_num += 1
            articles.append({
                "id": f"{date_str}_{article_num}",
                "date": date_str,
                "title": title,
                "url": url,
                "source": source,
                "category": "official" if is_official else current_category_id,
                "summary": summary,
                "section": "main",
                "isPick": False,
                "pickPriority": None,
                "rankingTier": 3,
                "rankingScore": 0,
                "isOfficial": is_official,
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

    # 既存のthumbnailキャッシュを読み込む（article id → thumbnail URL）
    existing_thumbnails = {}
    existing_data = {}
    if OUTPUT_FILE.exists():
        try:
            existing_data = json.loads(OUTPUT_FILE.read_text(encoding="utf-8"))
            for a in existing_data.get("articles", []):
                if a.get("thumbnail"):
                    existing_thumbnails[a["id"]] = a["thumbnail"]
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

    # GitHub Trending RSS から今日分を取得（毎日25件）
    today_str = datetime.now(JST).strftime("%Y-%m-%d")
    today_trending = fetch_github_trending(limit=25)

    # 既存trending（過去分）を引き継ぎ、今日分だけ差し替え
    past_trending = [r for r in existing_data.get("trending", []) if r.get("date") != today_str]

    # 過去の登場回数をURLごとに集計
    url_days: dict[str, int] = {}
    for r in past_trending:
        url_days[r["url"]] = url_days.get(r["url"], 0) + 1

    # 今日分に連続日数を付与し、過去分から重複URLを除外（最新=今日分を優先）
    past_urls_in_today = set()
    for r in today_trending:
        days = url_days.get(r["url"], 0) + 1  # 今日含む合計日数
        r["trendingDays"] = days
        if days >= 2:
            past_urls_in_today.add(r["url"])

    # 過去分から今日も登場したURLを除去（今日分に統合）
    past_trending_deduped = [r for r in past_trending if r["url"] not in past_urls_in_today]

    all_trending = today_trending + past_trending_deduped

    # GitHub APIキャッシュ（full_name→repo）を作成してレート制限対策
    existing_trending_cache = {}
    for r in past_trending:
        m = re.match(r"https://github\.com/([^/]+/[^/?#]+)", r.get("url", ""))
        if m and r.get("stars") is not None:
            existing_trending_cache[m.group(1).rstrip("/")] = r

    # GitHub APIで今日分の詳細情報を補完（stars・language・description）
    enrich_trending_with_github_api(today_trending, existing_trending_cache)

    # Gemini APIで英語descriptionを日本語要約に翻訳（summaryが空の全件対象）
    translate_trending_descriptions(all_trending)

    print(f"📊 Trending合計: {len(all_trending)}件 (今日{len(today_trending)}件 + 過去{len(past_trending)}件)")

    output = {
        "generatedAt": datetime.now(JST).isoformat(),
        "totalArticles": len(all_articles),
        "officialCount": sum(1 for a in all_articles if a.get("isOfficial")),
        "trendingCount": len(all_trending),
        "dateRange": {"from": date_from, "to": date_to},
        "dates": sorted(dates_meta, key=lambda x: x["date"], reverse=True),
        "categories": categories,
        "articles": all_articles,
        "trending": all_trending,
    }

    # サムネイル付与（既存キャッシュ引き継ぎ + 新規のみOGP取得）
    thumb_ok = 0
    thumb_new = 0
    for a in all_articles:
        if a["id"] in existing_thumbnails:
            a["thumbnail"] = existing_thumbnails[a["id"]]
            thumb_ok += 1
        elif a.get("url", "").startswith("http"):
            thumb = get_ogp_image(a["url"])
            if thumb:
                a["thumbnail"] = thumb
                thumb_new += 1
    print(f"🖼️  サムネイル: 引き継ぎ{thumb_ok}件 / 新規取得{thumb_new}件")

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


def fetch_github_trending(limit: int = 25) -> list[dict]:
    """GitHub Trending RSS (daily + weekly/all) からリポジトリ一覧を取得する（重複除去）"""
    feed_urls = [
        "https://mshibanami.github.io/GitHubTrendingRSS/daily/all.xml",
        "https://mshibanami.github.io/GitHubTrendingRSS/weekly/all.xml",
    ]
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

    for feed_url in feed_urls:
        try:
            items = parse_feed(feed_url)
            added = 0
            for full_name, url in items:
                if full_name in seen_names:
                    continue
                seen_names.add(full_name)
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
                added += 1
                if len(repos) >= limit:
                    break
            print(f"📡 RSS取得: +{added}件 ({feed_url.split('/')[-2]})")
        except Exception as e:
            print(f"⚠️  RSS取得失敗 ({feed_url.split('/')[-2]}): {e}")

        if len(repos) >= limit:
            break

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

        # 既存キャッシュがあれば再利用（ローカルのレート制限対策）
        if existing_cache and full_name in existing_cache:
            cached_repo = existing_cache[full_name]
            repo["stars"] = cached_repo.get("stars")
            repo["forks"] = cached_repo.get("forks")
            repo["language"] = cached_repo.get("language", "")
            repo["githubDescription"] = cached_repo.get("githubDescription", "")
            cached += 1
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
    """Gemini APIでGitHub Trendingリポジトリの説明文を日本語に一括翻訳する"""
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        print("⚠️  GEMINI_API_KEY未設定 - 翻訳スキップ")
        return

    # 翻訳対象（githubDescriptionあり・summaryが150文字未満）
    targets = [
        r for r in repos
        if r.get("githubDescription") and len(r.get("summary", "")) < 150
    ]
    if not targets:
        print("🌐 翻訳対象なし（全件150文字以上）")
        return

    # 一括翻訳プロンプト
    lines = "\n".join(
        f"{i+1}. [{r['title']}] {r['githubDescription']}"
        for i, r in enumerate(targets)
    )
    prompt = f"""以下はGitHubリポジトリの名前と英語説明文です。
各リポジトリについて、以下の内容を含む日本語の詳細説明を書いてください：
1. このリポジトリが何をするものか（主目的）
2. 具体的にどんなことができるか・主な機能や特徴
3. なぜ今注目されているか・どんな開発者・場面で役立つか

## ルール（最重要）
- **150文字以上・250文字以内**で書くこと
- 改行は一切しない（1行のみ）
- 説明文のみ出力（番号・タイトルは含めない）
- 技術用語（AI、LLM、Python、Claude等）はそのままでOK
- 出力は番号付きリスト形式（例: 1. 説明文）

{lines}"""

    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"
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
