from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import scrape_shopify  # noqa: E402
from pipeline import messages, run, watch  # noqa: E402
from pipeline.classify import parse_watch, watch_matches  # noqa: E402
from pipeline.history import MAX_WATCHES, History  # noqa: E402

NOW = datetime(2026, 11, 10, 1, 0, tzinfo=timezone.utc)
ETB = {"sku": "e1", "title": "Pokemon TCG: Mega Evolution Delta Reign Elite Trainer Box", "price_aud": 79.0,
       "url": "https://shop.example/e1"}
BLISTER = {"sku": "b1", "title": "Pokemon TCG: Scarlet & Violet Surging Sparks Blister", "price_aud": 8.5,
           "url": "https://shop.example/b1"}


def later(minutes):
    return NOW + timedelta(minutes=minutes)


class ParseTests(unittest.TestCase):
    def test_type_words_become_a_type_and_the_rest_are_terms(self):
        self.assertEqual(parse_watch("Delta Reign ETB"), ("delta reign", "etb"))
        self.assertEqual(parse_watch("any Pitch Black booster boxes"), ("pitch black", "booster_box"))
        self.assertEqual(parse_watch("Prismatic Evolutions"), ("prismatic evolutions", None))

    def test_matching_respects_type_price_and_store(self):
        w = {"terms": "delta reign", "ptype": "etb", "max_price": 80.0, "store": None}
        p = {"title": ETB["title"], "ptype": "etb", "price": 79.0, "store": "Big W"}
        self.assertTrue(watch_matches(w, p))
        self.assertFalse(watch_matches(w, dict(p, price=95.0)))
        self.assertFalse(watch_matches(w, dict(p, ptype="booster")))
        self.assertFalse(watch_matches(dict(w, store="kmart"), p))
        self.assertTrue(watch_matches(dict(w, store="big w"), p))
        self.assertFalse(watch_matches(dict(w, terms="reign delta x"), p))


class WatchFlowTests(unittest.TestCase):
    def setUp(self):
        self.h = History(":memory:")
        self.sent = []

    def scan(self, stock, minutes, specialist=()):
        return run.scan(self.h, list(stock), stock.get, self.sent.append, later(minutes), specialist=specialist)

    def test_watched_digest_item_pings_with_a_mention(self):
        self.scan({"Target": []}, 0)
        code, text = watch.add(self.h, "surging sparks blister", "tom", "123456789", None, None, NOW)
        self.assertEqual(code, 0)
        self.assertIn("Nothing matching is in stock", text)
        self.scan({"Target": [BLISTER]}, 5)
        self.assertEqual(len(self.sent), 1)
        self.assertIn("<@123456789>", self.sent[0])
        self.assertIn("NEW LISTING", self.sent[0])
        self.scan({"Target": [BLISTER]}, 10)
        self.assertEqual(len(self.sent), 1)  # told once

    def test_ping_and_watch_share_one_alert(self):
        self.scan({"Big W": []}, 0)
        watch.add(self.h, "delta reign etb", "tom", None, 80.0, None, NOW)
        self.scan({"Big W": [ETB]}, 5)
        self.assertEqual(len(self.sent), 1)
        self.assertEqual(self.sent[0].count("Delta Reign"), 1)
        self.assertIn("**tom** (watching \"delta reign etb\" under $80.00)", self.sent[0])
        self.assertEqual(self.h.unposted_pings(), [])
        self.assertEqual(self.h.unposted_hits(), [])

    def test_price_ceiling_blocks_arrival_then_a_drop_alerts(self):
        other = dict(BLISTER, sku="b0", title=BLISTER["title"] + " Three Pack", price_aud=20.0)
        self.scan({"Target": [other]}, 0)  # the set is already known, so it is not a "new set"
        watch.add(self.h, "surging sparks blister", "tom", "42424242", 8.0, None, NOW)
        BOTH = [other, BLISTER]
        self.scan({"Target": BOTH}, 5)
        self.assertEqual(self.sent, [])
        self.scan({"Target": [other, dict(BLISTER, price_aud=7.5)]}, 10)
        self.assertEqual(len(self.sent), 1)
        self.assertIn("PRICE DROP", self.sent[0])
        self.assertIn("$8.50 → **$7.50**", self.sent[0])

    def test_baseline_never_alerts_but_add_reports_current_stock(self):
        self.scan({"Target": [BLISTER]}, 0)
        code, text = watch.add(self.h, "surging sparks", "tom", None, None, None, NOW)
        self.assertIn("In stock right now (1)", text)
        self.scan({"Target": [BLISTER]}, 5)
        self.assertEqual(self.sent, [])

    def test_limits_duplicates_and_removal(self):
        self.assertEqual(watch.add(self.h, "pokemon etb box", "tom", None, None, None, NOW)[0], 0)  # type only is fine
        self.assertEqual(watch.add(self.h, "the", "tom", None, None, None, NOW)[0], 2)
        for i in range(MAX_WATCHES - 1):
            self.assertEqual(watch.add(self.h, f"set{i}", "tom", None, None, None, NOW)[0], 0)
        self.assertEqual(watch.add(self.h, "one more", "tom", None, None, None, NOW)[0], 1)
        self.assertIn("Already watching", watch.add(self.h, "SET1", "Tom", None, None, None, NOW)[1])
        self.assertEqual(watch.add(self.h, "one more", "max", None, None, None, NOW)[0], 0)  # limit is per person
        first = self.h.watches(asker="tom")[0]
        self.h.remove_watch(first["id"])
        self.assertEqual(len(self.h.watches(asker="tom")), MAX_WATCHES - 1)

    def test_only_user_mentions_are_allowed_to_notify(self):
        tag = messages.watcher_tag({"user_id": None, "asker": "@everyone", "text": "x", "max_price": None})
        self.assertNotIn("<@", tag)


