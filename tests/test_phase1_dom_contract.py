"""Static regression checks for the Phase 1 DOM compatibility contract."""

import re
import unittest
from html.parser import HTMLParser
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_JS = (ROOT / "app.js").read_text(encoding="utf-8")
NEWS_HTML = (ROOT / "news.html").read_text(encoding="utf-8")


class IdCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ids: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        for name, value in attrs:
            if name == "id" and value is not None:
                self.ids.append(value)


def required_ids() -> list[str]:
    match = re.search(
        r"const REQUIRED_DOM_IDS = Object\.freeze\(\[(.*?)\]\);",
        APP_JS,
        flags=re.DOTALL,
    )
    if not match:
        raise AssertionError("REQUIRED_DOM_IDS was not found")
    return re.findall(r'"([^"]+)"', match.group(1))


class Phase1DomContractTests(unittest.TestCase):
    def test_required_ids_exist_exactly_once(self) -> None:
        parser = IdCollector()
        parser.feed(NEWS_HTML)
        for element_id in required_ids():
            with self.subTest(element_id=element_id):
                self.assertEqual(parser.ids.count(element_id), 1)

    def test_literal_id_lookups_use_guarded_helper(self) -> None:
        self.assertNotRegex(APP_JS, r'document\.getElementById\(["\']')
        referenced_ids = set(re.findall(r'getDomById\("([^"]+)"\)', APP_JS))
        self.assertLessEqual(referenced_ids, set(required_ids()))

    def test_tab_events_are_scoped_to_header_data_tabs(self) -> None:
        self.assertNotIn('document.querySelectorAll(".tab-btn")', APP_JS)
        self.assertGreaterEqual(
            APP_JS.count('document.querySelectorAll("#tabbar .tab-btn[data-tab]")'),
            2,
        )

    def test_filter_scroll_uses_marker_with_top_fallback(self) -> None:
        render_block = re.search(
            r"function render\(resetScroll = false\) \{(.*?)const filtered = filterArticles\(\);",
            APP_JS,
            flags=re.DOTALL,
        )
        self.assertIsNotNone(render_block)
        block = render_block.group(1)
        self.assertIn('getDomById("article-list-start")', block)
        self.assertIn('scrollIntoView({ block: "start" })', block)
        self.assertIn("window.scrollTo(0, 0)", block)


if __name__ == "__main__":
    unittest.main()
