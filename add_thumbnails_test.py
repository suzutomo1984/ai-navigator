"""
テスト用: articles.jsonの最新10件にOGP画像URLを付与する
"""
import json
import urllib.request
import re

def get_ogp_image(url):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=8) as res:
            html = res.read().decode("utf-8", errors="ignore")
        m = re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']', html)
        if not m:
            m = re.search(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']', html)
        return m.group(1) if m else None
    except Exception as e:
        print(f"  NG: {e}")
        return None

INPUT = "C:/Users/moyam/OneDrive/ドキュメント/Obsidian保管庫/ai-navigator/articles.json"

with open(INPUT, encoding="utf-8") as f:
    data = json.load(f)

articles = data["articles"]
# 最新10件（日付降順）
targets = sorted(articles, key=lambda a: a["date"], reverse=True)[:10]

print(f"=== {len(targets)}件のOGP取得開始 ===")
count_ok = 0
for a in targets:
    url = a.get("url", "")
    if not url.startswith("http"):
        print(f"  SKIP (no url): {a['title'][:40]}")
        continue
    print(f"  取得中: {url[:60]}")
    thumb = get_ogp_image(url)
    if thumb:
        a["thumbnail"] = thumb
        count_ok += 1
        print(f"  -> OK: {thumb[:60]}")
    else:
        print(f"  -> なし")

with open(INPUT, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print(f"\n✅ 完了: {count_ok}/{len(targets)}件取得成功")
