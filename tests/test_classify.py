from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.classify import Watchlist, base_tier, classify, parse_watchlist  # noqa: E402

# Real titles seen on 2026-11-10 (plus the stale JB Hi-Fi file), with expectations.
CASES = [
    # (title, type, set)
    ("Licensed Pokemon 3 Pack Quarter Crew Socks", "not_tcg", None),
    ("Pokemon 2 Pack Older Boys Trunks", "not_tcg", None),
    ("Pokemon Short Sleeve Swim Rash Vest", "not_tcg", None),
    ("Pokemon Short Sleeve Swim Rashie", "not_tcg", None),
    ("Pokemon Select Eevee Evolutions Pack", "not_tcg", None),
    ("Christmas Pokemon Cards - 10 Pack", "not_tcg", None),
    ("Pokemon 8-inch Plush - Assorted*", "not_tcg", None),
    ("Pokemon Acrylic Booster Box Protector", "accessory", None),
    ("Pokemon TCG: Mini Portfolio - Assorted", "accessory", None),
    ("Pokemon: Mega Evolution 9-pocket Portfolio", "accessory", None),
    ("Pokemon TCG - 2025 Trainer's Toolkit", "accessory", None),
    ("Pokemon Eevee Heroes Booster Box Japanese", "booster_box", None),
    ("Pokemon TCG - Mega Evolutions 3: Perfect Order Display Box", "booster_box", "Perfect Order"),
    ("Pokemon TCG - Mega Evolutions 4: Chaos Rising Display Box", "booster_box", "Chaos Rising"),
    ("Pokemon TCG: Mega Evolution Chaos Rising Elite Trainer Box", "etb", "Chaos Rising"),
    ("Pokemon TCG: Scarlet & Violet Prismatic Evolutions Booster Bundle", "booster_bundle", "Prismatic Evolutions"),
    ("Pokemon TCG - Mega Zygarde ex Premium Collection", "collection", None),
    ("Pokemon TCG: Deck Crafter's Collection", "collection", None),
    ("Pokemon TCG: Mega Evolution Mini Tin - Assorted", "tin", "Mega Evolution"),
    ("Pokemon TCG: Mega Greninja ex League Battle Deck", "deck", None),
    ("Pokemon Trading Card Game: Mega Lucario ex League Battle Deck", "deck", None),
    ("Pokemon TCG - Mega Evolutions 3: Perfect Order Checklane Blister", "blister", "Perfect Order"),
    ("Pokémon TCG: Mega Evolution - Chaos Rising - Three-Booster Blister", "blister", "Chaos Rising"),
    ("Pokemon TCG: Mega Evolution - Phantasmal Flames Blisters - Assorted", "blister", "Phantasmal Flames"),
    ("Pokemon TCG: Scarlet & Violet—Journey Together - Blister Pack - Assorted*", "blister", "Journey Together"),
    ("Pokemon TCG: Mega Evolution—Chaos Rising Sleeved Booster - Assorted", "sleeved_booster", "Chaos Rising"),
    ("Pokemon Trading Card Game: Mega Evolution Pitch Black Sleeved Booster Pack - Assorted", "sleeved_booster", "Pitch Black"),
    ("Pokemon TCG: Mega Evolution Pitch Black Sleeved Booster", "sleeved_booster", "Pitch Black"),
    ("Pokemon TCG: Mega Evolution Chaos Rising Booster Pack", "booster", "Chaos Rising"),
    ("Pokemon TCG - Mega Evolutions 3: Perfect Order Booster", "booster", "Perfect Order"),
]


class ClassifyTests(unittest.TestCase):
    def test_real_titles(self):
        for title, ptype, set_name in CASES:
            with self.subTest(title=title):
                got = classify(title)
                self.assertEqual(got.ptype, ptype)
                self.assertEqual(got.set_name, set_name)

    def test_base_tiers(self):
        self.assertEqual(base_tier("booster_box"), "ping")
        self.assertEqual(base_tier("etb"), "ping")
        self.assertEqual(base_tier("booster_bundle"), "ping")
        self.assertEqual(base_tier("collection"), "ping")
        self.assertEqual(base_tier("tin"), "ping")
        self.assertEqual(base_tier("blister"), "digest")
        self.assertEqual(base_tier("booster"), "digest")
        self.assertEqual(base_tier("deck"), "digest")
        self.assertEqual(base_tier("accessory"), "ignore")
        self.assertEqual(base_tier("not_tcg"), "ignore")


class WatchlistTests(unittest.TestCase):
    def test_parse_and_precedence(self):
        wl = parse_watchlist(
            "# comment\n\nalways: Perfect Order\nnever: league battle\nignore: japanese\nrubbish line\n"
        )
        self.assertEqual(wl.override("Pokemon TCG: Perfect Order Booster"), "ping")
        self.assertEqual(wl.override("Mega Lucario ex League Battle Deck"), "digest")
        self.assertEqual(wl.override("Eevee Heroes Booster Box Japanese"), "ignore")
        self.assertIsNone(wl.override("Chaos Rising Booster"))
        # ignore beats never beats always
        self.assertEqual(wl.override("Perfect Order League Battle Deck"), "digest")
        self.assertEqual(wl.override("Japanese Perfect Order Booster"), "ignore")

    def test_empty(self):
        self.assertIsNone(Watchlist().override("anything"))


if __name__ == "__main__":
    unittest.main()
