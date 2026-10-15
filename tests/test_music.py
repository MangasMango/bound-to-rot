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

"""Music scene states + crossfade — BLUEPRINT §25.

    menu / loading silence / hub / death screen / per-depth rotation in
    the Anima / while waiting at the Pulse.

Two licensed tracks cover every state: Dark Loop (CC BY 3.0, Machine)
and Devilish Design (GPL 3.0, Johan Brodd). States sharing a file share
one loaded stream — see TestSharedStreams below.
"""

import os
import unittest
from unittest import mock
from pathlib import Path

from config import ASSETS
import systems.audio as audio_mod
from systems.audio import (AudioSystem, FADE_SECONDS, _MUSIC_FILES,
                           fade_step, wilds_key_for_depth)


class TestMusicRegistry(unittest.TestCase):
    def test_registry_files_exist(self):
        for name, rel in _MUSIC_FILES.items():
            self.assertTrue(os.path.exists(os.path.join(ASSETS, rel)),
                            f'missing track for {name}: {rel}')

    def test_expected_tracks(self):
        self.assertIn('Dark Loop.mp3', _MUSIC_FILES['menu'])
        self.assertIn('Devilish design.mp3', _MUSIC_FILES['hub'])
        self.assertIn('Dark Loop.mp3', _MUSIC_FILES['death'])
        self.assertIn('Dark Loop.mp3', _MUSIC_FILES['pulse_wait'])
        self.assertIn('Dark Loop.mp3', _MUSIC_FILES['wilds_1'])
        self.assertIn('Dark Loop.mp3', _MUSIC_FILES['wilds_2'])
        self.assertIn('Dark Loop.mp3', _MUSIC_FILES['wilds_3'])
        # the calm overlay and the old raid/menu variants are retired
        self.assertNotIn('calm', _MUSIC_FILES)
        self.assertNotIn('raid', _MUSIC_FILES)


class TestDepthRotation(unittest.TestCase):
    def test_rotates_a_b_c_by_depth(self):
        self.assertEqual(wilds_key_for_depth(1), 'wilds_1')
        self.assertEqual(wilds_key_for_depth(2), 'wilds_2')
        self.assertEqual(wilds_key_for_depth(3), 'wilds_3')
        self.assertEqual(wilds_key_for_depth(4), 'wilds_1')
        self.assertEqual(wilds_key_for_depth(5), 'wilds_2')
        self.assertEqual(wilds_key_for_depth(7), 'wilds_1')

    def test_depth_floor_guard(self):
        self.assertEqual(wilds_key_for_depth(0), 'wilds_1')


class TestFadeMath(unittest.TestCase):
    def test_linear_fade(self):
        self.assertAlmostEqual(
            fade_step(0.0, 1.0, FADE_SECONDS / 2, FADE_SECONDS), 0.5)
        self.assertAlmostEqual(
            fade_step(1.0, 0.0, FADE_SECONDS / 4, FADE_SECONDS), 0.75)

    def test_fade_clamps_at_target(self):
        self.assertEqual(fade_step(0.9, 1.0, 100.0, FADE_SECONDS), 1.0)
        self.assertEqual(fade_step(0.1, 0.0, 100.0, FADE_SECONDS), 0.0)


class TestStateApi(unittest.TestCase):
    def test_states_stored_before_music_ready(self):
        a = AudioSystem()
        a.set_music_state('hub')
        self.assertEqual(a._music_state, 'hub')
        a.set_delve_depth_music(5)
        self.assertEqual(a._music_state, 'wilds_2')
        a.set_pulse_wait_music()
        self.assertEqual(a._music_state, 'pulse_wait')
        a.set_music_state('off')
        self.assertEqual(a._music_state, 'off')


