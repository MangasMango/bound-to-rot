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

"""Console-driven clip recorder (`record ...`) - issue #58.

Records the final framebuffer (scene + post chain + HUD) for a fixed
countdown and saves one looping clip into the clips folder next to the
screenshots folder. Capture runs inside the main loop's begin/end_drawing
pair (before draw_fps, so clips never show the fps counter) and is throttled
to a per-mode fps via a dt accumulator - the game renders at its own pace
regardless. Assembly/muxing stalls a frame or two on finish, so it happens
OUTSIDE the drawing scope (see Game.finalize_recording_frame).

Modes:
  - mp4 (default; H.264 via local ffmpeg) - streams rawvideo over stdin,
    zero RAM growth, pixel-exact colors, mp4 is the most universally
    embeddable share format.
  - webm (VP9 via local ffmpeg) - same streaming path, slower encode.
  - gif - pillow-only fallback for machines without ffmpeg; JPEG-buffered
    frames (4:4:4 chroma) assembled into one looping palette GIF.

Owner ruling 2026-11: dev tool, no keybinds/replay buffer/settings UI, no
uploads; mp4 preferred over webm ("whatever is best").
"""

import datetime
import io
import os
import shutil
import time

import pyray as rl
from PIL import Image

# Capture cadence & size. The GIF mode stays at 15 fps; video modes get 30.
# Width cap: downscaling below the window size softens the frame and the
# softer image + 256-color dithering reads as washed-out colors next to a
# full-res probe PNG. 1280 covers the common window sizes; bigger windows
# still clamp.
REC_GIF_FPS         = 15
REC_VIDEO_FPS       = 30
REC_MAX_WIDTH       = 1280
# JPEG buffer (gif mode): 4:4:4 chroma (subsampling=0) - the default 4:2:0
# subsampling bleeds dark colors. q90 keeps the re-encode-to-GIF visual.
REC_JPEG_QUALITY     = 90
REC_JPEG_SUBSAMPLING = 0
REC_SECONDS_DEFAULT  = 10.0
REC_SECONDS_MAX      = 60.0

# Encoder quality: CRF 23 H.264 is transparent for gameplay footage.
REC_MP4_CRF  = 23
REC_WEBM_CRF = 30

MODE_GIF, MODE_MP4, MODE_WEBM = 'gif', 'mp4', 'webm'
REC_MODES = (MODE_GIF, MODE_MP4, MODE_WEBM)


def clips_dir():
    """BTR/clips next to the screenshots folder (APPDATA-or-home resolution)."""
    return os.path.join(os.environ.get('APPDATA', os.path.expanduser('~')),
                        'BTR', 'clips')


def _downscale(img):
    if img.width <= REC_MAX_WIDTH:
        return img
    h = max(1, round(img.height * REC_MAX_WIDTH / img.width))
    return img.resize((REC_MAX_WIDTH, h), Image.BILINEAR)


def _ffmpeg_args(mode, w, h, fps, path):
    """ffmpeg argument list for one clip. Rawvideo rgb24 over stdin (.rgb24
    skips a pointless alpha round trip); yuv420p needs even dimensions, so a
    center-safe crop filter floors both axes."""
    even = ('-vf', 'crop=trunc(iw/2)*2:trunc(ih/2)*2')
    if mode == MODE_MP4:
        codec = ('-c:v', 'libx264', '-preset', 'veryfast',
                 '-crf', str(REC_MP4_CRF), '-pix_fmt', 'yuv420p',
                 '-movflags', '+faststart')
    else:
        codec = ('-c:v', 'libvpx-vp9', '-crf', str(REC_WEBM_CRF),
                 '-deadline', 'realtime', '-cpu-used', '8', '-row-mt', '1')
    return [
        'ffmpeg', '-y', '-loglevel', 'error',
        '-f', 'rawvideo', '-pix_fmt', 'rgb24',
        '-s', f'{w}x{h}', '-r', str(fps), '-i', '-',
        *even,
        *codec,
        path,
    ]


class _FfmpegVideoSink:
    """Streams RGB frames into a local ffmpeg child process.

    Kept deliberately small: PIL-free input (raw rgb24 bytes), one stdin
    write per captured frame, close = mux. Tests drive all of the
    surrounding state machine with fakes; this class is only exercised on
    machines with ffmpeg.
    """

    def __init__(self, mode, w, h, fps, ext):
        self.path = os.path.join(
            clips_dir(),
            f'clip_{datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")}.{ext}')
        args = _ffmpeg_args(mode, w, h, fps, self.path)
        import subprocess
        self._proc = subprocess.Popen(args, stdin=subprocess.PIPE)

    def write(self, frame):
        self._proc.stdin.write(frame.tobytes())   # RGB, straight to mux

    def finish(self):
        self._proc.stdin.close()
        self._proc.wait()
        return self.path if self._proc.returncode == 0 else None

    def cancel(self):
        """Kill the child and discard the partial file."""
        self._proc.stdin.close()
        self._proc.kill()
        self._proc.wait()
        if os.path.exists(self.path):
            os.remove(self.path)


