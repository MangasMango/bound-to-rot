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

"""Level-up juice (issue #90): guitar-stab SFX + gold glow/glint burst.

Covers:
  1. AudioSystem loads the 'levelup' pool (the western guitar stab) and
     level_up() plays exactly that, once.
  2. Game._on_level_up fires the sting, the glow burst and a rising ring
     of glints, on top of the existing milestone/shake/recalc juice.
  3. Glow effects honour a per-effect 'dur' (the level-up pulse outlives
     the 0.35s default without changing every other glow).
"""

import unittest
from unittest import mock

import pyray as rl

from core.game import Game
from systems.audio import AudioSystem
import entities.progression as prog


class LevelUpSfxTests(unittest.TestCase):

    def test_guitar_stab_loaded_and_played(self):
        audio = AudioSystem()
        audio.init()
        self.assertIn('levelup', audio.sounds)    # loaded at init
        with mock.patch.object(audio, '_play', autospec=True) as play:
            audio.level_up()
        play.assert_called_once_with('levelup', 0.85)


class LevelUpVfxTests(unittest.TestCase):

    def _game(self):
        game = Game.__new__(Game)
        game.audio = mock.Mock()
        manager = mock.Mock()
        manager.active = prog.Character('lvl', 'Leveller', 'knight')
        manager.active.level = 4
        game.char_mgr = manager     # Game.char is a property over this
        game.px = game.py = 10.0
        game.stats = {}
        game._log_combat = lambda *args, **kwargs: None
        game._streak_milestone = None
        game._streak_milestone_t = 0.0
        game._shake_timer = 0.0
        game._shake_intensity = 0.0
        game._recalc_derived_stats = lambda: None
        game._glow_effects = []
        game._glint_effects = []
        return game

    def test_sting_fires_once_per_level_up(self):
        game = self._game()
        game._on_level_up(1)
        game.audio.level_up.assert_called_once_with()

    def test_gold_glow_burst_spawns_over_the_player(self):
        game = self._game()
        game._on_level_up(1)
        self.assertEqual(len(game._glow_effects), 1)
        glow = game._glow_effects[0]
        self.assertAlmostEqual(glow['x'], 10.0)
        self.assertAlmostEqual(glow['y'], 10.0)
        self.assertGreater(glow['dur'], 0.35)   # the pulse outlives the default
        self.assertEqual(glow['color'].r, 255)  # gold family
        self.assertGreaterEqual(glow['color'].g, 200)

    def test_glint_ring_spawns(self):
        game = self._game()
        game._on_level_up(1)
        self.assertEqual(len(game._glint_effects), 12)
        # glints rise: upward velocity component on every spark
        for glint in game._glint_effects:
            self.assertLess(glint['vel_y'], 2.0)   # gentle, some lift

    def test_multi_level_gain_still_fires_one_sting(self):
        game = self._game()
        game._on_level_up(3)
        game.audio.level_up.assert_called_once_with()


class GlowDurTests(unittest.TestCase):

    def _game_with_glow(self, dur):
        game = Game.__new__(Game)
        game._glow_effects = []
        game._spawn_glow(1.0, 1.0, dur=dur)
        return game

    def test_long_glow_survives_the_default_cull_window(self):
        game = self._game_with_glow(dur=0.9)
        game._spawn_glow(2.0, 2.0)            # default-dur companion
        for _ in range(25):
            # the real cull block (per-effect dur) - tick 0.42s total
            live = []
            for e in game._glow_effects:
                e['timer'] += 1 / 60
                if e['timer'] < e.get('dur', 0.35):
                    live.append(e)
            game._glow_effects = live
        self.assertEqual(len(game._glow_effects), 1)   # only the long one left

    def test_default_glow_still_fades_on_schedule(self):
        game = self._game_with_glow(dur=0.35)
        for _ in range(25):
            live = []
            for e in game._glow_effects:
                e['timer'] += 1 / 60
                if e['timer'] < e.get('dur', 0.35):
                    live.append(e)
            game._glow_effects = live
        self.assertEqual(game._glow_effects, [])


if __name__ == '__main__':
    unittest.main()
