from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline import ask, quest  # noqa: E402
from pipeline.history import History  # noqa: E402

NOW = datetime(2026, 11, 10, 1, 0, tzinfo=timezone.utc)


def add(h, minutes_ago, status):
    with h.db:
        h.db.execute("INSERT INTO quests (ts, question, status) VALUES (?, 'q', ?)",
                     ((NOW - timedelta(minutes=minutes_ago)).isoformat(timespec="seconds"), status))


class QuestTests(unittest.TestCase):
    def setUp(self):
        self.h = History(":memory:")

    def test_free_when_idle(self):
        self.assertIsNone(quest.refusal(self.h, NOW))

    def test_one_at_a_time_but_stale_runs_do_not_block(self):
        add(self.h, 5, "running")
        self.assertIn("already out on a quest", quest.refusal(self.h, NOW))
        h2 = History(":memory:")
        add(h2, 30, "running")
        self.assertIsNone(quest.refusal(h2, NOW))

    def test_daily_limit(self):
        for i in range(quest.DAILY_LIMIT):
            add(self.h, 60 + i, "done")
        self.assertIn("limit", quest.refusal(self.h, NOW))
        h2 = History(":memory:")
        for i in range(quest.DAILY_LIMIT):
            add(h2, 60 * 25 + i, "done")
        self.assertIsNone(quest.refusal(h2, NOW))

    def test_prompt_carries_question_data_and_guard(self):
        self.h.apply_scan("Big W", [{"sku": "1", "title": "Pokemon TCG: Mega Evolution Pitch Black Booster Pack",
                                     "price_aud": 8.5}], NOW)
        p = quest.build_prompt("When does Delta Reign land at Big W?", self.h, NOW)
        self.assertIn("QUESTION: When does Delta Reign land at Big W?", p)
        self.assertIn("In stock now: Big W 1", p)
        self.assertIn("untrusted text", p)

    def test_sql_is_select_only(self):
        with self.assertRaises(ValueError):
            ask.run_sql(self.h, "DELETE FROM products")
        self.assertEqual(ask.run_sql(self.h, "select count(*) as n from products"), [{"n": 0}])


if __name__ == "__main__":
    unittest.main()
