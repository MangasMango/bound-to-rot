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

"""Clip recorder (dev console `record ...`) - issue #58.

Covers:
  1. Cadence math - `should_capture` fires at most once per 1/fps of gathered
     dt, per mode (gif 15fps, video 30fps), and never when idle.
  2. State machine - start clamps seconds to [1, REC_SECONDS_MAX], refuses
     restarts while active, rejects unknown modes, cancel discards/kill-wipes
     everything, countdown zeroes out.
  3. GIF assembly - finish() writes one looping GIF (PIL-verified),
     normalizes size-mismatched frames from a mid-clip window resize,
     downscales wide captures to REC_MAX_WIDTH, refuses too-few-frame clips,
     honors a monkeypatched clips dir.
  4. Video streaming - ffmpeg arg builders (mp4/webm, even-dims crop filter),
     sink-free start via the `sink` test seam, frame feeds land on the sink,
     cancel kills it, finish muxes it, missing-ffmpeg refuses with a hint.
  5. Console grammar - record [gif|webm|mp4] [sec] / bare `record` = mp4 /
     record stop / record png through _exec_console with real or fake sinks.
"""

import os
from unittest import mock

import pytest
from PIL import Image

from core.game import STATE_PLAYING, Game
from systems import recorder as rec_mod
from systems.recorder import (ClipRecorder, MODE_GIF, MODE_MP4, MODE_WEBM,
                              REC_GIF_FPS, REC_JPEG_QUALITY,
                              REC_JPEG_SUBSAMPLING, REC_MAX_WIDTH, REC_MODES,
                              REC_SECONDS_DEFAULT, REC_SECONDS_MAX,
                              REC_VIDEO_FPS, _ffmpeg_args)


def _img(color, size=(320, 240)):
    return Image.new('RGB', size, color)


def _store(rec, color, size=(320, 240)):
    """Buffered gif capture (store_frame is the recorder's test seam)."""
    rec.store_frame(_img(color, size))


class FakeSink:
    """Video-sink double: captures feeds, never spawns a process."""

    def __init__(self):
        self.frames = []
        self.writes = 0
        self.finished = False
        self.cancelled = False
        self.path = '/fake/clip.mp4'

    def write(self, frame):
        self.writes += 1
        self.frames.append(frame)

    def finish(self):
        self.finished = True
        return self.path if self.frames else None

    def cancel(self):
        self.cancelled = True


class FailingSink(FakeSink):
    """Sink that always fails to mux (ffmpeg crash / disk full)."""

    def finish(self):
        self.finished = True
        return None


@pytest.fixture
def tmp_clips_dir(monkeypatch, tmp_path):
    monkeypatch.setattr(rec_mod, 'clips_dir', lambda: str(tmp_path))


@pytest.fixture
def fake_window(monkeypatch):
    """A live window for the tests that reach _video_dims (pyray seam)."""
    monkeypatch.setattr(rec_mod.rl, 'get_screen_width', lambda: 1280)
    monkeypatch.setattr(rec_mod.rl, 'get_screen_height', lambda: 720)


@pytest.fixture
def clock(monkeypatch):
    t = {'now': 0.0}
    monkeypatch.setattr(rec_mod.time, 'perf_counter', lambda: t['now'])
    return t


# ── 1. cadence ───────────────────────────────────────────────────────────

def test_idle_never_captures():
    r = ClipRecorder()
    for _ in range(100):
        assert r.should_capture(1.0 / 60) is False
    assert r.active is False


def test_gif_fires_at_its_15fps_cadence(clock):
    r = ClipRecorder()
    r.start(MODE_GIF, REC_SECONDS_DEFAULT)
    dt = 1.0 / 60
    hits = sum(r.should_capture(dt) for _ in range(60 * 10))
    assert hits == int(10 * REC_GIF_FPS)   # 10 s of dt through a 15 fps gate


def test_video_fires_at_the_30fps_cadence(clock):
    r = ClipRecorder()
    r.start(MODE_MP4, REC_SECONDS_DEFAULT, sink=FakeSink())
    dt = 1.0 / 60
    hits = sum(r.should_capture(dt) for _ in range(60 * 10))
    assert hits == int(10 * REC_VIDEO_FPS)


