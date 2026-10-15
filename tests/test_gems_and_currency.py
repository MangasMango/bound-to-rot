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

"""Tests for issue #73 DESIGN PIVOT.

Phase A — gems grant QWER abilities (blue=Q, green=W, red=E, white=R).
Phase B — tarot cards as PoE-style stacking currency + unidentified items.
"""

import unittest
import random

import systems.gems as gems
import systems.currency as currency
import systems.itemgen as itemgen
from systems.items import (ITEMS, can_equip, equip_from_grid, make_inventory,
                           grid_auto_place)


class TestGemAbilityMapping(unittest.TestCase):
    def test_color_slot_mapping(self):
        self.assertEqual(gems.GEM_COLOR_FOR_SLOT['Q'], 'blue')
        self.assertEqual(gems.GEM_COLOR_FOR_SLOT['W'], 'green')
        self.assertEqual(gems.GEM_COLOR_FOR_SLOT['E'], 'red')
        self.assertEqual(gems.GEM_COLOR_FOR_SLOT['R'], 'white')

    def test_gem_items_exist(self):
        for slot in gems.GEM_SLOTS:
            item_id = gems.gem_item_id(slot)
            self.assertIn(item_id, ITEMS)
            self.assertEqual(ITEMS[item_id]['isGem'], slot)

    def test_roll_for_gem_grants_slot_pool_ability(self):
        for slot in gems.GEM_SLOTS:
            with self.subTest(slot=slot):
                rng = random.Random(7)
                ok = False
                for _ in range(50):
                    slot_dict = itemgen.roll_for(gems.gem_item_id(slot), 1, 5, seed=None)
                    ab = slot_dict['instance_data']['ability']
                    if ab in gems.SLOT_GEM_POOLS[slot]:
                        ok = True
                        break
                self.assertTrue(ok)

    def test_socketed_ability_roundtrip(self):
        inv = make_inventory()
        slot_dict = itemgen.roll_for('gem_blue', 1, 5, seed=3)
        inv['gem_sockets']['Q'] = slot_dict
        found = gems.socketed_ability(inv, 'Q')
        self.assertIsNotNone(found)
        inst, ab, tier = found
        self.assertEqual(inst['ability'], slot_dict['instance_data']['ability'])
        self.assertIn(ab['type'], ('active', 'passive'))


class TestUnidentifiedItems(unittest.TestCase):
    def test_new_gear_drops_unidentified(self):
        slot = itemgen.roll_for('lungs', 1, 5, seed=11)
        self.assertFalse(itemgen.is_identified(slot))

    def test_gems_are_identified(self):
        slot = itemgen.roll_for('gem_blue', 1, 5, seed=11)
        self.assertTrue(itemgen.is_identified(slot))

    def test_identify_marks_instance(self):
        slot = itemgen.roll_for('heart', 1, 5, seed=2)
        itemgen.identify(slot)
        self.assertTrue(itemgen.is_identified(slot))

    def test_unidentified_stats_hidden_from_totals(self):
        slot = itemgen.roll_for('lungs', 1, 30, seed=5)
        hidden = itemgen.compute_item_stat_totals(slot)
        # unidentified exposes NO stat text at all — not even the base implicit
        self.assertEqual(hidden, {})
        self.assertEqual(itemgen.comparison_rows(slot, None), [])
        itemgen.identify(slot)
        revealed = itemgen.compute_item_stat_totals(slot)
        self.assertTrue(revealed)
        for key in set(hidden) | set(revealed):
            self.assertGreaterEqual(revealed.get(key, 0.0), hidden.get(key, 0.0))

    def test_unidentified_pickup_does_not_auto_equip(self):
        from core.game import Game

        class FakeAudio:
            def item_equip(self):
                raise AssertionError('unidentified item must not auto-equip')

            def item_pickup(self):
                pass

        inv = make_inventory()
        item = itemgen.roll_for('heart', 1, 5, seed=22)
        game = type('FakeGame', (), {
            'inventory': inv,
            'audio': FakeAudio(),
        })()
        Game._auto_place(game, item)
        self.assertIsNone(inv['equipped']['heart'])
        self.assertTrue(any(entry['item'] == 'heart' for entry in inv['grid']))

    def test_unidentified_item_cannot_be_equipped(self):
        """Owner rule (reverses #84): gear must be identified before equipping."""
        inv = make_inventory()
        item = itemgen.roll_for('heart', 1, 5, seed=21)
        item['col'], item['row'] = 0, 0
        inv['grid'].append(item)

        self.assertFalse(itemgen.is_identified(item))
        self.assertFalse(can_equip(item))
        grid_len = len(inv['grid'])
        self.assertFalse(equip_from_grid(inv, len(inv['grid']) - 1))
        self.assertIsNone(inv['equipped']['heart'])
        # the item stays in the backpack, untouched
        self.assertEqual(len(inv['grid']), grid_len)
        self.assertIs(inv['grid'][-1], item)

    def test_identified_item_can_be_equipped(self):
        inv = make_inventory()
        item = itemgen.roll_for('heart', 1, 5, seed=21)
        itemgen.identify(item)                      # e.g. a full 4/4 Fool
        item['col'], item['row'] = 0, 0
        inv['grid'].append(item)

        self.assertTrue(can_equip(item))
        self.assertTrue(equip_from_grid(inv, len(inv['grid']) - 1))
        self.assertIsNotNone(inv['equipped']['heart'])
        self.assertTrue(itemgen.is_identified(inv['equipped']['heart']))

    def test_non_equippable_item_is_never_equippable(self):
        inv = make_inventory()
        inv['grid'].append({'item': 'tarot_card_13', 'count': 5, 'col': 0, 'row': 0})
        self.assertFalse(equip_from_grid(inv, 0))

    def test_moon_rarity_supports_mythic(self):
        self.assertIn('mythic', itemgen.RARITY_ORDER)
        slot = itemgen.roll_for('liver', 1, 40, seed=9)
        slot['instance_data']['rarity'] = 'mythic'
        vals = itemgen.balanced_affix_values(slot['instance_data'])
        self.assertIsInstance(vals, dict)


