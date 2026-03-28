"""
今日の記事のsummaryをGemini APIで150〜250文字に再生成するスクリプト。

使い方:
  set GEMINI_API_KEY=your_key_here
  python update_summaries.py

または:
  GEMINI_API_KEY=your_key python update_summaries.py
"""

import json
import os
import sys
import urllib.request
import urllib.error
import time
from datetime import date

sys.stdout.reconfigure(encoding="utf-8")

ARTICLES_JSON = "articles.json"
TARGET_DATE = str(date.today())  # 今日の日付
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
BATCH_SIZE = 10  # 1回のAPIコールで処理する記事数


def call_gemini(prompt: str) -> str:
    body = json.dumps({"contents": [{"parts": [{"text": prompt}]}]}).encode("utf-8")
    req = urllib.request.Request(
        GEMINI_URL, data=body, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=60) as res:
        result = json.loads(res.read())
    return result["candidates"][0]["content"]["parts"][0]["text"]


def build_prompt(article: dict) -> str:
    source = article.get("source", "")
    title = article.get("title", "")
    existing = article.get("summary", "") or "(なし)"

    # GitHub Trendingリポジトリの場合は専用プロンプト
    if article.get("isTrending") or source == "GitHub Trending":
        github_desc = article.get("githubDescription", "")
        stars = article.get("stars", "")
        language = article.get("language", "")
        return f"""以下のGitHubリポジトリについて、日本語の詳しい説明を1行で書いてください。

## 内容に含めること
1. このリポジトリが何をするものか（主目的）
2. 具体的にどんなことができるか・どう使うか
3. どんな開発者・場面で役立つか

## 文字数ルール（最重要）
- **100文字以上・200文字以内**で書くこと
- 改行は一切しない（1行のみ）
- 説明文・前置き・番号は不要。説明文のみ出力すること

リポジトリ名: {title}
言語: {language}
スター数: {stars}
GitHubの説明文（英語）: {github_desc}
既存の日本語要約（参考）: {existing}
"""

    # 記事タイプ判定
    is_release = any(x in source for x in ["Releases", "Blog", "News"])

    if is_release:
        type_instruction = """これはリリースノート・公式ブログ記事です。
以下の形式で書いてください：
「v〇〇: [具体的な新機能1]、[具体的な変更点2]、[修正・改善点3]。[一言でこのリリースの意義]」
バージョン番号が分かれば必ず先頭に書く。変更点は3個以上列挙すること。"""
    else:
        type_instruction = """これは解説・ニュース・チュートリアル記事です。
以下の内容を含めて書いてください：
1. 何についての記事か（主題）
2. 具体的に何が分かるか・何ができるようになるか
3. どんな場面で役立つか
定型フレーズ（「〜を示唆し」「〜が重要」「必要がある」）は使わないこと。"""

    return f"""以下のAI・技術系記事について、日本語の詳しい要約を1行で書いてください。

{type_instruction}

## 文字数ルール（最重要）
- **180文字以上・250文字以内**で書くこと
- 短すぎる場合は具体的な情報・背景・使い方を追加して文字数を満たすこと
- 改行は一切しない（1行のみ）
- 説明文・前置き・番号は不要。要約文のみ出力すること

タイトル: {title}
ソース: {source}
既存の短い要約（参考）: {existing}
"""


def main():
    if not GEMINI_API_KEY:
        print("❌ GEMINI_API_KEY が設定されていません")
        print("   set GEMINI_API_KEY=your_key_here を実行してから再試行してください")
        sys.exit(1)

    with open(ARTICLES_JSON, encoding="utf-8") as f:
        data = json.load(f)

    articles = data["articles"]
    trending = data.get("trending", [])

    # articlesの対象: 非Trending・全日付（summaryが150文字未満のみ）
    targets = [
        ("articles", i, a) for i, a in enumerate(articles)
        if not a.get("isTrending")
        and len(a.get("summary", "")) < 150
    ]

    # trendingの対象: summaryが150文字未満
    targets += [
        ("trending", i, a) for i, a in enumerate(trending)
        if len(a.get("summary", "")) < 150
    ]

    if not targets:
        print(f"✅ 対象記事なし（全件150文字以上）")
        return

    print(f"📝 対象記事: {len(targets)}件\n")

    import re
    updated = 0
    for idx, (bucket, orig_idx, article) in enumerate(targets):
        # 100件ごとに中間保存
        if idx > 0 and idx % 100 == 0:
            data["articles"] = articles
            data["trending"] = trending
            with open(ARTICLES_JSON, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
            print(f"\n💾 中間保存 ({idx}件完了)\n")
        print(f"  [{idx+1}/{len(targets)}] [{bucket}] {article.get('source', article.get('name', ''))} | {str(article.get('title', article.get('name', '')))[:40]}...")
        try:
            response_text = call_gemini(build_prompt(article)).strip()
            # 番号付きリスト形式が返ってきた場合の除去
            response_text = re.sub(r"^\d+[\.\)]\s+", "", response_text)

            if response_text and len(response_text) >= 80:
                if bucket == "articles":
                    articles[orig_idx]["summary"] = response_text
                else:
                    trending[orig_idx]["summary"] = response_text
                updated += 1
                print(f"    ✓ {len(response_text)}文字: {response_text[:60]}...")
            else:
                print(f"    ⚠ スキップ（{len(response_text)}文字）: {response_text[:60]}")

            time.sleep(0.3)  # レート制限対策

        except urllib.error.HTTPError as e:
            print(f"    ❌ HTTPエラー {e.code}: {e.read().decode()[:100]}")
        except Exception as e:
            print(f"    ❌ エラー: {e}")

    if updated > 0:
        data["articles"] = articles
        data["trending"] = trending
        with open(ARTICLES_JSON, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
        print(f"\n✅ {updated}件を更新して articles.json を保存しました")
    else:
        print("\n⚠ 更新件数0件。articles.json は変更なし")


if __name__ == "__main__":
    main()
