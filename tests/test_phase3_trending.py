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

    def test_missing_reader_fields_are_retried_once_for_only_those_repositories(self) -> None:
        complete = repo("owner/complete")
        complete["githubDescription"] = "An AI agent management app"
        dropped = repo("obra/superpowers")
        dropped["githubDescription"] = "An agentic skills framework"

        def gemini(rows: list[dict]) -> MagicMock:
            response = MagicMock()
            response.__enter__.return_value.read.return_value = json.dumps({
                "candidates": [{"content": {"parts": [{"text": json.dumps(rows, ensure_ascii=False)}]}}]
            }).encode("utf-8")
            return response

        fields = {"workUse": "業務AIを作る時に使います。", "audience": "developer", "aiRelated": True}
        first = gemini([
            {"index": 1, "summary": "管理アプリです", "jaName": "AI管理アプリ", **fields},
            {"index": 2, "summary": "スキル集です", "jaName": "AIスキル集", **fields, "aiRelated": "true"},
        ])
        second = gemini([{"index": 1, "summary": "別の要約", "jaName": "AIスキル開発基盤", **fields}])

        with patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}), patch.object(
            parse_news.urllib.request, "urlopen", side_effect=[first, second]
        ) as urlopen:
            parse_news.translate_trending_descriptions([complete, dropped])

        self.assertEqual(urlopen.call_count, 2)
        retry_prompt = json.loads(urlopen.call_args.args[0].data)["contents"][0]["parts"][0]["text"]
        self.assertIn("1. [obra/superpowers]", retry_prompt)
        self.assertNotIn("owner/complete", retry_prompt)
        self.assertEqual(dropped["summary"], "スキル集です")
        self.assertEqual(dropped["jaName"], "AIスキル開発基盤")
        self.assertIs(dropped["aiRelated"], True)
        self.assertEqual(complete["jaName"], "AI管理アプリ")

    def test_same_day_rerun_keeps_dropped_repositories_and_their_days(self) -> None:
        # 朝の実行で今日付けになった前日分（2日目）と、それより前の履歴
        morning = [repo(f"owner/morning-{i}", "朝の要約", "2026-10-03") for i in range(3)]
        for row in morning:
            row["trendingDays"] = 2
        older = repo("owner/older", "古い要約", "2026-09-23")
        older["trendingDays"] = 1
        evening = [repo("owner/morning-0", "朝の要約", "2026-10-03"),
                   repo("owner/older", "古い要約", "2026-10-03"),
                   repo("owner/new", "新しい要約", "2026-10-03")]

        merged = parse_news.merge_trending_history(evening, morning + [older], "2026-10-03")

        self.assertEqual([row["title"] for row in merged], [
            "owner/morning-0", "owner/older", "owner/new", "owner/morning-1", "owner/morning-2",
        ])
        # morning-0 は同日なので同じ値、older は 9/23 から間が空いているので1
        self.assertEqual([row["trendingDays"] for row in merged[:3]], [2, 1, 1])

    def test_next_day_increments_days_from_latest_entry(self) -> None:
        yesterday = repo("owner/tool", "要約", "2026-10-02")
        yesterday["trendingDays"] = 3
        legacy = repo("owner/legacy", "要約", "2026-04-07")
        today = [repo("Owner/Tool", "要約", "2026-10-03"), repo("owner/legacy", "要約", "2026-10-03")]

        merged = parse_news.merge_trending_history(today, [yesterday, legacy], "2026-10-03")

        self.assertEqual(len(merged), 2)
        # 昨日から続く分は+1、間が空いた旧データは1から数え直す
        self.assertEqual([row["trendingDays"] for row in merged], [4, 1])

    def test_days_continue_from_latest_snapshot_by_calendar_gap(self) -> None:
        def days_after(previous_date: str, previous_days: int, snapshot_date: str) -> int:
            previous = repo("owner/tool", "要約", previous_date)
            previous["trendingDays"] = previous_days
            # 直近スナップショット（最新日付）を別のリポジトリで表す
            snapshot = repo("owner/other", "要約", snapshot_date)
            current = repo("owner/tool", "要約", "2026-10-03")
            parse_news.merge_trending_history([current], [snapshot, previous], "2026-10-03")
            return current["trendingDays"]

        # ① スナップショット10/01に居て、RSS未更新の10/02を挟んで10/03に継続 → +2
        self.assertEqual(days_after("2026-10-01", 3, "2026-10-01"), 5)
        # 昨日のスナップショットに居た → +1
        self.assertEqual(days_after("2026-10-02", 2, "2026-10-02"), 3)
        # ② 直近スナップショット(10/02)に居ない再登場 → 1
        self.assertEqual(days_after("2026-10-01", 3, "2026-10-02"), 1)
        # ③ 同じ日の再実行 → 同じ値
        self.assertEqual(days_after("2026-10-03", 4, "2026-10-03"), 4)
        # 日付が読めない → 1
        self.assertEqual(days_after("not-a-date", 4, "not-a-date"), 1)

    def test_month_boundary_counts_as_yesterday(self) -> None:
        previous = repo("owner/tool", "要約", "2026-09-30")
        previous["trendingDays"] = 2
        current = repo("owner/tool", "要約", "2026-10-01")

        parse_news.merge_trending_history([current], [previous], "2026-10-01")

        self.assertEqual(current["trendingDays"], 3)

    def test_unchanged_rss_set_keeps_dates_and_days(self) -> None:
        latest = [repo(f"owner/r-{i}", "要約", "2026-10-02") for i in range(6)]
        for row in latest:
            row["trendingDays"] = 2
        older = repo("owner/old", "要約", "2026-09-23")
        existing = latest + [older]
        # 同じ集合を順序違い・大文字違いで取得（翌朝の再実行を想定）
        fetched = [repo(f"Owner/R-{i}", "", "2026-10-03") for i in reversed(range(6))]

        self.assertTrue(parse_news.is_trending_snapshot_unchanged(fetched, existing))
        # 片方のフィードが取れず件数が減っただけでも未更新扱い
        self.assertTrue(parse_news.is_trending_snapshot_unchanged(fetched[:5], existing))
        self.assertEqual(parse_news.latest_trending_snapshot(existing), latest)

        existing_json = json.dumps(existing, ensure_ascii=False)
        with patch.object(parse_news, "translate_trending_descriptions") as translate, patch.object(
            parse_news, "enrich_trending_with_github_api"
        ) as enrich:
            output = parse_news.build_trending_output(fetched, existing, "2026-10-03")

        self.assertIs(output, existing)
        enrich.assert_not_called()
        translate.assert_called_once_with(latest)  # 欠けた読者向け項目の補完だけは続ける
        self.assertEqual(json.dumps(output, ensure_ascii=False), existing_json)
        self.assertEqual({row["date"] for row in latest}, {"2026-10-02"})
        self.assertEqual({row["trendingDays"] for row in latest}, {2})

    def test_partially_replaced_rss_is_treated_as_update(self) -> None:
        existing = [repo(f"owner/r-{i}", "要約", "2026-10-02") for i in range(6)]
        fetched = [repo(f"owner/r-{i}", "新しい要約", "2026-10-03") for i in range(5)]
        fetched.append(repo("owner/brand-new", "新しい要約", "2026-10-03"))

        self.assertFalse(parse_news.is_trending_snapshot_unchanged(fetched, existing))
        with patch.object(parse_news, "translate_trending_descriptions"), patch.object(
            parse_news, "enrich_trending_with_github_api"
        ):
            output = parse_news.build_trending_output(fetched, existing, "2026-10-03")
        self.assertEqual(output[0]["date"], "2026-10-03")
        self.assertEqual([row["trendingDays"] for row in output[:6]], [2, 2, 2, 2, 2, 1])
        self.assertFalse(parse_news.is_trending_snapshot_unchanged(fetched, []))
        self.assertFalse(parse_news.is_trending_snapshot_unchanged([], existing))

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

    def test_four_displayable_repositories_keep_previous_snapshot_unchanged(self) -> None:
        previous = [repo(f"owner/old-{i}", "以前の日本語要約") for i in range(7)]
        partial = [repo(f"owner/new-{i}", "新しい日本語要約") for i in range(4)]

        selected, status = parse_news.select_trending_snapshot(
            partial, previous, "2026-08-05"
        )

        self.assertIs(selected, previous)
        self.assertIn("表示可能4件 (<5)・前回値を維持", status)

    def test_seven_displayable_repositories_adopt_today_snapshot(self) -> None:
        previous = [repo(f"owner/old-{i}", "以前の日本語要約", "2026-08-04") for i in range(10)]
        current = [repo(f"owner/new-{i}", "新しい日本語要約") for i in range(7)]

        selected, status = parse_news.select_trending_snapshot(
            current, previous, "2026-08-05"
        )

        self.assertIsNot(selected, previous)
        self.assertEqual(selected[:7], current)
        self.assertEqual(sum(
            1 for row in selected
            if row.get("date") == "2026-08-05"
            and row.get("aiRelated") is not False
            and parse_news.has_trending_display_content(row)
        ), 7)
        self.assertIn("新7件を採用", status)

    def test_more_than_ten_displayable_repositories_are_capped_for_display(self) -> None:
        current = [repo(f"owner/new-{i}", "新しい日本語要約") for i in range(12)]

        selected, status = parse_news.select_trending_snapshot(
            current, [], "2026-08-05"
        )

        self.assertEqual(selected[:12], current)
        self.assertEqual(len([
            row for row in selected[:parse_news.TRENDING_DISPLAY_COUNT]
            if row.get("aiRelated") is not False
            and parse_news.has_trending_display_content(row)
        ]), 10)
        self.assertIn("新10件を採用", status)

    def test_nine_displayable_repositories_adopt_today_snapshot(self) -> None:
        previous = [repo(f"owner/old-{i}", "以前の日本語要約") for i in range(10)]
        current = [repo(f"owner/new-{i}", "新しい日本語要約") for i in range(10)]
        current[2]["summary"] = ""

        selected, status = parse_news.select_trending_snapshot(
            current, previous, "2026-08-05"
        )

        self.assertIsNot(selected, previous)
        self.assertEqual(selected[:10], current)
        self.assertIn("新9件を採用", status)

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