class _FfmpegMissing:
    """Stand-in sink when ffmpeg is not on PATH - start() refuses via this."""

    def __init__(self):
        self.error = "ffmpeg not found on PATH - use 'record gif'"
        self.path = None

    def write(self, frame):
        pass

    def finish(self):
        return None

    def cancel(self):
        pass


def _build_video_sink(mode, w, h, fps):
    """ffmpeg present? Otherwise the refusing stand-in."""
    if not shutil.which('ffmpeg'):
        return _FfmpegMissing()
    ext = mode if mode == MODE_WEBM else 'mp4'
    return _FfmpegVideoSink(mode, w, h, fps, ext)


class ClipRecorder:
    """Command-driven countdown recorder, mode-aware (gif | mp4 | webm).

    Load-bearing detail: the recorder must be state-machine only in its
    logic methods (should_capture / store_frame / finish / cancel / mode
    cadence) - tests drive those without pyray or a window. tick_grab and
    start are the pyray seams.
    """

    def __init__(self):
        self._frames   = []   # JPEG-encoded gif frames (bytes)
        self._acc      = 0.0  # dt accumulator for the capture cadence
        self._active   = False
        self._mode     = None
        self._sink     = None
        self._size     = None  # video target dims (w, h), snapshotted at start
        self.png_grab_pending = False   # `record png`: dump one probe frame
        self._started  = 0.0
        self._duration = 0.0

    # ── state machine ─────────────────────────────────────────────────

    def start(self, mode=MODE_MP4, seconds=None, sink=None):
        """Begin recording; seconds clamped to [1, REC_SECONDS_MAX].

        For video modes a sink is spawned eagerly (ffmpeg child, target size
        snapshotted from the current window) so the countdown and the muxed
        stream start together. Test seam: `sink` overrides the builder; errors
        land on `self.error` and keep the recorder inactive.
        """
        if self.active:
            self.error = 'Already recording'
            return False
        if mode not in (MODE_GIF, MODE_MP4, MODE_WEBM):
            self.error = f'Unknown clip mode: {mode}'
            return False
        try:
            seconds = float(seconds)
        except (TypeError, ValueError):
            seconds = REC_SECONDS_DEFAULT
        self._duration = max(1.0, min(REC_SECONDS_MAX, seconds))
        self._mode = mode
        self._frames = []
        self._acc = 0.0
        self._sink = None
        self.error = None
        if mode != MODE_GIF:
            # The builder probes ffmpeg (needs no window); a missing binary
            # comes back as the refusing stand-in with the actionable hint.
            if sink is None:
                target = self._video_dims()   # pyray seam: window dims
                if target is None:
                    # Prefer the missing-binary hint over the window error:
                    # ffmpeg is the actionable problem and needs no window.
                    if not shutil.which('ffmpeg'):
                        self.error = ("ffmpeg not found on PATH - "
                                      "use 'record gif'")
                    else:
                        self.error = 'No window to capture from'
                    return False
                self._size = target
                sink = _build_video_sink(mode, target[0], target[1],
                                         REC_VIDEO_FPS)
            # (test seam: a caller-provided sink adopts the frame size on
            # the first _feed_video instead)
            if getattr(sink, 'error', None):
                self.error = sink.error
                return False
            self._sink = sink
        self._started = time.perf_counter()
        self._active = True
        return True

    @property
    def mode(self):
        return self._mode

    @property
    def fps(self):
        """Capture cadence by mode - video wants frames, GIF only needs 15."""
        return REC_GIF_FPS if self._mode == MODE_GIF else REC_VIDEO_FPS

    def queue_png(self):
        """Queue one probe-frame PNG dump for the next capture tick."""
        self.png_grab_pending = True

    def _video_dims(self):
        """Target rgb24 frame size: window scaled into the width cap, as a
        pyray seam (called from the game loop, where the window exists).
        Returns None when there is no live window (headless/tests)."""
        w = rl.get_screen_width()
        h = rl.get_screen_height()
        if w <= 0 or h <= 0:
            return None
        if w > REC_MAX_WIDTH:
            h = max(1, round(h * REC_MAX_WIDTH / w))
            w = REC_MAX_WIDTH
        return w, h

    def cancel(self):
        """Drop the buffer / kill the mux - nothing is ever kept."""
        self._active = False
        self._frames = []
        if self._sink is not None:
            self._sink.cancel()
            self._sink = None

    def finish(self):
        """Assemble the current capture into a clip (even mid-countdown).

        Returns the clip path, or None when too few frames were captured /
        the mux failed. Buffer and mode are always reset. Cost: GIF decode of
        ~150 JPEGs + quantize pass, or an ffmpeg mux flush - a frame or two
        of stall, hence never called from inside the drawing scope.
        """
        mode, sink = self._mode, self._sink
        frames = self._frames
        self._active = False
        self._mode = None
        self._sink = None
        self._frames = []
        try:
            if mode == MODE_GIF:
                return self._finish_gif(frames)
            if sink is not None:
                return sink.finish()
            return None
        except Exception as exc:      # ffmpeg crash, disk full, ...
            print(f'[RECORDING] clip failed: {exc}')
            return None

    # ── cadence / timing ──────────────────────────────────────────────

    def should_capture(self, dt):
        """Cadence gate: True at most once per 1/self.fps of gathered dt."""
        if not self.active:
            return False
        self._acc += dt
        frame_gap = 1.0 / self.fps
        if self._acc < frame_gap:
            return False
        self._acc = min(self._acc - frame_gap, 0.1)
        return True

    @property
    def active(self):
        return self._active

    @property
    def elapsed(self):
        if not self._active:
            return self._duration
        return time.perf_counter() - self._started

    @property
    def remaining(self):
        return max(0.0, self._duration - self.elapsed)

    # ── capture (raylib seam) ─────────────────────────────────────────

    def tick_grab(self, dt):
        """Capture one screen frame if the cadence allows it.

        Called from the main loop inside begin/end_drawing, after game.draw()
        and before draw_fps. Returns True when a frame was captured/buffered.
        """
        if self.png_grab_pending:
            # `record png`: same grab path as clips, saved lossless - if this
            # looks right but a clip is off, the collision is in the clip
            # pipeline, not the readback.
            self.png_grab_pending = False
            frame = self._grab_screen()
            ts = datetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
            os.makedirs(clips_dir(), exist_ok=True)
            path = os.path.join(clips_dir(), f'probe_{ts}.png')
            frame.save(path, 'PNG')
            print(f'[RECORDING] PNG probe: {path}')
            return True
        if not self.active or self.elapsed >= self._duration:
            return False
        if not self.should_capture(dt):
            return False
        frame = self._grab_screen()
        if self._mode == MODE_GIF:
            self.store_frame(frame)
        else:
            self._feed_video(frame)
        return True

    def _grab_screen(self):
        """One frame of the final composite as a PIL RGB image.

        The only raylib-GL seam in this module. pyray structs are cffi
        objects - ctypes.string_at cannot take img.data; the raw R8G8B8A8
        buffer is copied out via the cffi API.
        """
        img = rl.load_image_from_screen()
        w = rl.get_screen_width()
        h = rl.get_screen_height()
        rgba = bytes(rl.ffi.buffer(img.data, w * h * 4))
        rl.unload_image(img)
        return Image.frombytes('RGBA', (w, h), rgba).convert('RGB')

    def _feed_video(self, frame):
        """One frame to the mux, resized to the snapshotted target dims so a
        mid-recording window resize cannot corrupt the rawvideo stream."""
        if self._sink is None:
            return
        if self._size is None:          # test seam: adopt the first frame
            self._size = frame.size
        if frame.size != self._size:
            frame = frame.resize(self._size, Image.BILINEAR)
        self._sink.write(frame)

    def finalize_tick(self):
        """Assemble + save when the countdown ran out. Call once per rendered
        frame from OUTSIDE the drawing scope."""
        if not self._active or self.elapsed < self._duration:
            return None
        return self.finish()

    # ── gif assembly (moviepy-style palette pass) ─────────────────────

    def store_frame(self, frame):
        """JPEG-buffer one gif capture. Test seam for the GIF mode."""
        frame = _downscale(frame)
        buf = io.BytesIO()
        frame.save(buf, 'JPEG', quality=REC_JPEG_QUALITY,
                   subsampling=REC_JPEG_SUBSAMPLING)
        self._frames.append(buf.getvalue())

    def _finish_gif(self, frames):
        if len(frames) < 2:
            return None
        imgs = []
        target = None
        for raw in frames:
            img = Image.open(io.BytesIO(raw)).convert('RGB')
            if target is None:
                target = img.size
            elif img.size != target:
                img = img.resize(target, Image.BILINEAR)
            imgs.append(img)
        # per-frame adaptive palette: ~40% tighter color match in the
        # delta test vs one global montage palette, at the cost of the
        # writer emitting local color tables (a barely-visible palette
        # settle between cuts). Dithering stays on - it is what keeps
        # the dark gradients from banding flat.
        quant = [im.quantize(colors=256, dither=Image.Dither.FLOYDSTEINBERG)
                 for im in imgs]
        dur = int(1000 / REC_GIF_FPS)
        os.makedirs(clips_dir(), exist_ok=True)
        ts = datetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
        path = os.path.join(clips_dir(), f'clip_{ts}.gif')
        quant[0].save(path, save_all=True, append_images=quant[1:],
                      duration=[dur] * len(quant), loop=0, disposal=2)
        print(f'[RECORDING] {path}')
        return path


GifClipRecorder = ClipRecorder    # pre-video name, kept as an alias
