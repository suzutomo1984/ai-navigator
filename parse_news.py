"""
AI NEWS HUB パーサー
自動ニュース配信/ フォルダのMDファイルを articles.json に変換する
"""

import io
import json
import os
import re
import sys
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
    ("ai-agent",    "AI/MCP",      "🤖", ["🤖", "AIエージェント", "LLM", "Claude"]),
    ("obsidian-pkm","Obsidian",    "📝", ["📝", "Obsidian", "PKM", "知識管理"]),
    ("dev-tools",   "開発ツール",   "🛠️", ["🛠", "開発ツール", "AI駆動開発", "プログラミング", "AIコーディング"]),
    ("no-code",     "ノーコード",   "🔌", ["🔌", "ノーコード", "Vibe Coding", "個人開発"]),
    ("efficiency",  "業務効率化",   "⚡", ["⚡", "業務効率化", "DX", "ビジネス"]),
    ("marketing",   "マーケ/収益化","💰", ["💰", "Webマーケティング", "マーケティング", "個人開発マネタイズ"]),
]

# スキップと見なす固定セクションのキーワード
SKIP_SECTIONS = ["今日のサマリー", "GitHub Trending", "その他の注目ニュース", "収集ソース"]

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

            article_num += 1
            articles.append({
                "id": f"{date_str}_{article_num}",
                "date": date_str,
                "title": title,
                "url": url,
                "source": source,
                "category": current_category_id,
                "summary": summary,
                "section": "main",
                "isPick": False,
                "pickPriority": None,
                "rankingTier": 3,
                "rankingScore": 0,
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

    output = {
        "generatedAt": datetime.now(JST).isoformat(),
        "totalArticles": len(all_articles),
        "dateRange": {"from": date_from, "to": date_to},
        "dates": sorted(dates_meta, key=lambda x: x["date"], reverse=True),
        "categories": categories,
        "articles": all_articles,
    }

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
