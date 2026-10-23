import io
import json
import xml.etree.ElementTree as ET
import tempfile
import unittest
from contextlib import contextmanager, redirect_stderr
from datetime import date
from pathlib import Path
from unittest.mock import Mock, patch

from daily import morning_edition as edition
import parse_news


def _edition_copy(summary, lead=None):
    return {
        "lead_line": "あ" * 20 if lead is None else lead,
        "summary": summary,
        "deep_topics": [
            {"heading": "◆一", "text": "う" * 300},
            {"heading": "◆二", "text": "う" * 300},
            {"heading": "◆三", "text": "う" * 280},
        ],
    }


def _articles_for(day, count=5):
    return [
        {
            "id": f"a{i}",
            "title": f"title {i}",
            "summary": "summary",
            "source": "Example",
            "url": f"https://example.com/{i}",
            "addedAt": f"{day}T08:00:00+09:00",
            "date": day,
        }
        for i in range(count)
    ]


def _gemini_http(text):
    response = Mock()
    response.raise_for_status = Mock()
    response.json.return_value = {"candidates": [{"content": {"parts": [{"text": text}]}}]}
    return response


@contextmanager
def _patched_generation(copies, day="2026-10-10"):
    articles = _articles_for(day)
    ranked = [{**article, "on_topic": 1} for article in articles]
    queue = list(copies)
    state = {"calls": 0, "refinements": []}

    def fake_copy(selected, bodies, refinement=""):
        state["calls"] += 1
        state["refinements"].append(refinement)
        return {"unused": True}

    def verify(raw, bodies):
        content = queue.pop(0) if len(queue) > 1 else queue[0]
        return content, {
            "dropped_sentences": [],
            "checks": [],
            "checked_sentence_count": 1,
            "model": "test",
        }

    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        output = root / "daily"
        output.mkdir()
        input_path = root / "articles.json"
        input_path.write_text(
            json.dumps({"articles": articles, "latestBatchAt": f"{day}T08:11:00+09:00"}),
            encoding="utf-8",
        )
        with patch.object(edition, "run_jev", return_value=ranked), \
             patch.object(edition, "crawl_body", return_value=("本文" * 200, "test")), \
             patch.object(edition, "generate_copy", side_effect=fake_copy), \
             patch.object(edition, "verify_and_filter", side_effect=verify), \
             patch.object(parse_news, "generate_sitemap"):
            yield input_path, output, state


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

    def test_morning_sns_payload_contains_only_verified_copy_and_canonical_url(self):
        content = {
            "lead_line": "今日の一言",
            "summary": "要点の文。次の文。",
            "deep_topics": [
                {"heading": "◆一", "text": "深掘り本文"},
                {"heading": "◆二", "text": "深掘り本文"},
                {"heading": "◆三", "text": "深掘り本文"},
            ],
        }
        payload = edition.sns_post_payload(date(2026, 10, 1), "am", content)
        self.assertEqual(payload["date"], "2026-10-01")
        self.assertEqual(payload["lead_line"], "今日の一言")
        self.assertEqual(payload["summary"], "要点の文。次の文。")
        self.assertEqual(
            payload["deep_topics"],
            [{"heading": "◆一"}, {"heading": "◆二"}, {"heading": "◆三"}],
        )
        self.assertEqual(payload["url"], "https://ai-navigator.dev/daily/2026-10-01-am")
        self.assertNotIn("text", payload["deep_topics"][0])

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
                    '<html><head><meta name="color-scheme" content="light"></head><body><main><footer>footer</footer></main></body></html>',
                    encoding="utf-8",
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

    def test_sync_adds_gtm_to_existing_issue_once(self):
        rows = [{"date": "2026-09-27", "edition": "am"}]
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)
            page_path = output / "2026-09-27-am.html"
            page_path.write_text(
                '<html><head><meta name="color-scheme" content="light"></head><body><main>過去号</main></body></html>',
                encoding="utf-8",
            )

            edition.sync_issue_navigation(rows, output)
            once = page_path.read_text(encoding="utf-8")
            edition.sync_issue_navigation(rows, output)
            twice = page_path.read_text(encoding="utf-8")

        self.assertEqual(once, twice)
        self.assertEqual(twice.count("<!-- Google Tag Manager -->"), 1)
        self.assertEqual(twice.count("<!-- Google Tag Manager (noscript) -->"), 1)
        self.assertEqual(twice.count("GTM-NNQDZVDZ"), 2)
        self.assertIn(
            '<meta name="color-scheme" content="light">  <!-- Google Tag Manager -->',
            twice,
        )
        self.assertIn(
            '<body>  <!-- Google Tag Manager (noscript) -->',
            twice,
        )

    def test_sync_adds_gtm_head_before_close_when_color_scheme_is_missing(self):
        rows = [{"date": "2026-09-27", "edition": "am"}]
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)
            page_path = output / "2026-09-27-am.html"
            page_path.write_text(
                "<html><head><title>旧号</title></head><body>本文</body></html>",
                encoding="utf-8",
            )
            edition.sync_issue_navigation(rows, output)
            page = page_path.read_text(encoding="utf-8")

        self.assertIn("</script></head>", page)
        self.assertIn("</head><body>  <!-- Google Tag Manager (noscript) -->", page)

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

    def test_selected_story_headings_link_to_the_source_url(self):
        selected = [
            {
                "title": "広告集計スプレッドシートの「重さ」を解消するAI診断",
                "summary": "要約A",
                "source": "Example",
                "url": "https://example.com/sheet?q=1&x=2",
                "thumbnail": "https://example.com/thumb.jpg",
            },
            {
                "title": "URLなし記事",
                "summary": "要約B",
                "source": "Local",
                "url": "   ",
            },
        ]
        page = edition.render_html(
            date(2026, 10, 23), "am", selected, selected,
            {
                "lead_line": "今日の一言",
                "summary": "要点",
                "deep_topics": [{"heading": "◆深掘り見出し", "text": "本文"}],
            },
            "2026-10-23T08:11:00+09:00",
            [],
        )
        linked = (
            '<article class="story" id="story-1"><div class="story-copy">'
            '<p class="story-kicker">ARTICLE 01</p>'
            '<h3><a class="story-title" href="https://example.com/sheet?q=1&amp;x=2" '
            'target="_blank" rel="noopener">広告集計スプレッドシートの「重さ」を解消するAI診断</a></h3>'
        )
        plain = (
            '<article class="story" id="story-2"><div class="story-copy">'
            '<p class="story-kicker">ARTICLE 02</p><h3>URLなし記事</h3>'
        )
        self.assertIn(linked, page)
        self.assertIn(
            '<a class="read-link" href="https://example.com/sheet?q=1&amp;x=2" '
            'target="_blank" rel="nofollow noopener">元記事を読む →</a>',
            page,
        )
        self.assertIn(plain, page)
        story2 = page.split('id="story-2"', 1)[1].split("</article>", 1)[0]
        self.assertNotIn("<a ", story2)
        self.assertNotIn("元記事を読む", story2)
        self.assertIn(
            '<a href="#story-1"><span>01</span>広告集計スプレッドシートの「重さ」を解消するAI診断</a>',
            page,
        )
        self.assertIn('<a href="#story-2"><span>02</span>URLなし記事</a>', page)
        self.assertIn('<article class="topic"><h3>◆深掘り見出し</h3>', page)
        self.assertNotIn("story-title", page.split("<article class=\"topic\">", 1)[1].split("</article>", 1)[0])
        self.assertIn(".story h3 a.story-title:hover", page)
        self.assertIn("text-decoration:underline", page)

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
                    ranked = [
                        {**articles[0], "id": f"one-{i}", "url": f"https://example.com/{i}", "on_topic": 1}
                        for i in range(5)
                    ]
                    controls = [patch.object(edition, "run_jev", return_value=ranked), patch.object(edition, "crawl_body", return_value=("x" * 350, "test"))]
                with target_mock, self.assertRaises(SystemExit):
                    for control in controls: control.start()
                    try:
                        edition.generate(input_path, date(2026, 9, 27), "am", output)
                    finally:
                        for control in controls: control.stop()
                self.assertEqual(json.loads((output / "editions.json").read_text(encoding="utf-8")), before)
                self.assertFalse((output / "2026-09-27-am.html").exists())
                self.assertFalse((output / "2026-09-27-am.sns.json").exists())

    def test_note_paywall_is_rejected_when_public_body_is_short(self):
        article = {"id": "paid", "url": "https://note.com/someone/n/nabc"}
        page = Mock(ok=True, text="<html><body><article>短いプレビュー</article></body></html>")
        page.raise_for_status = Mock()
        api = Mock()
        api.raise_for_status = Mock()
        api.json.return_value = {"data": {"body": "<p>短いリード</p>", "can_read": False, "price": 1480}}
        with patch.object(edition.requests, "get", side_effect=[page, api]):
            with self.assertRaises(ValueError) as caught:
                edition.crawl_body(article)
        self.assertIn("有料記事", str(caught.exception))

    def test_one_unreadable_body_is_replaced_by_the_next_ranked_article(self):
        articles = [
            {
                "id": f"a{i}",
                "title": f"title {i}",
                "summary": "summary",
                "source": "Example",
                "url": f"https://example.com/{i}",
                "addedAt": "2026-09-27T08:00:00+09:00",
                "date": "2026-09-27",
            }
            for i in range(6)
        ]
        ranked = [{**article, "on_topic": 1} for article in articles]

        def crawl(article):
            if article["id"] == "a2":
                raise ValueError("short body")
            return ("本文" * 200, "test")

        captured = {}

        def fake_copy(selected, bodies, refinement=""):
            captured["ids"] = [article["id"] for article in selected]
            captured["body_count"] = len(bodies)
            return {"unused": True}

        valid = {
            "lead_line": "あ" * 20,
            "summary": "い" * 400,
            "deep_topics": [
                {"heading": "◆一", "text": "う" * 300},
                {"heading": "◆二", "text": "う" * 300},
                {"heading": "◆三", "text": "う" * 280},
            ],
        }
        claim = {"dropped_sentences": [], "checks": [], "checked_sentence_count": 1, "model": "test"}
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            input_path = root / "articles.json"
            output = root / "daily"
            output.mkdir()
            input_path.write_text(
                json.dumps({"articles": articles, "latestBatchAt": "2026-09-27T08:11:00+09:00"}),
                encoding="utf-8",
            )
            with patch.object(edition, "run_jev", return_value=ranked), \
                 patch.object(edition, "crawl_body", side_effect=crawl), \
                 patch.object(edition, "generate_copy", side_effect=fake_copy), \
                 patch.object(edition, "verify_and_filter", return_value=(valid, dict(claim))), \
                 patch.object(parse_news, "generate_sitemap"):
                edition.generate(input_path, date(2026, 9, 27), "am", output)
            page = (output / "2026-09-27-am.html").read_text(encoding="utf-8")
            check = json.loads((output / "2026-09-27-am.claim_check.json").read_text(encoding="utf-8"))
            self.assertTrue((output / "2026-09-27-am.sns.json").exists())
        self.assertEqual(captured["ids"], ["a0", "a1", "a3", "a4", "a5"])
        self.assertEqual(captured["body_count"], 5)
        self.assertEqual([row["id"] for row in check["crawl"]], ["a0", "a1", "a3", "a4", "a5"])
        self.assertEqual(check["skipped_bodies"], [{"id": "a2", "url": "https://example.com/2", "error": "ValueError"}])
        self.assertEqual(check["body_source_ids"], ["a0", "a1", "a3", "a4", "a5"])
        self.assertIn("title 2", page)

    def test_morning_edition_still_fails_when_readable_bodies_are_under_five(self):
        articles = [
            {
                "id": f"a{i}",
                "title": f"title {i}",
                "summary": "summary",
                "source": "Example",
                "url": f"https://example.com/{i}",
                "addedAt": "2026-09-27T08:00:00+09:00",
                "date": "2026-09-27",
            }
            for i in range(5)
        ]
        ranked = [{**article, "on_topic": 1} for article in articles]

        def crawl(article):
            if article["id"] == "a0":
                raise ValueError("short body")
            return ("x" * 350, "test")

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            input_path = root / "articles.json"
            output = root / "daily"
            output.mkdir()
            before = [{"date": "2026-09-26", "edition": "pm"}]
            (output / "editions.json").write_text(json.dumps(before), encoding="utf-8")
            input_path.write_text(json.dumps({"articles": articles}), encoding="utf-8")
            with patch.object(edition, "run_jev", return_value=ranked), \
                 patch.object(edition, "crawl_body", side_effect=crawl), \
                 self.assertRaises(SystemExit):
                edition.generate(input_path, date(2026, 9, 27), "am", output)
            self.assertEqual(json.loads((output / "editions.json").read_text(encoding="utf-8")), before)
            self.assertFalse((output / "2026-09-27-am.html").exists())

    def test_copy_length_still_reports_a_343_character_summary(self):
        content = _edition_copy("い" * 343)
        problem = edition.copy_length_problem(content)
        self.assertIn("要点は343字", problem)
        self.assertIn("350〜450字", problem)

    def test_soften_summary_accepts_near_miss_and_rejects_broken_text(self):
        floor = edition.summary_soft_floor()
        self.assertEqual(floor, 280)
        kept, warning = edition.soften_summary("あ" * 343)
        self.assertEqual(kept, "あ" * 343)
        self.assertIn("343字", warning)
        self.assertIn("採用します", warning)
        at_floor, floor_warning = edition.soften_summary("あ" * floor)
        self.assertEqual(len(at_floor), floor)
        self.assertIn("採用します", floor_warning)
        in_range, quiet = edition.soften_summary("あ" * 400)
        self.assertEqual(in_range, "あ" * 400)
        self.assertIsNone(quiet)
        with self.assertRaises(ValueError):
            edition.soften_summary("あ" * (floor - 1))
        with self.assertRaises(ValueError):
            edition.soften_summary("  ")

    def test_soften_summary_trims_overlong_text_on_sentence_boundaries(self):
        sentence = "これはテストの文章です。"
        self.assertEqual(len(sentence), 12)
        trimmed, warning = edition.soften_summary(sentence * 40)
        self.assertEqual(trimmed, sentence * 37)
        self.assertEqual(len(trimmed), 444)
        self.assertIn("丸めました", warning)

        slight = ("あ" * 300 + "。") + ("い" * 160 + "。")
        self.assertEqual(len(slight), 462)
        kept, slight_warning = edition.soften_summary(slight)
        self.assertEqual(kept, slight)
        self.assertIn("極端ではない", slight_warning)

        blob = "あ" * 500
        kept_blob, blob_warning = edition.soften_summary(blob)
        self.assertEqual(kept_blob, blob)
        self.assertIn("極端ではない", blob_warning)

        long_sentence = "あ" * 300 + "。"
        extreme = long_sentence * 3
        self.assertGreater(len(extreme), edition.SUMMARY_EXTREME_MAX)
        shortened, extreme_warning = edition.soften_summary(extreme)
        self.assertEqual(shortened, long_sentence)
        self.assertGreaterEqual(len(shortened), edition.summary_soft_floor())
        self.assertIn("丸めました", extreme_warning)

    def test_summary_343_chars_is_published_after_two_regenerations(self):
        day = "2026-10-10"
        summary = "い" * 343
        err = io.StringIO()
        with _patched_generation([_edition_copy(summary) for _ in range(3)], day) as (input_path, output, state):
            with redirect_stderr(err):
                edition.generate(input_path, date.fromisoformat(day), "am", output)
            page = (output / f"{day}-am.html").read_text(encoding="utf-8")
            check = json.loads((output / f"{day}-am.claim_check.json").read_text(encoding="utf-8"))
            sns = json.loads((output / f"{day}-am.sns.json").read_text(encoding="utf-8"))
            editions = json.loads((output / "editions.json").read_text(encoding="utf-8"))
        self.assertEqual(state["calls"], 3)
        self.assertEqual(state["refinements"][0], "")
        self.assertIn("要点は343字", state["refinements"][1])
        self.assertIn("要点は343字", state["refinements"][2])
        self.assertIn(summary, page)
        self.assertEqual(sns["summary"], summary)
        self.assertEqual(check["gemini_calls"], 3)
        self.assertTrue(any("343字" in item for item in check["length_warnings"]))
        self.assertIn("採用します", err.getvalue())
        self.assertEqual(editions[0]["date"], day)

    def test_summary_corrected_on_retry_is_used_without_a_warning(self):
        day = "2026-10-10"
        fixed = "い" * 400
        err = io.StringIO()
        with _patched_generation([_edition_copy("い" * 343), _edition_copy(fixed)], day) as (input_path, output, state):
            with redirect_stderr(err):
                edition.generate(input_path, date.fromisoformat(day), "am", output)
            sns = json.loads((output / f"{day}-am.sns.json").read_text(encoding="utf-8"))
            check = json.loads((output / f"{day}-am.claim_check.json").read_text(encoding="utf-8"))
        self.assertEqual(state["calls"], 2)
        self.assertEqual(sns["summary"], fixed)
        self.assertNotIn("length_warnings", check)
        self.assertNotIn("採用します", err.getvalue())

    def test_overlong_summary_is_trimmed_and_published(self):
        day = "2026-10-11"
        sentence = "これはテストの文章です。"
        err = io.StringIO()
        with _patched_generation([_edition_copy(sentence * 40) for _ in range(3)], day) as (input_path, output, state):
            with redirect_stderr(err):
                edition.generate(input_path, date.fromisoformat(day), "am", output)
            sns = json.loads((output / f"{day}-am.sns.json").read_text(encoding="utf-8"))
        self.assertEqual(state["calls"], 3)
        self.assertEqual(sns["summary"], sentence * 37)
        self.assertIn("丸めました", err.getvalue())

    def test_broken_summary_or_lead_still_stops_the_edition(self):
        cases = {
            "short-summary": _edition_copy("い" * 100),
            "short-lead": _edition_copy("い" * 400, lead="短い"),
        }
        for name, copy in cases.items():
            with self.subTest(name=name):
                day = "2026-10-10"
                err = io.StringIO()
                with _patched_generation([copy], day) as (input_path, output, state):
                    before = [{"date": "2026-10-09", "edition": "am"}]
                    (output / "editions.json").write_text(json.dumps(before), encoding="utf-8")
                    with redirect_stderr(err), self.assertRaises(SystemExit):
                        edition.generate(input_path, date.fromisoformat(day), "am", output)
                    self.assertEqual(json.loads((output / "editions.json").read_text(encoding="utf-8")), before)
                    self.assertFalse((output / f"{day}-am.html").exists())
                    self.assertFalse((output / f"{day}-am.sns.json").exists())
                self.assertEqual(state["calls"], 6)
                self.assertIn("文字数条件を6回以内に満たせませんでした", err.getvalue())

    def test_parse_gemini_json_accepts_fences_and_preamble(self):
        self.assertEqual(edition.parse_gemini_json('{"ok": true}'), {"ok": True})
        self.assertEqual(edition.parse_gemini_json('```json\n{"ok": true}\n```'), {"ok": True})
        self.assertEqual(
            edition.parse_gemini_json('結果です。\n```JSON\n{"ok": true}\n```\n以上'),
            {"ok": True},
        )
        self.assertEqual(edition.parse_gemini_json('説明\n{"lead": "x"} 完'), {"lead": "x"})
        with self.assertRaises(json.JSONDecodeError):
            edition.parse_gemini_json("not json")
        with self.assertRaises(json.JSONDecodeError):
            edition.parse_gemini_json("[1, 2, 3]")
        with self.assertRaises(json.JSONDecodeError):
            edition.parse_gemini_json(None)

    def test_generate_copy_retries_unparseable_json_then_reads_a_fence(self):
        bad = _gemini_http("これはJSONではありません")
        good = _gemini_http('```json\n{"ok": true}\n```')
        err = io.StringIO()
        with patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}), \
             patch.object(edition.requests, "post", side_effect=[bad, good]) as post, \
             redirect_stderr(err):
            self.assertEqual(edition.generate_copy([], []), {"ok": True})
        self.assertEqual(post.call_count, 2)
        self.assertIn("再試行します", err.getvalue())

    def test_generate_copy_stops_after_three_unparseable_replies(self):
        bad = _gemini_http("{")
        with patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}), \
             patch.object(edition.requests, "post", side_effect=[bad, bad, bad]) as post, \
             redirect_stderr(io.StringIO()):
            with self.assertRaises(json.JSONDecodeError):
                edition.generate_copy([], [])
        self.assertEqual(post.call_count, 3)


if __name__ == "__main__":
    unittest.main()
