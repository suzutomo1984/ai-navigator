"""Regression tests for incomplete tech-news headings without source URLs."""

import io
import sys
from contextlib import redirect_stdout
from io import StringIO

_pytest_stdout = sys.stdout
sys.stdout = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
try:
    import parse_news
finally:
    sys.stdout = _pytest_stdout


def write_news(path, articles: str):
    path.write_text(
        "## ⚡ 業務効率化\n\n" + articles,
        encoding="utf-8",
    )
    return path


def test_parse_tech_news_keeps_url_article_and_skips_heading_only(tmp_path):
    news_file = write_news(
        tmp_path / "2026-09-27_テックニュース.md",
        """### 1. URL付きの記事
- ソース: [Example](https://example.com/article)
- 要約: 記事の要約です。

### 2. 見出しだけの記事
""",
    )
    log = StringIO()

    with redirect_stdout(log):
        articles = parse_news.parse_tech_news(news_file, "2026-09-27")

    assert len(articles) == 1
    assert articles[0]["title"] == "URL付きの記事"
    assert articles[0]["url"] == "https://example.com/article"
    assert "URLなし項目をスキップ: 1件" in log.getvalue()


def test_parse_tech_news_returns_no_articles_for_heading_only(tmp_path):
    news_file = write_news(
        tmp_path / "2026-09-27_テックニュース.md",
        "### 1. 見出しだけの記事\n",
    )

    assert parse_news.parse_tech_news(news_file, "2026-09-27") == []


def test_existing_url_article_keeps_its_added_at(tmp_path):
    news_file = write_news(
        tmp_path / "2026-09-27_テックニュース.md",
        """### 1. 既存記事
- ソース: [Example](https://example.com/existing)
""",
    )
    articles = parse_news.parse_tech_news(news_file, "2026-09-27")
    previous_added_at = "2026-09-26T08:11:57+09:00"

    new_count = parse_news.apply_existing_added_at(
        articles,
        {"https://example.com/existing": previous_added_at},
    )

    assert new_count == 0
    assert articles[0]["addedAt"] == previous_added_at
