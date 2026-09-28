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
        prompt = json.loads(urlopen.call_args.args[0].data)["contents"][0]["parts"][0]["text"]
        self.assertIn("2文・60〜100字", prompt)
        self.assertIn("1〜2文・40〜80字", prompt)
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

    def test_fewer_than_ten_keeps_previous_snapshot_unchanged(self) -> None:
        previous = [repo(f"owner/old-{i}", "以前の日本語要約") for i in range(10)]
        partial = [repo(f"owner/new-{i}", "新しい日本語要約") for i in range(9)]

        selected, status = parse_news.select_trending_snapshot(
            partial, previous, "2026-08-05"
        )

        self.assertIs(selected, previous)
        self.assertIn("前回値を維持", status)

    def test_incomplete_display_content_keeps_last_complete_ten(self) -> None:
        previous = [repo(f"owner/old-{i}", "以前の日本語要約") for i in range(10)]
        current = [repo(f"owner/new-{i}", "新しい日本語要約") for i in range(10)]
        current[2]["summary"] = ""

        selected, status = parse_news.select_trending_snapshot(
            current, previous, "2026-08-05"
        )

        self.assertIs(selected, previous)
        self.assertIn("前回正常値を維持", status)

    def test_initial_incomplete_summaries_use_pending_snapshot(self) -> None:
        current = [repo(f"owner/new-{i}") for i in range(10)]

        selected, status = parse_news.select_trending_snapshot(
            current, [], "2026-08-05"
        )

        self.assertEqual(selected[:10], current)
        self.assertIn("準備中表示", status)

    def test_ten_displayable_ai_repositories_are_adopted_and_non_ai_are_skipped(self) -> None:
        current = [repo(f"owner/new-{i}", "日本語の要約") for i in range(10)]
        current[0]["aiRelated"] = False
        current.append(repo("owner/extra", "別の日本語要約"))

        selected, status = parse_news.select_trending_snapshot(
            current, [], "2026-08-05"
        )

        self.assertIs(selected[0], current[0])
        self.assertIn("新10件を採用", status)

    def test_display_requires_summary_or_japanese_name(self) -> None:
        self.assertFalse(parse_news.has_trending_display_content(repo("owner/empty")))
        self.assertTrue(parse_news.has_trending_display_content({"jaName": "ツール名"}))
        self.assertTrue(parse_news.has_trending_display_content({"summary": "説明"}))

    def test_fetch_uses_weekly_feed_as_unique_candidates_after_daily(self) -> None:
        def rss(names: list[str]) -> bytes:
            items = "".join(
                f"<item><title>{name}</title><link>https://github.com/{name}</link></item>"
                for name in names
            )
            return f"<rss><channel>{items}</channel></rss>".encode()

        daily = [f"daily/repo-{i}" for i in range(1, 10)]
        weekly = ["DAILY/REPO-1", "daily/repo-2"] + [f"weekly/repo-{i}" for i in range(1, 10)]
        responses = []
        for content in (rss(daily), rss(weekly)):
            response = MagicMock()
            response.__enter__.return_value.read.return_value = content
            responses.append(response)

        with patch.object(parse_news.urllib.request, "urlopen", side_effect=responses) as urlopen:
            fetched = parse_news.fetch_github_trending(limit=15)

        self.assertEqual(urlopen.call_count, 2)
        self.assertIn("/daily/", urlopen.call_args_list[0].args[0].full_url)
        self.assertIn("/weekly/", urlopen.call_args_list[1].args[0].full_url)
        self.assertEqual(len(fetched), 15)
        self.assertEqual(fetched[0]["title"], daily[0])
        self.assertEqual(len({row["url"].lower() for row in fetched}), 15)


if __name__ == "__main__":
    unittest.main()
