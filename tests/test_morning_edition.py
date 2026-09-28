import json
import xml.etree.ElementTree as ET
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import Mock, patch

from daily import morning_edition as edition
import parse_news


class MorningEditionTests(unittest.TestCase):
    def test_candidate_filter_requires_batch_url_and_fresh_article_date(self):
        rows = [
            {"id": "ok", "url": "https://example.com/1", "addedAt": "2026-09-28T08:00:00+09:00", "date": "2026-09-25"},
            {"id": "no-url", "url": "", "addedAt": "2026-09-28T08:00:00+09:00", "date": "2026-09-28"},
            {"id": "old", "url": "https://example.com/old", "addedAt": "2026-09-28T08:00:00+09:00", "date": "2026-09-24"},
            {"id": "other-batch", "url": "https://example.com/2", "addedAt": "2026-09-27T08:00:00+09:00", "date": "2026-09-28"},
            {"id": "pm", "url": "https://example.com/3", "addedAt": "2026-09-28T19:00:00+09:00", "date": "2026-09-28"},
        ]
        found = edition.filter_candidates(rows, date(2026, 9, 28), "am")
        self.assertEqual([row["id"] for row in found], ["ok"])

    def test_score_formula_matches_reader_pick_weights(self):
        self.assertAlmostEqual(edition.score_candidate(0.9, 0.8, 0.2, 0.1), (0.4 * 0.9 + 0.25 * 0.8 + 0.35 * 0.8) * 0.95)

    def test_copy_lengths_are_checked(self):
        content = {"lead_line": "短い", "summary": "要点", "deep_topics": [{"text": "深掘り"}]}
        self.assertIn("15〜25字", edition.copy_length_problem(content))

    def test_gemini_timeout_is_retried_once(self):
        response = Mock()
        response.json.return_value = {"candidates": [{"content": {"parts": [{"text": '{"ok": true}'}]}}]}
        with patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}), patch.object(
            edition.requests, "post", side_effect=[edition.requests.Timeout(), response]
        ) as post:
            self.assertEqual(edition.generate_copy([], []), {"ok": True})
        self.assertEqual(post.call_count, 2)

    def test_claim_check_drops_sentence_with_unsupported_number_or_name(self):
        copy, check = edition.verify_and_filter({
            "lead_line": {"text": "OpenAIが発表した", "sources": [1], "evidence_terms": ["OpenAI"]},
            "summary": [{"text": "OpenAIの記事です。", "sources": [1], "evidence_terms": ["OpenAI"]}, {"text": "売上は99%増えた。", "sources": [1], "evidence_terms": ["99%"]}],
            "deep_topics": [{"heading": "◆一", "sentences": [{"text": "本文の説明。", "sources": [1], "evidence_terms": []}]}, {"heading": "◆二", "sentences": [{"text": "本文の説明。", "sources": [1], "evidence_terms": []}]}, {"heading": "◆三", "sentences": [{"text": "本文の説明。", "sources": [1], "evidence_terms": []}]}],
        }, ["OpenAIの記事本文と本文の説明です。"])
        self.assertNotIn("99%", copy["summary"])
        self.assertEqual(len(check["dropped_sentences"]), 1)

    def test_editions_upsert_replaces_same_issue_and_sorts_latest(self):
        rows = [{"date": "2026-09-27", "edition": "am", "generatedAt": "old"}, {"date": "2026-09-26", "edition": "pm"}]
        updated = edition.upsert_edition(rows, {"date": "2026-09-27", "edition": "am", "generatedAt": "new"})
        self.assertEqual(len(updated), 2)
        self.assertEqual(updated[0]["generatedAt"], "new")

    def test_archive_is_static_newest_first_and_marks_latest(self):
        rows = [
            {"date": "2026-09-27", "edition": "am", "leadLine": "古い号", "summaryExcerpt": "前日の要約"},
            {"date": "2026-09-28", "edition": "am", "leadLine": "最新の見出し", "summaryExcerpt": "最新の要約"},
        ]
        page = edition.render_archive_html(rows)
        self.assertNotIn("http-equiv=\"refresh\"", page)
        self.assertLess(page.index("最新の見出し"), page.index("古い号"))
        self.assertIn("最新号", page)
        self.assertIn("2026年9月28日（月）朝刊", page)
        self.assertIn("2026-09-28-am.html", page)

    def test_archive_and_issue_pages_include_gtm(self):
        archive = edition.render_archive_html([])
        issue = edition.render_html(
            date(2026, 9, 28), "am", [], [],
            {"lead_line": "今日の一言", "summary": "要点", "deep_topics": []},
            "2026-09-28T08:11:00+09:00", [],
        )
        for page in (archive, issue):
            with self.subTest(page=page[:40]):
                self.assertIn("GTM-NNQDZVDZ", page)
                self.assertIn("ns.html?id=GTM-NNQDZVDZ", page)

    def test_issue_navigation_has_only_available_static_neighbors(self):
        rows = [
            {"date": "2026-09-28", "edition": "am"},
            {"date": "2026-09-27", "edition": "am"},
        ]
        latest = edition.render_issue_navigation(rows[0], rows)
        older = edition.render_issue_navigation(rows[1], rows)
        self.assertIn("← 前の号", latest)
        self.assertNotIn("次の号 →", latest)
        self.assertIn("2026-09-27-am.html", latest)
        self.assertNotIn("前の号", older)
        self.assertIn("次の号 →", older)
        self.assertIn("2026-09-28-am.html", older)

    def test_sync_updates_previous_issue_and_is_idempotent(self):
        rows = [
            {"date": "2026-09-28", "edition": "am"},
            {"date": "2026-09-27", "edition": "am"},
        ]
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)
            for row in rows:
                (output / f'{row["date"]}-{row["edition"]}.html').write_text(
                    "<main><footer>footer</footer></main>", encoding="utf-8"
                )
            edition.sync_issue_navigation(rows, output)
            edition.sync_issue_navigation(rows, output)
            latest = (output / "2026-09-28-am.html").read_text(encoding="utf-8")
            older = (output / "2026-09-27-am.html").read_text(encoding="utf-8")
        self.assertEqual(latest.count("EDITION_NAV:start"), 1)
        self.assertIn("← 前の号", latest)
        self.assertNotIn("次の号 →", latest)
        self.assertNotIn("前の号", older)
        self.assertIn("次の号 →", older)

    def test_rendered_week_only_lists_existing_morning_issues(self):
        rows = [
            {"date": "2026-09-27", "edition": "am", "selectedCount": 10},
            {"date": "2026-09-27", "edition": "pm", "selectedCount": 8},
            {"date": "2026-09-26", "edition": "am", "selectedCount": 9},
        ]
        page = edition.render_html(
            date(2026, 9, 27), "am", [], [],
            {"lead_line": "今日の一言", "summary": "要点", "deep_topics": []},
            "2026-09-27T08:11:00+09:00", rows,
        )
        self.assertIn("今週の朝刊</h2>", page)
        self.assertIn("9/27 (日)", page)
        self.assertIn("9/26 (土)", page)
        self.assertNotIn("9/25", page)
        self.assertNotIn("夕刊", page)
        self.assertIn("次の朝刊は <b>明朝8時ごろ</b>", page)
        self.assertNotIn("次の夕刊", page)

    def test_rendered_update_time_uses_batch_at(self):
        page = edition.render_html(
            date(2026, 9, 27), "am", [], [],
            {"lead_line": "今日の一言", "summary": "要点", "deep_topics": []},
            "2026-09-27T08:11:57+09:00",
            [{"date": "2026-09-27", "edition": "am", "selectedCount": 10}],
        )
        self.assertIn("更新 08:11</span>", page)
        self.assertNotIn("更新 00:14", page)

    def test_sitemap_includes_archive_and_canonical_edition_urls(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            editions_path = root / "editions.json"
            sitemap_path = root / "sitemap.xml"
            editions_path.write_text(json.dumps([
                {"date": "2026-09-27", "edition": "am"},
                {"date": "2026-09-27", "edition": "pm"},
                {"date": "not-a-date", "edition": "am"},
            ]), encoding="utf-8")
            with patch.object(parse_news, "SITEMAP_FILE", sitemap_path):
                parse_news.generate_sitemap(editions_path)
            urls = [node.text for node in ET.parse(sitemap_path).iter() if node.tag.endswith("loc")]
        self.assertIn("https://ai-navigator.dev/daily/", urls)
        self.assertIn("https://ai-navigator.dev/daily/2026-09-27-am", urls)
        self.assertIn("https://ai-navigator.dev/daily/2026-09-27-pm", urls)
        self.assertFalse(any(".html" in url for url in urls))

    def test_jev_or_gemini_failure_creates_no_issue_and_keeps_editions(self):
        articles = [{"id": "one", "title": "Example", "summary": "Example summary", "source": "Example", "url": "https://example.com/a", "addedAt": "2026-09-27T08:00:00+09:00", "date": "2026-09-27"}]
        for failure_target in ("run_jev", "generate_copy"):
            with self.subTest(failure_target=failure_target), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                input_path = root / "articles.json"
                output = root / "daily"
                output.mkdir()
                input_path.write_text(json.dumps({"articles": articles}), encoding="utf-8")
                before = [{"date": "2026-09-26", "edition": "pm"}]
                (output / "editions.json").write_text(json.dumps(before), encoding="utf-8")
                target_mock = patch.object(edition, failure_target, side_effect=SystemExit(1))
                controls = []
                if failure_target == "generate_copy":
                    controls = [patch.object(edition, "run_jev", return_value=[{**articles[0], "on_topic": 1}]), patch.object(edition, "crawl_body", return_value=("x" * 350, "test"))]
                with target_mock, self.assertRaises(SystemExit):
                    for control in controls: control.start()
                    try:
                        edition.generate(input_path, date(2026, 9, 27), "am", output)
                    finally:
                        for control in controls: control.stop()
                self.assertEqual(json.loads((output / "editions.json").read_text(encoding="utf-8")), before)
                self.assertFalse((output / "2026-09-27-am.html").exists())


if __name__ == "__main__":
    unittest.main()
