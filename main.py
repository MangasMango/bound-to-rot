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

"""
Bound To Rot — entry point.
Run from the project root:  python main.py
"""

import os
import time

import pyray as rl
from config import SCREEN_W, SCREEN_H
from core.game import Game

TARGET_FPS = 0
SHOW_PROFILER = False   # toggle with F3


def _draw_profiler(sections: list[tuple[str, float]], sw: int, sh: int):
    """Draw a waterfall bar showing ms cost of each named section."""
    BAR_H   = 18
    BAR_MAX = 300          # px width = 1 full bar
    MS_MAX  = 33.3         # ms that fills the bar (= 30 fps budget)
    PAD     = 8
    y       = sh - PAD - len(sections) * (BAR_H + 2)

    total = sum(ms for _, ms in sections)
    rl.draw_rectangle(PAD - 2, y - 2,
                      BAR_MAX + 160, len(sections) * (BAR_H + 2) + 4,
                      rl.Color(0, 0, 0, 160))

    colors = [
        rl.Color(80,  180, 255, 220),
        rl.Color(255, 180, 60,  220),
        rl.Color(80,  220, 120,  220),
        rl.Color(220,  80,  80,  220),
        rl.Color(200, 120, 255, 220),
        rl.Color(255, 220,  80,  220),
    ]
    for i, (label, ms) in enumerate(sections):
        bw  = int(min(1.0, ms / MS_MAX) * BAR_MAX)
        col = colors[i % len(colors)]
        rl.draw_rectangle(PAD, y, bw, BAR_H, col)
        rl.draw_rectangle_lines(PAD, y, bw, BAR_H, rl.Color(60, 60, 60, 180))
        rl.draw_text(f"{label}: {ms:.2f}ms", PAD + BAR_MAX + 6, y + 2, 13, rl.WHITE)
        y += BAR_H + 2

    rl.draw_text(f"total: {total:.2f}ms  ({1000/total:.0f} fps budget)",
                 PAD, y + 2, 13, rl.Color(200, 200, 200, 220))


def main():
    global SHOW_PROFILER

    # Window opens at the boot resolution and can be resized freely; the
    # game renders at the current window size (no fixed virtual canvas).
    rl.set_config_flags(rl.FLAG_WINDOW_RESIZABLE)
    rl.init_window(SCREEN_W, SCREEN_H, "Bound To Rot")
    rl.set_exit_key(0)
    rl.init_audio_device()
    rl.set_target_fps(TARGET_FPS)

    game = Game()
    game.init()

    try:
        while not rl.window_should_close():
            if rl.is_key_pressed(rl.KEY_F3):
                SHOW_PROFILER = not SHOW_PROFILER
            if rl.is_key_pressed(rl.KEY_F12):
                rl.take_screenshot(f"screenshot_{int(time.time())}.png")

            # Drain raylib's char queue once per frame into per-tick text buffers.
            game.poll_frame_input()

            # Variable timestep: one sim update per rendered frame, dt = real
            # frame time (clamped so a hitch can't teleport entities).
            dt = min(rl.get_frame_time(), 0.1)

            t0 = time.perf_counter()
            game.update(dt)
            t1 = time.perf_counter()

            rl.begin_drawing()
            t2 = time.perf_counter()
            game.draw()
            t3 = time.perf_counter()
            rl.draw_fps(8, 8)
            t4 = time.perf_counter()

            if SHOW_PROFILER:
                cw = rl.get_screen_width()
                ch = rl.get_screen_height()
                sections = [
                    ("update",      (t1 - t0) * 1000),
                    ("begin_draw",  (t2 - t1) * 1000),
                    ("game.draw",   (t3 - t2) * 1000),
                    ("fps+overlay", (t4 - t3) * 1000),
                ]
                for name, ms in game.profile_ms.items():
                    sections.append((f"  {name}", ms))
                _draw_profiler(sections, cw, ch)

            rl.end_drawing()
    finally:
        # Also runs on Ctrl+C (KeyboardInterrupt) — release textures/audio.
        game.cleanup()
        rl.close_audio_device()
        rl.close_window()


if __name__ == '__main__':
    main()
