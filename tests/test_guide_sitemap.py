"""Sitemap entries for handwritten guide pages under guide/<slug>.html."""

import io
import json
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

# parse_news は import 時に sys.stdout を包む。pytest の capture を壊さないよう、
# tests/test_parse_news_empty_url.py と同じくダミーへ向けてから戻す。
_pytest_stdout = sys.stdout
sys.stdout = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
try:
    import parse_news
finally:
    sys.stdout = _pytest_stdout


FIXED_LOCS = [
    "https://ai-navigator.dev/",
    "https://ai-navigator.dev/news",
    "https://ai-navigator.dev/official",
    "https://ai-navigator.dev/about",
    "https://ai-navigator.dev/privacy",
    "https://ai-navigator.dev/daily/",
]

FIXED_META = {
    "https://ai-navigator.dev/": ("daily", "1.0"),
    "https://ai-navigator.dev/news": ("daily", "0.9"),
    "https://ai-navigator.dev/official": ("daily", "0.8"),
    "https://ai-navigator.dev/about": ("monthly", "0.6"),
    "https://ai-navigator.dev/privacy": ("yearly", "0.3"),
    "https://ai-navigator.dev/daily/": ("daily", "0.8"),
}


def _rows(path: Path) -> list[dict[str, str]]:
    rows = []
    for node in ET.parse(path).getroot():
        row = {}
        for child in node:
            row[child.tag.rsplit("}", 1)[-1]] = child.text or ""
        rows.append(row)
    return rows


def _guide_html(
    slug: str,
    *,
    canonical: str | None = None,
    modified: str | None = "2026-04-15",
    published: str | None = None,
    include_canonical: bool = True,
    extra_head: str = "",
) -> str:
    if canonical is None:
        canonical = f"https://ai-navigator.dev/guide/{slug}"
    metas = []
    if published is not None:
        metas.append(f'<meta property="article:published_time" content="{published}">')
    if modified is not None:
        metas.append(f'<meta property="article:modified_time" content="{modified}">')
    canonical_tag = f'<link rel="canonical" href="{canonical}">' if include_canonical else ""
    return (
        "<!DOCTYPE html><html lang=\"ja\"><head><meta charset=\"UTF-8\">"
        f"{extra_head}{''.join(metas)}{canonical_tag}<title>{slug}</title>"
        f"</head><body><p>{slug}</p></body></html>"
    )