def test_one_tick_cannot_fire_twice(clock):
    r = ClipRecorder()
    r.start(MODE_GIF, REC_SECONDS_DEFAULT)
    r.should_capture(0.0)                       # prime the accumulator
    assert r.should_capture(1.0 / REC_GIF_FPS)  # gap met → capture
    assert not r.should_capture(0.0)            # same tick, no double fire


# ── 2. state machine ─────────────────────────────────────────────────────

def test_start_uses_default_when_seconds_is_none(clock):
    r = ClipRecorder()
    assert r.start(MODE_MP4, None, sink=FakeSink())
    assert r.active
    assert r.mode == MODE_MP4
    assert r.remaining == pytest.approx(REC_SECONDS_DEFAULT)


def test_bare_gif_start_defaults_to_gif_mode(clock):
    r = ClipRecorder()
    assert r.start(MODE_GIF, None)
    assert r.mode == MODE_GIF
    assert r.fps == REC_GIF_FPS


def test_start_clamps_seconds(clock):
    r = ClipRecorder()
    r.start(MODE_GIF, REC_SECONDS_MAX * 2)
    assert r.remaining <= REC_SECONDS_MAX
    r2 = ClipRecorder()
    r2.start(MODE_GIF, 0)
    assert r2.remaining >= 1.0


def test_rejects_restart_while_active(clock):
    r = ClipRecorder()
    assert r.start(MODE_GIF, 10)
    assert not r.start(MODE_MP4, 20, sink=FakeSink())   # no silent reset
    assert r.active and r.mode == MODE_GIF


def test_rejects_unknown_mode(clock):
    r = ClipRecorder()
    assert not r.start('avi', 10)
    assert not r.active
    assert 'avi' in r.error


def test_cancel_discards_buffer_and_deactivates(tmp_clips_dir, clock):
    r = ClipRecorder()
    r.start(MODE_GIF, 10)
    _store(r, (10, 20, 30))
    r.cancel()
    assert not r.active
    assert r._frames == []
    assert r.finish() is None   # canceling mid-countdown writes nothing


def test_video_cancel_kills_the_sink(tmp_clips_dir, clock):
    sink = FakeSink()
    r = ClipRecorder()
    r.start(MODE_MP4, 10, sink=sink)
    r.cancel()
    assert sink.cancelled
    assert not r.active
    assert r._sink is None


def test_countdown_reaches_zero(tmp_clips_dir, clock):
    r = ClipRecorder()
    r.start(MODE_GIF, 5)
    assert r.remaining == pytest.approx(5.0)
    clock['now'] = 2.5
    assert r.remaining == pytest.approx(2.5)
    clock['now'] = 5.0
    assert r.remaining == 0.0
    # 0 frames buffered → discarded, but the recorder must still deactivate
    assert r.finalize_tick() is None
    assert not r.active
    assert r._frames == []


def test_finalize_tick_silent_before_deadline(tmp_clips_dir, clock):
    r = ClipRecorder()
    r.start(MODE_GIF, 10)
    _store(r, (10, 20, 30))
    _store(r, (40, 50, 60))
    clock['now'] = 9.5
    assert r.finalize_tick() is None
    assert r.active


def test_video_deadline_muxes_via_finalize(tmp_clips_dir, clock):
    sink = FakeSink()
    r = ClipRecorder()
    r.start(MODE_MP4, 5, sink=sink)
    r._feed_video(_img((10, 20, 30)))
    clock['now'] = 5.0
    assert r.finalize_tick() == '/fake/clip.mp4'
    assert sink.finished and not r.active


def test_video_deadline_without_frames_discards(tmp_clips_dir, clock):
    sink = FakeSink()
    r = ClipRecorder()
    r.start(MODE_MP4, 5, sink=sink)
    clock['now'] = 5.0
    assert r.finalize_tick() is None
    assert not r.active


def test_failing_sink_finish_reports_none(tmp_clips_dir, clock):
    r = ClipRecorder()
    r.start(MODE_MP4, 10, sink=FailingSink())
    assert r.finish() is None
    assert not r.active


# ── 3. GIF assembly ──────────────────────────────────────────────────────

