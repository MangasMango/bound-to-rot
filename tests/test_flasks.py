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

"""Tests for the T-slot flask (issue #73 ADDITION, Phase A scope)."""

import unittest

import systems.flasks as flasks
import systems.itemgen as itemgen
from systems.items import ITEMS, make_inventory


def make_stats(max_health=100.0, health=50.0):
    return {'max_health': max_health, 'health': health}


class TestFlaskBasics(unittest.TestCase):
    def test_flask_items_exist_with_kinds(self):
        for kind, item_id in flasks.FLASK_ITEM_FOR_KIND.items():
            self.assertIn(item_id, ITEMS)
            self.assertEqual(ITEMS[item_id]['isFlask'], kind)

    def test_new_inventory_has_starter_flask(self):
        inv = make_inventory()
        flask = inv['flask_slot']
        self.assertIsNotNone(flask)
        self.assertEqual(flask['item'], 'flask_health')
        self.assertEqual(flask['charges'], 1)   # one use per wave

    def test_roll_for_flask_initializes_charges(self):
        slot = itemgen.roll_for('flask_utility', 1, 1, seed=5)
        self.assertEqual(slot['charges'], 1)


    def test_mana_flask_was_retired_with_mana(self):
        """Owner ruling 2026-10-29: mana left the game, so neither the item
        def nor its projectable kind exists any more."""
        self.assertNotIn('flask_mana', ITEMS)
        self.assertNotIn('mana', flasks.FLASK_KINDS)


class TestFlaskUsage(unittest.TestCase):
    def test_health_flask_regen_over_duration(self):
        inv = make_inventory()
        state = {'_flask_cd': 0.0, 'flask_effects': []}
        stats = make_stats(health=50.0)
        kind = flasks.use_flask(inv, state, stats)
        self.assertEqual(kind, 'health')
        self.assertEqual(inv['flask_slot']['charges'], 0)
        self.assertEqual(state['_flask_cd'], flasks.FLASK_CD)
        # tick the 3s duration: regen 40% of 100 over 3s (the tick that
        # crosses the duration boundary is dropped, hence the delta)
        for _ in range(30):
            flasks.tick_flask_effects(state, stats, 0.1)
        self.assertAlmostEqual(stats['health'], 90.0, delta=1.5)
        self.assertEqual(state['flask_effects'], [])

    def test_utility_flask_haste_multiplier(self):
        inv = make_inventory()
        inv['flask_slot'] = {'item': 'flask_utility', 'count': 1, 'charges': 3}
        state = {'_flask_cd': 0.0, 'flask_effects': []}
        stats = make_stats()
        self.assertEqual(flasks.use_flask(inv, state, stats), 'utility')
        haste = flasks.tick_flask_effects(state, stats, 0.1)
        self.assertEqual(haste, flasks.UTILITY_MULT)
        # expires after the duration
        flasks.tick_flask_effects(state, stats, flasks.UTILITY_DURATION + 0.01)
        haste = flasks.tick_flask_effects(state, stats, 0.1)
        self.assertEqual(haste, 1.0)

    def test_one_charge_per_wave_then_blocked(self):
        # Owner's tuning rule: exactly one use per wave. After the single
        # drink the flask is empty until the next wave resets it to 1.
        inv = make_inventory()
        state = {'_flask_cd': 0.0, 'flask_effects': []}
        self.assertIsNotNone(flasks.use_flask(inv, state, make_stats()))
        self.assertEqual(inv['flask_slot']['charges'], 0)
        state['_flask_cd'] = 0.0
        self.assertIsNone(flasks.use_flask(inv, state, make_stats()))
        # next wave/encounter begins -> reset to 1
        flasks.reset_for_wave(inv)
        self.assertEqual(inv['flask_slot']['charges'], 1)
        state['_flask_cd'] = 0.0
        self.assertIsNotNone(flasks.use_flask(inv, state, make_stats()))

    def test_reset_for_wave_ties_to_wave_lifecycle(self):
        # reset_for_wave is what _delve_spawn_wave calls; never a timer.
        inv = make_inventory()
        inv['flask_slot'] = {'item': 'flask_utility', 'count': 1, 'charges': 0}
        flasks.reset_for_wave(inv)
        self.assertEqual(inv['flask_slot']['charges'], flasks.WAVE_CHARGES)
        self.assertEqual(flasks.WAVE_CHARGES, 1)

    def test_empty_charges_block_drink(self):
        inv = make_inventory()
        inv['flask_slot'] = {'item': 'flask_health', 'count': 1, 'charges': 0}
        state = {'_flask_cd': 0.0, 'flask_effects': []}
        self.assertIsNone(flasks.use_flask(inv, state, make_stats()))

    def test_no_flask_equipped(self):
        inv = make_inventory()
        inv['flask_slot'] = None
        state = {'_flask_cd': 0.0, 'flask_effects': []}
        self.assertIsNone(flasks.use_flask(inv, state, make_stats()))


class TestFlaskRefill(unittest.TestCase):
    def test_refill_restores_single_wave_charge(self):
        inv = make_inventory()
        inv['flask_slot']['charges'] = 0
        flasks.refill_inventory(inv)
        self.assertEqual(inv['flask_slot']['charges'], 1)

    def test_refill_without_flask_is_noop(self):
        inv = make_inventory()
        inv['flask_slot'] = None
        flasks.refill_inventory(inv)   # must not raise


if __name__ == '__main__':
    unittest.main()