class TestTarotCurrency(unittest.TestCase):
    def test_fraction_stacking_to_4(self):
        grid = []
        for _ in range(3):
            self.assertTrue(currency.add_card_to_grid(grid, 0, 1))
        self.assertEqual(grid[0]['count'], 3)
        currency.add_card_to_grid(grid, 0, 1)
        self.assertEqual(grid[0]['count'], 4)
        self.assertTrue(currency.card_complete(grid[0]))
        self.assertEqual(currency.stack_label(grid[0]), '4/4')

    def test_starter_set_present_in_new_inventory(self):
        self.assertEqual(currency.STARTER_CARD_QUARTERS, {0: 4, 1: 1, 10: 1})
        inv = make_inventory()
        cards = [e for e in inv['grid'] if currency.is_card_item(e['item'])]
        self.assertTrue(cards)
        fool = [e for e in cards if e['item'] == currency.card_item_id(0)]
        self.assertEqual(fool[0]['count'], 4)

    def test_roll_fraction_drop_respects_depth_gates(self):
        rng = random.Random(1)
        for depth in (1, 2, 3, 4):
            for _ in range(40):
                arc, quarters = currency.roll_fraction_drop(depth, rng)
                self.assertIn(arc, currency.CURRENCY_CARDS)
                self.assertGreaterEqual(depth, currency.CURRENCY_CARDS[arc]['depth_min'])
                # whole-card drops (BLUEPRINT §19.218) — per-arcana counts
                self.assertEqual(quarters, currency.quarters_needed(arc))

    def test_fool_identifies_target(self):
        target = itemgen.roll_for('lungs', 1, 5, seed=4)
        self.assertFalse(itemgen.is_identified(target))

        class FakeChar:
            level = 5
            available_points = 2
            inventory = make_inventory()

        class FakeGame:
            char = FakeChar()
            inventory = FakeChar().inventory

        game = FakeGame()
        game.inventory['grid'].append(target)
        t_idx = game.inventory['grid'].index(target)
        # card in grid slot after gear entry
        game.inventory['grid'].append(currency.make_card_slot(0, 4, col=1, row=0))
        c_idx = len(game.inventory['grid']) - 1
        card_entry = game.inventory['grid'][c_idx]
        game._card_apply_target = ('grid', game.inventory['grid'].index(target))
        result = currency.apply_card(game, 0, 'grid', c_idx)
        self.assertEqual(result, 'Identified.')
        self.assertTrue(itemgen.is_identified(target))
        # the 4 quarters were consumed; the emptied stack is removed
        self.assertNotIn(card_entry, game.inventory['grid'])

    def test_magician_upgrades_common_only(self):
        target = itemgen.roll_for('kidney', 1, 5, seed=6)
        target['col'] = 0; target['row'] = 2
        target['instance_data']['rarity'] = 'common'
        target['instance_data']['identified'] = True

        class FakeChar:
            level = 5
            available_points = 2

        class FakeGame:
            char = FakeChar()
            inventory = make_inventory()

        game = FakeGame()
        game.inventory['grid'].append(target)
        t_idx = 0
        game.inventory['grid'].append(currency.make_card_slot(1, 4, col=1, row=0))
        c_idx = 1
        game._card_apply_target = ('grid', game.inventory['grid'].index(target))
        currency.apply_card(game, 1, 'grid', len(game.inventory['grid']) - 1)
        self.assertEqual(target['instance_data']['rarity'], 'uncommon')

    def test_empress_is_retired(self):
        self.assertNotIn(3, currency.CURRENCY_CARDS)
        self.assertNotIn(3, currency.DEFAULT_ARCANA_ORDER)
        self.assertNotIn('tarot_card_03', ITEMS)


