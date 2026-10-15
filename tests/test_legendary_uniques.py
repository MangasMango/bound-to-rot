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

"""Gameplay regression tests for legendary unique modifiers."""

from unittest import mock

import pytest

from entities.player_stats import create_stats, reset_stats
from systems import combat
from systems.itemgen import aggregate_item_bonuses, equipped_uniques


def _unique_inventory(*unique_ids):
    equipped = {}
    for index, unique_id in enumerate(unique_ids):
        equipped[str(index)] = {
            'item': 'lungs',
            'instance_data': {
                'identified': True,
                'unique': {'id': unique_id, 'title': unique_id},
                'affixes': {'prefixes': {}, 'suffixes': {}},
            },
        }
    return {'equipped': equipped}


def test_glass_cannon_increases_damage_and_halves_life():
    stats = create_stats(max_health=100)
    stats['health'] = 80
    bonuses = aggregate_item_bonuses(_unique_inventory('glass_cannon'))
    assert all(value == 60 for key, value in bonuses.items() if key.endswith('damage_pct'))
    reset_stats(stats, max_health=100, **bonuses)
    assert stats['max_health'] == 50
    assert stats['health'] == 50


@mock.patch('systems.combat.random.random', side_effect=[0.0, 0.99, 0.99, 0.0, 0.99, 0.99, 0.99])
def test_bang_bang_makes_two_half_damage_strikes(mock_random):
    defender = {'evasion': 0, 'health': 1000}
    normal = combat.resolve_attack(1000, defender, 101)
    doubled = combat.resolve_attack(1000, defender, 101, double_strike=True)
    assert normal['damage'] == 101
    assert doubled['strikes'] == [51, 50]
    assert sum(doubled['strikes']) == normal['damage']


def test_vampiric_heals_for_ten_percent_of_melee_damage():
    from core.game import Game
    game = object.__new__(Game)
    game.stats = create_stats(max_health=100)
    game.stats['health'] = 50
    game.inventory = _unique_inventory('vampiric')
    game._vampiric_heal(40)
    assert game.stats['health'] == 54


def test_juggernaut_reduces_movement_speed():
    bonuses = aggregate_item_bonuses(_unique_inventory('juggernaut'))
    assert bonuses['move_speed_pct'] == -15


def test_second_wind_survives_lethal_hit_and_respects_cooldown():
    stats = create_stats(max_health=100)
    stats['health'] = 20
    assert combat.apply_health_damage(stats, 30, second_wind=True) is True
    assert stats['health'] == 50
    assert combat.apply_health_damage(stats, 30, second_wind=True,
                                      cooldown_remaining=59.0) is False
    assert stats['health'] == 20


def test_two_equipped_uniques_both_apply():
    inventory = _unique_inventory('glass_cannon', 'juggernaut')
    bonuses = aggregate_item_bonuses(inventory)
    assert equipped_uniques(inventory) == {'glass_cannon', 'juggernaut'}
    assert bonuses['move_speed_pct'] == -15
    assert bonuses['max_health_pct'] == -50
    assert bonuses['physical_damage_pct'] == 60
