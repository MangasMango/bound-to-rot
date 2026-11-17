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

"""Full-inventory loot loss (issue #86).

A pickup that does not fit must NEVER consume the ground pile. Covers:
  1. The click-to-pickup loop: full/partial/happy paths.
  2. `_auto_place` returning a truthful bool (equip vs grid vs none).
  3. `grid_auto_place` atomicity: a failed call never half-merges a stack.
"""

import unittest
from unittest.mock import MagicMock

import core.game as game_mod
from core.game import Game
import systems.items as items
from systems.itemgen import generate_instance


# ── helpers ────────────────────────────────────────────────────────────

def _bare_game():
    """A Game stub running the real inventory methods, audio muted."""
    game = Game()
    game.audio = MagicMock()
    game.audio.item_pickup = MagicMock()
    game.audio.item_equip = MagicMock()
    game.inventory['grid'] = []     # clear the starter cards
    return game


def _ground_pile(*slots):
    return {'x': 10.0, 'y': 10.0, 'items': list(slots), 'type': 'drop'}


def _fill_grid(game, item_id='stone_s3', rows=4):
    for col in range(items.INV_COLS):
        for row in range(rows):
            game.inventory['grid'].append({
                'item': item_id, 'count': 1, 'col': col, 'row': row})


# ── pickup loop ────────────────────────────────────────────────────────

class PickupLoopTests(unittest.TestCase):
    """The drop_target arrival block in Game._update_game."""

    def _pickup(self, game, pile):
        """Drive the same slot pass the arrival block runs."""
        picked_any = False
        remaining_slots = []
        for item in pile['items']:
            if game._auto_place(item):
                picked_any = True
            else:
                remaining_slots.append(item)
        if picked_any:
            game.tracker.loot += 1
        if not remaining_slots:
            game.ground_items.remove(pile)
        else:
            pile['items'] = remaining_slots
        return picked_any

    def test_full_inventory_consumes_nothing(self):
        game = _bare_game()
        _fill_grid(game)
        game.inventory['equipped'] = {key: {'item': 'heart', 'count': 1}
                                      for key in items.EQUIP_SLOT_LABELS}
        game.tracker.loot = 0
        pile = _ground_pile({'item': 'heart', 'count': 1, 'col': 0, 'row': 0},
                            {'item': 'stone_s3', 'count': 1, 'col': 1, 'row': 1})
        game.ground_items = [pile]

        self._pickup(game, pile)

        # the pile survives with BOTH slots - nothing was deleted
        self.assertIn(pile, game.ground_items)
        self.assertEqual(len(pile['items']), 2)
        self.assertEqual(game.tracker.loot, 0)
        self.assertGreater(game._inv_full_timer, 0.0)
        # and nothing landed in the grid
        self.assertEqual(len(game.inventory['grid']), items.INV_COLS * 4)

    def test_full_inventory_leaves_no_duplicate_on_partial_stack(self):
        game = _bare_game()
        game.inventory['grid'].append({'item': 'health_potion',
                                       'count': 9, 'col': 0, 'row': 0})
        _fill_grid(game)
        game.inventory['grid'].pop(0)   # the potion stack took cell (0,0)
        game.inventory['grid'].insert(0, {'item': 'health_potion',
                                          'count': 9, 'col': 0, 'row': 0})
        pile = _ground_pile({'item': 'health_potion', 'count': 5,
                             'col': 0, 'row': 0})
        game.ground_items = [pile]

        self._pickup(game, pile)

        stack_count = game.inventory['grid'][0]['count']
        ground_count = pile['items'][0]['count']
        # conservation: nothing appears twice
        self.assertLessEqual(stack_count,
                             items.ITEMS['health_potion']['maxStack'])
        self.assertEqual(stack_count + ground_count, 14)
        self.assertIn(pile, game.ground_items)

    def test_partial_pickup_keeps_the_rest_on_the_ground(self):
        game = _bare_game()
        # fill everything except ONE cell (top-left stays free)
        _fill_grid(game)
        game.inventory['grid'].pop(0)   # cell (0, 0) is now the last free spot
        pile = _ground_pile({'item': 'stone_s3', 'count': 1, 'col': 0, 'row': 0},
                            {'item': 'stone_s3', 'count': 1, 'col': 1, 'row': 1})
        game.ground_items = [pile]
        game.tracker.loot = 0

        picked = self._pickup(game, pile)

        self.assertTrue(picked)
        self.assertEqual(game.tracker.loot, 1)
        self.assertIn(pile, game.ground_items)
        self.assertEqual(len(pile['items']), 1)

    def test_happy_path_still_consumes_the_pile(self):
        game = _bare_game()
        pile = _ground_pile({'item': 'stone_s3', 'count': 1, 'col': 0, 'row': 0},
                            {'item': 'stone_s3', 'count': 1, 'col': 1, 'row': 1})
        game.ground_items = [pile]

        picked = self._pickup(game, pile)

        self.assertTrue(picked)
        self.assertNotIn(pile, game.ground_items)
        self.assertEqual(game.tracker.loot, 1)
        self.assertEqual(len(game.inventory['grid']), 2)

    def test_free_organ_slot_wins_over_full_grid(self):
        game = _bare_game()
        _fill_grid(game)
        game.inventory['equipped']['heart'] = None
        heart_instance = generate_instance('heart', 10)
        heart_instance['identified'] = True
        pile = _ground_pile({'item': 'heart', 'count': 1,
                             'col': 0, 'row': 0,
                             'instance_data': heart_instance})
        game.ground_items = [pile]

        picked = self._pickup(game, pile)

        self.assertTrue(picked)
        self.assertIsNotNone(game.inventory['equipped']['heart'])
        self.assertNotIn(pile, game.ground_items)


