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

"""Keyboard navigation in the item grids (issue #13).

Covers:
  1. Arrow movement of the grid cursor, clamped per focused grid dims.
  2. Tab cycles the focused grid (backpack -> bank -> forge).
  3. Enter opens the SAME context menu dict a right-click produces;
     Enter on an empty cell is a no-op.
  4. Context-menu keyboard mode: Up/Down clamp, Enter executes the
     selected option, a disabled option keeps the menu open and explains.
  5. Apply-targeting accepts Enter on the cursor slot.
  6. Held arrows repeat respect the cooldown.
  7. Focus sync: closing a panel drops the cursor back on the backpack.
"""

import unittest
from unittest import mock

import pyray as rl

from ui.inventory_ui import InventoryUI
import systems.items as items


def _inv(entries):
    return {
        'equipped': {'lungs': None, 'heart': None, 'liver': None,
                     'intestine': None, 'kidney': None},
        'grid': list(entries),
        'gem_sockets': {'Q': None, 'W': None, 'E': None},
        'flask_slot': None,
        'grid_v': items.INV_GRID_VERSION,
    }


def _slot(item_id, col, row, count=1):
    return {'item': item_id, 'count': count, 'col': col, 'row': row}


class NavHarness(unittest.TestCase):
    """Drives _update_kb_nav with patched key state."""

    def setUp(self):
        self.ui = InventoryUI()
        self.ui.open = True
        self.down = set()          # raylib key codes currently held
        self.pressed = set()       # edges this tick

        def fake_key_down(key):
            return key in self.down

        def fake_key_pressed(consumer, key):
            if key in self.pressed:
                self.pressed.discard(key)
                return True
            return False

        def fake_frame_time():
            return 1 / 60

        self._patches = [
            mock.patch.object(rl, 'is_key_down', fake_key_down),
            mock.patch.object(rl, 'get_frame_time', fake_frame_time),
            mock.patch.object(self.ui.inp_module if hasattr(self.ui, 'inp_module')
                              else __import__('systems.input', fromlist=['x']),
                              'key_pressed', fake_key_pressed),
        ]
        for p in self._patches:
            p.start()
        self.addCleanup(lambda: [p.stop() for p in self._patches])

    def tap(self, key):
        self.pressed.add(key)

    def hold(self, *keys):
        self.down.update(keys)

    def release(self, *keys):
        self.down.difference_update(keys)


class MovementTests(NavHarness):

    def test_arrow_moves_the_cursor(self):
        self.ui._kb_cursor = {'source': 'grid', 'col': 0, 'row': 0}
        self.hold(rl.KEY_RIGHT)
        self.ui._update_kb_nav(_inv([]), {})
        self.assertEqual((self.ui._kb_cursor['col'], self.ui._kb_cursor['row']),
                         (1, 0))

    def test_movement_clamps_at_the_grid_edge(self):
        self.ui._kb_cursor = {'source': 'grid',
                              'col': items.INV_COLS - 1, 'row': 0}
        self.hold(rl.KEY_RIGHT)
        self.ui._update_kb_nav(_inv([]), {})
        self.assertEqual(self.ui._kb_cursor['col'], items.INV_COLS - 1)

    def test_stash_focus_uses_bank_dimensions(self):
        self.ui.stash_open = True
        self.ui._stash_grid = []
        self.ui._kb_cursor = {'source': 'stash', 'col': 0, 'row': 0}
        self.hold(rl.KEY_DOWN)
        for _ in range(10):    # far past the bank's 8 rows - must clamp
            self.ui._kb_move_cd = 0.0
            self.ui._update_kb_nav(_inv([]), {})
        self.assertEqual(self.ui._kb_cursor['row'], 7)

    def test_held_arrow_respects_the_repeat_cooldown(self):
        self.ui._kb_cursor = {'source': 'grid', 'col': 0, 'row': 0}
        self.hold(rl.KEY_RIGHT)
        self.ui._update_kb_nav(_inv([]), {})
        self.assertEqual(self.ui._kb_cursor['col'], 1)
        # still within the cooldown window (frame_time is 1/60 < 0.12)
        self.ui._update_kb_nav(_inv([]), {})
        self.assertEqual(self.ui._kb_cursor['col'], 1)

    def test_tab_cycles_focus_and_closes_sync_back(self):
        self.ui.stash_open = True
        self.ui._stash_grid = []
        self.ui.forge_open = True
        self.ui._forge_grid = []
        self.ui._kb_cursor = {'source': 'grid', 'col': 0, 'row': 0}
        self.tap(rl.KEY_TAB)
        self.ui._update_kb_nav(_inv([]), {})
        self.assertEqual(self.ui._kb_cursor['source'], 'stash')
        self.tap(rl.KEY_TAB)
        self.ui._update_kb_nav(_inv([]), {})
        self.assertEqual(self.ui._kb_cursor['source'], 'forge')
        # closing the stash must drop the cursor onto an open panel
        self.ui.stash_open = False
        self.ui._stash_grid = None
        self.ui._sync_kb_focus()
        self.assertEqual(self.ui._kb_cursor['source'], 'forge')


