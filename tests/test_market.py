from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline import market, messages  # noqa: E402
from pipeline.history import History  # noqa: E402

NOW = datetime(2026, 11, 10, 1, 0, tzinfo=timezone.utc)

GROUPS = {"results": [
    {"groupId": 24655, "name": "ME04: Chaos Rising", "publishedOn": "2026-05-22T00:00:00"},
    {"groupId": 24831, "name": "ME06: Delta Reign", "publishedOn": "2026-11-06T00:00:00"},
    {"groupId": 24451, "name": "ME: Mega Evolution Promo", "publishedOn": "2025-09-26T00:00:00"},
    {"groupId": 24461, "name": "MEE: Mega Evolution Energies", "publishedOn": "2025-09-26T00:00:00"},
    {"groupId": 1422, "name": "POP Series 1", "publishedOn": "2026-11-09T00:00:00"},
    {"groupId": 100, "name": "SV01: Scarlet & Violet Base Set", "publishedOn": "2023-03-31T00:00:00"},
]}
PRODUCTS = {
    24655: [(1, "Chaos Rising Booster Box", 181.25), (2, "Chaos Rising Booster Box Case", 1033.9),
            (3, "Chaos Rising Elite Trainer Box", 70.44), (4, "Chaos Rising Pokemon Center Elite Trainer Box", 119.75),
            (5, "Chaos Rising Booster Bundle", 37.92), (6, "Chaos Rising Booster Pack", 5.48),
            (7, "Chaos Rising Sleeved Booster Pack", 6.6), (8, "Charizard ex - 001/100", 12.0),
            (9, "Chaos Rising 3-Pack Blister [Charmeleon]", 20.88)],
    24831: [(11, "Delta Reign Elite Trainer Box [Latias]", 80.0), (12, "Delta Reign Elite Trainer Box [Latios]", 90.0),
            (13, "Delta Reign Booster Box", None)],
}


def fake_fetch(url):
    if url.endswith("/groups"):
        return GROUPS
    if "frankfurter" in url:
        return {"rates": {"AUD": 1.5}}
    gid = int(url.split("/")[-2])
    if url.endswith("/products"):
        return {"results": [{"productId": p, "name": n, "url": f"https://tcg.example/{p}"} for p, n, _ in PRODUCTS[gid]]}
    return {"results": [{"productId": p, "marketPrice": m, "subTypeName": "Normal"} for p, _, m in PRODUCTS[gid]]}


