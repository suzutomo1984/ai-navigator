"""Top stats bar and site-count regression tests."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import parse_news


class TopStatsTests(unittest.TestCase):
    def test_stats_context_uses_meta_counts_and_date_range(self) -> None:
        dates = [{"date": "2026-08-11"}, {"date": "2026-08-10"}]
        meta = {
            "totalArticles": 57,
            "officialCount": 3,
            "dates": dates,
            "dateRange": {"from": "2026-08-10", "to": "2026-08-11"},
        }

        self.assertEqual(
            parse_news._stats_context(meta, dates),
            (57, 3, 2, "2026/8/10〜8/11"),
        )

    def test_update_is_idempotent_without_legacy_top_pick_block(self) -> None:
        source = """<!-- TOP_STATS_BAR:start -->
old
<!-- TOP_STATS_BAR:end -->
<!-- TOP_STATS_COUNT:start -->
old
<!-- TOP_STATS_COUNT:end -->
"""
        dates = [{"date": "2026-08-11"}]
        meta = {
            "totalArticles": 57,
            "officialCount": 3,
            "dates": dates,
            "dateRange": {"from": "2026-08-11", "to": "2026-08-11"},
        }

        with tempfile.TemporaryDirectory() as directory:
            index_file = Path(directory) / "index.html"
            index_file.write_text(source, encoding="utf-8")
            with patch.object(parse_news, "INDEX_FILE", index_file):
                parse_news.update_top_stats(meta, dates)
                first = index_file.read_text(encoding="utf-8")
                parse_news.update_top_stats(meta, dates)
                second = index_file.read_text(encoding="utf-8")

        self.assertEqual(first, second)
        self.assertIn("<dd>57本</dd>", first)
        self.assertIn("累計記事数", first)
        self.assertNotIn("TOP_HERO_STATS", first)
        self.assertNotIn("今日の全57本を見る", first)


if __name__ == "__main__":
    unittest.main()