# ── _auto_place contract ───────────────────────────────────────────────

class AutoPlaceContractTests(unittest.TestCase):

    def test_returns_true_on_grid_success(self):
        game = _bare_game()
        self.assertTrue(game._auto_place({'item': 'stone_s3', 'count': 1,
                                          'col': 0, 'row': 0}))

    def test_returns_false_on_full_grid(self):
        game = _bare_game()
        _fill_grid(game)
        self.assertFalse(game._auto_place({'item': 'stone_s3', 'count': 1,
                                           'col': 0, 'row': 0}))

    def test_returns_false_sets_the_full_banner(self):
        game = _bare_game()
        _fill_grid(game)
        game._auto_place({'item': 'stone_s3', 'count': 1, 'col': 0, 'row': 0})
        self.assertGreater(game._inv_full_timer, 0.0)


# ── grid_auto_place atomicity ──────────────────────────────────────────

class GridAutoPlaceAtomicityTests(unittest.TestCase):

    def test_failed_stack_merge_leaves_the_grid_untouched(self):
        grid = [{'item': 'health_potion', 'count': 9, 'col': 0, 'row': 0}]
        # one full stack occupies (0,0); nothing else fits in the 1x1 probe
        result = items.grid_auto_place(grid, 'health_potion', 5,
                                       cols=1, rows=1)
        self.assertFalse(result)
        self.assertEqual(grid[0]['count'], 9)   # no partial merge leaked
        self.assertEqual(len(grid), 1)

    def test_successful_merge_still_works(self):
        grid = [{'item': 'health_potion', 'count': 4, 'col': 0, 'row': 0}]
        self.assertTrue(items.grid_auto_place(grid, 'health_potion', 3,
                                              cols=2, rows=1))
        self.assertEqual(grid[0]['count'], 7)
        self.assertEqual(len(grid), 1)

    def test_success_places_new_stacks_as_before(self):
        grid = []
        self.assertTrue(items.grid_auto_place(grid, 'health_potion', 12,
                                              cols=2, rows=2))
        counts = [entry['count'] for entry in grid]
        self.assertEqual(counts, [10, 2])
        positions = [(entry['col'], entry['row']) for entry in grid]
        self.assertEqual(positions, [(0, 0), (1, 0)])

    def test_no_free_cell_for_instance_returns_false_untouched(self):
        grid = [{'item': 'stone_s3', 'count': 1, 'col': 0, 'row': 0}]
        slot = {'item': 'lungs', 'count': 1,
                'instance_data': generate_instance('lungs', 5)}
        self.assertFalse(items.grid_auto_place_instance(
            _full_grid(), slot, cols=1, rows=1))


def _full_grid():
    return [{'item': 'stone_s3', 'count': 1, 'col': 0, 'row': 0}]


if __name__ == '__main__':
    unittest.main()
