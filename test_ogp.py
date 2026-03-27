import urllib.request
import re

urls = [
    "https://zenn.dev/zaico/articles/d6b882c78fe4b3",
    "https://qiita.com/hirokidaichi/items/243bd176b84900f4cc0d",
    "https://claude.com/blog/complete-guide-to-building-skills-for-claude",
    "https://zenn.dev/nrs/articles/ea37ed55b8704a",
    "https://openai.com/index/gpt-4o/",
]

def get_ogp_image(url):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=8) as res:
            html = res.read().decode("utf-8", errors="ignore")
        # property="og:image" content="..."
        m = re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']', html)
        if not m:
            # content="..." property="og:image"
            m = re.search(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']', html)
        return m.group(1) if m else None
    except Exception as e:
        return f"ERROR: {e}"

for url in urls:
    result = get_ogp_image(url)
    print(f"{'OK' if result and not result.startswith('ERROR') else 'NG'}: {str(result)[:80]}")
    print(f"   <- {url[:60]}")
    print()
