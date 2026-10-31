# Copyright (C) 2026 MangasMango
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

"""Drop-rate rework - BLUEPRINT §23 (whole-card drops, per-card weights,
Fool depth taper, chart-truthful room rewards) and the fixed
wing-loot / kill-table paths."""

import random
import unittest
from collections import Counter
from pathlib import Path

import core.game as game_mod
import core.delve_gen as delve_gen
import systems.currency as currency
import systems.itemgen as itemgen
from systems.items import ITEMS


ROOT = Path(__file__).resolve().parent.parent


# ── whole-card drops + per-card weights ───────────────────────────────

class TestCardDrops(unittest.TestCase):
    def test_every_card_drop_is_a_complete_card(self):
        rng = random.Random(2)
        for depth in (1, 3, 7, 12):
            for _ in range(50):
                arcana, quarters = currency.roll_fraction_drop(depth, rng)
                # one whole card either way: Fool as 4 quarters, others as 1
                self.assertEqual(quarters, currency.quarters_needed(arcana))

    def test_fool_most_likely_at_low_depth(self):
        rng = random.Random(3)
        counts = Counter()
        for _ in range(3000):
            arcana, _ = currency.roll_fraction_drop(1, rng)
            counts[arcana] += 1
        fool, _top = counts.most_common(1)[0]
        self.assertEqual(fool, 0)

    def test_fool_weight_tapers_and_floors(self):
        self.assertGreater(currency.fool_weight(1), currency.fool_weight(6))
        self.assertGreater(currency.fool_weight(6), currency.fool_weight(20))
        floor = currency.CARD_DROP_WEIGHTS[0] * currency.FOOL_TAPER_FLOOR
        self.assertEqual(currency.fool_weight(1000), floor)

    def test_depth_gates_respected(self):
        rng = random.Random(4)
        for depth, forbidden in ((1, (4, 10, 11, 13, 15, 17)),
                                 (2, (4, 11, 13, 15, 17)),
                                 (3, (13, 15))):
            for _ in range(200):
                arcana, _ = currency.roll_fraction_drop(depth, rng)
                self.assertNotIn(arcana, forbidden,
                                 f'arcana {arcana} dropped below its depth_min')

    def test_every_weighted_card_is_registered(self):
        self.assertEqual(set(currency.CARD_DROP_WEIGHTS),
                         set(currency.CURRENCY_CARDS))


# ── chart-truthful room rewards (§24) ─────────────────────────────────

class TestRoomRewards(unittest.TestCase):
    def _game(self):
        g = game_mod.Game()
        return g

    def test_room_grants_exactly_the_chart_rewards(self):
        g = self._game()
        node = {'rewards': [{'item': 'lungs', 'count': 1},
                            {'item': 'gem_blue', 'count': 1}]}
        slots = g._room_reward_slots(node, 10)
        dropped = [s['item'] for s in slots if not currency.is_card_item(s['item'])]
        self.assertEqual(dropped, ['lungs', 'gem_blue'])
        # each reward rolled a fresh instance
        lungs = next(s for s in slots if s['item'] == 'lungs')
        self.assertIn('instance_data', lungs)
        # organs drop unidentified, gems identified - same as any drop
        self.assertFalse(itemgen.is_identified(lungs))

    def test_empty_node_drops_nothing_but_the_card_roll(self):
        g = self._game()
        node = {'rewards': []}
        for _ in range(30):
            slots = g._room_reward_slots(node, 5)
            non_cards = [s for s in slots if not currency.is_card_item(s['item'])]
            self.assertEqual(non_cards, [])
            self.assertLessEqual(len(slots), 1)

    def test_legacy_node_without_rewards_key_falls_back(self):
        g = self._game()
        node = {}                       # old save: no 'rewards' key at all
        for _ in range(10):
            slots = g._room_reward_slots(node, 5)
            self.assertGreaterEqual(len(slots), 1)   # legacy roll never empty

    def test_reward_table_rows_have_names_and_defs(self):
        for node_type, table in delve_gen.REWARD_TABLES.items():
            for item_id, _mn, _mx, _chance in table:
                self.assertIn(item_id, delve_gen.ITEM_NAMES,
                              f'{node_type}: {item_id} has no chart label')
                self.assertIn(item_id, ITEMS,
                              f'{node_type}: {item_id} has no item def')

    def test_combat_nodes_can_roll_gems(self):
        rng = random.Random(5)
        saw_gem = False
        for _ in range(200):
            if any(r['item'].startswith('gem_')
                   for r in delve_gen._roll_rewards(rng, 'combat')):
                saw_gem = True
                break
        self.assertTrue(saw_gem)


# ── fixed wing loot + kill table ──────────────────────────────────────

class TestWingAndKillDrops(unittest.TestCase):
    def test_wing_guaranteed_equip_does_not_crash_and_honors_floor(self):
        g = game_mod.Game()
        for _ in range(25):
            slots = g._roll_hidden_loot(10)      # crashed (KeyError: 1) before
            equips = [s['instance_data'] for s in slots
                      if s.get('instance_data') and s['item'] in ITEMS
                      and ITEMS[s['item']].get('equipSlot')]
            self.assertTrue(equips)              # depth 10: equip guaranteed
            floor = delve_gen.hidden_tier_for_depth(10)['rarity_floor']
            # the guaranteed slot meets the floor (the 80% organ roll may be common)
            self.assertTrue(any(
                itemgen.RARITY_ORDER.index(inst['rarity']) >= floor
                for inst in equips))

    def test_wing_organ_pools_include_liver(self):
        g = game_mod.Game()
        organs_seen = set()
        rng_backup = random.Random(9)
        for _ in range(120):
            for slot in g._roll_hidden_loot(5):
                if slot['item'] in ('lungs', 'liver', 'heart', 'kidney', 'intestine'):
                    organs_seen.add(slot['item'])
        self.assertIn('liver', organs_seen)

    def test_utility_flask_drops_from_kills(self):
        item_ids = {row[0] for row in game_mod.SKELETON_DROP_TABLE}
        self.assertIn('flask_utility', item_ids)


# ── Anima-panel modal guards (part 7) ────────────────────────────────

class TestAnimaPanelInputGuards(unittest.TestCase):
    def test_world_clicks_and_keys_guard_the_panel(self):
        src = (ROOT / 'core' / 'input.py').read_text(encoding='utf-8')
        self.assertGreaterEqual(src.count('_delve_chart_is_open()'), 3,
                                'mouse, QWER/T guards missing in input.py')

    def test_hover_cursor_guards_the_panel(self):
        src = (ROOT / 'core' / 'game.py').read_text(encoding='utf-8')
        self.assertIn('_hover_interactable', src)
        # the guard line inside _hover_interactable
        self.assertRegex(src, r"inv\.open or self\._hub_popup or self\._delve_chart_is_open")

    def test_delve_chart_open_flag_roundtrip(self):
        g = game_mod.Game()
        self.assertFalse(g._delve_chart_is_open())
        g._delve_chart_open = True
        self.assertTrue(g._delve_chart_is_open())


if __name__ == '__main__':
    unittest.main()
