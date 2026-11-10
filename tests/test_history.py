from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.classify import parse_watchlist  # noqa: E402
from pipeline.history import History  # noqa: E402

T0 = datetime(2026, 11, 10, 0, 0, tzinfo=timezone.utc)


def at(minutes: float) -> datetime:
    return T0 + timedelta(minutes=minutes)


def item(sku, title, price=10.0, **extra):
    d = {"sku": sku, "title": title, "price_aud": price, "url": f"https://shop.example/{sku}"}
    d.update(extra)
    return d


BOOSTER = item("b1", "Pokemon TCG: Mega Evolution Chaos Rising Booster Pack", 8.5)
ETB = item("e1", "Pokemon TCG: Mega Evolution Chaos Rising Elite Trainer Box", 79.0)
SOCKS = item("s1", "Licensed Pokemon 3 Pack Quarter Crew Socks", 12.0)


class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.h = History(":memory:")

    def kinds(self, events):
        return [(e["kind"], e["label"], e["tier"], e["baseline"]) for e in events]

    def test_baseline_is_silent_and_ignores_non_tcg(self):
        ev = self.h.apply_scan("Big W", [BOOSTER, ETB, SOCKS], at(0))
        self.assertEqual(len(ev), 2)
        self.assertTrue(all(e["baseline"] == 1 for e in ev))
        self.assertEqual(self.h.unposted_pings(), [])
        self.assertEqual(sorted(p["sku"] for p in self.h.in_stock_now()), ["b1", "e1"])

    def test_new_listing_after_baseline_pings(self):
        self.h.apply_scan("Big W", [BOOSTER], at(0))
        ev = self.h.apply_scan("Big W", [BOOSTER, ETB], at(5))
        self.assertEqual(self.kinds(ev), [("appeared", "new", "ping", 0)])
        pings = self.h.unposted_pings()
        self.assertEqual([p["sku"] for p in pings], ["e1"])
        self.assertEqual(pings[0]["price"], 79.0)
        self.h.mark_posted([pings[0]["id"]])
        self.assertEqual(self.h.unposted_pings(), [])

    def test_digest_tier_item_does_not_ping(self):
        self.h.apply_scan("Big W", [ETB], at(0))
        other = item("b2", "Pokemon TCG: Mega Evolution Chaos Rising Checklane Blister", 8.0)
        self.h.apply_scan("Kmart", [BOOSTER], at(0))  # makes Chaos Rising a baseline set
        ev = self.h.apply_scan("Big W", [ETB, other], at(5))
        self.assertEqual(self.kinds(ev), [("appeared", "new", "digest", 0)])
        self.assertEqual(self.h.unposted_pings(), [])

    def test_two_miss_rule_and_restock(self):
        self.h.apply_scan("Big W", [BOOSTER, ETB], at(0))
        self.assertEqual(self.h.apply_scan("Big W", [BOOSTER], at(5)), [])  # first miss: nothing
        self.assertEqual(len(self.h.in_stock_now()), 2)
        ev = self.h.apply_scan("Big W", [BOOSTER], at(10))  # second miss: gone
        self.assertEqual(self.kinds(ev), [("disappeared", None, "ping", 0)])
        self.assertEqual(ev[0]["duration_min"], 10)
        ev = self.h.apply_scan("Big W", [BOOSTER, ETB], at(60))
        self.assertEqual(self.kinds(ev), [("appeared", "restock", "ping", 0)])
        self.assertEqual([p["sku"] for p in self.h.unposted_pings()], ["e1"])

    def test_reappearing_after_one_miss_is_not_an_event(self):
        self.h.apply_scan("Big W", [ETB], at(0))
        self.h.apply_scan("Big W", [], at(5))
        self.assertEqual(self.h.apply_scan("Big W", [ETB], at(10)), [])
        self.assertEqual(self.h.apply_scan("Big W", [], at(15)), [])  # miss counter was reset

    def test_failed_store_records_nothing_but_the_failure(self):
        self.h.apply_scan("Big W", [ETB], at(0))
        self.h.record_failure("Big W", at(5))
        self.h.record_failure("Big W", at(10))
        self.assertEqual(len(self.h.in_stock_now()), 1)
        self.assertEqual(self.h.apply_scan("Big W", [], at(15)), [])  # still only the first miss
        stats = self.h.run_stats(at(-1), at(60))
        self.assertEqual(stats["Big W"], {"ok": 2, "failed": 2})

    def test_first_success_after_failures_is_still_baseline(self):
        self.h.record_failure("JB Hi-Fi", at(0))
        ev = self.h.apply_scan("JB Hi-Fi", [ETB], at(5))
        self.assertEqual(self.kinds(ev), [("appeared", "new", "ping", 1)])
        self.assertEqual(self.h.unposted_pings(), [])

    def test_price_change(self):
        self.h.apply_scan("Big W", [ETB], at(0))
        ev = self.h.apply_scan("Big W", [dict(ETB, price_aud=69.0)], at(5))
        self.assertEqual(self.kinds(ev), [("price", None, "ping", 0)])
        self.assertEqual((ev[0]["old_price"], ev[0]["price"]), (79.0, 69.0))
        self.assertEqual(self.h.apply_scan("Big W", [dict(ETB, price_aud=69.0)], at(10)), [])

    def test_new_set_promotes_to_ping_for_90_days(self):
        self.h.apply_scan("Big W", [BOOSTER], at(0))  # Chaos Rising is a baseline set
        fresh = item("b9", "Pokemon TCG: Mega Evolution Pitch Black Booster Pack", 8.5)
        ev = self.h.apply_scan("Big W", [BOOSTER, fresh], at(5))
        self.assertEqual(self.kinds(ev), [("appeared", "new", "ping", 0)])
        # Same set, another product, 91 days later: no longer new.
        later = item("b10", "Pokemon TCG: Mega Evolution Pitch Black Sleeved Booster", 8.5)
        ev = self.h.apply_scan("Big W", [BOOSTER, fresh, later], T0 + timedelta(days=91))
        self.assertEqual(self.kinds(ev), [("appeared", "new", "digest", 0)])

    def test_watchlist_overrides(self):
        wl = parse_watchlist("never: elite trainer\nalways: chaos rising booster pack\nignore: blister\n")
        self.h.apply_scan("Big W", [], at(0), wl)
        blister = item("x1", "Pokemon TCG: Mega Evolution Chaos Rising Checklane Blister")
        ev = self.h.apply_scan("Big W", [ETB, BOOSTER, blister], at(5), wl)
        tiers = {e["sku"]: e["tier"] for e in ev}
        # ETB forced down, booster forced up, blister dropped entirely. (Chaos Rising is
        # also a new set here, which would have pinged the ETB without the override.)
        self.assertEqual(tiers, {"e1": "digest", "b1": "ping"})

    def test_preorder_label_and_cart_url(self):
        self.h.apply_scan("Big W", [], at(0))
        pre = dict(ETB, status="pre_order", release_label="Available 14 Nov", cart_url="https://shop.example/cart/1")
        ev = self.h.apply_scan("Big W", [pre], at(5))
        self.assertEqual(ev[0]["label"], "preorder")
        ping = self.h.unposted_pings()[0]
        self.assertEqual(ping["cart_url"], "https://shop.example/cart/1")
        self.assertEqual(ping["release_label"], "Available 14 Nov")

    def test_ping_context_counts_stints_and_last_duration(self):
        self.h.apply_scan("Big W", [], at(0))
        self.h.apply_scan("Big W", [ETB], at(5))        # appears (1)
        self.h.apply_scan("Big W", [], at(10))
        self.h.apply_scan("Big W", [], at(45))          # gone after 40 min
        self.h.apply_scan("Big W", [ETB], at(100))      # appears (2)
        ping = self.h.unposted_pings()[-1]
        self.assertEqual(self.h.ping_context(ping), {"times_30d": 2, "last_duration_min": 40})

    def test_persists_to_disk(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "h.db"
            h = History(p)
            h.apply_scan("Big W", [ETB], at(0))
            h.close()
            h2 = History(p)
            self.assertEqual(len(h2.in_stock_now()), 1)
            h2.close()


if __name__ == "__main__":
    unittest.main()
