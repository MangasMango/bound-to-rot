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

"""Music scene states + crossfade.

    menu / loading silence / hub / death screen — plus the continuous
    delve playlist (western_ingame1/2/3) that advances on track ends and
    is never re-triggered by waves, depths or node choices.

    States sharing a file share one loaded stream — see TestSharedStreams.
"""

import os
import unittest
from unittest import mock
from pathlib import Path

from config import ASSETS
import systems.audio as audio_mod
from systems.audio import (AudioSystem, FADE_SECONDS, _MUSIC_FILES,
                           _GAME_PLAYLIST, GAME_MUSIC_STATE, fade_step)


class TestMusicRegistry(unittest.TestCase):
    def test_registry_files_exist(self):
        for name, rel in _MUSIC_FILES.items():
            self.assertTrue(os.path.exists(os.path.join(ASSETS, rel)),
                            f'missing track for {name}: {rel}')
        for rel in _GAME_PLAYLIST:
            self.assertTrue(os.path.exists(os.path.join(ASSETS, rel)),
                            f'missing playlist track: {rel}')

    def test_expected_tracks(self):
        self.assertIn('Western_menu.ogg', _MUSIC_FILES['menu'])
        self.assertIn('western_hub.ogg', _MUSIC_FILES['hub'])
        self.assertIn('westernguitarstab.ogg', _MUSIC_FILES['death'])
        self.assertEqual(_GAME_PLAYLIST,
                         ('ost/western_ingame1.ogg',
                          'ost/western_ingame2.ogg',
                          'ost/western_ingame3.ogg'))
        # the old maxstack / Devilish Design registry states are retired
        self.assertNotIn('pulse_wait', _MUSIC_FILES)
        self.assertNotIn('wilds_1', _MUSIC_FILES)


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
        a.set_delve_music()
        self.assertEqual(a._music_state, GAME_MUSIC_STATE)
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


class TestDelvePlaylist(unittest.TestCase):
    """The delve playlist is continuous: entering 'game' restarts at track 1,
    `tick()` advances on bare track ends (crossfaded), it loops forever, and
    gameplay events never touch it (the old wave/depth triggers were removed
    from the API entirely)."""

    def _ready_audio(self):
        a = AudioSystem()
        a._music_ready = True
        a._music = {'menu': object(), 'hub': object(), 'death': object()}
        a._playlist_streams = [object(), object(), object()]
        a._file_streams = {}
        return a

    def test_enter_game_restarts_playlist_and_plays_track_1(self):
        a = self._ready_audio()
        a._playlist_index = 2
        with mock.patch.object(audio_mod, 'rl') as rl_mock:
            rl_mock.is_music_stream_playing.return_value = False
            a.set_music_state(GAME_MUSIC_STATE)
        self.assertEqual(a._playlist_index, 0)
        rl_mock.play_music_stream.assert_called_once_with(a._playlist_streams[0])

    def test_tick_advances_on_track_end(self):
        a = self._ready_audio()
        with mock.patch.object(audio_mod, 'rl') as rl_mock:
            playing = set()

            def _playing(m):
                return m in playing

            def _play(m):
                playing.add(m)
                return None

            def _seek(_m, _p):
                return None

            rl_mock.is_music_stream_playing.side_effect = _playing
            rl_mock.play_music_stream.side_effect = _play
            rl_mock.seek_music_stream.side_effect = _seek
            rl_mock.stop_music_stream.side_effect = lambda m: playing.discard(m)
            a.set_music_state(GAME_MUSIC_STATE)     # track 1 playing
            self.assertIs(a._state_stream(GAME_MUSIC_STATE),
                          a._playlist_streams[0])
            a.tick(FADE_SECONDS)                    # its fade-in completes
            self.assertEqual(a._fades, [])
            # track 1 ends
            playing.clear()
            a.tick(0.1)
            self.assertNotEqual(a._fades, [])        # track 2 fading in
            self.assertEqual(a._playlist_index, 1)   # target = track 2
            a.tick(FADE_SECONDS)                     # fade completes
            self.assertEqual(a._fades, [])
            self.assertIs(a._state_stream(GAME_MUSIC_STATE),
                          a._playlist_streams[1])
            # track 2 ends -> track 3
            playing.clear()
            a.tick(0.1)
            a.tick(FADE_SECONDS)
            self.assertEqual(a._playlist_index, 2)
            # track 3 ends -> wraps to track 1
            playing.clear()
            a.tick(0.1)
            a.tick(FADE_SECONDS)
            self.assertEqual(a._playlist_index, 0)

    def test_rapid_flips_keep_single_fader_per_stream(self):
        a = self._ready_audio()
        with mock.patch.object(audio_mod, 'rl') as rl_mock:
            rl_mock.is_music_stream_playing.return_value = True
            a.set_music_state('menu')
            a.set_music_state(GAME_MUSIC_STATE)
            a.set_music_state('menu')       # flip back mid-fade
        counts = {}
        for f in a._fades:
            counts[id(f['music'])] = counts.get(id(f['music']), 0) + 1
        self.assertTrue(all(n == 1 for n in counts.values()))


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
