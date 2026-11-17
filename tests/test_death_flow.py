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

"""Death flow under issue #31: the character survives, the anima is lost,
and a PoE-style XP penalty is applied. Supersedes the permadeath era."""

import unittest
from unittest import mock

import entities.progression as prog
import systems.xp as xp
from core.game import Game, STATE_DEAD


def _game_stub(char):
    game = Game.__new__(Game)
    game.tracker = type('T', (), {'kills': 12, 'time': 65.0, 'loot': 3})()
    manager = mock.Mock()
    manager.save = mock.Mock()
    manager.delete = mock.Mock()
    manager.active = char          # Game.char is a property over this
    game.char_mgr = manager
    game.state = 'playing'
    game.audio = mock.Mock()
    game._saved_anima = {'anima': {'depth': 9}}
    game._anima = {'depth': 9}
    return game


class DeathReworkTests(unittest.TestCase):
    def test_character_survives_and_loses_fraction(self):
        char = prog.Character('d1', 'Doomed', 'knight')
        char.level = 5
        char.xp = xp.xp_for_level(5)
        char_mgr_saved = []
        game = _game_stub(char)
        game.char_mgr.save.side_effect = lambda: char_mgr_saved.append(True)

        game._on_death()

        # Character not removed from the roster
        game.char_mgr.delete.assert_not_called()
        # XP penalty applied: 10% of the current level's requirement
        self.assertEqual(char.level, 5)
        self.assertEqual(char.xp,
                         xp.xp_for_level(5) - int(round(xp.xp_for_level(5) * 0.10)))
        # Roster persisted (the surviving character must be saved)
        self.assertTrue(char_mgr_saved)
        # End screen carries the loss for the death copy
        self.assertEqual(game._raid_results['xp_lost'],
                         int(round(xp.xp_for_level(5) * 0.10)))
        self.assertEqual(game._raid_results['level'], 5)
        self.assertEqual(game.state, STATE_DEAD)

    def test_anima_is_wiped_but_character_saved(self):
        char = prog.Character('d2', 'FallenLater', 'knight')
        game = _game_stub(char)
        with mock.patch.object(prog, 'clear_anima_data') as clear:
            game._on_death()
        clear.assert_called_once_with('d2')
        self.assertIsNone(game._saved_anima)
        self.assertIsNone(game._anima)

    def test_cap_level_death_loses_nothing(self):
        char = prog.Character('d3', 'Maxed', 'knight')
        char.level = xp.MAX_LEVEL
        char.xp = 777
        game = _game_stub(char)
        game._on_death()
        self.assertEqual(char.xp, 777)
        self.assertEqual(game._raid_results['xp_lost'], 0)

    def test_music_and_dead_state_match_extracted_flow(self):
        char = prog.Character('d4', 'Ash', 'knight')
        game = _game_stub(char)
        game._on_death()
        game.audio.set_music_state.assert_called_once_with('death')
        self.assertEqual(game.state, STATE_DEAD)


class KillXpFunnelTests(unittest.TestCase):
    def _kill_stub(self):
        game = Game.__new__(Game)
        manager = mock.Mock()
        manager.active = prog.Character('kf', 'Killer', 'knight')
        game.char_mgr = manager
        game.tracker = type('T', (), {'kills': 0})()
        game._anima = {'depth': 1}
        game._last_kill_t = -999.0
        game._kill_streak = 0
        game._streak_pop_t = -1.0
        game._shake_timer = 0.0
        game._shake_intensity = 0.0
        game._streak_milestone = None
        game._streak_milestone_t = -1.0
        game._log_combat = mock.Mock()
        game._add_angel_meter = mock.Mock()
        game._recalc_derived_stats = mock.Mock()
        return game

    def test_kill_awards_depth_scaled_xp_and_levels_up(self):
        game = self._kill_stub()
        enemy = {'level': 50.0}
        with mock.patch('pyray.get_time', lambda: 1.0):
            game._register_enemy_kill(enemy)
        self.assertGreater(game.char.xp, 0)
        self.assertEqual(game.tracker.kills, 1)

    def test_enemy_level_used_over_depth_fallback(self):
        game = self._kill_stub()
        game._anima = None                      # fallback path
        with mock.patch('systems.xp.award_for_kill',
                        wraps=xp.award_for_kill) as award:
            game._register_enemy_kill(None)
        award.assert_called_once()
        monster_level = award.call_args[0][1]
        from core.anima_gen import effective_level
        self.assertAlmostEqual(monster_level, effective_level(1), places=3)

    def test_level_up_grants_points_and_recalcs(self):
        game = self._kill_stub()
        game.char.xp = xp.xp_for_level(1)      # one level's worth banked
        game._award_kill_xp({'level': 1.0})
        self.assertEqual(game.char.level, 2)
        self.assertEqual(game.char.available_points, 1)
        game._recalc_derived_stats.assert_called_once()


if __name__ == '__main__':
    unittest.main()
