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

"""Procedural GUI widgets plus the spellbook menu theme.

Menu screens draw an open spellbook (assets/gui/spellbookForFlare.png —
Fantasy Book by yd, CC0) with the LEFT page centred and the right page
hanging offscreen; wooden buttons, gold frame edges and checkboxes are
cut from assets/gui/RPG_GUI_v1.png (RPG GUI Construction Kit v1.0 by
Lamoot, CC-BY 3.0). All kit pieces degrade to the plain drawn widgets
when the textures are missing.

Palette kept from the original UI design guide:

    Main Red #A90D01   Red hover #DA0000
    Main Black #111111 Grey Dark #373737  Grey Light #666666
    Main White #D2D2D2

Widgets own their fill, border, pressed-inset and hover pulse ring.
Callers layer text and any extra accents on top.
"""

import math
import os

import pyray as rl

import config


# ── Palette ───────────────────────────────────────────────────────────
def col(r, g, b, a=255):
    return rl.Color(r, g, b, a)

RED       = col(0xA9, 0x0D, 0x01, 255)   # Main Red
RED_HOT   = col(0xDA, 0x00, 0x00, 255)   # Red hover
BLACK     = col(0x11, 0x11, 0x11, 255)   # Main Black
GREY_DARK = col(0x37, 0x37, 0x37, 255)   # Grey Dark
GREY_LT   = col(0x66, 0x66, 0x66, 255)   # Grey Light
WHITE     = col(0xD2, 0xD2, 0xD2, 255)   # Main White

# Spellbook page palette
INK       = col(0x2B, 0x20, 0x16, 255)   # dark ink on parchment
INK_DIM   = col(0x5A, 0x4A, 0x38, 255)   # faded ink
GOLD      = col(0xB8, 0x8A, 0x2E, 255)   # kit gold accent
DANGER    = col(0x8B, 0x1E, 0x12, 255)   # dark red for danger text
PAGE_BG   = col(0x14, 0x0C, 0x08, 255)   # letterbox behind the book

_PANEL_FILL   = col(0x11, 0x11, 0x11, 205)
_PANEL_BORDER = col(0xD2, 0xD2, 0xD2, 136)
_BTN_FILL     = col(0x11, 0x11, 0x11, 200)
_BTN_FILL_OFF = col(0x00, 0x00, 0x00, 190)
_TRACK_FILL   = col(0x11, 0x11, 0x11, 225)

# ── Kit textures (lazy) ───────────────────────────────────────────────
_GUI_DIR  = os.path.join(config.ASSETS, 'gui')
_TEX      = {}          # name -> Texture2D or None (missing)

_BOOK_FILE = 'spellbookForFlare.png'
_SHEET_FILE = 'RPG_GUI_v1.png'
_PAPER_FILE = 'paper background.png'

# Source rects inside RPG_GUI_v1.png (measured from the sheet)
_PIECES = {
    'wood1':  (12, 125, 287, 58),    # grey-brown plank (default)
    'wood2':  (12, 203, 287, 58),    # darker plank (pressed)
    'wood3':  (12, 281, 287, 58),    # lighter plank (hover)
    'wood4':  (12, 359, 287, 58),    # green-tinged plank
    'sq_wood':   (117, 450, 83, 83),
    'sq_bronze': (38, 487, 47, 47),
    'gold_bar':  (794, 72, 208, 20),
    'gold_bar_thin': (795, 113, 205, 13),
    'edge_h': (893, 190, 73, 15),    # gold double-line, horizontal
    'edge_v': (857, 227, 15, 55),    # gold double-line, vertical
    'ck_off': (147, 16, 30, 27),     # unchecked box (gold)
    'ck_on':  (147, 55, 30, 27),     # checked box (gold tick)
}

# Left page usable content area inside the book image (inside the gold
# ornament border, clear of the spine shadow).
_PAGE_RECT = (220, 80, 675, 845)     # x, y, w, h in book-image pixels
_BOOK_H    = 1080.0


def _tex(name: str):
    """Lazy-load a kit texture once; None when the file is missing."""
    if name not in _TEX:
        path = os.path.join(_GUI_DIR, name)
        try:
            _TEX[name] = rl.load_texture(path) if os.path.exists(path) else None
        except Exception:
            _TEX[name] = None
    return _TEX[name]


def _sheet():
    return _tex(_SHEET_FILE)