class TestCrossfadeLifecycle(unittest.TestCase):
    """Regression: the crossfade must look streams up by STATE NAME and
    actually play them (a file-path lookup bug once silenced all music)."""

    def _ready_audio(self):
        a = AudioSystem()
        a._music_ready = True
        a._music = {'menu': object(), 'hub': object()}
        return a

    def test_set_music_state_plays_the_target_stream(self):
        a = self._ready_audio()
        with mock.patch.object(audio_mod, 'rl') as rl_mock:
            rl_mock.is_music_stream_playing.return_value = False
            a.set_music_state('menu')
        rl_mock.play_music_stream.assert_called_once_with(a._music['menu'])
        self.assertEqual(len(a._fades), 1)
        self.assertEqual(a._fades[0]['target'], 1.0)
        self.assertEqual(a._fades[0]['vol'], 0.0)

    def test_state_change_fades_old_out_and_new_in(self):
        a = self._ready_audio()
        with mock.patch.object(audio_mod, 'rl') as rl_mock:
            # only the menu stream is playing; the hub stream isn't
            rl_mock.is_music_stream_playing.side_effect = (
                lambda m: m is a._music['menu'])
            a.set_music_state('menu')       # starts menu (fade-in)
            a.set_music_state('hub')        # crossfade menu -> hub
        # exactly one fader per stream: menu fading out, hub fading in
        self.assertEqual(len(a._fades), 2)
        targets = sorted(f['target'] for f in a._fades)
        self.assertEqual(targets, [0.0, 1.0])
        rl_mock.play_music_stream.assert_called_with(a._music['hub'])

    def test_tick_completes_fade_and_stops_old_stream(self):
        a = self._ready_audio()
        menu_s, hub_s = a._music['menu'], a._music['hub']
        with mock.patch.object(audio_mod, 'rl') as rl_mock:
            # faithful mini-simulator: streams start stopped; play/stop
            # mocks keep the playing-state dict in sync
            playing = {menu_s: False, hub_s: False}
            rl_mock.is_music_stream_playing.side_effect = lambda m: playing.get(m, False)
            rl_mock.play_music_stream.side_effect = lambda m: playing.__setitem__(m, True)
            rl_mock.stop_music_stream.side_effect = lambda m: playing.__setitem__(m, False)

            a.set_music_state('menu')
            self.assertTrue(playing[menu_s])          # menu started
            a.tick(FADE_SECONDS)                      # menu fade-in completes
            self.assertEqual(a._fades, [])
            a.set_music_state('hub')                  # menu -> hub crossfade
            a.tick(FADE_SECONDS)                      # both fades complete
            self.assertTrue(playing[hub_s])
            self.assertFalse(playing[menu_s])
        self.assertEqual(a._fades, [])
        rl_mock.stop_music_stream.assert_called_once_with(menu_s)
        rl_mock.update_music_stream.assert_called()

    def test_rapid_state_flip_keeps_single_fader_per_stream(self):
        a = self._ready_audio()
        with mock.patch.object(audio_mod, 'rl') as rl_mock:
            rl_mock.is_music_stream_playing.return_value = True
            a.set_music_state('menu')
            a.set_music_state('hub')
            a.set_music_state('menu')       # flip back mid-fade
        self.assertEqual(len(a._fades), 2)  # never duplicated faders

    def test_off_state_fades_everything_out(self):
        a = self._ready_audio()
        with mock.patch.object(audio_mod, 'rl') as rl_mock:
            rl_mock.is_music_stream_playing.return_value = True
            a.set_music_state('menu')
            a.set_music_state('off')
        self.assertTrue(all(f['target'] == 0.0 for f in a._fades))
        rl_mock.play_music_stream.assert_not_called()


class TestSharedStreams(unittest.TestCase):
    """States that point at the same file must share ONE loaded stream,
    otherwise several independent copies play stacked during crossfades."""

    def test_same_file_yields_same_stream(self):
        with mock.patch.object(audio_mod, 'rl') as rl_mock:
            streams = {}

            def fake_load(path):
                return streams.setdefault(path, object())

            rl_mock.load_music_stream.side_effect = fake_load
            a = AudioSystem()
            a.init_music()
        load_counts = {}
        for args in rl_mock.load_music_stream.call_args_list:
            load_counts[args[0][0]] = load_counts.get(args[0][0], 0) + 1
        for rel, n in load_counts.items():
            self.assertEqual(n, 1, f'{rel} loaded {n} times')
        # every state that shares a file resolves to the identical object
        by_file = {}
        for name, rel in _MUSIC_FILES.items():
            by_file.setdefault(rel, a._music[name])
            self.assertIs(a._music[name], by_file[rel])


if __name__ == '__main__':
    unittest.main()