class SpecialistTests(unittest.TestCase):
    def setUp(self):
        self.h = History(":memory:")
        self.sent = []

    def test_specialist_store_pings_only_new_sets_and_is_checked_less_often(self):
        calls = []
        old_etb = {"sku": "o1", "title": "Pokemon TCG Crown Zenith Elite Trainer Box", "price_aud": 199.0}

        def scrape(store):
            calls.append(store)
            return stock[store]

        stock = {"Gameology": []}
        run.scan(self.h, ["Gameology"], scrape, self.sent.append, NOW, specialist={"Gameology"})
        stock["Gameology"] = [old_etb]
        run.scan(self.h, ["Gameology"], scrape, self.sent.append, later(5), specialist={"Gameology"})
        self.assertEqual(len(calls), 1)  # too soon: skipped, and not counted as a failure
        run.scan(self.h, ["Gameology"], scrape, self.sent.append, later(15), specialist={"Gameology"})
        self.assertEqual(len(calls), 2)
        self.assertEqual(self.sent, [])  # an old ETB at a specialist shop is digest tier
        self.assertEqual(self.h.in_stock_now()[0]["tier"], "digest")

    def test_digest_counts_specialist_stock_instead_of_listing_it(self):
        stock = [{"store": "Gameology", "title": f"Pokemon TCG Thing {i} Tin", "ptype": "tin", "price": 30.0, "url": None}
                 for i in range(40)]
        stock.append({"store": "Kmart", "title": "Pokemon TCG Tin", "ptype": "tin", "price": 25.0, "url": None})
        text = "\n".join(messages.build_digest("Tue 10 Nov", [], stock, {"Kmart": {"ok": 1, "failed": 0}},
                                               specialist={"Gameology"}, watch_count=2))
        self.assertIn("**In stock now (1)**", text)
        self.assertIn("• Gameology: 40 products in stock", text)
        self.assertNotIn("Thing 7", text)
        self.assertIn("2 personal watches active", text)


class ShopifyScraperTests(unittest.TestCase):
    def test_only_buyable_variants_count_and_category_marks_tcg(self):
        products = [
            {"id": 1, "handle": "a", "title": "Crown Zenith Elite Trainer Box", "product_type": "Trading Card Games",
             "variants": [{"available": False, "price": "10.00"}, {"available": True, "price": "199.95"}]},
            {"id": 2, "handle": "b", "title": "Sold Out Box", "product_type": "Trading Card Games",
             "variants": [{"available": False, "price": "5.00"}]},
        ]
        result = scrape_shopify.scrape("gameology", fetch=lambda base, handle, page: products, pause=0)
        self.assertEqual(len(result["in_stock"]), 1)
        item = result["in_stock"][0]
        self.assertEqual((item["sku"], item["price_aud"]), ("1", 199.95))
        self.assertTrue(item["title"].endswith("(TCG)"))
        self.assertTrue(item["url"].endswith("/products/a"))


class SenderTests(unittest.TestCase):
    def test_discord_id_comes_from_the_latest_message_with_that_name(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            now = 1_800_000_000.0
            def msg(name, uid, age):
                return json.dumps({"type": "message", "message": {
                    "role": "user", "content": "watch x", "timestamp": int((now - age) * 1000),
                    "__openclaw": {"senderId": uid, "senderName": name, "senderUsername": name + "_u"}}})
            (d / "a.jsonl").write_text(msg("max", "111", 600) + "\n" + msg("Tom", "222", 20) + "\n")
            (d / "sessions.json").write_text(json.dumps({
                "agent:main:discord:channel:1": {"sessionFile": str(d / "a.jsonl"), "updatedAt": int(now * 1000)},
                "agent:main:whatsapp:direct:2": {"sessionFile": str(d / "a.jsonl"), "updatedAt": int(now * 1000)}}))
            self.assertEqual(watch.discord_sender("tom", d, now), {"id": "222", "name": "Tom"})
            self.assertEqual(watch.discord_sender("tom_u", d, now)["id"], "222")
            self.assertIsNone(watch.discord_sender("max", d, now))      # not the latest message
            self.assertIsNone(watch.discord_sender("tom", d, now + 3600))  # too old


if __name__ == "__main__":
    unittest.main()
