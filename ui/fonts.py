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

"""Shared font — loaded once, used by all UI modules."""
from __future__ import annotations

import pyray as rl

_font: rl.Font | None = None


def load(path: str, size: int = 64):
    global _font
    try:
        _font = rl.load_font_ex(path, size, None, 0)
        rl.set_texture_filter(_font.texture, rl.TEXTURE_FILTER_BILINEAR)
    except Exception:
        _font = None


def unload():
    global _font
    if _font and _font.baseSize > 0:
        rl.unload_font(_font)
    _font = None


def draw(text, x, y, size, color):
    if _font and _font.baseSize > 0:
        rl.draw_text_ex(_font, str(text), rl.Vector2(float(x), float(y)),
                        float(size), 1.0, color)
    else:
        rl.draw_text(str(text), int(x), int(y), int(size), color)


def measure(text, size) -> int:
    if _font and _font.baseSize > 0:
        v = rl.measure_text_ex(_font, str(text), float(size), 1.0)
        return int(v.x)
    return rl.measure_text(str(text), int(size))


def label(text, cx, y, size, color, bg_alpha: int = 160, pad_x: int = 5, pad_y: int = 3):
    """Draw centred text with a semi-transparent black background."""
    w = measure(text, size)
    bx = cx - w // 2 - pad_x
    by = y - pad_y
    rl.draw_rectangle(bx, by, w + pad_x * 2, size + pad_y * 2,
                      rl.Color(0, 0, 0, bg_alpha))
    draw(text, cx - w // 2, y, size, color)


def draw_panel(tex, x: int, y: int, w: int, h: int, corner: int = 10):
    """9-slice panel. Falls back to plain rect when tex is None/invalid."""
    if tex is None or tex.id == 0:
        rl.draw_rectangle(x, y, w, h, rl.Color(0, 0, 0, 0x99))
        rl.draw_rectangle_lines(x, y, w, h, rl.Color(50, 65, 50, 200))
        return
    tw = tex.width
    th = tex.height
    c = min(corner, tw // 2, th // 2)
    for sx, sy, sw, sh, dx, dy, dw, dh in [
        (0,      0,      c,       c,       x,       y,       c,       c),
        (c,      0,      tw-2*c,  c,       x+c,     y,       w-2*c,   c),
        (tw-c,   0,      c,       c,       x+w-c,   y,       c,       c),
        (0,      c,      c,       th-2*c,  x,       y+c,     c,       h-2*c),
        (c,      c,      tw-2*c,  th-2*c,  x+c,     y+c,     w-2*c,   h-2*c),
        (tw-c,   c,      c,       th-2*c,  x+w-c,   y+c,     c,       h-2*c),
        (0,      th-c,   c,       c,       x,       y+h-c,   c,       c),
        (c,      th-c,   tw-2*c,  c,       x+c,     y+h-c,   w-2*c,   c),
        (tw-c,   th-c,   c,       c,       x+w-c,   y+h-c,   c,       c),
    ]:
        if dw <= 0 or dh <= 0:
            continue
        rl.draw_texture_pro(
            tex,
            rl.Rectangle(float(sx), float(sy), float(sw), float(sh)),
            rl.Rectangle(float(dx), float(dy), float(dw), float(dh)),
            rl.Vector2(0, 0), 0.0, rl.WHITE)
