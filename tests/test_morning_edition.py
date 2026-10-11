import html
import json
import re
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
        self.assertIn('href="2026-09-28-am"', page)
        self.assertNotIn("2026-09-28-am.html", page)
        self.assertIn("<title>AIニュースの朝刊・夕刊バックナンバー｜AI Navigator</title>", page)
        self.assertIn('rel="canonical" href="https://ai-navigator.dev/daily/"', page)
        self.assertIn('property="og:url" content="https://ai-navigator.dev/daily/"', page)

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
        self.assertIn('href="2026-09-27-am"', latest)
        self.assertNotIn("2026-09-27-am.html", latest)
        self.assertNotIn("前の号", older)
        self.assertIn("次の号 →", older)
        self.assertIn('href="2026-09-28-am"', older)
        self.assertNotIn("2026-09-28-am.html", older)

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

    def test_issue_seo_uses_toc_title_summary_and_sitemap_url(self):
        summary = (
            "AIを活用して会議のアジェンダ作成やニュース収集を自動化し、業務効率を高める手法が紹介されています。"
            "会議では目的や議題をAIに渡し、時間配分付きの案を作成させますが、最終的な妥当性は人が確認します。"
            "属人化した業務をAIに引き継ぐ際は、まず手順を書き出し、土台となる元データの掃除を行うことが重要です。"
        )
        selected = [
            {"title": "AIで会議のアジェンダを自動作成：目的から時間配分まで準備", "summary": "要約", "url": "https://example.com/1", "source": "例"},
            {"title": "GeminiがPDFを読めない時の解決チェックリスト", "summary": "要約", "url": "https://example.com/2", "source": "例"},
        ]
        page = edition.render_html(
            date(2026, 9, 30), "am", selected, selected,
            {"lead_line": "AIで会議準備や情報収集を効率化し属人化を防ぐ", "summary": summary, "deep_topics": []},
            "2026-09-30T08:11:57+09:00",
            [{"date": "2026-09-30", "edition": "am", "selectedCount": 2}],
            "2026-09-30T08:40:00+09:00",
        )
        title = re.search(r"<title>(.*?)</title>", page).group(1)
        pre_brand = title.rsplit("｜", 1)[0]
        self.assertEqual(title, "AIで会議のアジェンダを自動作成：目的から時間配分まで準備｜9/30朝刊｜AI Navigator")
        self.assertLessEqual(edition.display_width(pre_brand), 35)
        self.assertIn("<h1>2026年9月30日（水）朝刊</h1>", page)
        description = html.unescape(re.search(r'name="description" content="(.*?)"', page).group(1))
        self.assertGreaterEqual(len(description), 80)
        self.assertLessEqual(len(description), 120)
        self.assertTrue(description.startswith("AIを活用して会議のアジェンダ作成"))
        self.assertNotIn("属人化した業務", description)
        canonical = "https://ai-navigator.dev/daily/2026-09-30-am"
        self.assertIn(f'rel="canonical" href="{canonical}"', page)
        self.assertIn(f'property="og:title" content="{html.escape(title, quote=True)}"', page)
        self.assertIn(f'property="og:url" content="{canonical}"', page)
        self.assertNotIn(canonical + "/", page)
        self.assertNotIn(canonical + ".html", page)
        payload = json.loads(re.search(r'<script type="application/ld\+json">(.*?)</script>', page).group(1))
        self.assertEqual(payload["@type"], "NewsArticle")
        self.assertNotIn("author", payload)
        self.assertEqual(payload["datePublished"], "2026-09-30T08:11:57+09:00")
        self.assertEqual(payload["dateModified"], "2026-09-30T08:40:00+09:00")
        self.assertEqual(payload["publisher"]["name"], "AI Navigator")
        self.assertEqual(payload["url"], canonical)

    def test_long_toc_title_is_cut_before_the_brand(self):
        selected = [{"title": "あ" * 80, "summary": "要約", "url": "https://example.com/1", "source": "例"}]
        page = edition.render_html(
            date(2026, 9, 30), "am", [], selected,
            {"lead_line": "短い見出しですよ", "summary": "要点", "deep_topics": []},
            "", [],
        )
        title = re.search(r"<title>(.*?)</title>", page).group(1)
        self.assertIn("ほか｜9/30朝刊｜AI Navigator", title)
        self.assertLessEqual(edition.display_width(title.rsplit("｜", 1)[0]), 35)
        self.assertNotIn("author", page)
        payload = json.loads(re.search(r'<script type="application/ld\+json">(.*?)</script>', page).group(1))
        self.assertNotIn("dateModified", payload)
        self.assertEqual(payload["datePublished"], "2026-09-30")

    def test_second_toc_title_is_used_when_it_alone_fits(self):
        selected = [
            {"title": "あ" * 40 + "｜" + "い" * 40, "summary": "要約", "url": "https://example.com/1", "source": "例"},
            {"title": "GeminiがPDFを読めない時の解決チェックリスト", "summary": "要約", "url": "https://example.com/2", "source": "例"},
        ]
        page = edition.render_html(
            date(2026, 9, 30), "am", [], selected,
            {"lead_line": "見出し", "summary": "あ" * 90 + "。", "deep_topics": []},
            "", [],
        )
        title = html.unescape(re.search(r"<title>(.*?)</title>", page).group(1))
        self.assertIn("GeminiがPDFを読めない時の解決チェックリスト｜9/30朝刊｜", title)

    def test_archive_description_mentions_latest_issue_and_stays_in_range(self):
        page = edition.render_archive_html([
            {"date": "2026-09-30", "edition": "am", "leadLine": "AIで会議準備や情報収集を効率化し属人化を防ぐ", "summaryExcerpt": "要約"},
            {"date": "2026-09-29", "edition": "am", "leadLine": "前日の見出し", "summaryExcerpt": "前日"},
        ])
        description = html.unescape(re.search(r'name="description" content="(.*?)"', page).group(1))
        self.assertGreaterEqual(len(description), 80)
        self.assertLessEqual(len(description), 120)
        self.assertIn("9月30日朝刊", description)
        self.assertIn("「AIで会議準備や情報収集を効率化し属人化を防ぐ」", description)
        self.assertNotIn("前日の見出し", description)
        nested = edition.archive_description([
            {"date": "2026-10-01", "edition": "am", "leadLine": "AI活用は「任せ方」と「確認」の仕組みで決まる"},
        ])
        self.assertIn("『AI活用は「任せ方」と「確認」の仕組みで決まる』", nested)
        self.assertLessEqual(len(nested), 120)
        self.assertGreaterEqual(len(nested), 80)
        self.assertIn('"@type":"CollectionPage"', page)
        self.assertNotIn('"author"', page)

    def test_sync_rewrites_existing_issue_head_without_touching_h1(self):
        summary = "生成AIの回答はもっともらしさと正しさが別物であり、実務では出典の照合や数値の単独検証が不可欠です。業務効率化で浮いた時間を会社に報告せず、自分の余白とする動きが広がっています。"
        rows = [{
            "date": "2026-09-27",
            "edition": "am",
            "leadLine": "AIで浮いた時間の再配分と価値の翻訳",
            "summaryExcerpt": summary[:140],
            "batchAt": "2026-09-27T08:11:57+09:00",
            "generatedAt": "2026-09-28T00:14:24+09:00",
        }]
        original = (
            '<!doctype html><html lang="ja"><head><meta charset="utf-8"><title>2026年9月27日（日）朝刊｜AI Navigator</title></head>'
            '<body><main><h1>2026年9月27日（日）朝刊</h1>'
            '<section class="brief"><p class="brief-label">30秒でわかる</p>'
            '<h2>AIで浮いた時間の再配分と価値の翻訳</h2>'
            f'<p>{summary}</p></section>'
            '<nav class="toc"><a href="#story-1"><span>01</span>初めて扱うテーマの調査ほどAIの誤りに気づけない｜回答チェック4ステップ</a>'
            '<a href="#story-2"><span>02</span>価値が伝わらないなら、「翻訳」してみる</a></nav>'
            '<a href="2026-09-26-am.html">前</a></main></body></html>'
        )
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)
            path = output / "2026-09-27-am.html"
            path.write_text(original, encoding="utf-8")
            edition.sync_issue_seo(rows, output)
            once = path.read_text(encoding="utf-8")
            edition.sync_issue_seo(rows, output)
            twice = path.read_text(encoding="utf-8")
        self.assertEqual(once, twice)
        self.assertIn("<h1>2026年9月27日（日）朝刊</h1>", twice)
        self.assertIn("初めて扱うテーマの調査ほどAIの誤りに気づけない｜9/27朝刊｜AI Navigator", twice)
        self.assertIn('rel="canonical" href="https://ai-navigator.dev/daily/2026-09-27-am"', twice)
        self.assertIn('href="2026-09-26-am"', twice)
        self.assertNotIn("2026-09-26-am.html", twice)
        self.assertEqual(twice.count("SEO_META:start"), 1)
        self.assertEqual(twice.count('name="description"'), 1)

    def test_sync_skips_issue_without_copy(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)
            path = output / "2026-06-24-pm.html"
            original = "<html><head><title>旧号</title></head><body>本文</body></html>"
            path.write_text(original, encoding="utf-8")
            edition.sync_issue_seo([], output)
            self.assertEqual(path.read_text(encoding="utf-8"), original)


if __name__ == "__main__":
    unittest.main()