def piece(name: str):
    """(texture, src_rect) for a kit piece, or (None, None)."""
    t = _sheet()
    if t is None or t.id == 0:
        return None, None
    x, y, w, h = _PIECES[name]
    return t, rl.Rectangle(float(x), float(y), float(w), float(h))


def _piece_dst(rec, src, corner_px, tint):
    """Nine-slice `src` into `rec` keeping caps of ~corner_px unstretched."""
    x, y, w, h = rec.x, rec.y, rec.width, rec.height
    sx, sy, sw, sh = src.x, src.y, src.width, src.height
    c = min(corner_px, sw / 2, sh / 2, w / 2, h / 2)
    sx2, sy2 = sx + sw - c, sy + sh - c
    dx2, dy2 = x + w - c, y + h - c
    for cx, cy, cw, ch, px, py, pw, ph in [
        (sx,    sy,    c,  c,  x,    y,    c,  c),
        (sx+c,  sy,    sw-2*c, c,  x+c,  y,    w-2*c,  c),
        (sx2,   sy,    c,  c,  dx2,  y,    c,  c),
        (sx,    sy+c,  c,  sh-2*c,  x,    y+c,  c,  h-2*c),
        (sx+c,  sy+c,  sw-2*c, sh-2*c,  x+c,  y+c,  w-2*c,  h-2*c),
        (sx2,   sy+c,  c,  sh-2*c,  dx2,  y+c,  c,  h-2*c),
        (sx,    sy2,   c,  c,  x,    dy2,  c,  c),
        (sx+c,  sy2,   sw-2*c, c,  x+c,  dy2,  w-2*c,  c),
        (sx2,   sy2,   c,  c,  dx2,  dy2,  c,  c),
    ]:
        if pw <= 0 or ph <= 0 or cw <= 0 or ch <= 0:
            continue
        rl.draw_texture_pro(_sheet(),
            rl.Rectangle(float(cx), float(cy), float(cw), float(ch)),
            rl.Rectangle(float(px), float(py), float(pw), float(ph)),
            rl.Vector2(0, 0), 0.0, tint)


# ── Spellbook pages ───────────────────────────────────────────────────
def book_page(cw: int, ch: int, margin: int = 40):
    """Draw the open spellbook centred with breathing room over whatever
    backdrop the caller has drawn. The book keeps its aspect ratio.

    Returns (left_page, right_page) — the usable inner-parchment content
    rects of both pages — or None when the book texture is missing."""
    book = _tex(_BOOK_FILE)
    if book is None or book.id == 0:
        return None
    scale = min((ch - 2 * margin) / _BOOK_H,
                (cw - 2 * margin) / book.width)
    bw = book.width * scale
    bh = book.height * scale
    ox = (cw - bw) / 2
    oy = (ch - bh) / 2
    rl.draw_texture_pro(book,
        rl.Rectangle(0, 0, float(book.width), float(book.height)),
        rl.Rectangle(float(ox), float(oy), float(bw), float(bh)),
        rl.Vector2(0, 0), 0.0, rl.WHITE)
    px, py, pw, ph = _PAGE_RECT
    left  = rl.Rectangle(ox + px * scale, oy + py * scale,
                         pw * scale, ph * scale)
    # right page mirrors the left one around the spine (book centre)
    right = rl.Rectangle(ox + (book.width - px - pw) * scale, oy + py * scale,
                         pw * scale, ph * scale)
    return left, right


def _roundness(corner: float, w: float, h: float) -> float:
    """raylib roundness is a fraction of half the shortest side."""
    return max(0.0, min(1.0, 2.0 * corner / max(1.0, min(w, h))))


def panel(x: int, y: int, w: int, h: int, corner: int = 32):
    """Rounded near-black slab with a soft hairline border — the frame
    background used behind menus and settings sheets."""
    rec = rl.Rectangle(float(x), float(y), float(w), float(h))
    r = _roundness(corner, w, h)
    rl.draw_rectangle_rounded(rec, r, 6, _PANEL_FILL)
    rl.draw_rectangle_rounded_lines_ex(rec, r, 6, 1, _PANEL_BORDER)


