"""Phase 3 GitHub Trending cache and fallback regression tests."""

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

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
            "jaName": "AIリポジトリ要約",
            "workUse": "AI開発の調査を助けます。",
            "audience": "developer",
            "aiRelated": True,
        })
        cache = parse_news.build_trending_cache([cached])
        current = repo("owner/repo")

        parse_news.enrich_trending_with_github_api([current], cache)

        self.assertEqual(set(cache), {"owner/repo"})
        self.assertEqual(current["summary"], "日本語の要約です")
        self.assertEqual(current["stars"], 123)
        self.assertEqual(current["jaName"], "AIリポジトリ要約")
        self.assertEqual(current["audience"], "developer")
        self.assertIs(current["aiRelated"], True)

    def test_gemini_adds_reader_fields_in_one_request_and_keeps_existing_summary(self) -> None:
        current = repo("owner/repo", "既存の要約はそのまま残します")
        current["githubDescription"] = "An AI agent management app"
        response_text = [{
            "index": 1,
            "summary": "生成側の要約",
            "jaName": "AIエージェント管理アプリ",
            "workUse": "複数の業務AIを一か所で管理できます。",
            "audience": "install",
            "aiRelated": True,
        }]
        response = MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps({
            "candidates": [{"content": {"parts": [{"text": json.dumps(response_text, ensure_ascii=False)}]}}]
        }).encode("utf-8")

        with patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}), patch.object(
            parse_news.urllib.request, "urlopen", return_value=response
        ) as urlopen:
            parse_news.translate_trending_descriptions([current])

        self.assertEqual(urlopen.call_count, 1)
        self.assertEqual(current["summary"], "既存の要約はそのまま残します")
        self.assertEqual(current["jaName"], "AIエージェント管理アプリ")
        self.assertEqual(current["workUse"], "複数の業務AIを一か所で管理できます。")
        self.assertEqual(current["audience"], "install")
        self.assertIs(current["aiRelated"], True)

    def test_incomplete_gemini_output_keeps_legacy_summary_without_new_fields(self) -> None:
        current = repo("owner/repo")
        current["githubDescription"] = "A useful tool"
        incomplete = [{"index": 1, "summary": "日本語の既存形式要約"}]
        response = MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps({
            "candidates": [{"content": {"parts": [{"text": json.dumps(incomplete, ensure_ascii=False)}]}}]
        }).encode("utf-8")

        with patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}), patch.object(
            parse_news.urllib.request, "urlopen", return_value=response
        ):
            parse_news.translate_trending_descriptions([current])

        self.assertEqual(current["summary"], "日本語の既存形式要約")
        self.assertFalse(any(field in current for field in ("jaName", "workUse", "audience", "aiRelated")))

    def test_malformed_gemini_output_falls_back_without_raising(self) -> None:
        current = repo("owner/repo")
        current["githubDescription"] = "A useful tool"
        response = MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps({
            "candidates": [{"content": {"parts": [{"text": "{broken json"}]}}]
        }).encode("utf-8")

        with patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}), patch.object(
            parse_news.urllib.request, "urlopen", return_value=response
        ):
            parse_news.translate_trending_descriptions([current])

        self.assertEqual(current["summary"], "")
        self.assertFalse(any(field in current for field in ("jaName", "workUse", "audience", "aiRelated")))

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
