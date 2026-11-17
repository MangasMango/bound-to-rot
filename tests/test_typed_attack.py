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

"""Typed attack rules (owner rulings, #95 session):

  1. ROT is the anti-armour type: it ignores damage_reduction AND
     resistances entirely (magic no longer bypasses armour - it is a
     normal element at half DR, resistable).
  2. Every attack ADDS UP all typed sources: each component is mitigated
     by its own type's rules and the hit shows a damage number PER TYPE,
     in that type's colour.
  3. Full immunity to a breakdown shows the immune marker.
"""

import unittest
from types import SimpleNamespace
from unittest import mock

import pyray as rl

from core.game import Game


def _game():
    game = SimpleNamespace()
    game.stats = {}
    game._dmg_numbers = []
    game.audio = mock.Mock()
    # bind the real methods
    for name in ('_apply_typed_attack', '_apply_damage_to_enemy',
                 '_typed_attack_breakdown', '_spawn_dmg_number'):
        setattr(game, name, getattr(Game, name).__get__(game))
    game._DMG_NUMBER_COLORS = Game._DMG_NUMBER_COLORS
    return game


def _armoured_enemy(dr=0.6, rot_resist=0.5, **extra):
    enemy = {'x': 10.0, 'y': 10.0, 'health': 10000, 'max_health': 10000,
             'damage_reduction': dr, 'enemy_type': 'skeleton',
             'resist_pct': {'rot': rot_resist, 'physical': 0.3,
                            'fire': 0.3, 'cold': 0.3, 'lightning': 0.3,
                            'magic': 0.3},
             'hit_count': 0}
    enemy.update(extra)
    return enemy


class RotAntiArmourTests(unittest.TestCase):

    def test_rot_ignores_armour_and_resist(self):
        game = _game()
        enemy = _armoured_enemy(dr=0.6, rot_resist=0.5)
        dealt = game._apply_damage_to_enemy(enemy, 100.0, 'rot', pen=0.0)
        self.assertEqual(dealt, 100)   # nothing mitigated - the full 100

    def test_magic_is_a_normal_element_now(self):
        game = _game()
        enemy = _armoured_enemy(dr=0.6)   # 30% magic resist
        dealt = game._apply_damage_to_enemy(enemy, 100.0, 'magic', pen=0.0)
        # half DR (0.3) then 30% resist: 100 * 0.7 * 0.7 = 49
        self.assertEqual(dealt, 49)

    def test_physical_keeps_full_armour(self):
        game = _game()
        enemy = _armoured_enemy(dr=0.6)   # 30% physical resist
        dealt = game._apply_damage_to_enemy(enemy, 100.0, 'physical', pen=0.0)
        # full DR then resist: 100 * 0.4 * 0.7 = 28
        self.assertEqual(dealt, 28)

    def test_penetration_still_works_per_type(self):
        game = _game()
        enemy = _armoured_enemy(dr=0.0)   # resist only
        dealt = game._apply_damage_to_enemy(enemy, 100.0, 'magic', pen=0.3)
        self.assertEqual(dealt, 100)      # 30% resist - 30% pen


class TypedBreakdownTests(unittest.TestCase):

    def test_breakdown_carries_base_plus_all_flats(self):
        game = _game()
        game.stats = {'damage_flat': {'physical': 1.5, 'magic': 2.0,
                                      'rot': 3.0, 'cold': 0.0,
                                      'lightning': 4.0, 'fire': 0.0}}
        breakdown = game._typed_attack_breakdown('magic', 20.0)
        self.assertEqual(breakdown['magic'], {'base': 20.0, 'flat': 2.0})
        self.assertEqual(breakdown['physical'], {'base': 0.0, 'flat': 1.5})
        self.assertEqual(breakdown['rot'], {'base': 0.0, 'flat': 3.0})
        self.assertEqual(breakdown['lightning'], {'base': 0.0, 'flat': 4.0})
        self.assertNotIn('fire', breakdown)          # zero flats stay out
        self.assertNotIn('cold', breakdown)

    def test_multi_type_hit_adds_up_and_colors_numbers(self):
        game = _game()
        enemy = _armoured_enemy(dr=0.0)   # no resist, no DR: clean math
        enemy['resist_pct'] = {}
        breakdown = {'physical': {'base': 40.0, 'flat': 0.0},
                     'magic': {'base': 0.0, 'flat': 30.0},
                     'rot': {'base': 0.0, 'flat': 30.0}}
        dealt = game._apply_typed_attack(enemy, breakdown)
        self.assertEqual(dealt, 100)
        # one coloured number per component, in the component's colour
        colors = {n['color'] for n in game._dmg_numbers}
        self.assertEqual(colors, {Game._DMG_NUMBER_COLORS['physical'],
                                  Game._DMG_NUMBER_COLORS['magic'],
                                  Game._DMG_NUMBER_COLORS['rot']})
        values = sorted(n['value'] for n in game._dmg_numbers)
        self.assertEqual(values, [30, 30, 40])

    def test_health_drops_by_the_added_total(self):
        game = _game()
        enemy = _armoured_enemy(dr=0.0)
        enemy['resist_pct'] = {}        # clean math: no resists
        enemy['health'] = 100.0
        game._apply_typed_attack(enemy, {'physical': {'base': 60.0, 'flat': 0.0},
                                         'rot': {'base': 0.0, 'flat': 25.0}})
        self.assertEqual(enemy['health'], 15.0)

    def test_full_immunity_shows_the_marker(self):
        """An enemy immune to its own element shows the immune marker when
        the whole breakdown is that element."""
        game = _game()
        enemy = _armoured_enemy(dr=0.0, dmg_type='fire')
        game._apply_typed_attack(enemy, {'fire': {'base': 50.0, 'flat': 0.0}})
        self.assertTrue(any(n['value'] == -1 for n in game._dmg_numbers))

    def test_single_type_routing_still_works(self):
        """_apply_damage_to_enemy (DoTs, chain echoes) routes through the
        typed rules - single fire tick keeps the element's half-DR rule."""
        game = _game()
        enemy = _armoured_enemy(dr=0.6)   # 30% fire resist
        dealt = game._apply_damage_to_enemy(enemy, 100.0, 'fire', pen=0.0)
        self.assertEqual(dealt, 49)       # half DR then resist, same as magic


if __name__ == '__main__':
    unittest.main()