def button(r, kind: str = 'grey', state: str = 'default'):
    """Square two-tone button fill/border/press states.

    kind:  'grey' | 'red'
    state: 'default' | 'hover' | 'pressed' | 'disabled'
    """
    rec = rl.Rectangle(float(r.x), float(r.y),
                       float(r.width), float(r.height))

    if state == 'disabled':
        fill, border = _BTN_FILL_OFF, col(0x88, 0x88, 0x88, 102)
    elif kind == 'red':
        fill   = {'default': col(0xA9, 0x0D, 0x01, 235),
                  'hover':   col(0xDA, 0x00, 0x00, 235),
                  'pressed': col(0x70, 0x08, 0x01, 240)}[state]
        border = WHITE if state == 'hover' else col(0xA9, 0x0D, 0x01, 255)
    else:
        fill   = {'default': _BTN_FILL,
                  'hover':   col(0x37, 0x37, 0x37, 225),
                  'pressed': col(0x00, 0x00, 0x00, 235)}[state]
        border = (RED_HOT if state == 'hover'
                  else col(0xD2, 0xD2, 0xD2, 110))

    rl.draw_rectangle_rec(rec, fill)

    if state == 'pressed':
        # pressed-inset: light hairline shifted down/right reads as depth
        rl.draw_rectangle_lines(
            int(rec.x) + 2, int(rec.y) + 2,
            int(rec.width) - 4, int(rec.height) - 4,
            col(0xD2, 0xD2, 0xD2, 70))
    else:
        rl.draw_rectangle_lines_ex(rec, 2, border)

    if state == 'hover':
        # pulsing outer ring (kept from the old hover effect)
        pulse = (math.sin(rl.get_time() * 5.0) + 1.0) / 2.0
        ring = rl.Rectangle(rec.x - 4, rec.y - 4,
                            rec.width + 8, rec.height + 8)
        rl.draw_rectangle_lines_ex(
            ring, 1, col(0xA9, 0x0D, 0x01, int(60 + 110 * pulse)))


