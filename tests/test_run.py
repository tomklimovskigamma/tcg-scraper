from __future__ import annotations

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline import run  # noqa: E402
from pipeline.history import History  # noqa: E402

NOW = datetime(2026, 11, 10, 1, 0, tzinfo=timezone.utc)
ETB = {"sku": "e1", "title": "Pokemon TCG: Mega Evolution Chaos Rising Elite Trainer Box", "price_aud": 79.0,
       "url": "https://shop.example/e1"}


class ScanTests(unittest.TestCase):
    def setUp(self):
        self.h = History(":memory:")
        self.sent = []

    def post(self, text):
        self.sent.append(text)

    def test_all_scrapers_failing_is_an_error(self):
        rc = run.scan(self.h, ["Big W", "Kmart"], lambda store: None, self.post, NOW)
        self.assertEqual(rc, 1)
        self.assertEqual(self.h.run_stats(NOW, NOW.replace(hour=2))["Big W"], {"ok": 0, "failed": 1})
        self.assertEqual(self.sent, [])

    def test_baseline_then_ping_is_posted_and_marked(self):
        stock = {"Big W": [], "Kmart": None}
        self.assertEqual(run.scan(self.h, ["Big W", "Kmart"], stock.get, self.post, NOW), 0)
        stock["Big W"] = [ETB]
        self.assertEqual(run.scan(self.h, ["Big W", "Kmart"], stock.get, self.post, NOW.replace(minute=5)), 0)
        self.assertEqual(len(self.sent), 1)
        self.assertIn("NEW LISTING", self.sent[0])
        self.assertEqual(self.h.unposted_pings(), [])

    def test_failed_post_is_retried_next_scan(self):
        stock = {"Big W": []}
        run.scan(self.h, ["Big W"], stock.get, self.post, NOW)
        stock["Big W"] = [ETB]

        def boom(text):
            raise OSError("network down")

        self.assertEqual(run.scan(self.h, ["Big W"], stock.get, boom, NOW.replace(minute=5)), 1)
        self.assertEqual(len(self.h.unposted_pings()), 1)
        self.assertEqual(run.scan(self.h, ["Big W"], stock.get, self.post, NOW.replace(minute=10)), 0)
        self.assertEqual(len(self.sent), 1)
        self.assertEqual(self.h.unposted_pings(), [])

    def test_no_post_function_leaves_events_unposted(self):
        stock = {"Big W": []}
        run.scan(self.h, ["Big W"], stock.get, None, NOW)
        stock["Big W"] = [ETB]
        self.assertEqual(run.scan(self.h, ["Big W"], stock.get, None, NOW.replace(minute=5)), 0)
        self.assertEqual(len(self.h.unposted_pings()), 1)


class DigestTests(unittest.TestCase):
    def test_digest_posts_todays_events(self):
        h = History(":memory:")
        sent = []
        stock = {"Big W": []}
        run.scan(h, ["Big W"], stock.get, sent.append, NOW)
        stock["Big W"] = [ETB]
        run.scan(h, ["Big W"], stock.get, sent.append, NOW.replace(minute=5))
        sent.clear()
        self.assertEqual(run.digest(h, sent.append, NOW.replace(hour=7)), 0)
        text = "\n".join(sent)
        self.assertIn("daily digest · Tue 10 Nov", text)
        self.assertIn("**Arrived today (1)**", text)
        self.assertIn("**In stock now (1)**", text)


if __name__ == "__main__":
    unittest.main()
