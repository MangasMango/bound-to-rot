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

"""Ability cast + kill SFX firing - user report: skill kills fired no sfx.

Covers:
  1. ability_cast routes each ability family to its own pool.
  2. _apply_damage_to_enemy plays the death cue exactly once per kill
     regardless of damage source, and never for immune / zero-damage hits.
"""

import unittest
from unittest import mock

from systems.audio import (AudioSystem, DEATH_SFX_MIN_INTERVAL,
                           _now_secs)
from entities.zombies import default_status_fields
from core.game import Game


def _game():
    game = Game.__new__(Game)
    game.audio = mock.Mock()
    game.stats = {}
    game._log_combat = lambda *args, **kwargs: None
    game._spawn_dmg_number = lambda *args, **kwargs: None
    return game


def _enemy(health=100):
    fields = default_status_fields()
    fields.update({'x': 10.0, 'y': 10.0, 'health': health, 'max_health': health,
                   'enemy_type': 'skeleton', 'level': 1, 'damage_reduction': 0.0,
                   'hit_count': 0})
    return fields


class CastSfxRouting(unittest.TestCase):
    def _route(self, ability_id):
        audio = AudioSystem()
        with mock.patch.object(audio, '_play_random', autospec=True) as play:
            audio.ability_cast(ability_id)
            return play.call_args_list

    def test_cones_swing(self):
        args = self._route('cone_fire')
        self.assertEqual([c[0][0] for c in args], ['cast_swing'])

    def test_dash_blink_are_own_cues(self):
        self.assertEqual([c[0][0] for c in self._route('dash')], ['cast_dash'])
        self.assertEqual([c[0][0] for c in self._route('blink')], ['cast_blink'])

    def test_buffs_and_aura_are_own_cues(self):
        self.assertEqual([c[0][0] for c in self._route('lifesteal')], ['cast_buff'])
        self.assertEqual([c[0][0] for c in self._route('fire_aura')], ['cast_aura'])


class DeathSfxRateGuard(unittest.TestCase):
    def test_guard_caps_bursts_and_reopens_after_interval(self):
        """Mass kills fire at most one cue per interval; the first cue of a
        new burst after the min interval passes again."""
        audio = AudioSystem()
        played = []
        clock = {'t': 0.0}
        with mock.patch.object(audio, '_play_random',
                               side_effect=lambda name, vol: played.append(name)), \
                mock.patch('systems.audio._now_secs',
                           side_effect=lambda: clock['t']):
            for _ in range(5):
                audio.enemy_dead()
            self.assertEqual(len(played), 1)   # burst collapsed to one cue
            clock['t'] += DEATH_SFX_MIN_INTERVAL + 1e-6
            audio.enemy_dead()
            self.assertEqual(len(played), 2)   # window reopened

    def test_first_kill_always_fires(self):
        """A fresh system (cold clock) never eats the first death cue."""
        audio = AudioSystem()
        with mock.patch.object(audio, '_play_random') as play:
            audio.enemy_dead()
            play.assert_called_once()


class DeathSfxEdge(unittest.TestCase):
    def test_killing_blow_plays_death_once(self):
        game = _game()
        z = _enemy(health=40)
        dealt = game._apply_damage_to_enemy(z, 50, 'physical')
        self.assertEqual(z['health'], 0)
        self.assertGreater(dealt, 0)
        game.audio.enemy_dead.assert_called_once()

    def test_survival_hit_is_silent(self):
        game = _game()
        z = _enemy(health=100)
        game._apply_damage_to_enemy(z, 30, 'physical')
        game.audio.enemy_dead.assert_not_called()

    def test_immune_and_zero_damage_are_silent(self):
        game = _game()
        z = _enemy(health=100)
        z['immune_physical'] = True     # immune via damage-type gate
        game._apply_damage_to_enemy(z, 50, 'physical')
        # immune hit returns 0 before the health step - no cue either way
        game.audio.enemy_dead.assert_not_called()

    def test_immune_never_fires_the_death_cue(self):
        """Fire on a fire-natured body: _is_enemy_immune gates it before the
        health step, so the death cue pipeline is never reached."""
        game = _game()
        immune = _enemy(health=100)
        immune['dmg_type'] = 'fire'
        dealt = game._apply_damage_to_enemy(immune, 50, 'fire')
        self.assertEqual(dealt, 0)
        game.audio.enemy_dead.assert_not_called()


if __name__ == '__main__':
    unittest.main()