def slider_bar(x: int, y: int, w: int, h: int, pct: float):
    """Rounded track with a red fill up to pct (0..1)."""
    pct   = max(0.0, min(1.0, pct))
    round_ = _roundness(h // 2, w, h)          # pill ends
    track = rl.Rectangle(float(x), float(y), float(w), float(h))
    rl.draw_rectangle_rounded(track, round_, 6, _TRACK_FILL)
    rl.draw_rectangle_rounded_lines_ex(track, round_, 6, 1, GREY_DARK)
    if pct > 0.02:
        fw = max(h, int(w * pct))
        fill = rl.Rectangle(float(x), float(y), float(fw), float(h))
        rl.draw_rectangle_rounded(fill, round_, 6, RED)


def slider_knob(cx: int, y: int, h: int):
    """Rounded pill knob centred on x = cx at the bar's vertical range."""
    kh = h + 10
    kw = max(8, int(kh * 0.55))
    rec = rl.Rectangle(float(cx - kw // 2), float(y - 5), float(kw), float(kh))
    rl.draw_rectangle_rounded(rec, 0.5, 8, GREY_LT)
    rl.draw_rectangle_rounded_lines_ex(rec, 0.5, 8, 1, WHITE)


def check(x: int, y: int, size: int, color=None):
    """Two-stroke tick inside a size x size box (box drawn by caller)."""
    c = color or WHITE
    t = max(2, size // 5)
    p1 = rl.Vector2(float(x + int(size * 0.20)), float(y + int(size * 0.54)))
    p2 = rl.Vector2(float(x + int(size * 0.42)), float(y + int(size * 0.76)))
    p3 = rl.Vector2(float(x + int(size * 0.82)), float(y + int(size * 0.24)))
    rl.draw_line_ex(p1, p2, float(t), c)
    rl.draw_line_ex(p2, p3, float(t), c)


# ── Spellbook-page widgets (RPG_GUI_v1 kit pieces) ────────────────────

def wood_button(r, state: str = 'default', danger: bool = False):
    """Wooden plank button nine-sliced from the kit sheet — the plank art
    carries its own painted border, so nothing is stroked on top.

    state: 'default' | 'hover' | 'pressed' | 'disabled'
    danger: burnt-red tint for destructive actions.
    Falls back to the square drawn button when the sheet is missing.
    """
    src_t, src = piece({'hover': 'wood3', 'pressed': 'wood2'}.get(state, 'wood1'))
    if src_t is None:
        button(r, 'red' if danger else 'grey', state)
        return
    if state == 'disabled':
        tint = col(110, 100, 90, 190)
    elif danger:
        tint = col(255, 150, 130, 255)
    elif state == 'pressed':
        tint = col(170, 150, 130, 255)
    else:
        tint = rl.WHITE
    rec = rl.Rectangle(float(r.x), float(r.y), float(r.width), float(r.height))
    _piece_dst(rec, src, corner_px=48, tint=tint)


def paper_panel(x: int, y: int, w: int, h: int, border: bool = True):
    """Parchment card: tiled paper fill with gold double-line edges."""
    paper = _tex(_PAPER_FILE)
    if paper is None or paper.id == 0:
        rl.draw_rectangle_rec(rec_p := rl.Rectangle(float(x), float(y),
                                                    float(w), float(h)),
                              col(0xE8, 0xDC, 0xB8, 255))
    else:
        # manual tile loop (pyray has no DrawTextureTiled binding)
        tw, th = paper.width, paper.height
        ty = y
        while ty < y + h - 0.5:
            tx = x
            dh = min(th, y + h - ty)
            while tx < x + w - 0.5:
                dw = min(tw, x + w - tx)
                rl.draw_texture_pro(paper,
                    rl.Rectangle(0, 0, float(dw), float(dh)),
                    rl.Rectangle(float(tx), float(ty), float(dw), float(dh)),
                    rl.Vector2(0, 0), 0.0, col(0xE6, 0xD8, 0xB2, 255))
                tx += dw
            ty += dh
    if border:
        et, st = piece('edge_h'), piece('edge_v')
        if et[0] is not None and st[0] is not None:
            b = 6   # on-screen edge thickness
            rl.draw_texture_pro(et[0], et[1],
                rl.Rectangle(x + b, y, w - 2 * b, b), rl.Vector2(0, 0), 0.0, rl.WHITE)
            rl.draw_texture_pro(et[0], et[1],
                rl.Rectangle(x + b, y + h - b, w - 2 * b, b), rl.Vector2(0, 0), 0.0, rl.WHITE)
            rl.draw_texture_pro(st[0], st[1],
                rl.Rectangle(x, y + b, b, h - 2 * b), rl.Vector2(0, 0), 0.0, rl.WHITE)
            rl.draw_texture_pro(st[0], st[1],
                rl.Rectangle(x + w - b, y + b, b, h - 2 * b), rl.Vector2(0, 0), 0.0, rl.WHITE)
        else:
            rl.draw_rectangle_lines_ex(rec, 1, col(0x8A, 0x6A, 0x2E, 255))


def kit_check(x: int, y: int, size: int, checked: bool):
    """Kit checkbox sprite scaled into a size x size box; falls back to
    the drawn tick inside a slate box when the sheet is missing."""
    name = 'ck_on' if checked else 'ck_off'
    t, src = piece(name)
    if t is None:
        rl.draw_rectangle(x, y, size, size, _BTN_FILL)
        rl.draw_rectangle_lines_ex(rl.Rectangle(float(x), float(y),
                                                float(size), float(size)),
                                   1, GOLD if checked else GREY_DARK)
        if checked:
            check(x, y, size)
        return
    rl.draw_texture_pro(t, src,
        rl.Rectangle(float(x), float(y), float(size), float(size)),
        rl.Vector2(0, 0), 0.0, rl.WHITE)


def kit_slider(x: int, y: int, w: int, h: int, pct: float):
    """Kit-styled slider: bronze track, gold fill, bronze-square knob.
    Falls back to slider_bar/slider_knob without the sheet."""
    pct = max(0.0, min(1.0, pct))
    bt, bs = piece('gold_bar_thin')
    kt, ks = piece('sq_bronze')
    if bt is None or kt is None:
        slider_bar(x, y, w, h, pct)
        slider_knob(x + int(w * pct), y, h)
        return
    # track: thin gold bar stretched, vertically centred in the strip
    th = max(6, h // 2)
    rl.draw_texture_pro(bt, bs,
        rl.Rectangle(float(x), float(y + (h - th) / 2), float(w), float(th)),
        rl.Vector2(0, 0), 0.0, col(110, 95, 70, 255))
    if pct > 0.02:
        fw = max(th, int(w * pct))
        rl.draw_texture_pro(bt, bs,
            rl.Rectangle(float(x), float(y + (h - th) / 2), float(fw), float(th)),
            rl.Vector2(0, 0), 0.0, rl.WHITE)
    # knob: bronze square
    kh = h + 8
    rl.draw_texture_pro(kt, ks,
        rl.Rectangle(float(x + int(w * pct) - kh / 2), float(y + h / 2 - kh / 2),
                     float(kh), float(kh)),
        rl.Vector2(0, 0), 0.0, rl.WHITE)
