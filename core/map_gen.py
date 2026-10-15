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
Procedural battlefield map generator.
50 x 50 grid: 0 = floor, 1 = wall.

Open ruined-city feel: ruin formations have wide gaps so the player is
never enclosed.  Designed for bullet-heaven ARPG play.
"""

import math
import random

MAP_SIZE    = 50
SPAWN_C     = MAP_SIZE // 2   # 25
SPAWN_R     = MAP_SIZE // 2   # 25
SPAWN_CLEAR = 10              # hard radius around player start — no walls
BORDER      = 3               # perimeter wall thickness


# ── Public API ────────────────────────────────────────────────────────

def generate(seed: int = 0, difficulty: int = 1) -> list[list[int]]:
    """Build one battlefield grid.

    `difficulty` was previously misnamed after the character level, which was
    wrong on two counts: it was never a character level, and it is not read
    anywhere in this function — the layout is driven entirely by `seed`. It is
    kept as a parameter for the day map density is actually wired to run
    difficulty.
    """
    _ = difficulty          # accepted, currently unused
    rng  = random.Random(seed)
    grid = [[0] * MAP_SIZE for _ in range(MAP_SIZE)]

    _place_border(grid)

    # One large landmark formation placed close to centre
    _place_landmark(grid, rng)

    # Regular formations spread across the map
    target   = rng.randint(24, 34)
    placed   = 0
    attempts = 0
    while placed < target and attempts < target * 10:
        attempts += 1
        if _place_formation(grid, rng):
            placed += 1

    # Standalone 2×2 pillars for mid-ground cover
    pillars_left = rng.randint(14, 22)
    for _ in range(pillars_left * 8):
        if pillars_left <= 0:
            break
        if _place_pillar(grid, rng):
            pillars_left -= 1

    return grid


# ── Primitives ────────────────────────────────────────────────────────

def _wall(grid, c: int, r: int):
    """Place a wall cell if within safe bounds and outside spawn clear zone."""
    if (BORDER <= c < MAP_SIZE - BORDER and
            BORDER <= r < MAP_SIZE - BORDER and
            math.hypot(c - SPAWN_C, r - SPAWN_R) > SPAWN_CLEAR):
        grid[c][r] = 1


def _place_border(grid):
    for c in range(MAP_SIZE):
        for r in range(MAP_SIZE):
            if (c < BORDER or c >= MAP_SIZE - BORDER or
                    r < BORDER or r >= MAP_SIZE - BORDER):
                grid[c][r] = 1


def _can_place(grid, cells_abs: list) -> bool:
    """True if none of the cells (plus a 2-tile buffer) overlap existing walls."""
    for c, r in cells_abs:
        for dc in range(-2, 3):
            for dr in range(-2, 3):
                nc, nr = c + dc, r + dr
                if 0 <= nc < MAP_SIZE and 0 <= nr < MAP_SIZE:
                    if grid[nc][nr] == 1:
                        return False
    return True


def _stamp(grid, col: int, row: int, cells_rel: list):
    for dc, dr in cells_rel:
        _wall(grid, col + dc, row + dr)


# ── Landmark ──────────────────────────────────────────────────────────

def _place_landmark(grid, rng: random.Random):
    """One large hollow rectangle placed 14-28 tiles from spawn."""
    w = rng.randint(14, 22)
    h = rng.randint(12, 20)
    cells, _, _ = _hollow_rect(rng, w, h)

    for _ in range(80):
        angle = rng.uniform(0, math.tau)
        dist  = rng.uniform(14, 28)
        col   = int(SPAWN_C + math.cos(angle) * dist) - w // 2
        row   = int(SPAWN_R + math.sin(angle) * dist) - h // 2
        col   = max(BORDER + 2, min(MAP_SIZE - w - BORDER - 2, col))
        row   = max(BORDER + 2, min(MAP_SIZE - h - BORDER - 2, row))

        cells_abs = [(col + dc, row + dr) for dc, dr in cells]
        if _can_place(grid, cells_abs):
            _stamp(grid, col, row, cells)
            return


# ── Formation dispatcher ──────────────────────────────────────────────

def _place_formation(grid, rng: random.Random) -> bool:
    ftype = rng.choices(
        ['hollow_rect', 'l_wall', 'u_wall', 'broken_line', 'pillar_row'],
        weights=[4, 3, 3, 5, 2],
        k=1,
    )[0]

    cells, bw, bh = _make_formation(rng, ftype)

    margin = BORDER + 3
    for _ in range(60):
        col = rng.randint(margin, MAP_SIZE - bw - margin)
        row = rng.randint(margin, MAP_SIZE - bh - margin)

        # Formation centre must be far enough from player spawn
        cx = col + bw // 2
        cr = row + bh // 2
        if math.hypot(cx - SPAWN_C, cr - SPAWN_R) < SPAWN_CLEAR + 4:
            continue

        cells_abs = [(col + dc, row + dr) for dc, dr in cells]
        if _can_place(grid, cells_abs):
            _stamp(grid, col, row, cells)
            return True

    return False


def _place_pillar(grid, rng: random.Random) -> bool:
    margin = BORDER + 4
    for _ in range(40):
        col = rng.randint(margin, MAP_SIZE - margin - 2)
        row = rng.randint(margin, MAP_SIZE - margin - 2)
        if math.hypot(col - SPAWN_C, row - SPAWN_R) < SPAWN_CLEAR:
            continue
        cells_abs = [(col, row), (col+1, row), (col, row+1), (col+1, row+1)]
        if _can_place(grid, cells_abs):
            for c, r in cells_abs:
                _wall(grid, c, r)
            return True
    return False


def _make_formation(rng, ftype):
    if ftype == 'hollow_rect':
        return _hollow_rect(rng)
    elif ftype == 'l_wall':
        return _l_wall(rng)
    elif ftype == 'u_wall':
        return _u_wall(rng)
    elif ftype == 'broken_line':
        return _broken_line(rng)
    else:
        return _pillar_row(rng)


# ── Formation shapes ──────────────────────────────────────────────────

def _hollow_rect(rng, w=None, h=None):
    w = w or rng.randint(9, 18)
    h = h or rng.randint(9, 16)

    cells = set()
    for c in range(w):
        cells.add((c, 0))
        cells.add((c, h - 1))
    for r in range(1, h - 1):
        cells.add((0, r))
        cells.add((w - 1, r))

    # Cut 2-4 gaps of 3-5 tiles on different sides
    sides_used = set()
    for _ in range(rng.randint(2, 4)):
        side = rng.choice(['top', 'bottom', 'left', 'right'])
        sides_used.add(side)
        gw = rng.randint(3, 5)
        if side == 'top' and w > gw + 6:
            s = rng.randint(3, w - gw - 3)
            for c in range(s, s + gw):
                cells.discard((c, 0))
        elif side == 'bottom' and w > gw + 6:
            s = rng.randint(3, w - gw - 3)
            for c in range(s, s + gw):
                cells.discard((c, h - 1))
        elif side == 'left' and h > gw + 6:
            s = rng.randint(3, h - gw - 3)
            for r in range(s, s + gw):
                cells.discard((0, r))
        elif side == 'right' and h > gw + 6:
            s = rng.randint(3, h - gw - 3)
            for r in range(s, s + gw):
                cells.discard((w - 1, r))

    return list(cells), w, h


def _l_wall(rng):
    a = rng.randint(7, 14)
    b = rng.randint(7, 14)
    variant = rng.randint(0, 3)

    cells = set()
    if variant == 0:     # bottom-left corner
        for c in range(a): cells.add((c, 0))
        for r in range(b): cells.add((0, r))
    elif variant == 1:   # bottom-right corner
        for c in range(a): cells.add((c, 0))
        for r in range(b): cells.add((a - 1, r))
    elif variant == 2:   # top-left corner
        for c in range(a): cells.add((c, b - 1))
        for r in range(b): cells.add((0, r))
    else:                # top-right corner
        for c in range(a): cells.add((c, b - 1))
        for r in range(b): cells.add((a - 1, r))

    return list(cells), a, b


def _u_wall(rng):
    w         = rng.randint(9, 16)
    depth     = rng.randint(7, 13)
    open_side = rng.choice(['top', 'bottom', 'left', 'right'])

    cells = set()
    if open_side in ('top', 'bottom'):
        for r in range(depth):
            cells.add((0, r))
            cells.add((w - 1, r))
        closed_r = 0 if open_side == 'bottom' else depth - 1
        for c in range(w):
            cells.add((c, closed_r))
    else:
        for c in range(w):
            cells.add((c, 0))
            cells.add((c, depth - 1))
        closed_c = 0 if open_side == 'right' else w - 1
        for r in range(depth):
            cells.add((closed_c, r))

    return list(cells), w, depth


def _broken_line(rng):
    length    = rng.randint(10, 18)
    thickness = rng.randint(1, 2)
    vertical  = rng.random() < 0.5

    cells = set()
    for i in range(length):
        for t in range(thickness):
            cells.add((i, t) if not vertical else (t, i))

    # Carve 1-3 gaps
    for _ in range(rng.randint(1, 3)):
        gs = rng.randint(2, length - 4)
        gl = rng.randint(2, 4)
        for i in range(gs, min(gs + gl, length)):
            for t in range(thickness):
                cells.discard((i, t) if not vertical else (t, i))

    bw = thickness if vertical else length
    bh = length    if vertical else thickness
    return list(cells), bw, bh


def _pillar_row(rng):
    n       = rng.randint(2, 5)
    spacing = rng.randint(4, 7)
    vertical = rng.random() < 0.5

    cells = set()
    for i in range(n):
        off = i * spacing
        if not vertical:
            cells.update([(off, 0), (off+1, 0), (off, 1), (off+1, 1)])
        else:
            cells.update([(0, off), (1, off), (0, off+1), (1, off+1)])

    bw = (n - 1) * spacing + 2 if not vertical else 2
    bh = 2                      if not vertical else (n - 1) * spacing + 2
    return list(cells), bw, bh