def test_finish_writes_looping_gif(tmp_clips_dir, clock):
    r = ClipRecorder()
    r.start(MODE_GIF, 10)
    # strongly distinct frames: PIL folds palette-identical neighbors into
    # one frame, so near-colors would collapse and lie about n_frames
    for rgb in ((200, 10, 10), (10, 200, 10), (10, 10, 200), (250, 250, 10)):
        _store(r, rgb)
    path = r.finish()
    assert path is not None and path.endswith('.gif')
    assert os.path.exists(path)
    with Image.open(path) as gif:
        assert gif.format == 'GIF'
        assert gif.n_frames == 4
        assert gif.info.get('loop') == 0   # loops for the reddit post
    assert not r.active
    assert r._frames == []
    assert r.mode is None   # finished recorders go fully defunct


def test_finish_normalizes_size_mismatch(tmp_clips_dir, clock):
    r = ClipRecorder()
    r.start(MODE_GIF, 10)
    _store(r, (10, 20, 30), (200, 200))    # first frame sets the target size
    _store(r, (40, 50, 60), (100, 100))    # window resized mid-clip
    path = r.finish()
    assert path is not None
    with Image.open(path) as gif:
        assert gif.size == (200, 200)


def test_finish_downscales_wide_captures(tmp_clips_dir, clock):
    r = ClipRecorder()
    r.start(MODE_GIF, 10)
    _store(r, (10, 20, 30), (REC_MAX_WIDTH * 2, 400))
    _store(r, (40, 50, 60), (REC_MAX_WIDTH * 2, 400))
    path = r.finish()
    with Image.open(path) as gif:
        assert gif.width == REC_MAX_WIDTH


def test_window_sized_captures_are_not_downscaled(tmp_clips_dir, clock):
    """A 1280x720 window is kept at full width - downscaling softens the
    frame and the softer image + 256-color dithering reads as washed-out
    colors next to the full-res `record png` probe."""
    r = ClipRecorder()
    r.start(MODE_GIF, 10)
    _store(r, (10, 20, 30), (REC_MAX_WIDTH, 720))
    _store(r, (40, 50, 60), (REC_MAX_WIDTH, 720))
    path = r.finish()
    with Image.open(path) as gif:
        assert gif.size == (REC_MAX_WIDTH, 720)


def test_finish_discards_singleton_clip(tmp_clips_dir, clock):
    r = ClipRecorder()
    r.start(MODE_GIF, 10)
    _store(r, (10, 20, 30))
    assert r.finish() is None
    assert not r.active
    assert r._frames == []


def test_finish_saves_partial_clip_past_deadline(tmp_clips_dir, clock):
    """Game.cleanup finish-saves an active clip; finish() is callable at any
    point of the countdown, even far past the deadline."""
    r = ClipRecorder()
    r.start(MODE_GIF, 5)
    _store(r, (10, 20, 30))
    _store(r, (40, 50, 60))
    clock['now'] = 999.0
    assert r.finish() is not None


def test_jpeg_buffer_quality_is_pinned():
    """The JPEG buffer is the RAM cap; q must stay memory-bounded, and the
    chroma must be 4:4:4 (subsampling=0) - default subsampling bled dark
    colors and was visibly wrong in clips."""
    assert REC_JPEG_QUALITY == 90
    assert REC_JPEG_SUBSAMPLING == 0


# ── 4. video streaming ───────────────────────────────────────────────────

def test_mp4_args_are_h264_faststart():
    args = _ffmpeg_args(MODE_MP4, 1280, 720, REC_VIDEO_FPS, 'clip.mp4')
    args = ' '.join(args)
    assert '-f rawvideo -pix_fmt rgb24' in args
    assert '-s 1280x720 -r 30' in args
    assert 'libx264' in args and 'yuv420p' in args
    assert '+faststart' in args      # streams on the web without moov-hunting
    assert 'crop=trunc(iw/2)*2:trunc(ih/2)*2' in args   # even-dims for 420p


def test_webm_args_are_vp9_realtime():
    args = ' '.join(_ffmpeg_args(MODE_WEBM, 1280, 720, REC_VIDEO_FPS,
                                 'clip.webm'))
    assert 'libvpx-vp9' in args
    assert 'realtime' in args        # VP9 would otherwise crawl
    assert 'clip.webm' in args


def test_video_frames_land_on_the_sink(clock):
    sink = FakeSink()
    r = ClipRecorder()
    r.start(MODE_MP4, 10, sink=sink)
    r._feed_video(_img((200, 30, 30)))
    r._feed_video(_img((40, 80, 190), (160, 90)))   # resized to first frame
    assert sink.writes == 2
    assert sink.frames[0].tobytes() != sink.frames[1].tobytes()


