from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline import messages  # noqa: E402
from pipeline.history import History  # noqa: E402

NOW = datetime(2026, 11, 10, 1, 0, tzinfo=timezone.utc)


def seed(h, set_name, group, published, series):
    """series: {ptype: [(days_ago, usd), ...]}"""
    h.upsert_market_set(set_name, group, published)
    pid = group * 10
    for ptype, points in series.items():
        pid += 1
        h.upsert_market_product(pid, group, set_name, f"{set_name} {ptype}", ptype, None)
        for days_ago, usd in points:
            h.add_market_price((NOW - timedelta(days=days_ago)).date().isoformat(), pid, usd)
    h.set_fx(NOW.date().isoformat(), 1.5)


class TrendTests(unittest.TestCase):
    def setUp(self):
        self.h = History(":memory:")
        seed(self.h, "Pitch Black", 1, "2026-07-17", {
            "etb": [(35, 60.0), (28, 62.0), (14, 64.0), (0, 70.0)],
            "booster": [(35, 5.0), (0, 5.6)],
            "booster_box": [(35, 180.0), (0, 200.0)],
        })
        seed(self.h, "Chaos Rising", 2, "2026-05-22", {
            "etb": [(35, 70.0), (0, 66.0)],
            "booster": [(35, 5.5), (0, 5.5)],
        })

    def test_market_value_carries_30_day_trend(self):
        v = self.h.market_value("Pitch Black", "etb")
        # 30 days ago falls between points; the latest point at or before that day (35 days ago) is used.
        self.assertAlmostEqual(v["change_30d"], (70.0 - 60.0) / 60.0, places=4)
        self.assertAlmostEqual(self.h.market_value("Chaos Rising", "etb")["change_30d"], -4 / 70, places=4)

    def test_no_trend_without_old_enough_point(self):
        seed(self.h, "Delta Reign", 3, "2026-11-06", {"etb": [(3, 90.0), (0, 80.0)]})
        self.assertIsNone(self.h.market_value("Delta Reign", "etb")["change_30d"])

    def test_hot_set_is_median_rise_of_ten_percent(self):
        self.assertTrue(self.h.is_hot_set("pitch black"))     # +16.7%, +12%, +11.1%
        self.assertFalse(self.h.is_hot_set("Chaos Rising"))   # -5.7%, 0%
        self.assertFalse(self.h.is_hot_set("Unknown Set"))
        self.assertFalse(self.h.is_hot_set(None))

    def test_hot_set_promotes_digest_items_to_ping(self):
        hot = {"sku": "p1", "title": "Pokemon TCG: Mega Evolution Pitch Black Sleeved Booster", "price_aud": 8.5}
        cold = {"sku": "c1", "title": "Pokemon TCG: Mega Evolution Chaos Rising Sleeved Booster", "price_aud": 8.5}
        self.h.apply_scan("Big W", [], NOW)
        ev = self.h.apply_scan("Big W", [hot, cold], NOW + timedelta(minutes=5))
        self.assertEqual({e["sku"]: e["tier"] for e in ev}, {"p1": "ping", "c1": "digest"})
        ping = self.h.unposted_pings()[0]
        self.assertTrue(self.h.ping_context(ping)["hot"])

    def test_market_line_with_trend(self):
        ml = messages.market_line
        m = {"usd": 70.0, "aud": 105.0, "change_30d": 0.1667}
        self.assertEqual(ml(79.0, m), "US market ≈ A$105 (US$70, converted), up 17% in 30 days · shelf price is 25% below")
        m["change_30d"] = -0.057
        self.assertEqual(ml(79.0, m), "US market ≈ A$105 (US$70, converted), down 6% in 30 days · shelf price is 25% below")
        m["change_30d"] = 0.01
        self.assertEqual(ml(79.0, m), "US market ≈ A$105 (US$70, converted), flat over 30 days · shelf price is 25% below")
        m["change_30d"] = None
        self.assertEqual(ml(79.0, m), "US market ≈ A$105 (US$70, converted) · shelf price is 25% below")

    def test_hot_tag_on_ping(self):
        e = {"id": 1, "store": "Big W", "title": "X", "label": "restock", "ptype": "sleeved_booster", "price": 8.5, "url": None}
        head = messages.format_ping(e, {"times_30d": 1, "last_duration_min": None, "hot": True}).splitlines()[0]
        self.assertEqual(head, "🚨 **RESTOCK** · Sleeved Booster · **$8.50** · 🔥 hot set")

    def test_opportunities(self):
        self.h.apply_scan("Big W", [
            {"sku": "a", "title": "Pokemon TCG: Mega Evolution Pitch Black Elite Trainer Box", "price_aud": 79.0, "url": "https://b.example/a"},
            {"sku": "b", "title": "Pokemon TCG: Mega Evolution Chaos Rising Booster Pack", "price_aud": 8.5},
            {"sku": "c", "title": "Pokemon TCG: Mega Evolution Pitch Black Booster Pack", "price_aud": 7.0},
            {"sku": "d", "title": "Pokemon TCG: Mega Lucario ex League Battle Deck", "price_aud": 39.0},
        ], NOW)
        opps = self.h.opportunities()
        # ETB: market A$105 vs 79 = 24.8% below. Pitch Black pack: A$8.40 vs 7.00 = 16.7% below.
        # Chaos Rising pack: A$8.25 vs 8.50 = shelf above market -> not an opportunity. Deck: no market match.
        self.assertEqual([o["sku"] for o in opps], ["a", "c"])
        self.assertAlmostEqual(opps[0]["discount"], (105 - 79) / 105, places=3)
        text = "\n".join(messages.build_digest("Tue 10 Nov", [], self.h.in_stock_now(), {"Big W": {"ok": 1, "failed": 0}},
                                               opportunities=opps, sets=self.h.set_calendar(NOW)))
        self.assertIn("**Best value on shelves (2)**", text)
        self.assertIn("• [Mega Evolution Pitch Black Elite Trainer Box](<https://b.example/a>) · Big W $79.00 · "
                      "25% under US market (A$105), up 17% in 30 days", text)
        self.assertIn("• Mega Evolution Pitch Black Booster Pack · Big W $7.00 · 17% under US market (A$8.40), up 12% in 30 days", text)

    def test_opportunities_merge_the_same_product_across_stores(self):
        pack = {"title": "Pokemon TCG: Mega Evolution Pitch Black Booster Pack"}
        self.h.apply_scan("Big W", [dict(pack, sku="1", price_aud=7.5)], NOW)
        self.h.apply_scan("Kmart", [dict(pack, sku="2", price_aud=7.0)], NOW)
        self.h.apply_scan("Target", [dict(pack, sku="3", price_aud=7.5)], NOW)
        opps = self.h.opportunities()
        self.assertEqual(len(opps), 1)
        self.assertEqual((opps[0]["store"], sorted(opps[0]["also"])), ("Kmart", ["Big W", "Target"]))
        text = "\n".join(messages.build_digest("Tue 10 Nov", [], [], {"Kmart": {"ok": 1, "failed": 0}}, opportunities=opps))
        self.assertIn("Kmart $7.00 · 17% under US market (A$8.40), up 12% in 30 days · also at Big W, Target", text)

    def test_set_calendar_and_digest_section(self):
        seed(self.h, "Delta Reign", 3, "2026-11-06", {"etb": [(0, 80.0)]})
        seed(self.h, "Future Storm", 4, "2026-12-04", {})
        seed(self.h, "Far Future", 5, "2027-06-01", {})
        cal = self.h.set_calendar(NOW)
        self.assertEqual([(c["set_name"], c["status"]) for c in cal],
                         [("Delta Reign", "released"), ("Future Storm", "upcoming")])
        text = "\n".join(messages.build_digest("Tue 10 Nov", [], [], {"Big W": {"ok": 1, "failed": 0}}, sets=cal,
                                               hot_sets=["Pitch Black"]))
        self.assertIn("**Sets to watch**", text)
        self.assertIn("• 🔥 Pitch Black: US market up 10% or more in 30 days, so every product pings", text)
        self.assertIn("• 🆕 Delta Reign: released 6 Nov, every product pings until 4 Feb", text)
        self.assertIn("• 📅 Future Storm: releases 4 Dec", text)


if __name__ == "__main__":
    unittest.main()
