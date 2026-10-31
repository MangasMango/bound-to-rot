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
Slice the open-source desert tileset (Amstrad, CC-BY-SA 3.0) into:

  * floor tile canvases  -> assets/environment/plain_*.png / brush_*.png
  * magic circles        -> assets/portal/portal1_frame_<i>.png
  * path stone (derived) -> assets/environment/path_tiles.png

Prop sprites are NOT sliced anymore: the engine crops them directly from
the master atlas at load (core/iso_engine.py `_PROP_WINDOWS` — that table
is the single source of truth for prop windows/upScale now).

The engine draws floors from the tileset's NATIVE cells: each atlas
diamond is trimmed and pasted un-scaled into a 64×64 tile cell whose
diamond bounding box is (0, 16, 64, 32) — matching core/iso_engine.py.

Run from the project root:  python scripts/slice_environment.py
Deterministic — re-running only overwrites with identical output.
"""
import os
import sys
import hashlib

from PIL import Image

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ATLAS        = os.path.join(PROJECT_ROOT, 'assets', 'environment', 'tileset_desert.png')
OUT_ROOT     = os.path.join(PROJECT_ROOT, 'assets')

# ── canvas geometry (mirror core/iso_engine.py) ─────────────────────
CANVAS       = 256            # entity/prop sprite canvas (world-object art)
TILE_CANVAS  = 64             # floor tile cell = the tileset's native size
DIAMOND_W    = 64             # native 2:1 diamond (atlas tiles are 64x32)
DIAMOND_H    = 32
DIAMOND_X    = 0
DIAMOND_Y    = 16

ALPHA_MIN = 8                # trim threshold
ALPHA_TIP = 120              # 'content' threshold for tight trimming

# ── window specs: (window, upscale, dirs) ───────────────────────────
# Prop windows/upScale moved to core/iso_engine.py `_PROP_WINDOWS` (the
# engine crops props from the atlas at load) — do NOT re-add per-prop
# PNG slicing here.

# Roaming floor tiles: (row y band, column offset)
FLOOR_ROWS = [
    ('plain', 32 * 0, 0),      # flat sand diamonds, y 0..32, tips on k*64
    ('brush', 32 * 1, 0),      # textured sand diamonds, y 32..64, tips on k*64
]

# Magic-circle platform row: 5 circles, pitch 128, content y ~1060..1128
CIRCLE_ROW = (1058, 1129, 128)

DIR_ANGLE = {'E': 0.0, 'NEE': 22.5, 'NE': 45.0, 'NNE': 67.5,
             'N': 90.0, 'NNW': 112.5, 'NW': 135.0, 'NWW': 157.5,
             'W': 180.0, 'SWW': 202.5, 'SW': 225.0, 'SSW': 247.5,
             'S': 270.0, 'SSE': 292.5, 'SE': 315.0, 'SEE': 337.5}


def content_bbox(img, thresh=ALPHA_MIN, clamp=None):
    """Tight opaque bbox (alpha > thresh), optionally clamped to a box."""
    a = img.getchannel('A')

    def _extremes(px_obj, w, h):
        xs, ys, w_all = [], [], px_obj.load()
        bbox = px_obj.getbbox()
        return bbox

    # getbbox on alpha channel is the fastest way
    alpha_bbox = a.point(lambda v: 255 if v > thresh else 0).getbbox()
    if alpha_bbox is None:
        return None
    if clamp:
        cl = (max(alpha_bbox[0], clamp[0]), max(alpha_bbox[1], clamp[1]),
              min(alpha_bbox[2], clamp[2]), min(alpha_bbox[3], clamp[3]))
        if cl[2] <= cl[0] or cl[3] <= cl[1]:
            return None
        alpha_bbox = cl
    return alpha_bbox


def largest_component_bbox(img, thresh=ALPHA_TIP):
    """Bbox of the largest 4-connected opaque region (>60% of window content).
    Falls back to the plain content bbox when the window holds one merged
    cluster or multiple real parts."""
    w, h = img.size
    a = img.getchannel('A').point(lambda v: 255 if v > thresh else 0)
    px = a.load()
    seen = [[False] * w for _ in range(h)]
    best = None   # (n, bbox)
    all_bbox = a.getbbox()
    if all_bbox is None:
        return None
    for yy in range(h):
        for xx in range(w):
            if not px[xx, yy] or seen[yy][xx]:
                continue
            stack = [(xx, yy)]
            seen[yy][xx] = True
            n = 0
            b = [xx, yy, xx, yy]
            while stack:
                x, y = stack.pop()
                n += 1
                if x < b[0]: b[0] = x
                if x > b[2]: b[2] = x
                if y < b[1]: b[1] = y
                if y > b[3]: b[3] = y
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nx, ny = x + dx, y + dy
                    if 0 <= nx < w and 0 <= ny < h and px[nx, ny] and not seen[ny][nx]:
                        seen[ny][nx] = True
                        stack.append((nx, ny))
            if best is None or n > best[0]:
                best = (n, tuple(b))
    aw = (all_bbox[2] - all_bbox[0])
    ah = (all_bbox[3] - all_bbox[1])
    if best[0] < 0.3 * max(1, aw * ah):
        return all_bbox
    return best[1]


def make_prop_canvas(art, upscale):
    """Paste content-centred, upscaled art into a transparent 256x256 canvas."""
    if upscale:
        art = art.resize((art.width * upscale, art.height * upscale), Image.NEAREST)
    if art.width > CANVAS or art.height > CANVAS:
        factor = min(CANVAS / art.width, CANVAS / art.height)
        nw = max(1, int(art.width * factor))
        nh = max(1, int(art.height * factor))
        art = art.resize((nw, nh), Image.NEAREST)
    canvas = Image.new('RGBA', (CANVAS, CANVAS), (0, 0, 0, 0))
    ox = (CANVAS - art.width) // 2
    oy = (CANVAS - art.height) // 2
    canvas.paste(art, (ox, oy))
    return canvas


def _mask_and_extrude(rgba):
    """Numpy RGBA (h, w, 4) -> PIL image on an (h+2, w+2) canvas:
    1. Alpha-masked to the diamond equation — kills the tips of the
       neighbouring diamonds that intrude into the cell corners.
    2. Alpha hardened (this is pixel art: the atlas' semi-transparent AA
       edges never fully overlap on abutting tiles and leave a dotted
       hairline; full opacity + the extruded rim joins seamlessly).
    3. Edge pixels extruded 1 px outward on all sides so abutting tiles
       overlap instead of gapping.
    """
    import numpy as np
    a = np.array(rgba, dtype=np.uint8)
    h, w = a.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w]
    inside = (np.abs(xx + 0.5 - w / 2) / (w / 2)
              + np.abs(yy + 0.5 - h / 2) / (h / 2)) <= 1.04
    a[..., 3] = np.where(inside, a[..., 3], 0)
    a[..., 3] = np.where(a[..., 3] > 0, 255, 0)

    out = np.zeros((h + 2, w + 2, 4), dtype=np.uint8)
    out[1:h + 1, 1:w + 1] = a
    out[0, 1:w + 1]      = a[0]          # top row replicated upward
    out[h + 1, 1:w + 1]  = a[h - 1]      # bottom row replicated downward
    out[:, 0]            = out[:, 1]     # left column replicated outward
    out[:, w + 1]        = out[:, w]     # right column replicated outward
    return Image.fromarray(out, 'RGBA')


def make_floor_canvas(cell):
    """Turn a full 64×32 atlas cell into the engine's 64×64 tile cell.
    Pasted at (-1, 15) so the extruded diamond keeps the canonical
    (0, 16, 64, 32) bounding box."""
    canvas = Image.new('RGBA', (TILE_CANVAS, TILE_CANVAS), (0, 0, 0, 0))
    canvas.paste(_mask_and_extrude(cell), (DIAMOND_X - 1, DIAMOND_Y - 1))
    return canvas


def center_diamond_art(art):
    """Match the 'tiles' full-tile sprite: art's diamond must align to the
    canonical diamond box (32, 80, 192, 96).  Scales a 64x32-based piece so
    the tile diamond spans DIAMOND_W x DIAMOND_H and sits under DIAMOND_Y."""
    scale = DIAMOND_W / 64.0
    art = art.resize((round(art.width * scale), round(art.height * scale)), Image.NEAREST)
    canvas = Image.new('RGBA', (CANVAS, CANVAS), (0, 0, 0, 0))
    canvas.paste(art, (DIAMOND_X, DIAMOND_Y))
    return canvas


def main():
    atlas = Image.open(ATLAS).convert('RGBA')
    counters = {'prop': 0, 'floor': 0, 'portal': 0}

    # ── floors ────────────────────────────────────────────────────────
    seen = {}
    for fname, row_y, offset in FLOOR_ROWS:
        slug = []
        for col in range(0, atlas.width // 64):
            x0 = col * 64 + offset
            cell = atlas.crop((x0, row_y, x0 + 64, row_y + 32))
            bbox = content_bbox(cell, ALPHA_TIP)
            if bbox is None:
                continue
            if bbox[2] - bbox[0] < 40 or bbox[3] - bbox[1] < 20:
                continue
            key = hashlib.sha1(
                cell.resize((12, 10), Image.NEAREST).tobytes()).hexdigest()[:12]
            slug.append(key)
            if key in seen:
                continue
            seen[key] = f'{fname}_{len(seen) + 1}.png'
            make_floor_canvas(cell).save(
                os.path.join(PROJECT_ROOT, 'assets', 'environment', seen[key]))
            counters['floor'] += 1
        print(f'floor row {fname}: cells={len(slug)} unique in row')

    # ── props: removed — the engine crops props from the atlas
    #    (core/iso_engine.py `_PROP_WINDOWS`); no per-prop PNGs are baked.

    # ── portal magic circles (256×256 canvases, engine draws square) ───
    cy0, cy1, pitch = CIRCLE_ROW
    band = atlas.crop((0, cy0, atlas.width, cy1))
    idx = 0
    col = 0
    while col < band.width:
        cell = band.crop((max(0, col - 4), 0, col + pitch - 4, band.height))
        bbox = content_bbox(cell, ALPHA_MIN)
        if bbox is not None and (bbox[2] - bbox[0]) > 60:
            idx += 1
            art = cell.crop(bbox)
            canvas = make_prop_canvas(art, 2)
            outdir = os.path.join(OUT_ROOT, 'portal')
            os.makedirs(outdir, exist_ok=True)
            canvas.save(os.path.join(outdir, f'portal1_frame_{idx}.png'))
            counters['portal'] += 1
            col += pitch
        else:
            col += 16

    # ── derived: 'tiles' path stone — plain floor diamond tinted darker ──
    # The engine draws cluster/path sprites at 1.5x the tile canvas, so the
    # path diamond is baked at half tile size INSIDE the 64 cell (still
    # centred) to read as a stone slab on the floor. Same mask+extrude as
    # the floor cells so it blends with the ground.
    plain = Image.open(os.path.join(
        PROJECT_ROOT, 'assets', 'environment', 'plain_1.png'))
    SMALL = DIAMOND_W // 2           # diamond inside cell: 32 px wide
    cx_px = TILE_CANVAS // 2         # 32 — cell centre
    x0 = cx_px - SMALL // 2
    y0 = cx_px - SMALL // 4
    sub = plain.crop((x0, y0, x0 + SMALL, y0 + SMALL // 2))
    tint_rgb = (162, 148, 125)   # packed-earth browner, reads as a worn path
    r, g, b, a = sub.split()
    r = r.point(lambda v: min(255, v * tint_rgb[0] // 128))
    g = g.point(lambda v: min(255, v * tint_rgb[1] // 128))
    b = b.point(lambda v: min(255, v * tint_rgb[2] // 128))
    tinted = Image.new('RGBA', sub.size)
    tinted.paste(Image.merge('RGBA', (r, g, b, a)), (0, 0))

    small = _mask_and_extrude(tinted)   # 34×18 extruded small diamond
    canvas = Image.new('RGBA', (TILE_CANVAS, TILE_CANVAS), (0, 0, 0, 0))
    canvas.paste(small, (x0 - 1, y0 - 1))
    canvas.save(os.path.join(PROJECT_ROOT, 'assets', 'environment',
                             'path_tiles.png'))
    counters['path_tile'] = 1
    print(f'sliced: {counters["floor"]} floors, '
          f'{counters["portal"]} portal frames, path_tile baked')
    return 0


if __name__ == '__main__':
    sys.exit(main())
