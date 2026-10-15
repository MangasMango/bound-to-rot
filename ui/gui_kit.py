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

"""Grunge GUI kit (assets/gui) — texture loader + shared draw helpers.

Reskins the procedural menu widgets with the kit's black/red grunge art:
buttons, sliders, toggles, panel frames. Palette mirrors the kit's own
style guide (assets/gui/Layout/Colors.png):

    Main Red #A90D01   Red hover #DA0000
    Main Black #111111 Grey Dark #373737  Grey Light #666666
    Main White #D2D2D2

All loaders degrade to None (callers fall back to plain rects), matching
the rest of the UI's graceful-without-GL behaviour. Textures are unloaded
as a group via unload().
"""

import os

import pyray as rl
import config

_GUI_DIR = os.path.join(config.ASSETS, 'gui')

# ── Kit palette (Colors.png) ──────────────────────────────────────────
def col(r, g, b, a=255):
    return rl.Color(r, g, b, a)

RED       = col(0xA9, 0x0D, 0x01, 255)   # Main Red
RED_HOT   = col(0xDA, 0x00, 0x00, 255)   # Red hover
BLACK     = col(0x11, 0x11, 0x11, 255)   # Main Black
GREY_DARK = col(0x37, 0x37, 0x37, 255)   # Grey Dark
GREY_LT   = col(0x66, 0x66, 0x66, 255)   # Grey Light
WHITE     = col(0xD2, 0xD2, 0xD2, 255)   # Main White

_TEX_CACHE = {}
_SPECS = {
    'btn_grey':     r'Button\Button#2\Button#2_Status=Grey_Default.png',
    'btn_grey_hov': r'Button\Button#2\Button#2_Status=Grey_Hover.png',
    'btn_red':      r'Button\Button#2\Button#2_Status=Red_Default.png',
    'btn_red_hov':  r'Button\Button#2\Button#2_Status=Red_Hover.png',
    'btn_pressed':  r'Button\Button#2\Button#2_Status=Pressed.png',
    'btn_disable':  r'Button\Button#2\Button#2_Status=Disable.png',
    'btn1_down':    r'Button\Button#1\Status=Pressed.png',
    'btn1_hov':     r'Button\Button#1\Status=Red_Hover.png',
    'slider_track': r'Slider\Rectangle\Progress_Bar=Rectangle_empty_v1.png',
    'slider_fill':  r'Slider\Rectangle\Progress_Bar=Rectangle_full_v1.png',
    'slider_knob':  r'Slider\Rectangle (Segments)\Slider_toggler.png',
    'checkmark':    r'Toggle\Icon Checkmark 3 (Rect).png',
    'frame_bg':     r'Frame\Frame_background.png',
    'frame_outline': r'Frame\Frame_outline.png',
    'frame_menu':   r'Frame\Frame_main_menu.png',
    'notice':       r'Notice\Frame_notice_v1.png',
}


def _load(key):
    path = os.path.join(_GUI_DIR, *_SPECS[key].split('\\'))
    if not os.path.exists(path):
        return None
    try:
        return rl.load_texture(path)
    except Exception:
        return None


def tex(key):
    """Texture for a kit piece, or None. Loads lazily, cached."""
    global _TEX_CACHE
    t = _TEX_CACHE.get(key)
    if t is None:
        t = _load(key)
        _TEX_CACHE[key] = t
    return t


def unload():
    global _TEX_CACHE
    for t in _TEX_CACHE.values():
        if t and t.id > 0:
            rl.unload_texture(t)
    _TEX_CACHE = {}


def nine_slice(t, x: int, y: int, w: int, h: int, corner: int = 24,
               tint=None):
    """Draw a kit sheet stretched into rect x/y/w/h, 9-slice so the
    brushed border ends stay unstretched. Falls back to a flat fill when
    the sheet is unavailable."""
    if t is None or t.id == 0:
        return False
    tw, th = t.width, t.height
    c = min(corner, tw // 2, th // 2, w // 2, h // 2)
    for sx, sy, sw, sh, dx, dy, dw, dh in [
        (0,    0,    c,      c,      x,       y,       c,      c),
        (c,    0,    tw-2*c, c,      x+c,     y,       w-2*c,  c),
        (tw-c, 0,    c,      c,      x+w-c,   y,       c,      c),
        (0,    c,    c,      th-2*c, x,       y+c,     c,      h-2*c),
        (c,    c,    tw-2*c, th-2*c, x+c,     y+c,     w-2*c,  h-2*c),
        (tw-c, c,    c,      th-2*c, x+w-c,   y+c,     c,      h-2*c),
        (0,    th-c, c,      c,      x,       y+h-c,   c,      c),
        (c,    th-c, tw-2*c, c,      x+c,     y+h-c,   w-2*c,  c),
        (tw-c, th-c, c,      c,      x+w-c,   y+h-c,   c,      c),
    ]:
        if dw <= 0 or dh <= 0:
            continue
        rl.draw_texture_pro(
            t,
            rl.Rectangle(float(sx), float(sy), float(sw), float(sh)),
            rl.Rectangle(float(dx), float(dy), float(dw), float(dh)),
            rl.Vector2(0, 0), 0.0, tint or rl.WHITE)
    return True
