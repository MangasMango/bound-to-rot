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

"""Creation baseline and UI flow tests (issue #103, updated for #31)."""

import unittest
from unittest import mock

from entities.descend import DESCEND_ATTRIBUTES, vessel_baseline_stats
from entities.progression import Character, CharacterManager
from systems.xp import MAX_LEVEL
from ui.menus import MenuSystem


class CharacterCreationBaselineTests(unittest.TestCase):
    def _manager(self):
        manager = CharacterManager.__new__(CharacterManager)
        manager.characters = []
        manager.active_idx = 0
        manager.unlocked_vessels = ['knight', 'warrior', 'fighter']
        manager.save = mock.Mock()
        return manager

    def test_every_vessel_creates_zeroed_at_level_1(self):
        # Owner ruling (issue #31): vessels grant NO attribute baselines -
        # every attribute starts at 0 and points come from level-ups only.
        for looks in ('knight', 'warrior', 'fighter'):
            with self.subTest(looks=looks):
                manager = self._manager()
                char = manager.create('Vessel Pilot', looks)
                self.assertEqual(char.descend, vessel_baseline_stats(looks))
                self.assertEqual({k: v for k, v in char.descend.items() if v}, {})
                self.assertEqual(set(char.descend), set(DESCEND_ATTRIBUTES))
                self.assertEqual(char.available_points, 0)
                self.assertEqual(char.level, 1)
                self.assertEqual(char.xp, 0)

    def test_start_creates_directly_without_allocation_state(self):
        manager = self._manager()
        text_input = mock.Mock()
        menu = MenuSystem.__new__(MenuSystem)
        menu.char_mgr = manager
        menu._char_name = '  Vessel Pilot  '
        menu._char_looks = 'knight'
        menu.char_name_input = text_input

        MenuSystem._do_create(menu)

        self.assertEqual(manager.characters[0].name, 'Vessel Pilot')
        self.assertEqual(menu.state, 'characters')
        self.assertFalse(hasattr(menu, '_creation_mode'))
        text_input.clear.assert_called_once_with()

    def test_old_save_is_rejected_without_crashing(self):
        with self.assertRaises(ValueError):
            Character.from_dict({'id': 'legacy', 'name': 'Legacy', 'xp': 99})

    def test_new_character_save_carries_level_and_xp(self):
        data = Character('fresh', 'Fresh', 'knight').to_dict()
        self.assertEqual(data['level'], 1)
        self.assertEqual(data['xp'], 0)

    def test_from_dict_clamps_nonsense_level_xp(self):
        c = Character.from_dict({'id': 'x', 'name': 'X', 'looks': 'knight',
                                 'descend': {}, 'perks': {},
                                 'available_points': 0,
                                 'inventory': None, 'stash': [],
                                 'level': 9999, 'xp': -5})
        self.assertEqual(c.level, MAX_LEVEL)
        self.assertEqual(c.xp, 0)


if __name__ == '__main__':
    unittest.main()
