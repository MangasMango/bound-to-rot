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

"""Shared font — loaded once, used by all UI modules.

Pixel fonts (see CRISP_SIZES) rasterize cleanly only at specific point
sizes, so one font object per crisp size is kept and every requested
size snaps to the nearest crisp one before drawing (1:1 glyphs — no
scaling artifacts). Scalable fonts keep bilinear filtering and free
sizes."""
from __future__ import annotations

import pyray as rl
from pyray import ffi

_font: rl.Font | None = None            # scalable font (single object)
_pixel_sizes: list[int] | None = None   # None = scalable; list = pixel font
_pixel_fonts: dict[int, rl.Font] = {}   # crisp size -> font object
_last_path: str = ''                    # pixel font file, for lazy per-size loads

# Point sizes at which bundled bitmap fonts render pixel-perfect — kept
# as a hook; the current UI font (Sancreek) is scalable, so it loads at
# free sizes with bilinear filtering instead.
CRISP_SIZES = {}


_cp_buf = None   # cffi int[] buffer — MUST outlive load_font_ex calls
_cp_n = 0


def _codepoints():
    """ASCII + Latin-1 accents + common punctuation — load_font_ex with
    a NULL codepoint list only loads 95 ASCII glyphs, which turns em-dashes
    and accented text into '?'. Returns (int* pointer, count); the buffer
    is cached module-level because a cast does NOT keep it alive."""
    global _cp_buf, _cp_n
    if _cp_buf is None:
        cps = ([c for c in range(0x20, 0x7F)]
               + [c for c in range(0xA0, 0x100)]
               + [0x2013, 0x2014, 0x2018, 0x2019, 0x201C, 0x201D, 0x2026, 0x2022])
        _cp_buf = ffi.new('int[]', cps)
        _cp_n = len(cps)
    return ffi.cast('int *', _cp_buf), _cp_n


def _load_font_at(path: str, size: int, pixel: bool) -> rl.Font | None:
    try:
        if pixel:
            cp, n = _codepoints()
            f = rl.load_font_ex(path, size, cp, n)
            rl.set_texture_filter(f.texture, rl.TEXTURE_FILTER_POINT)
        else:
            f = rl.load_font_ex(path, size, None, 0)
            rl.set_texture_filter(f.texture, rl.TEXTURE_FILTER_BILINEAR)
        return f
    except Exception:
        return None


def load(path: str, sizes=None):
    """Load a font. `sizes` is the crisp-size list for pixel fonts — one
    font object per size is created EAGERLY (loading a font mid-frame
    corrupts the render batch). None/empty = scalable font drawn at free
    sizes with bilinear filtering."""
    global _font, _pixel_sizes, _pixel_fonts, _last_path
    unload()
    _last_path = path
    if sizes:
        _pixel_sizes = sorted(int(s) for s in sizes)
        for s in _pixel_sizes:
            f = _load_size(path, s)
            if f is not None:
                _pixel_fonts[s] = f
    else:
        _font = _load_font_at(path, 64, pixel=False)


def _load_size(path: str, size: int) -> rl.Font | None:
    return _load_font_at(path, size, pixel=True)


def unload():
    global _font, _pixel_sizes, _pixel_fonts
    if _font and _font.baseSize > 0:
        rl.unload_font(_font)
    for f in _pixel_fonts.values():
        rl.unload_font(f)
    _font = None
    _pixel_sizes = None
    _pixel_fonts = {}


def _snap(size) -> int:
    """Nearest crisp size (ties -> smaller); free sizes pass through."""
    if _pixel_sizes:
        s = int(size)
        best = _pixel_sizes[0]
        for c in _pixel_sizes:
            if abs(c - s) < abs(best - s):
                best = c
        return best
    return int(size)


def draw(text, x, y, size, color):
    size = _snap(size)
    if _pixel_sizes is not None:
        path_size = _pixel_sizes
        f = _pixel_fonts.get(size)
        if f is None:
            # the caller tracks the path via load(); reuse the last path
            f = _load_size(_last_path, size)
            if f is None:
                return
            _pixel_fonts[size] = f
        rl.draw_text_ex(f, str(text), rl.Vector2(float(x), float(y)),
                        float(size), 1.0, color)
    elif _font and _font.baseSize > 0:
        rl.draw_text_ex(_font, str(text), rl.Vector2(float(x), float(y)),
                        float(size), 1.0, color)
    else:
        rl.draw_text(str(text), int(x), int(y), int(size), color)


def measure(text, size) -> int:
    size = _snap(size)
    if _pixel_sizes is not None:
        f = _pixel_fonts.get(size)
        if f is None:
            f = _load_size(_last_path, size)
            if f is None:
                return rl.measure_text(str(text), int(size))
            _pixel_fonts[size] = f
        v = rl.measure_text_ex(f, str(text), float(size), 1.0)
        return int(v.x)
    if _font and _font.baseSize > 0:
        v = rl.measure_text_ex(_font, str(text), float(size), 1.0)
        return int(v.x)
    return rl.measure_text(str(text), int(size))


def label(text, cx, y, size, color, bg_alpha: int = 160, pad_x: int = 5, pad_y: int = 3):
    """Draw centred text with a semi-transparent black background."""
    size = _snap(size)
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