def test_video_feed_adopts_first_frame_size(clock):
    """Test seam: caller-built sinks have no dims - the first feed adopts."""
    sink = FakeSink()
    r = ClipRecorder()
    r.start(MODE_MP4, 10, sink=sink)
    r._feed_video(_img((10, 20, 30), (640, 360)))   # sets target
    r._feed_video(_img((40, 50, 60), (320, 180)))   # resized to match
    assert sink.frames[0].size == (640, 360)
    assert sink.frames[1].size == (640, 360)


def test_missing_ffmpeg_refuses_to_start(monkeypatch):
    """No ffmpeg on PATH: mp4/webm must refuse with the gif hint, never a
    broken empty file. (GIF needs no ffmpeg and still works.)"""
    monkeypatch.setattr(rec_mod.shutil, 'which', lambda _name: None)
    r = ClipRecorder()
    assert not r.start(MODE_MP4, 10)
    assert not r.active
    assert 'record gif' in r.error


def test_ffmpeg_presence_is_probed_per_start(monkeypatch, clock, fake_window):
    """The probe is per-start, not cached - a player could install/move the
    binary while the game runs."""
    r = ClipRecorder()
    with mock.patch.object(rec_mod.shutil, 'which', return_value=None):
        assert not r.start(MODE_MP4, 10)
    sink = FakeSink()
    rec_spy = mock.Mock(return_value=sink)
    with mock.patch.object(rec_mod, '_build_video_sink', rec_spy):
        assert r.start(MODE_MP4, 10)
        rec_spy.assert_called_once()
        assert r._size == (1280, 720)    # dims snapshot feeds the -s arg
    assert r.active


# ── 5. console grammar ───────────────────────────────────────────────────

def _game(recorder):
    game = Game.__new__(Game)
    game.state = STATE_PLAYING
    game._chat_log = []
    game._chat_open = True
    game.recorder = recorder
    return game


def _exec_last_output(game, cmd):
    """Runs a console command; returns the OUTPUT text of the log entry
    (triples are (prompt, output, birth) since the PoE chat rename)."""
    game._exec_console(cmd)
    return game._chat_log[-1][1]


def test_record_gif_starts_default_clip(clock):
    rec = ClipRecorder()
    out = _exec_last_output(_game(rec), 'record gif')
    assert rec.active and rec.mode == MODE_GIF
    assert rec.remaining == pytest.approx(REC_SECONDS_DEFAULT)
    assert rec.fps == REC_GIF_FPS
    assert 'BTR/clips' in out


def test_record_mp4_starts_video_with_graceful_missing_ffmpeg(
        monkeypatch, clock, fake_window):
    rec = ClipRecorder()
    game = _game(rec)
    monkeypatch.setattr(rec_mod, '_build_video_sink',
                        lambda *a, **k: FakeSink())
    out = _exec_last_output(game, 'record mp4')
    assert rec.active and rec.mode == MODE_MP4 and rec.fps == REC_VIDEO_FPS
    assert 'MP4' in out


def test_record_mp4_ffmpeg_missing_shows_hint(monkeypatch, clock):
    rec = ClipRecorder()
    game = _game(rec)
    monkeypatch.setattr(rec_mod.shutil, 'which', lambda _n: None)
    out = _exec_last_output(game, 'record mp4')
    assert not rec.active
    assert 'record gif' in out         # graceful fallback hint
    assert game._chat_open is True  # no implicit close on refusal


def test_bare_record_is_an_mp4_clip(monkeypatch, clock, fake_window):
    rec = ClipRecorder()
    game = _game(rec)
    monkeypatch.setattr(rec_mod, '_build_video_sink',
                        lambda *a, **k: FakeSink())
    out = _exec_last_output(game, 'record')
    assert rec.active and rec.mode == MODE_MP4
    assert rec.remaining == pytest.approx(REC_SECONDS_DEFAULT)
    assert 'MP4' in out


def test_record_webm_uses_the_vp9_path(monkeypatch, clock, fake_window):
    rec = ClipRecorder()
    game = _game(rec)
    monkeypatch.setattr(rec_mod, '_build_video_sink',
                        lambda *a, **k: FakeSink())
    _exec_last_output(game, 'record webm 20')
    assert rec.active and rec.mode == MODE_WEBM
    assert rec.remaining == pytest.approx(20.0)
    assert rec.fps == REC_VIDEO_FPS


