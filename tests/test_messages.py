from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline import messages  # noqa: E402


def ping(i=1, **kw):
    d = {
        "id": i, "ts": "2026-11-09T22:40:00+00:00", "store": "Big W", "sku": f"e{i}", "kind": "appeared",
        "label": "restock", "tier": "ping", "price": 79.0, "ptype": "etb",
        "title": "Pokémon TCG: Mega Evolution Chaos Rising ETB", "url": "https://shop.example/e1",
        "cart_url": None, "release_label": None, "in_stock": 1,
    }
    d.update(kw)
    return d


class PingTests(unittest.TestCase):
    def test_full_ping(self):
        p = ping(cart_url="https://shop.example/cart/1")
        out = messages.build_pings([(p, {"times_30d": 3, "last_duration_min": 40})])
        self.assertEqual(len(out), 1)
        text, ids = out[0]
        self.assertEqual(ids, [1])
        self.assertEqual(
            text,
            "🚨 **RESTOCK** · Elite Trainer Box · **$79.00**\n"
            "**Pokémon TCG: Mega Evolution Chaos Rising ETB**\n"
            "Big W · <https://shop.example/e1> · 🛒 <https://shop.example/cart/1>\n"
            "3rd time in stock in 30 days · last time it sold out in 40 min",
        )

    def test_first_sighting_has_no_history_line_and_labels(self):
        text, _ = messages.build_pings([(ping(label="new", price=None), {"times_30d": 1, "last_duration_min": None})])[0]
        self.assertEqual(text.splitlines()[0], "🆕 **NEW LISTING** · Elite Trainer Box")
        self.assertEqual(len(text.splitlines()), 3)
        text, _ = messages.build_pings(
            [(ping(label="preorder", release_label="Available 14 Nov"), {"times_30d": 1, "last_duration_min": None})])[0]
        self.assertEqual(text.splitlines()[0], "📅 **PRE-ORDER** · Elite Trainer Box · **$79.00** · Available 14 Nov")

    def test_many_pings_split_under_limit_with_matching_ids(self):
        many = [(ping(i, title="X" * 300), {"times_30d": 1, "last_duration_min": None}) for i in range(1, 13)]
        out = messages.build_pings(many)
        self.assertGreater(len(out), 1)
        self.assertTrue(all(len(t) <= messages.LIMIT for t, _ in out))
        self.assertEqual([i for _, ids in out for i in ids], list(range(1, 13)))

    def test_duration_words(self):
        self.assertEqual(messages.duration(40), "40 min")
        self.assertEqual(messages.duration(130), "2 h 10 min")
        self.assertEqual(messages.duration(120), "2 h")
        self.assertEqual(messages.duration(60 * 27), "1 d 3 h")
        self.assertEqual(messages.duration(0), "under 5 min")


class DigestTests(unittest.TestCase):
    def test_digest_sections(self):
        events = [
            ping(1, ts="2026-11-09T22:40:00+00:00"),  # 09:40 Melbourne, still in stock
            ping(2, ts="2026-11-09T23:00:00+00:00", title="Tin A", ptype="tin", in_stock=0, label="new", price=25.0),
            ping(3, ts="2026-11-09T23:45:00+00:00", kind="disappeared", label=None, title="Tin A", ptype="tin",
                 duration_min=45, sku="e2", in_stock=0, price=25.0),
            ping(4, ts="2026-11-10T01:00:00+00:00", kind="price", label=None, old_price=89.0, price=79.0),
        ]
        stock = [
            {"store": "Big W", "title": "Pokémon TCG: Mega Evolution Chaos Rising ETB", "ptype": "etb",
             "price": 79.0, "url": "https://shop.example/e1"},
            {"store": "Kmart", "title": "Booster", "ptype": "booster", "price": None, "url": "https://k.example/b"},
        ]
        runs = {"Big W": {"ok": 130, "failed": 2}, "JB Hi-Fi": {"ok": 0, "failed": 132}, "Kmart": {"ok": 132, "failed": 0}}
        out = messages.build_digest("Tue 10 Nov", events, stock, runs)
        text = "\n".join(out)
        self.assertTrue(all(len(m) <= messages.LIMIT for m in out))
        self.assertIn("📋 **Pokémon TCG daily digest · Tue 10 Nov**", text)
        self.assertIn("**Arrived today (2)**", text)
        self.assertIn("• 09:40 · Big W · Mega Evolution Chaos Rising ETB · $79.00 · still in stock", text)
        self.assertIn("• 10:00 · Big W · Tin A · $25.00 · gone after 45 min", text)
        self.assertIn("**Sold out today (1)**", text)
        self.assertIn("• 10:45 · Big W · Tin A · lasted 45 min", text)
        self.assertIn("**Price changes (1)**", text)
        self.assertIn("$89.00 → $79.00", text)
        self.assertIn("**In stock now (2)**", text)
        self.assertIn("__Big W__", text)
        self.assertIn("• Elite Trainer Box · [Mega Evolution Chaos Rising ETB](<https://shop.example/e1>) · $79.00", text)
        self.assertIn("⚠️ JB Hi-Fi: every scrape failed today (132)", text)
        self.assertIn("⚠️ Big W: 2 of 132 scrapes failed", text)
        self.assertNotIn("Kmart:", text)

    def test_short_title(self):
        st = messages.short_title
        self.assertEqual(st("Pokemon TCG: Mega Evolution—Chaos Rising Sleeved Booster - Assorted"),
                         "Mega Evolution—Chaos Rising Sleeved Booster")
        self.assertEqual(st("Pokemon Trading Card Game: Mega Lucario ex League Battle Deck"),
                         "Mega Lucario ex League Battle Deck")
        self.assertEqual(st("Pokémon TCG: Mega Evolution - Chaos Rising Blister - Assorted*"),
                         "Mega Evolution - Chaos Rising Blister")
        self.assertEqual(st("Pokemon TCG - Mega Zygarde ex Premium Collection"), "Mega Zygarde ex Premium Collection")
        self.assertEqual(st("Pokemon Eevee Heroes Booster Box Japanese"), "Pokemon Eevee Heroes Booster Box Japanese")
        self.assertEqual(st("Pokemon TCG"), "Pokemon TCG")

    def test_quiet_day(self):
        out = messages.build_digest("Tue 10 Nov", [], [], {})
        text = "\n".join(out)
        self.assertIn("No scrapes ran today", text)

    def test_quiet_day_with_stock(self):
        stock = [{"store": "Kmart", "title": "Booster", "ptype": "booster", "price": 8.5, "url": None}]
        text = "\n".join(messages.build_digest("Tue 10 Nov", [], stock, {"Kmart": {"ok": 10, "failed": 0}}))
        self.assertIn("Nothing arrived, sold out or changed price today.", text)
        self.assertIn("• Booster Pack · Booster · $8.50", text)

    def test_long_digest_splits(self):
        stock = [{"store": "Target", "title": f"Item {i} " + "y" * 80, "ptype": "booster", "price": 8.5,
                  "url": f"https://t.example/{i}"} for i in range(60)]
        out = messages.build_digest("Tue 10 Nov", [], stock, {"Target": {"ok": 1, "failed": 0}})
        self.assertGreater(len(out), 1)
        self.assertTrue(all(len(m) <= messages.LIMIT for m in out))


if __name__ == "__main__":
    unittest.main()