class EnterOpensMenuTests(NavHarness):

    def test_enter_on_item_opens_the_rmb_menu_dict(self):
        entries = [_slot('heart', 2, 1)]
        inv = _inv(entries)
        self.ui._kb_cursor = {'source': 'grid', 'col': 2, 'row': 1}
        self.tap(rl.KEY_ENTER)
        self.ui._update_kb_nav(inv, {})

        self.assertIsNotNone(self.ui._ctx)
        self.assertEqual(self.ui._ctx['source'], 'grid')
        self.assertEqual(self.ui._ctx['index'], 0)
        self.assertEqual(self.ui._ctx['slot'], entries[0])

    def test_enter_opens_the_same_dict_shape_as_a_right_click(self):
        """The keyboard menu must be the same dict _rmb_hit produces -
        {x, y, source, index, slot} - so _exec/_draw behave identically."""
        entries = [_slot('heart', 2, 1)]
        inv = _inv(entries)
        self.ui._kb_cursor = {'source': 'grid', 'col': 2, 'row': 1}
        self.tap(rl.KEY_ENTER)
        self.ui._update_kb_nav(inv, {})
        self.assertEqual(set(self.ui._ctx),
                         {'x', 'y', 'source', 'index', 'slot'})
        self.assertEqual(self.ui._ctx['source'], 'grid')
        self.assertEqual(self.ui._ctx['index'], 0)

    def test_enter_on_empty_cell_is_a_noop(self):
        self.ui._kb_cursor = {'source': 'grid', 'col': 5, 'row': 3}
        self.tap(rl.KEY_ENTER)
        self.ui._update_kb_nav(_inv([]), {})
        self.assertIsNone(self.ui._ctx)

    def test_enter_on_stash_item_targets_the_bank(self):
        self.ui.stash_open = True
        self.ui._stash_grid = [_slot('heart', 0, 0)]
        self.ui._kb_cursor = {'source': 'stash', 'col': 0, 'row': 0}
        self.tap(rl.KEY_ENTER)
        self.ui._update_kb_nav(_inv([]), {})
        self.assertEqual(self.ui._ctx['source'], 'stash')


class ContextKeyboardModeTests(NavHarness):

    def _open_ctx(self, entries=None):
        entries = entries or [_slot('heart', 0, 0)]
        self.ui._inventory_for_menu = entries
        self.ui._inventory_for_ctx = _inv(entries)
        self.ui._ctx = {'x': 100, 'y': 100, 'source': 'grid',
                        'index': 0, 'slot': entries[0]}
        self.ui._ctx_sel = 0
        return self.ui._ctx_options()

    def test_arrow_down_moves_the_highlight(self):
        opts = self._open_ctx()
        self.assertGreater(len(opts), 1)
        self.tap(rl.KEY_DOWN)
        self.ui._update_kb_nav(_inv([]), {})
        self.assertEqual(self.ui._ctx_sel, 1)

    def test_highlight_clamps_at_both_ends(self):
        self._open_ctx()
        for _ in range(20):
            self.tap(rl.KEY_DOWN)
            self.ui._update_kb_nav(_inv([]), {})
        opts = self.ui._ctx_options()
        self.assertEqual(self.ui._ctx_sel, len(opts) - 1)
        self.tap(rl.KEY_UP)
        self.ui._update_kb_nav(_inv([]), {})
        self.assertEqual(self.ui._ctx_sel, len(opts) - 2)

    def test_enter_executes_the_selected_option(self):
        self._open_ctx()
        self.ui._exec = mock.Mock()
        self.tap(rl.KEY_ENTER)
        self.ui._update_kb_nav(_inv([]), {})
        self.ui._exec.assert_called_once()
        self.assertIsNone(self.ui._ctx)   # executed menus close

    def test_disabled_option_keeps_the_menu_and_explains(self):
        # an unidentified item produces a disabled IMPLANT option
        slot = _slot('heart', 0, 0)
        slot['instance_data'] = {'rarity': 'common', 'ilvl': 5,
                                 'identified': False}
        self._open_ctx([slot])
        opts = self.ui._ctx_options()
        disabled = [o for o in opts if not o.get('enabled', True)]
        self.assertTrue(disabled, 'expected a disabled option on the fixture')
        self.ui._ctx_sel = opts.index(disabled[0])
        self.ui._exec = mock.Mock()
        self.tap(rl.KEY_ENTER)
        self.ui._update_kb_nav(_inv([]), {})
        self.ui._exec.assert_not_called()
        self.assertIsNotNone(self.ui._ctx)   # menu stays open
        self.assertEqual(self.ui._notice, disabled[0]['why'])


class ApplyTargetingTests(NavHarness):

    def test_enter_applies_the_card_to_the_cursor_slot(self):
        card = {'item': 'poker_joker', 'count': 4, 'col': 0, 'row': 0}
        self.ui.on_apply_card = mock.Mock()
        self.ui._apply_pending = {'entry': card, 'src': 'grid', 'idx': 0}
        self.ui._kb_cursor = {'source': 'grid', 'col': 2, 'row': 1}
        self.tap(rl.KEY_ENTER)
        self.ui.update(_inv([card, _slot('heart', 2, 1)]), {})

        self.ui.on_apply_card.assert_called_once()
        args = self.ui.on_apply_card.call_args[0]
        self.assertEqual(args[3], 'grid')     # target source
        self.assertEqual(args[4], 1)          # target index
        self.assertIsNone(self.ui._apply_pending)


if __name__ == '__main__':
    unittest.main()
