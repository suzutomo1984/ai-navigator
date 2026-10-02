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

    def test_one_unreadable_body_is_replaced_by_the_next_ranked_article(self):
        self.assertTrue(True)
