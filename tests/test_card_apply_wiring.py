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

"""Card APPLY wiring (issue #95).

The bug: InventoryUI.on_apply_card was never wired to Game._apply_currency_card,
so EVERY currency card application silently did nothing - the pending apply
was discarded and the card was never consumed ("the card that unrots doesn't
work at all").

Covers:
  1. The wiring exists on a real Game.
  2. The InventoryUI apply-targeting path reaches the game callback and the
     card is consumed (the exact flow the mouse click drives).
  3. The Queen of Hearts cleanse works end to end through that flow.
"""

import unittest
from unittest import mock

import entities.progression as prog
import systems.currency as currency
import systems.itemgen as itemgen
import systems.items as items
from core.game import Game


class CardApplyWiringTests(unittest.TestCase):

    def test_callback_is_wired_on_a_real_game(self):
        game = Game()
        self.assertEqual(game.inv.on_apply_card, game._apply_currency_card)

    def test_ui_apply_flow_reaches_the_game_and_consumes_the_card(self):
        """Drive the UI exactly like the mouse does: _exec 'apply' sets the
        pending card, the targeting click calls the wired callback."""
        game = Game()
        game.inventory['grid'] = []
        organ = {'item': 'heart', 'count': 1, 'col': 0, 'row': 0,
                 'instance_data': itemgen.generate_instance('heart', 10)}
        organ['instance_data']['identified'] = True
        itemgen.add_rot(organ)
        itemgen.add_rot(organ)
        game.inventory['grid'].append(organ)

        card = currency.make_card_slot(14, quarters=1)   # Queen of Hearts
        game.inventory['grid'].append(card)

        # _exec 'apply' (the right-click menu action) arms the pending card
        ui = game.inv
        ui.open = True
        ui._exec({'type': 'apply', 'source': 'grid', 'index': 1},
                 game.inventory, game.stats)
        self.assertIsNotNone(ui._apply_pending)

        # the targeting click on the organ slot (inventory_ui passes the
        # card identity + the clicked target to the wired callback)
        ui.on_apply_card(card, 'grid', 1, 'grid', 0)

        self.assertEqual(itemgen.rot_of(organ['instance_data']), 0.0)
        self.assertFalse(itemgen.is_rotten(organ['instance_data']))
        # the card was consumed
        self.assertEqual(len(game.inventory['grid']), 1)

    def test_ace_of_hearts_upgrades_and_rerolls(self):
        """Owner ruling (issue #95 follow-up): the Ace of Hearts upgrades a
        common item to uncommon AND rerolls its stats - the fresh instance
        replaces the old one, rolls at the new rarity and is identified
        (rolled in front of the player)."""
        game = Game()
        game.inventory['grid'] = []
        organ = {'item': 'heart', 'count': 1, 'col': 0, 'row': 0,
                 'instance_data': itemgen.generate_instance('heart', 10)}
        organ['instance_data']['identified'] = True
        organ['instance_data']['rarity'] = 'common'
        old_inst = organ['instance_data']
        game.inventory['grid'].append(organ)
        game.inventory['grid'].append(
            currency.make_card_slot(1, quarters=1))

        game._apply_currency_card(game.inventory['grid'][1], 'grid', 1,
                               'grid', 0)

        inst = organ['instance_data']
        self.assertIsNot(inst, old_inst)          # the roll was rebuilt
        self.assertEqual(inst['rarity'], 'uncommon')
        self.assertTrue(inst['identified'])       # visibly rolled
        self.assertEqual(inst['ilvl'], 10)        # item level carries over

    def test_ace_of_hearts_refuses_non_common(self):
        game = Game()
        game.inventory['grid'] = []
        organ = {'item': 'heart', 'count': 1, 'col': 0, 'row': 0,
                 'instance_data': itemgen.generate_instance('heart', 10)}
        organ['instance_data']['identified'] = True
        organ['instance_data']['rarity'] = 'rare'
        old_inst = organ['instance_data']
        game.inventory['grid'].append(organ)
        game.inventory['grid'].append(
            currency.make_card_slot(1, quarters=1))

        game._apply_currency_card(game.inventory['grid'][1], 'grid', 1,
                               'grid', 0)

        self.assertIs(organ['instance_data'], old_inst)   # untouched
        self.assertEqual(len(game.inventory['grid']), 2)  # card not consumed

    def test_queen_of_hearts_cleanse_end_to_end(self):
        """Full revert: rot to 0, ROTTEN state and drawback suffix removed,
        original name restored."""
        game = Game()
        game.inventory['grid'] = []
        organ = {'item': 'heart', 'count': 1, 'col': 0, 'row': 0,
                 'instance_data': itemgen.generate_instance('heart', 10)}
        organ['instance_data']['identified'] = True
        for _ in range(6):
            itemgen.add_rot(organ)
        self.assertTrue(itemgen.is_rotten(organ['instance_data']))
        rotten_name = organ['instance_data']['display_name']
        game.inventory['grid'].append(organ)
        game.inventory['grid'].append(
            currency.make_card_slot(14, quarters=1))

        game._apply_currency_card(game.inventory['grid'][1], 'grid', 1,
                               'grid', 0)

        inst = organ['instance_data']
        self.assertEqual(itemgen.rot_of(inst), 0.0)
        self.assertFalse(itemgen.is_rotten(inst))
        self.assertNotIn('rot_prev', inst)
        self.assertNotEqual(inst['display_name'], rotten_name)
        self.assertFalse(inst['display_name'].startswith('ROTTEN'))


if __name__ == '__main__':
    unittest.main()