class MarketTests(unittest.TestCase):
    def setUp(self):
        self.h = History(":memory:")

    def test_group_selection_and_set_name(self):
        picked = market.select_groups(GROUPS["results"], NOW)
        self.assertEqual([(g["groupId"], g["set_name"]) for g in picked],
                         [(24655, "Chaos Rising"), (24831, "Delta Reign")])

    def test_product_type_from_market_name(self):
        f = market.market_ptype
        self.assertEqual(f("Chaos Rising Booster Box", "Chaos Rising"), "booster_box")
        self.assertIsNone(f("Chaos Rising Booster Box Case", "Chaos Rising"))
        self.assertEqual(f("Chaos Rising Elite Trainer Box", "Chaos Rising"), "etb")
        self.assertIsNone(f("Chaos Rising Pokemon Center Elite Trainer Box", "Chaos Rising"))
        self.assertEqual(f("Delta Reign Elite Trainer Box [Latias]", "Delta Reign"), "etb")
        self.assertEqual(f("Chaos Rising Booster Bundle", "Chaos Rising"), "booster_bundle")
        self.assertEqual(f("Chaos Rising Booster Pack", "Chaos Rising"), "booster")
        self.assertEqual(f("Chaos Rising Sleeved Booster Pack", "Chaos Rising"), "sleeved_booster")
        self.assertIsNone(f("Charizard ex - 001/100", "Chaos Rising"))
        self.assertIsNone(f("Chaos Rising 3-Pack Blister [Charmeleon]", "Chaos Rising"))

    def test_sync_stores_prices_fx_and_release_dates(self):
        n = market.sync(self.h, NOW, fetch=fake_fetch)
        self.assertEqual(n, 7)  # 5 Chaos Rising + 2 Delta Reign ETBs; the unpriced box is skipped
        self.assertEqual(self.h.latest_fx(), 1.5)
        v = self.h.market_value("chaos rising", "etb")
        self.assertEqual((v["usd"], v["aud"]), (70.44, 105.66))
        # Two ETB variants: the cheaper one is the reference.
        self.assertEqual(self.h.market_value("Delta Reign", "etb")["usd"], 80.0)
        self.assertIsNone(self.h.market_value("Delta Reign", "booster_box"))
        self.assertIsNone(self.h.market_value(None, "etb"))
        self.assertEqual(self.h.set_release("delta reign"), "2026-11-06")
        # Syncing twice on the same day does not duplicate rows.
        market.sync(self.h, NOW, fetch=fake_fetch)
        self.assertEqual(len(self.h.market_series("etb", "2026-01-01")), 2)

    def test_fx_failure_falls_back_to_last_rate(self):
        market.sync(self.h, NOW, fetch=fake_fetch)

        def no_fx(url):
            if "frankfurter" in url:
                raise OSError("down")
            return fake_fetch(url)

        market.sync(self.h, NOW + timedelta(days=1), fetch=no_fx)
        self.assertEqual(self.h.latest_fx(), 1.5)

    def test_release_date_drives_the_new_set_rule(self):
        market.sync(self.h, NOW, fetch=fake_fetch)
        new = {"sku": "d1", "title": "Pokemon TCG: Mega Evolution Delta Reign Booster Pack", "price_aud": 8.5}
        old = {"sku": "c1", "title": "Pokemon TCG: Mega Evolution Chaos Rising Booster Pack", "price_aud": 8.5}
        self.h.apply_scan("Kmart", [], NOW)
        ev = self.h.apply_scan("Kmart", [new, old], NOW + timedelta(minutes=5))
        self.assertEqual({e["sku"]: e["tier"] for e in ev}, {"d1": "ping", "c1": "digest"})
        # A released-4-days-ago set counts as new even when first seen in a baseline run.
        ev = self.h.apply_scan("Target", [new], NOW)
        self.assertEqual((ev[0]["tier"], ev[0]["baseline"]), ("ping", 1))

    def test_market_line_on_ping(self):
        line = messages.market_line(79.0, {"usd": 70.44, "aud": 105.66})
        self.assertEqual(line, "US market ≈ A$106 (US$70, converted) · shelf price is 25% below")
        self.assertEqual(messages.market_line(120.0, {"usd": 70.44, "aud": 105.66}),
                         "US market ≈ A$106 (US$70, converted) · shelf price is 14% above")
        self.assertEqual(messages.market_line(106.0, {"usd": 70.44, "aud": 105.66}),
                         "US market ≈ A$106 (US$70, converted) · shelf price is about the same")
        self.assertEqual(messages.market_line(None, {"usd": 70.44, "aud": None}), "US market ≈ US$70")
        self.assertIsNone(messages.market_line(79.0, None))
        e = {"id": 1, "store": "Big W", "title": "X ETB", "label": "restock", "ptype": "etb", "price": 79.0, "url": None}
        text = messages.format_ping(e, {"times_30d": 1, "last_duration_min": None,
                                        "market": {"usd": 70.44, "aud": 105.66}})
        self.assertEqual(text.splitlines()[-1], "US market ≈ A$106 (US$70, converted) · shelf price is 25% below")

    def test_archive_dates(self):
        self.assertEqual(market.weekly_dates(NOW, 3), ["2026-10-20", "2026-10-27", "2026-11-03"])


if __name__ == "__main__":
    unittest.main()
