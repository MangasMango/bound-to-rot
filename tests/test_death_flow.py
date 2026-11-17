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

"""Death flow under issues #31 + #48: the character survives, a PoE-style
XP penalty is applied, and death goes STRAIGHT TO THE HUB with the anima
BANKED, not wiped - enemies, ground loot and node state survive so the
delve resumes exactly where it stood. Supersedes the permadeath era and
the old death screen."""

import unittest
from unittest import mock

import entities.progression as prog
import systems.xp as xp
from core.game import Game, STATE_HUB


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
    game._ambient = None
    game._death_notice = None
    game._raid_results = None
    game.map = [[0]]
    game.zombies = []
    game.ground_items = []
    game._decor_items = []
    game.stats = {'health': 0.0, 'max_health': 50.0,
                  'energy_shield': 0.0, 'max_energy_shield': 20.0}
    game._ammo = 0
    game._ammo_max = 6
    game._reload_t = 1.0
    game._reload_total = 1.5
    game._orb_spin = 120.0
    game.hit_flash = 0.4

    def _banked_exit(*_args, **_kwargs):
        """Mirror the real _exit_anima essentials: bank + save + hub."""
        game._saved_anima = {'anima': {'depth': 9, 'banked': True}}
        game._anima = None
        game.char_mgr.save()
        game.state = STATE_HUB
    game._exit_anima = mock.Mock(side_effect=_banked_exit)
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
        # Straight to the hub with the banked delve - no death screen,
        # no end-screen results dict (issue #48)
        self.assertEqual(game.state, STATE_HUB)
        self.assertIsNone(game._raid_results)
        # The hub banner announces the exact loss
        self.assertEqual(game._death_notice['lost'],
                         int(round(xp.xp_for_level(5) * 0.10)))
        self.assertGreater(game._death_notice['timer'], 0.0)
        # the leave path ran exactly once (banks + enters the hub)
        game._exit_anima.assert_called_once_with('hub')

    def test_death_refills_pools_and_reloads_the_revolver(self):
        """Owner ruling (issue #48 follow-up): death is a full refill point -
        the player must not stand in the hub (or resume the delve) at 0 HP
        with an empty cylinder, or the resume insta-dies straight back."""
        char = prog.Character('d5', 'Wounded', 'knight')
        game = _game_stub(char)
        game._on_death()
        self.assertEqual(game.stats['health'], game.stats['max_health'])
        self.assertEqual(game.stats['energy_shield'],
                         game.stats['max_energy_shield'])
        self.assertEqual(game._ammo, game._ammo_max)
        self.assertEqual(game._reload_t, 0.0)
        self.assertEqual(game.hit_flash, 0.0)   # no stuck red flash

    def test_anima_is_banked_but_character_saved(self):
        """Owner ruling (issue #48): the anima SURVIVES death - enemies,
        ground loot and node state persist so re-entry resumes the delve
        where it stood. The snapshot is BANKED via save_anima_data, never
        cleared."""
        char = prog.Character('d2', 'FallenLater', 'knight')
        game = _game_stub(char)
        with mock.patch.object(prog, 'clear_anima_data') as clear, \
                mock.patch.object(prog, 'save_anima_data') as save_anim:
            game._exit_anima = Game._exit_anima.__get__(game)   # real path
            game._enter_hub = mock.Mock()                       # hub needs a world
            game._on_death()
        clear.assert_not_called()          # the delve is NOT wiped
        save_anim.assert_called_once()     # the delve snapshot is banked
        self.assertIsNone(game._anima)     # live state handed back to the hub
        self.assertIsNotNone(game._saved_anima)   # banked for re-entry
        game._enter_hub.assert_called_once()

    def test_cap_level_death_loses_nothing(self):
        char = prog.Character('d3', 'Maxed', 'knight')
        char.level = xp.MAX_LEVEL
        char.xp = 777
        game = _game_stub(char)
        game._on_death()
        self.assertEqual(char.xp, 777)
        self.assertEqual(game._death_notice['lost'], 0)

    def test_no_death_music_and_state_is_hub(self):
        char = prog.Character('d4', 'Ash', 'knight')
        game = _game_stub(char)
        game._on_death()
        for call_args in game.audio.set_music_state.call_args_list:
            self.assertNotEqual(call_args.args[0], 'death')
        self.assertEqual(game.state, STATE_HUB)


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
        game.audio = mock.Mock()          # level-up sting (issue #90)
        game._glow_effects = []
        game._glint_effects = []
        game.px = game.py = 0.0
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