class GuideSitemapTests(unittest.TestCase):
    def _generate(self, root: Path, editions: list[dict] | None = None, guide: Path | None = None) -> tuple[list[dict[str, str]], str]:
        sitemap_path = root / "sitemap.xml"
        if editions is None:
            editions_path = root / "missing-editions.json"
        else:
            editions_path = root / "editions.json"
            editions_path.write_text(json.dumps(editions), encoding="utf-8")
        if guide is None:
            guide = root / "guide"
        log = StringIO()
        with patch.object(parse_news, "SITEMAP_FILE", sitemap_path), redirect_stdout(log):
            parse_news.generate_sitemap(editions_path, guide)
        return _rows(sitemap_path), log.getvalue()

    def test_missing_guide_dir_keeps_six_fixed_pages(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            rows, log = self._generate(root, guide=root / "no-guide-here")
        self.assertEqual([row["loc"] for row in rows], FIXED_LOCS)
        self.assertEqual(log, "")
        for row in rows:
            self.assertNotIn(".html", row["loc"])
            self.assertEqual(
                (row["changefreq"], row["priority"]),
                FIXED_META[row["loc"]],
            )

    def test_empty_guide_dir_keeps_fixed_sitemap_shape(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            guide = root / "guide"
            guide.mkdir()
            (guide / "notes.txt").write_text("not a page", encoding="utf-8")
            rows, log = self._generate(root, guide=guide)
            text = (root / "sitemap.xml").read_text(encoding="utf-8")
        self.assertEqual([row["loc"] for row in rows], FIXED_LOCS)
        self.assertEqual(log, "")
        self.assertIn("    <priority>0.8</priority>\n  </url>\n\n</urlset>", text)
        self.assertFalse(any(".html" in row["loc"] for row in rows))

    def test_guide_page_uses_modified_time_and_extensionless_url(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            guide = root / "guide"
            guide.mkdir()
            (guide / "pdf-unreadable.html").write_text(
                _guide_html(
                    "pdf-unreadable",
                    modified="2026-04-15T08:11:00+09:00",
                    published="2026-01-01",
                ),
                encoding="utf-8",
            )
            rows, log = self._generate(root, guide=guide)
        locs = [row["loc"] for row in rows]
        self.assertEqual(locs[:6], FIXED_LOCS)
        guide_rows = rows[6:]
        self.assertEqual(
            guide_rows,
            [{
                "loc": "https://ai-navigator.dev/guide/pdf-unreadable",
                "lastmod": "2026-04-15",
                "changefreq": "monthly",
                "priority": "0.6",
            }],
        )
        self.assertNotIn(".html", guide_rows[0]["loc"])
        self.assertIn("悩みごとページをsitemapに追加: 1件", log)
        self.assertNotIn("除外", log)

    def test_published_time_is_used_only_when_modified_time_is_absent(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            guide = root / "guide"
            guide.mkdir()
            (guide / "scan-blank.html").write_text(
                _guide_html("scan-blank", modified=None, published="2025-12-31T23:59:00Z"),
                encoding="utf-8",
            )
            rows, log = self._generate(root, guide=guide)
        self.assertEqual(rows[-1]["loc"], "https://ai-navigator.dev/guide/scan-blank")
        self.assertEqual(rows[-1]["lastmod"], "2025-12-31")
        self.assertNotIn(".html", rows[-1]["loc"])
        self.assertNotIn("除外", log)

    def test_missing_dates_are_omitted_with_warning_and_build_continues(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            guide = root / "guide"
            guide.mkdir()
            (guide / "undated.html").write_text(
                _guide_html("undated", modified=None, published=None),
                encoding="utf-8",
            )
            (guide / "kept.html").write_text(
                _guide_html("kept", modified="2026-02-02"),
                encoding="utf-8",
            )
            rows, log = self._generate(root, guide=guide)
        locs = [row["loc"] for row in rows]
        self.assertIn("https://ai-navigator.dev/guide/kept", locs)
        self.assertNotIn("https://ai-navigator.dev/guide/undated", locs)
        self.assertEqual(locs[:6], FIXED_LOCS)
        self.assertIn("undated.html", log)
        self.assertIn("article:modified_time も article:published_time もありません", log)
        self.assertNotIn("kept.html", log)

    def test_unreadable_modified_time_does_not_fall_back_to_published_time(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            guide = root / "guide"
            guide.mkdir()
            (guide / "bad-date.html").write_text(
                _guide_html("bad-date", modified="2026-02-31", published="2026-02-01"),
                encoding="utf-8",
            )
            rows, log = self._generate(root, guide=guide)
        self.assertEqual([row["loc"] for row in rows], FIXED_LOCS)
        self.assertIn("article:modified_time の日付を読めません", log)
        self.assertIn("bad-date.html", log)
        self.assertNotIn("https://ai-navigator.dev/guide/bad-date", log)

    def test_missing_canonical_is_omitted_with_warning(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            guide = root / "guide"
            guide.mkdir()
            (guide / "no-canonical.html").write_text(
                _guide_html("no-canonical", include_canonical=False, modified="2026-03-03"),
                encoding="utf-8",
            )
            rows, log = self._generate(root, guide=guide)
        self.assertEqual([row["loc"] for row in rows], FIXED_LOCS)
        self.assertIn("no-canonical.html", log)
        self.assertIn("canonicalがありません", log)

    def test_canonical_must_match_extensionless_url(self) -> None:
        mismatches = {
            "with-html": "https://ai-navigator.dev/guide/with-html.html",
            "trailing-slash": "https://ai-navigator.dev/guide/trailing-slash/",
            "wrong-host": "https://example.com/guide/wrong-host",
            "http": "http://ai-navigator.dev/guide/http",
        }
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            guide = root / "guide"
            guide.mkdir()
            (guide / "matches.html").write_text(
                _guide_html("matches", modified="2026-06-06"),
                encoding="utf-8",
            )
            for slug, canonical in mismatches.items():
                (guide / f"{slug}.html").write_text(
                    _guide_html(slug, canonical=canonical, modified="2026-06-06"),
                    encoding="utf-8",
                )
            rows, log = self._generate(root, guide=guide)
        locs = [row["loc"] for row in rows]
        self.assertEqual(locs[:6], FIXED_LOCS)
        self.assertEqual(locs[6:], ["https://ai-navigator.dev/guide/matches"])
        self.assertFalse(any(loc.endswith(".html") for loc in locs))
        for slug, canonical in mismatches.items():
            self.assertNotIn(f"https://ai-navigator.dev/guide/{slug}", locs)
            self.assertIn(f"{slug}.html", log)
            self.assertIn(canonical, log)
            self.assertIn(f"https://ai-navigator.dev/guide/{slug}", log)

    def test_reversed_attribute_order_still_reads_canonical_and_lastmod(self) -> None:
        html = """<!DOCTYPE html><html><head>
        <link href="https://ai-navigator.dev/guide/ordered" rel="canonical">
        <meta content="2026-08-08T00:00:00+09:00" property="article:modified_time">
        </head><body></body></html>"""
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            guide = root / "guide"
            guide.mkdir()
            (guide / "ordered.html").write_text(html, encoding="utf-8")
            rows, log = self._generate(root, guide=guide)
        self.assertEqual(rows[-1]["loc"], "https://ai-navigator.dev/guide/ordered")
        self.assertEqual(rows[-1]["lastmod"], "2026-08-08")
        self.assertNotIn("除外", log)

    def test_underscore_template_is_excluded_without_warning(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            guide = root / "guide"
            nested = guide / "_template"
            nested.mkdir(parents=True)
            valid = _guide_html("_template", canonical="https://ai-navigator.dev/guide/_template", modified="2026-07-07")
            (guide / "_template.html").write_text(valid, encoding="utf-8")
            (guide / "_draft.html").write_text(
                _guide_html("_draft", canonical="https://ai-navigator.dev/guide/_draft", modified="2026-07-07"),
                encoding="utf-8",
            )
            (nested / "page.html").write_text(
                _guide_html("page", canonical="https://ai-navigator.dev/guide/page", modified="2026-07-07"),
                encoding="utf-8",
            )
            (guide / "real.html").write_text(_guide_html("real", modified="2026-07-01"), encoding="utf-8")
            rows, log = self._generate(root, guide=guide)
        locs = [row["loc"] for row in rows]
        self.assertEqual(locs[6:], ["https://ai-navigator.dev/guide/real"])
        self.assertNotIn("https://ai-navigator.dev/guide/_template", locs)
        self.assertNotIn("https://ai-navigator.dev/guide/_draft", locs)
        self.assertNotIn("https://ai-navigator.dev/guide/page", locs)
        self.assertNotIn("_template", log)
        self.assertNotIn("_draft", log)
        self.assertNotIn("除外", log)

    def test_editions_stay_ahead_of_guide_pages_and_keep_issue_dates(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            guide = root / "guide"
            guide.mkdir()
            (guide / "zeta.html").write_text(_guide_html("zeta", modified="2026-09-01"), encoding="utf-8")
            (guide / "alpha.html").write_text(_guide_html("alpha", modified="2026-08-02"), encoding="utf-8")
            (guide / "broken.html").write_bytes(b"\xff\xfe<html>")
            rows, log = self._generate(
                root,
                editions=[
                    {"date": "2026-09-27", "edition": "am"},
                    {"date": "2026-09-27", "edition": "pm"},
                    {"date": "not-a-date", "edition": "am"},
                ],
                guide=guide,
            )
        locs = [row["loc"] for row in rows]
        self.assertEqual(
            locs,
            FIXED_LOCS + [
                "https://ai-navigator.dev/daily/2026-09-27-am",
                "https://ai-navigator.dev/daily/2026-09-27-pm",
                "https://ai-navigator.dev/guide/alpha",
                "https://ai-navigator.dev/guide/zeta",
            ],
        )
        by_loc = {row["loc"]: row for row in rows}
        self.assertEqual(by_loc["https://ai-navigator.dev/daily/2026-09-27-am"]["lastmod"], "2026-09-27")
        self.assertEqual(by_loc["https://ai-navigator.dev/daily/2026-09-27-am"]["changefreq"], "never")
        self.assertEqual(by_loc["https://ai-navigator.dev/daily/2026-09-27-am"]["priority"], "0.7")
        self.assertEqual(by_loc["https://ai-navigator.dev/guide/alpha"]["lastmod"], "2026-08-02")
        self.assertEqual(by_loc["https://ai-navigator.dev/guide/zeta"]["lastmod"], "2026-09-01")
        self.assertFalse(any(".html" in loc for loc in locs))
        self.assertIn("broken.html", log)
        self.assertIn("読めません", log)
        self.assertIn("悩みごとページをsitemapに追加: 2件", log)

    def test_unreadable_editions_still_raises(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            bad = root / "editions.json"
            bad.write_text("{", encoding="utf-8")
            with patch.object(parse_news, "SITEMAP_FILE", root / "sitemap.xml"):
                with self.assertRaises(ValueError):
                    parse_news.generate_sitemap(bad, root / "guide")

    def test_template_documents_extensionless_canonical_and_article_dates(self) -> None:
        template = Path(__file__).resolve().parents[1] / "docs" / "guide-page-template.html"
        html = template.read_text(encoding="utf-8")
        self.assertIn('property="article:modified_time"', html)
        self.assertIn('property="article:published_time"', html)
        self.assertIn('rel="canonical" href="https://ai-navigator.dev/guide/SLUG"', html)
        self.assertIn('property="og:url" content="https://ai-navigator.dev/guide/SLUG"', html)
        self.assertNotIn("guide/SLUG.html", html)
        self.assertIn('href="/style.css"', html)
        self.assertIn('src="/ai-consult.js"', html)
        self.assertNotIn('href="style.css"', html)
        canonical, modified, published = parse_news._read_guide_meta(html)
        self.assertEqual(canonical, "https://ai-navigator.dev/guide/SLUG")
        self.assertEqual(modified, "YYYY-MM-DD")
        self.assertEqual(published, "YYYY-MM-DD")
        self.assertIsNone(parse_news._guide_day(modified or ""))


if __name__ == "__main__":
    unittest.main()
