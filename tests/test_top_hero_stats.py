"""Top hero daily-count and PICK-count regression tests."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import parse_news


def article(index: int, date: str, *, is_pick: bool = False, valid: bool = True) -> dict:
    return {
        "url": f"https://example.com/{index}" if valid else f"invalid-{index}",
        "date": date,
        "isPick": is_pick,
        "pickPriority": "must-read" if is_pick and index % 2 == 0 else None,
    }


class TopHeroStatsTests(unittest.TestCase):
    def test_latest_day_uses_valid_articles_and_real_pick_count(self) -> None:
        articles = [article(i, "2026-08-11", is_pick=i < 4) for i in range(57)]
        articles += [article(100, "2026-08-11", valid=False)]
        articles += [article(200, "2026-08-10", is_pick=True)]

        self.assertEqual(
            parse_news._top_hero_context({"articles": articles}),
            ("2026-08-11", 57, 4),
        )

    def test_pick_count_is_not_fixed_to_four(self) -> None:
        articles = [article(i, "2026-08-07", is_pick=i < 3) for i in range(91)]

        self.assertEqual(
            parse_news._top_hero_context({"articles": articles}),
            ("2026-08-07", 91, 3),
        )

    def test_update_is_idempotent_and_updates_both_hero_numbers(self) -> None:
        source = """<!-- JSON_LD:start -->\njson\n<!-- JSON_LD:end -->
<!-- TOP_STATS_BAR:start -->\nold\n<!-- TOP_STATS_BAR:end -->
<!-- TOP_STATS_COUNT:start -->\nold\n<!-- TOP_STATS_COUNT:end -->
<!-- TOP_HERO_STATS:start -->\nold\n<!-- TOP_HERO_STATS:end -->
"""
        articles = [article(i, "2026-08-11", is_pick=i < 4) for i in range(57)]
        meta = {
            "articles": articles,
            "totalArticles": 57,
            "officialCount": 0,
            "dates": [{"date": "2026-08-11"}],
        }

        with tempfile.TemporaryDirectory() as directory:
            index_file = Path(directory) / "index.html"
            index_file.write_text(source, encoding="utf-8")
            with patch.object(parse_news, "INDEX_FILE", index_file):
                parse_news.update_top_stats(meta, meta["dates"])
                first = index_file.read_text(encoding="utf-8")
                parse_news.update_top_stats(meta, meta["dates"])
                second = index_file.read_text(encoding="utf-8")

        self.assertEqual(first, second)
        self.assertIn("毎日2回、57本のAI記事を集めて、4本を選びました。", first)
        self.assertIn("今日の全57本を見る", first)
        self.assertIn('class="top-pick-summary"', first)
        self.assertIn('class="top-pick-actions"', first)
        self.assertNotIn("このサイトの作り方", first)


if __name__ == "__main__":
    unittest.main()
