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
Missing-asset detection and procedural placeholders.

The remaining asset packs are not distributed with this repository (see
THIRD_PARTY_ASSETS.md). The game runs without them: loaders skip missing
files, entities fall back to placeholder silhouettes, and the menus show a
notice explaining what is missing and where to get it.
"""

import os

import pyray as rl

from config import ASSETS

# Folders excluded from the public repository (Lords-of-Pain pack content).
# environment and prop are now open-source: floors live in
# assets/environment/ (desert tileset) and props in assets/prop/desert/.
EXCLUDED_ASSET_DIRS = (
    'boss',
    'enemy',
    'none-playable character',
    'playable character',
    'prop',
)


def missing_asset_folders(root=None):
    """Return the excluded asset folders that have no real content here.

    A folder counts as missing when it is absent, or when its only files are
    README.md placeholders. `root` defaults to the game's assets directory.
    """
    root = root if root is not None else ASSETS
    missing = []
    for name in EXCLUDED_ASSET_DIRS:
        d = os.path.join(root, name)
        if not os.path.isdir(d):
            missing.append(name)
            continue
        try:
            entries = [f for f in os.listdir(d)
                       if f.lower() != 'readme.md' and not f.startswith('.')]
        except OSError:
            entries = []
        if not entries:
            missing.append(name)
    return missing


def missing_notice(names):
    """One-line human-readable explanation for console and on-screen banner."""
    return (f"Missing game assets: {', '.join(names)}. "
            "Affected entities render as placeholders. "
            "See THIRD_PARTY_ASSETS.md and the README in each "
            "assets/<folder>/ for how to obtain them.")


# ── Procedural placeholder textures (require a GL context) ────────────

_cache = {}

# (w, h, fill, outline) — diamond silhouettes tinted per entity kind.
_KIND_STYLE = {
    'player':   (120, 96,  (40, 140, 90, 230),  (140, 255, 180, 255)),
    'enemy':    (112, 88,  (140, 45, 45, 230),  (255, 150, 150, 255)),
    'prop':     (104, 80,  (110, 80, 45, 220),  (200, 160, 100, 255)),
    'npc':      (112, 88,  (50, 80, 150, 225),  (140, 190, 255, 255)),
    'generic':  (104, 80,  (95, 55, 130, 220),  (190, 140, 240, 255)),
}

_KIND_HINTS = (
    (('knight', 'warrior', 'fighter'),        'player'),
    (('skeleton', 'sk_', 'slime', 'sl_', 'zombie'), 'enemy'),
    (('crate', 'barrel', 'column', 'torch', 'brazier', 'bones',
      'rocks', 'mushrooms', 'tiles', 'gold_drop', 'rocks'), 'prop'),
    (('subservient',),                        'npc'),
)


def _kind_for(name):
    lowered = (name or '').lower()
    for hints, kind in _KIND_HINTS:
        for hint in hints:
            if hint in lowered:
                return kind
    return 'generic'


def _make_diamond(w, h, fill, outline):
    """Diamond silhouette image: filled rhombus + bright outline."""
    img = rl.gen_image_color(w, h, rl.BLANK)
    cx, cy = w / 2.0, h / 2.0
    fill_c   = rl.Color(*fill)
    line_c   = rl.Color(*outline)
    half_w, half_h = w / 2.0 - 1, h / 2.0 - 1
    for y in range(h):
        # width of the diamond at this row (linear ramp to the point)
        t = abs(y + 0.5 - cy) / half_h
        row_half = (1.0 - t) * half_w
        if row_half <= 0:
            continue
        x0 = int(cx - row_half)
        x1 = int(cx + row_half)
        edge = y == int(cy - half_h) or y == int(cy + half_h) - 1 or row_half < 2.5
        col = line_c if edge else fill_c
        rl.image_draw_pixel(img, x0, y, col)
        rl.image_draw_pixel(img, x1, y, col)
        for x in range(x0 + 1, x1):
            rl.image_draw_pixel(img, x, y, fill_c)
    tex = rl.load_texture_from_image(img)
    rl.unload_image(img)
    return tex


def _window_ready():
    try:
        return bool(rl.is_window_ready())
    except Exception:
        return False


def entity_placeholder(kind_hint=''):
    """Cached placeholder silhouette for a missing sprite.

    Returns None when no window/GL context exists (headless tests) — callers
    keep their existing empty-frames behaviour in that case.
    """
    if not _window_ready():
        return None
    kind = _kind_for(kind_hint)
    key = 'entity:' + kind
    tex = _cache.get(key)
    if tex is None:
        w, h, fill, outline = _KIND_STYLE[kind]
        tex = _make_diamond(w, h, fill, outline)
        _cache[key] = tex
    return tex