def test_record_gif_honors_custom_length(clock):
    rec = ClipRecorder()
    _exec_last_output(_game(rec), 'record gif 20')
    assert rec.active and rec.remaining == pytest.approx(20.0)


def test_record_unknown_mode_shows_usage(clock):
    rec = ClipRecorder()
    out = _exec_last_output(_game(rec), 'record avi 20')
    assert not rec.active
    assert 'Usage' in out


def test_record_gif_rejects_garbage_and_out_of_range(clock):
    rec = ClipRecorder()
    for bad in ('record gif 999', 'record gif there'):
        out = _exec_last_output(_game(rec), bad)
        assert not rec.active
        assert 'Usage' in out


def test_repeat_start_is_answered_not_restarted(clock):
    rec = ClipRecorder()
    game = _game(rec)
    _exec_last_output(game, 'record gif')
    with mock.patch.object(rec, 'start', return_value=False) as spy:
        out = _exec_last_output(game, 'record gif')
        spy.assert_not_called()
    assert rec.active
    assert 'Already recording' in out


def test_record_stop_closes_chat_and_saves_clip(tmp_clips_dir, clock):
    rec = ClipRecorder()
    game = _game(rec)
    _exec_last_output(game, 'record gif')
    _store(rec, (10, 20, 30))
    _store(rec, (40, 50, 60))
    out = _exec_last_output(game, 'record stop')
    assert not rec.active
    assert 'Clip saved:' in out
    assert game._chat_open is False


def test_record_stop_without_frames_discards(tmp_clips_dir, clock):
    rec = ClipRecorder()
    game = _game(rec)
    _exec_last_output(game, 'record gif')
    out = _exec_last_output(game, 'record stop')
    assert not rec.active
    assert 'discarded' in out


def test_record_stop_video_muxes_sink(clock):
    rec = ClipRecorder()
    game = _game(rec)
    sink = FakeSink()
    rec.start(MODE_MP4, 10, sink=sink)
    rec._feed_video(_img((10, 20, 30)))
    _exec_last_output(game, 'record stop')
    assert sink.finished
    assert 'Clip saved:' in game._chat_log[-1][1]


def test_record_stop_video_without_frames_discards(clock):
    rec = ClipRecorder()
    game = _game(rec)
    rec.start(MODE_MP4, 10, sink=FakeSink())
    out = _exec_last_output(game, 'record stop')
    assert 'discarded' in out


def test_record_stop_when_not_recording(clock):
    rec = ClipRecorder()
    assert 'Not recording' in _exec_last_output(_game(rec), 'record stop')


def test_record_commands_close_chat(clock):
    rec = ClipRecorder()
    game = _game(rec)
    _exec_last_output(game, 'record gif')
    assert game._chat_open is False


def test_invalid_record_keeps_chat_open(clock):
    rec = ClipRecorder()
    game = _game(rec)
    for bad in ('record avi', 'record gif 999'):
        game._chat_open = True
        _exec_last_output(game, bad)
        assert game._chat_open is True


def test_no_window_refuses_video_start(monkeypatch, clock):
    """Headless guard: no live window -> no 0x0 rawvideo stream spawn."""
    rec = ClipRecorder()
    monkeypatch.setattr(rec_mod.shutil, 'which', lambda _n: '/usr/bin/ffmpeg')
    # _video_dims reads the real pyray singleton; in a test process the game
    # window does not exist, which must refuse, not spawn a 0x0 stream.
    assert not rec.start(MODE_MP4, 10)
    assert 'window' in (rec.error or '')
    assert not rec.active


def test_record_png_queues_probe(clock):
    rec = ClipRecorder()
    game = _game(rec)
    out = _exec_last_output(game, 'record png')
    assert rec.png_grab_pending
    assert not rec.active   # does not start a clip
    assert 'PNG' in out


def test_help_advertises_record_family(clock):
    text = _exec_last_output(_game(ClipRecorder()), 'help')
    for member in ('record', 'gif', 'webm', 'mp4'):
        assert member in text


def test_rec_modes_match_chat_vocabulary():
    assert set(REC_MODES) == {MODE_GIF, MODE_MP4, MODE_WEBM}