class TestWholeCardsExceptFool(unittest.TestCase):
    """Only the Fool is quarter-stacked; every other card is whole
    (owner ruling 2026-10-07, BLUEPRINT §19.193)."""

    def test_quarters_needed_per_arcana(self):
        self.assertEqual(currency.quarters_needed(0), 4)
        for arc in currency.CURRENCY_CARDS:
            if arc == 0:
                continue
            self.assertEqual(currency.quarters_needed(arc), 1)

    def test_whole_card_usable_at_one_and_consumes_one(self):
        inv = make_inventory()
        grid = inv['grid']
        grid[:] = []
        grid.append(currency.make_card_slot(1, 1))    # one Magician
        entry = grid[0]
        self.assertTrue(currency.card_complete(entry))
        self.assertTrue(currency.consume_card(inv, entry, 'grid', 0))
        self.assertNotIn(entry, grid)                 # stack removed after one use

    def test_fool_still_needs_four(self):
        entry = currency.make_card_slot(0, 3)
        self.assertFalse(currency.card_complete(entry))
        entry['count'] = 4
        self.assertTrue(currency.card_complete(entry))

    def test_stack_label_per_arcana(self):
        self.assertEqual(currency.stack_label(currency.make_card_slot(0, 3)), '3/4')
        self.assertEqual(currency.stack_label(currency.make_card_slot(11, 2)), '2')

    def test_emperor_makes_mythic(self):
        target = itemgen.roll_for('liver', 1, 10, seed=8)
        target['col'] = 0; target['row'] = 2
        target['instance_data']['identified'] = True

        class FakeChar:
            level = 5
            available_points = 0

        class FakeGame:
            char = FakeChar()
            inventory = make_inventory()

        game = FakeGame()
        game.inventory['grid'].append(target)
        game.inventory['grid'].append(currency.make_card_slot(4, 4, col=1, row=0))
        game._card_apply_target = ('grid', game.inventory['grid'].index(target))
        currency.apply_card(game, 4, 'grid', len(game.inventory['grid']) - 1)
        self.assertEqual(target['instance_data']['rarity'], 'mythic')

    def test_death_full_reroll_destroys_values(self):
        target = itemgen.roll_for('lungs', 1, 10, seed=12)
        target['instance_data']['identified'] = True
        old_inst = target['instance_data']

        class FakeChar:
            level = 5
            available_points = 0

        class FakeGame:
            char = FakeChar()
            inventory = make_inventory()

        game = FakeGame()
        game.inventory['grid'].append(target)
        game.inventory['grid'].append(currency.make_card_slot(13, 4, col=1, row=0))
        game._card_apply_target = ('grid', game.inventory['grid'].index(target))
        currency.apply_card(game, 13, 'grid', len(game.inventory['grid']) - 1)
        self.assertIsNot(target['instance_data'], old_inst)
        self.assertTrue(target['instance_data'].get('identified'))

    def test_star_rerolls_gem_ability(self):
        target = itemgen.roll_for('gem_blue', 1, 5, seed=14)
        old_ab = target['instance_data']['ability']

        class FakeChar:
            level = 5
            available_points = 0

        class FakeGame:
            char = FakeChar()
            inventory = make_inventory()

        game = FakeGame()
        game.inventory['grid'].append(target)
        # 20 whole cards — the loop below consumes one per iteration
        game.inventory['grid'].append(currency.make_card_slot(17, 20, col=1, row=0))
        game._card_apply_target = ('grid', game.inventory['grid'].index(target))
        # reroll stays inside the Q pool
        for _ in range(20):
            result = currency.apply_card(game, 17, 'grid', len(game.inventory['grid']) - 1)
            self.assertIsNotNone(result, 'reroll must keep firing every iteration')
            self.assertIn(target['instance_data']['ability'], gems.SLOT_GEM_POOLS['Q'])

    def test_devil_duplicates_cursed_reflection(self):
        target = itemgen.roll_for('heart', 1, 10, seed=16)
        target['col'] = 0; target['row'] = 2
        target['instance_data']['identified'] = True

        class FakeChar:
            level = 5
            available_points = 0

        class FakeGame:
            char = FakeChar()
            inventory = make_inventory()

        game = FakeGame()
        game.inventory['grid'].append(target)
        game.inventory['grid'].append(currency.make_card_slot(15, 4, col=1, row=0))
        game._card_apply_target = ('grid', game.inventory['grid'].index(target))
        result = currency.apply_card(game, 15, 'grid', len(game.inventory['grid']) - 1)
        self.assertIsNotNone(result)
        twin = game.inventory['grid'][-1]
        self.assertEqual(twin['item'], target['item'])
        self.assertTrue(twin['instance_data'].get('cursed'))
        self.assertIn('Cursed Reflection', twin['instance_data']['display_name'])

    def test_justice_balances_values(self):
        slot = itemgen.roll_for('lungs', 1, 20, seed=18)
        inst = slot['instance_data']
        balanced = itemgen.balanced_affix_values(inst)
        self.assertTrue(balanced)
        for aid, val in balanced.items():
            a = itemgen._AFFIX_BY_ID[aid]
            fair = a['base'] * (1 + inst['ilvl'] / 100.0) * itemgen.M_RARITY[inst['rarity']]
            self.assertAlmostEqual(val, itemgen._round_val(fair, a['round']))


if __name__ == '__main__':
    unittest.main()
