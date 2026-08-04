"""Phase 3 GitHub Trending cache and fallback regression tests."""

import sys
import unittest
from pathlib import Path

# tests/ から直接実行しても親の parse_news.py を import できるようにする
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import parse_news


def repo(name: str, summary: str = "", date: str = "2026-08-05") -> dict:
    return {
        "title": name,
        "url": f"https://github.com/{name}",
        "date": date,
        "summary": summary,
    }


class Phase3TrendingTests(unittest.TestCase):
    def test_cache_key_is_normalized_and_summary_is_restored(self) -> None:
        cached = repo("Owner/Repo", "日本語の要約です")
        cached.update({
            "stars": 123,
            "forks": 4,
            "language": "Python",
            "githubDescription": "An English description",
        })
        cache = parse_news.build_trending_cache([cached])
        current = repo("owner/repo")

        parse_news.enrich_trending_with_github_api([current], cache)

        self.assertEqual(set(cache), {"owner/repo"})
        self.assertEqual(current["summary"], "日本語の要約です")
        self.assertEqual(current["stars"], 123)

    def test_fewer_than_five_keeps_previous_snapshot_unchanged(self) -> None:
        previous = [repo(f"owner/old-{i}", "以前の日本語要約") for i in range(5)]
        partial = [repo(f"owner/new-{i}", "新しい日本語要約") for i in range(4)]

        selected, status = parse_news.select_trending_snapshot(
            partial, previous, "2026-08-05"
        )

        self.assertIs(selected, previous)
        self.assertIn("前回値を維持", status)

    def test_incomplete_summaries_keep_last_complete_five(self) -> None:
        previous = [repo(f"owner/old-{i}", "以前の日本語要約") for i in range(5)]
        current = [repo(f"owner/new-{i}", "新しい日本語要約") for i in range(5)]
        current[2]["summary"] = ""

        selected, status = parse_news.select_trending_snapshot(
            current, previous, "2026-08-05"
        )

        self.assertIs(selected, previous)
        self.assertIn("前回正常値を維持", status)

    def test_initial_incomplete_summaries_use_pending_snapshot(self) -> None:
        current = [repo(f"owner/new-{i}") for i in range(5)]

        selected, status = parse_news.select_trending_snapshot(
            current, [], "2026-08-05"
        )

        self.assertEqual(selected[:5], current)
        self.assertIn("準備中表示", status)


if __name__ == "__main__":
    unittest.main()
