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

import unittest
from unittest.mock import patch

import ui.inventory_ui as invmod
from ui.inventory_ui import InventoryUI
from systems import currency


class TestIdentifyMenuRobustness(unittest.TestCase):
    def _menu(self, fool):
        target = {'item': 'sword', 'instance_data': {'identified': False}}
        ui = InventoryUI()
        ui._ctx = {'slot': target, 'source': 'grid', 'index': 0, 'x': 10, 'y': 10}
        grid = ['legacy-raw-item-id']
        if fool:
            grid.append(currency.make_card_slot(0, 4))
        ui._inventory_for_menu = grid
        return ui

    def test_raw_string_entry_does_not_crash_or_hide_fool(self):
        options = self._menu(True)._ctx_options()
        identify = next(x for x in options if x['type'] == 'identify')
        self.assertTrue(identify['enabled'])

    def test_raw_string_entry_without_fool_is_disabled(self):
        identify = next(x for x in self._menu(False)._ctx_options()
                        if x['type'] == 'identify')
        self.assertFalse(identify['enabled'])

    def test_draw_context_survives_raw_string_entry(self):
        ui = self._menu(True)
        with patch.object(invmod.rl, 'draw_rectangle'), \
             patch.object(invmod.rl, 'draw_rectangle_lines'), \
             patch.object(invmod.rl, 'get_screen_width', return_value=800), \
             patch.object(invmod.rl, 'get_screen_height', return_value=600), \
             patch.object(invmod.fonts, 'draw'):
            ui._draw_ctx(10, 10)
