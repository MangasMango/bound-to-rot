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
Isometric renderer — replaces engine.py for the iso rewrite.
Tile cell: 64×64. Native desert tileset diamond: 64×32, bounding box at
(0, 16) — engine projection matches the tileset's own 2:1 camera and the
tiles render at (or near) native pixel size, no pre-scaled bake.
  step_x = DIAMOND_W * scale / 2 = 32 * scale
  step_y = DIAMOND_H * scale / 2 = 16 * scale
ISO_W = 64 drives tile draw size; the diamond constants drive projection.
"""

from config import ASSETS

import os, math
import pyray as rl

_ASSETS = ASSETS

# ── Projection constants ──────────────────────────────────────────────
TILE_SRC      = 64         # source PNG canvas size (64×64 cell)

ISO_W         = 64         # tile draw size at 1x scale (= TILE_SRC)
# Diamond geometry inside the 64×64 PNG — bounding box origin (DIAMOND_X, DIAMOND_Y),
# size DIAMOND_W × DIAMOND_H. Heart of the cell lands at (32, 32) = PNG centre.
# Desert tileset (Amstrad, CC-BY-SA 3.0) floors are sliced by
# scripts/slice_environment.py to this native cell format.
DIAMOND_X     = 0          # left edge of diamond bounding box
DIAMOND_Y     = 16         # top edge of diamond bounding box
DIAMOND_W     = 64         # diamond width  (step_x = DIAMOND_W/2 per tile)
DIAMOND_H     = 32         # diamond height (step_y = DIAMOND_H/2 per tile)
DEFAULT_SCALE = 2.0        # 128px drawn tile (2× native); 32/16 px steps
MIN_SCALE     = 1.0        # native 1:1 pixel art
MAX_SCALE     = 3.0
FLOOR_PAD     = 1        # px overlap between adjacent floor tiles

# World-entity sprite canvas: characters, props, portals and effect quads
# are authored on 256×256 canvases and keep their on-screen size tied to
# ENTITY_BASE * scale — INDEPENDENT of the tile scale, so shrinking the
# tiles (more of the scene in view) does not shrink the actors with them.
ENTITY_BASE   = 256

# ── 16 compass directions ─────────────────────────────────────────────
DIRS = ['E','NEE','NE','NNE','N','NNW','NW','NWW',
        'W','SWW','SW','SSW','S','SSE','SE','SEE']

DIR_ANGLE = {
    'E':0.0, 'NEE':22.5, 'NE':45.0, 'NNE':67.5,
    'N':90.0,'NNW':112.5,'NW':135.0,'NWW':157.5,
    'W':180.0,'SWW':202.5,'SW':225.0,'SSW':247.5,
    'S':270.0,'SSE':292.5,'SE':315.0,'SEE':337.5,
}

# Map movement vector → nearest 8 iso screen directions
MOVE_DIR = {
    ( 1, 0):'SE', (-1, 0):'NW',
    ( 0,-1):'NE', ( 0, 1):'SW',
    ( 1,-1):'E',  (-1,-1):'N',
    ( 1, 1):'S',  (-1, 1):'W',
}

def angle_to_dir(angle_deg: float) -> str:
    """Nearest 16-direction name from an angle (0=East, CCW positive)."""
    a = angle_deg % 360
    idx = int((a + 11.25) / 22.5) % 16
    return DIRS[idx]

# ── Colours ───────────────────────────────────────────────────────────
def _rgba(r, g, b, a=255): return rl.Color(r, g, b, a)
FLOOR_COL  = _rgba(55,  60,  55,  255)
PUDDLE_COL = _rgba(24,  30,  40,  235)   # baked puddle base under the reflection shader
HOVER_GOLD = _rgba(230, 190, 90,  220)   # code-drawn hovered-tile outline
TARGET_RED = _rgba(230,  60,  60,  220)  # code-drawn attack-target ring

TILE_COL = {
    6:   _rgba(155, 115, 75,  255),   # cabinet
    9:   _rgba(35,  85,  35,  255),   # spawn marker (floor)
    247: _rgba(255, 225, 75,  255),   # ceiling light
    248: _rgba(75,  215, 115, 255),   # exit
}

# Wall tiles (1/2/3) are stripped to floor in generate_props — walls no
# longer exist at runtime, so there is no wall sprite table.

_FLOOR_TIDS = frozenset({0, 9})


def is_walkable(map_data, col: int, row: int) -> bool:
    """Return True if the tile is floor (walkable)."""
    if not map_data:
        return True
    if not (0 <= col < len(map_data) and 0 <= row < len(map_data[0])):
        return False
    return map_data[col][row] == 0

# ── Pre-allocated draw objects ────────────────────────────────────────
# Raylib receives Rectangle/Vector2 BY VALUE (ctypes copies the struct),
# so mutating these between calls is safe in single-threaded Python.
_FULL_SRC    = rl.Rectangle(0.0, 0.0, float(TILE_SRC), float(TILE_SRC))
_SRC_TEX     = rl.Rectangle(0.0, 0.0, 256.0, 256.0)   # per-texture full rect
_ZERO_VEC    = rl.Vector2(0.0, 0.0)
_MUTABLE_DST = rl.Rectangle(0.0, 0.0, 0.0, 0.0)
_MUTABLE_PAD = rl.Rectangle(0.0, 0.0, 0.0, 0.0)
_V0 = rl.Vector2(0.0, 0.0)
_V1 = rl.Vector2(0.0, 0.0)
_V2 = rl.Vector2(0.0, 0.0)
_V3 = rl.Vector2(0.0, 0.0)


def _tex_src(tex):
    """Mutable source rect sized to a texture — entity/prop canvases are
    256×256 while floor tiles are 64×64, so draws must not assume TILE_SRC."""
    _SRC_TEX.x = 0.0
    _SRC_TEX.y = 0.0
    _SRC_TEX.width = float(max(1, tex.width))
    _SRC_TEX.height = float(max(1, tex.height))
    return _SRC_TEX

# ── Sprite ────────────────────────────────────────────────────────────

class IsoSprite:
    """16-direction animation loaded from individual frame PNGs."""

    def __init__(self, base: str, name: str, n_frames: int, fps: float = 8.0):
        self._base     = base
        self._name     = name
        self._frame_count        = n_frames
        self._fps      = fps
        self._textures: dict = {}   # dir → [Texture2D]
        self._placeholder = False  # frames are a shared asset_guard texture

    def load(self, dirs=None):
        for direction in (dirs or DIRS):
            angle  = DIR_ANGLE[direction]
            frames = []
            for frame_idx in range(self._frame_count):
                fname = f"{self._name}_{direction}_{angle}_{frame_idx}.png"
                path  = os.path.join(self._base, direction, fname)
                if os.path.exists(path):
                    frames.append(rl.load_texture(path))
            self._textures[direction] = frames
        if frames and 'desert' in (self._base or ''):
            # desert prop canvases are pixel art (nearest-baked) — crisp
            for tex in frames:
                rl.set_texture_filter(tex, rl.TEXTURE_FILTER_POINT)
        if not any(self._textures.values()):
            # Pack missing (non-distributed assets): one shared placeholder
            # silhouette per direction so the entity stays visible.
            from systems import asset_guard
            ph = asset_guard.entity_placeholder(self._name)
            if ph is not None:
                self._placeholder = True
                for direction in (dirs or DIRS):
                    self._textures[direction] = [ph]

    def unload(self):
        if self._placeholder:
            self._textures.clear()   # shared cache owns the texture
            return
        for frames in self._textures.values():
            for t in frames:
                if t.id > 0:
                    rl.unload_texture(t)
        self._textures.clear()

    def get(self, direction: str, t: float):
        frames = self._textures.get(direction) or self._textures.get('E', [])
        if not frames:
            return None
        idx = int(t * self._fps) % len(frames)
        return frames[idx]

    def get_idle(self, direction: str):
        frames = self._textures.get(direction)
        return frames[0] if frames else None

    def get_last(self, direction: str):
        frames = self._textures.get(direction) or next(iter(self._textures.values()), [])
        return frames[-1] if frames else None


# ── Renderer ──────────────────────────────────────────────────────────

class IsoRenderer:

    PROP_TILE_SCALE = 1.5  # tile prop size relative to tile size
    # per-prop multiplier on top of PROP_TILE_SCALE — oversized art shrink
    _PROP_EXTRA_SCALE = {'cactus1': 0.6, 'cactus2': 0.6}

    # Extra pixel offset as a fraction of tile size (x, y). Negative y = up.
    PROP_TILE_OFFSET = (0.0, 0.0)

    def __init__(self):
        self.scale  = DEFAULT_SCALE
        self._cam_x = 0.0    # camera offset in pixel space
        self._cam_y = 0.0
        self._floor_tex    = None   # ground tile Texture2D
        self._variation_textures = []     # ground variation textures
        self._prop_sprites = {} # static prop IsoSprites keyed by name
        # Precomputed per-level prop placements (populated by generate_props)
        self._tile_cells       = set()   # (col, row)
        self._floor_prop_cells = {}      # (col, row) -> (name, direction)
        self._path_cells       = set()   # (col, row) — hub floor paths, draw tiles sprite full-size
        self._any_prop_cells   = set()   # union of above three — fast guard in draw_map pass 1
        self._puddle_cells     = frozenset()  # (col, row) — wet floor tiles (render-only)
        self._puddle_bounds    = None    # (col0, row0, col1, row1) over all puddles, or None
        self._minimap_render_tex           = None    # cached minimap render texture
        self._minimap_cached_col       = -9999  # player tile pos when cache was built
        self._minimap_cached_row       = -9999

    # ── Init / cleanup ────────────────────────────────────────────────

    def load(self):
        def _load_tex(rel):
            p = os.path.join(_ASSETS, rel)
            tex = rl.load_texture(p) if os.path.exists(p) else None
            if tex is not None:
                # desert floors/props are pixel art — point filtering keeps
                # them crisp; the default bilinear filter smears edge halos
                # that read as a border between tiles
                rl.set_texture_filter(tex, rl.TEXTURE_FILTER_POINT)
            return tex
        # Desert tileset floors (plain_1..16, brush_17..32) sliced by
        # scripts/slice_environment.py — native 64×64 cells; plain_1 is the
        # base ground, the other 31 are the hash-picked variation pool.
        self._floor_tex = _load_tex('environment/plain_1.png')
        self._variation_textures = [
            t for t in ([_load_tex(f'environment/plain_{n}.png')
                         for n in range(2, 17)]
                        + [_load_tex(f'environment/brush_{n}.png')
                           for n in range(17, 33)]) if t is not None
        ]
        prop_dir = os.path.join(_ASSETS, 'prop', 'desert')
        for name in ('rocks', 'mushrooms', 'tiles',
                     'bush1', 'bush_purple', 'reed1', 'reed2',
                     'grass1', 'grass2', 'grass3',
                     'stone_s1', 'stone_s2', 'stone_s3', 'stone_s4',
                     'cactus1', 'cactus2'):
            sprite = IsoSprite(os.path.join(prop_dir, name), name, 1, 1.0)
            sprite.load(['SE', 'SW'])
            self._prop_sprites[name] = sprite

    def unload(self):
        for t in [self._floor_tex] + self._variation_textures:
            if t and t.id > 0:
                rl.unload_texture(t)
        for sprite in self._prop_sprites.values():
            sprite.unload()
        if self._minimap_render_tex is not None:
            rl.unload_render_texture(self._minimap_render_tex)
            self._minimap_render_tex = None

    # ── Prop precomputation ───────────────────────────────────────────

    def generate_props(self, map_data: list):
        """Call once after each level load to build deterministic prop placement."""
        import collections
        cols = len(map_data)
        rows = len(map_data[0]) if map_data else 0

        # Walls are removed from the game entirely — flatten every wall tile
        # (1/2/3) to open floor so collision, minimap, spawning and the
        # renderer all see a wall-free battlefield. Runs on every level
        # load and segment carve, since delve generation keeps placing
        # wall tiles.
        for col in range(cols):
            map_row = map_data[col]
            for row in range(rows):
                if map_row[row] in (1, 2, 3):
                    map_row[row] = 0

        self._tile_cells.clear()
        self._floor_prop_cells.clear()
        self._puddle_cells = frozenset()
        self._puddle_bounds = None

        # ── Tile clusters ─────────────────────────────────────────────
        # Gather seeds (~3% of floor cells), process lowest-hash first so
        # nearby seeds resolve deterministically.
        seeds = []
        for col in range(cols):
            for row in range(rows):
                if map_data[col][row] not in (0, 9):
                    continue
                if self._prop_hash(col, row) < 0x07AE147B:
                    seeds.append((col, row))
        seeds.sort(key=lambda c: self._prop_hash(c[0], c[1]))

        claimed = set()

        for sc, sr in seeds:
            if (sc, sr) in claimed:
                continue

            # BFS: 70 % of reachable neighbours join the cluster
            cluster = [(sc, sr)]
            frontier = collections.deque([(sc, sr)])
            g_vis = {(sc, sr)}

            while frontier and len(cluster) < 8:
                fc, fr = frontier.popleft()
                for dc, dr in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                    nc, nr = fc + dc, fr + dr
                    nb = (nc, nr)
                    if nb in g_vis or nb in claimed:
                        continue
                    if not (0 <= nc < cols and 0 <= nr < rows):
                        continue
                    if map_data[nc][nr] not in (0, 9):
                        continue
                    g_vis.add(nb)
                    if self._prop_hash(nc, nr) < 0xB3333333:   # 70 %
                        cluster.append(nb)
                        frontier.append(nb)

            if len(cluster) < 4:
                continue

            comp = set(cluster)
            self._tile_cells.update(comp)
            claimed.update(comp)

        # ── Rocks, bushes & grasses on remaining unclaimed floor cells ──
        # Weighted scatter across the desert prop pool; hash channels keep
        # the pick deterministic per seed like the old rocks/mushrooms split.
        # Each entry is an exclusive upper bound of a hash band.
        _SCATTER = (
            (0x02A00000, 'rocks'),
            (0x04000000, ('stone_s1', 'stone_s2')),
            (0x05400000, ('grass1', 'grass2', 'grass3')),
            (0x06800000, 'mushrooms'),
            (0x07700000, ('bush1', 'bush_purple')),
            (0x08400000, ('reed1', 'reed2')),
            (0x09000000, ('cactus1', 'cactus2')),
        )
        for col in range(cols):
            for row in range(rows):
                if map_data[col][row] not in (0, 9):
                    continue
                if (col, row) in claimed:
                    continue
                n = self._prop_hash(col, row)
                if n >= 0x09000000:
                    continue
                for hi, names in _SCATTER:
                    if n < hi:
                        break
                self._floor_prop_cells[(col, row)] = (
                    names if isinstance(names, str)
                    else names[(n >> 8) % len(names)],
                    self._PROP_DIRS[(n >> 20) % 2])

        self._rebuild_any_prop_cells()

    def generate_puddles(self, map_data: list, strength: float = 0.0):
        """Deterministic puddle placement for the wet-weather look.

        strength: 0..1 rain intensity — 0 clears puddles. Uses an
        independent hash channel from props so puddles never mutate the
        deterministic rock/mushroom/cluster sets, and only lands on plain
        floor tiles (no props, no paths, no tile clusters). Call after
        generate_props on every level load / segment carve.
        """
        if strength <= 0.001:
            self._puddle_cells = frozenset()
            self._puddle_bounds = None
            return
        cols = len(map_data)
        rows = len(map_data[0]) if map_data else 0
        cells = []
        # `strength` is the per-cell puddle fraction (0.0..1.0); safety-clamped
        # so a bad uniform can never flood the whole map.
        frac = min(strength, 0.05)
        thresh = int(0xFFFFFFFF - int(0xFFFFFFFF * frac))
        blocked = self._any_prop_cells
        for col in range(cols):
            for row in range(rows):
                if map_data[col][row] != 0:
                    continue
                if (col, row) in blocked:
                    continue   # never under rocks/mushrooms/tile clusters/paths
                n = self._prop_hash(col, row)
                if n >= thresh:
                    cells.append((col, row))
        self._puddle_cells = frozenset(cells)
        if cells:
            cs = [c for c, _r in cells]
            rs = [r for _c, r in cells]
            self._puddle_bounds = (min(cs), min(rs), max(cs), max(rs))
        else:
            self._puddle_bounds = None

    def puddles_on_screen(self, map_data: list, sw: int, sh: int) -> bool:
        """Cheap cull: any puddle tile inside the current camera window?"""
        if not self._puddle_cells or self._puddle_bounds is None or not map_data:
            return False
        cols = len(map_data)
        rows = len(map_data[0]) if map_data else 0
        step_x, step_y = self._steps()
        half     = int(ISO_W * self.scale) / 2
        cam_col_diff = (self._cam_x - half) / step_x
        cam_col_sum  = (self._cam_y - half) / step_y
        centre_col   = (cam_col_diff + cam_col_sum) / 2
        centre_row   = (cam_col_sum  - cam_col_diff) / 2
        margin       = int(sw / (2 * step_x)) + int(sh / (2 * step_y)) + 4
        col_min = max(0, int(centre_col - margin))
        col_max = min(cols - 1, int(centre_col + margin) + 1)
        row_min = max(0, int(centre_row - margin))
        row_max = min(rows - 1, int(centre_row + margin) + 1)
        b0, b1, b2, b3 = self._puddle_bounds
        return not (col_max < b0 or col_min > b2 or row_max < b1 or row_min > b3)

    def puddle_cells_in_view(self, map_data: list, sw: int, sh: int):
        """Yield (col, row, sx, sy) for puddle tiles inside the camera window,
        using the same diagonal iteration as draw_map pass 1."""
        if not self._puddle_cells:
            return
        cols = len(map_data)
        rows = len(map_data[0]) if map_data else 0
        step_x, step_y = self._steps()
        tile_size  = int(ISO_W * self.scale)
        half       = tile_size / 2
        cam_col_diff = (self._cam_x - half) / step_x
        cam_col_sum  = (self._cam_y - half) / step_y
        centre_col   = (cam_col_diff + cam_col_sum) / 2
        centre_row   = (cam_col_sum  - cam_col_diff) / 2
        margin       = int(sw / (2 * step_x)) + int(sh / (2 * step_y)) + 4
        col_min = max(0, int(centre_col - margin))
        col_max = min(cols - 1, int(centre_col + margin) + 1)
        row_min = max(0, int(centre_row - margin))
        row_max = min(rows - 1, int(centre_row + margin) + 1)
        sw_half = sw * 0.5
        sh_half = sh * 0.5
        puddle_cells = self._puddle_cells
        for diag in range(col_min + row_min, col_max + row_max + 1):
            for col in range(max(col_min, diag - row_max),
                             min(col_max, diag - row_min) + 1):
                row = diag - col
                if (col, row) not in puddle_cells:
                    continue
                sx = (col - row) * step_x - self._cam_x + sw_half
                sy = (col + row) * step_y - self._cam_y + sh_half
                if sx + tile_size < 0 or sx > sw or sy + tile_size < 0 or sy > sh + tile_size:
                    continue
                yield col, row, math.floor(sx), math.floor(sy)

    def _steps(self):
        """Return (step_x, step_y): screen pixels per world tile in each iso axis."""
        return (DIAMOND_W * self.scale / 2, DIAMOND_H * self.scale / 2)

    def world_to_screen(self, col: float, row: float, sw: int, sh: int):
        step_x, step_y = self._steps()
        sx = (col - row) * step_x - self._cam_x + sw / 2
        sy = (col + row) * step_y - self._cam_y + sh / 2
        return math.floor(sx), math.floor(sy)

    def screen_to_world(self, sx: int, sy: int, sw: int, sh: int):
        step_x, step_y = self._steps()
        half  = int(ISO_W * self.scale) / 2   # tile_size/2: diamond centre is at PNG centre
        rx    = (sx - sw / 2 + self._cam_x - half) / step_x
        ry    = (sy - sh / 2 + self._cam_y - half) / step_y
        col   = (rx + ry) / 2
        row   = (ry - rx) / 2
        return col, row

    def follow(self, col: float, row: float):
        step_x, step_y = self._steps()
        half = int(ISO_W * self.scale) / 2   # tile_size/2: diamond centre is at PNG centre
        target_x = (col - row) * step_x + half
        target_y = (col + row) * step_y + half
        lerp_speed = 0.12
        self._cam_x += (target_x - self._cam_x) * lerp_speed
        self._cam_y += (target_y - self._cam_y) * lerp_speed

    # ── Map drawing ───────────────────────────────────────────────────

    def draw_map(self, map_data: list, entities: list,
                 sw: int, sh: int, hover_cell=None, overlay_entities=None):
        """
        Draw tiles + entities depth-sorted (painter's algorithm).
        entities: list of dicts with keys col, row, sprite, direction, time,
                  and optionally highlight (bool), dead (bool).
        """
        cols = len(map_data)
        rows = len(map_data[0]) if map_data else 0
        tile_size      = int(ISO_W * self.scale)
        step_x, step_y = self._steps()
        tile_size_f    = float(tile_size)

        # Bucket entities by iso depth so they interleave with tile diagonals.
        ent_by_diag: dict = {}
        for e in entities:
            key = int(e['col'] + e['row'])
            ent_by_diag.setdefault(key, []).append(e)

        # Derive visible tile range from camera position.
        half         = tile_size / 2
        cam_col_diff = (self._cam_x - half) / step_x
        cam_col_sum  = (self._cam_y - half) / step_y
        centre_col   = (cam_col_diff + cam_col_sum) / 2
        centre_row   = (cam_col_sum  - cam_col_diff) / 2
        margin       = int(sw / (2 * step_x)) + int(sh / (2 * step_y)) + 4

        col_min = max(0, int(centre_col - margin))
        col_max = min(cols - 1, int(centre_col + margin) + 1)
        row_min = max(0, int(centre_row - margin))
        row_max = min(rows - 1, int(centre_row + margin) + 1)

        diag_range = range(col_min + row_min, col_max + row_max + 1)

        def _iter_cols(diag):
            return range(max(col_min, diag - row_max),
                         min(col_max, diag - row_min) + 1)

        var_count  = 0
        if self._variation_textures:
            var_count = len(self._variation_textures)
        has_props      = bool(self._prop_sprites)
        floor_tex      = self._floor_tex if self._floor_tex and self._floor_tex.id > 0 else None
        any_prop_cells = self._any_prop_cells
        puddle_cells   = self._puddle_cells

        # Pre-compute projection constants so inner loops avoid attribute lookups.
        _cam_x   = self._cam_x
        _cam_y   = self._cam_y
        _sw_half = sw * 0.5
        _sh_half = sh * 0.5

        # Local aliases for module globals — local var lookup is ~80ns faster than global.
        _dst    = _MUTABLE_DST
        _padded = _MUTABLE_PAD
        _src    = _FULL_SRC
        _orig   = _ZERO_VEC

        # ── Pass 1: floor for ALL tiles + variation/props for floor tiles only ──
        _dst.width  = tile_size_f
        _dst.height = tile_size_f
        _padded.width  = tile_size_f + FLOOR_PAD * 2
        _padded.height = tile_size_f + FLOOR_PAD * 2
        _floor_tids = _FLOOR_TIDS  # local alias for tight-loop frozenset check
        for diag in diag_range:
            for col in _iter_cols(diag):
                row = diag - col
                sx = (col - row) * step_x - _cam_x + _sw_half
                sy = (col + row) * step_y - _cam_y + _sh_half
                if sx + tile_size < 0 or sx > sw or sy + tile_size < 0 or sy > sh + tile_size:
                    continue
                tid = map_data[col][row]
                _dst.x = float(sx)
                _dst.y = float(sy)
                if floor_tex:
                    _padded.x = _dst.x - FLOOR_PAD
                    _padded.y = _dst.y - FLOOR_PAD
                    rl.draw_texture_pro(floor_tex, _src, _padded, _orig,
                                        0.0, TILE_COL.get(tid) or rl.WHITE)
                else:
                    self._diamond(int(sx), int(sy), tile_size, TILE_COL.get(tid) or FLOOR_COL, pad=FLOOR_PAD)
                if tid not in _floor_tids:
                    continue
                # variation overlay (~35 % of floor tiles, whole hash pool)
                if var_count:
                    var_h = col ^ (row << 16) ^ (col * row)
                    var_h = ((var_h ^ (var_h >> 14)) * 0x9E3779B9) & 0xFFFFFFFF
                    var_h = ((var_h ^ (var_h >> 15)) * 0x85EBCA77) & 0xFFFFFFFF
                    var_h ^= var_h >> 13
                    if var_h < 0x40000000:
                        var_tex = (self._variation_textures
                                   [var_h % var_count])
                        if var_tex and var_tex.id > 0:
                            rl.draw_texture_pro(var_tex, _src, _dst, _orig, 0.0, rl.WHITE)
                # wet-weather puddle base — flat colour disc the reflection
                # shader composites over later
                if puddle_cells and (col, row) in puddle_cells:
                    self._diamond(int(sx), int(sy), tile_size, PUDDLE_COL)
                # floor-level props — guarded by union set; skips ~70 % of tiles immediately
                if has_props and (col, row) in any_prop_cells:
                    self._draw_floor_prop(col, row, int(sx), int(sy), tile_size)
                    _dst.width  = tile_size_f
                    _dst.height = tile_size_f

        # ── Pass 2: hover + entities (depth-sorted) ──────────────────────────
        for diag in diag_range:
            for col in _iter_cols(diag):
                row = diag - col
                sx = int((col - row) * step_x - _cam_x + _sw_half)
                sy = int((col + row) * step_y - _cam_y + _sh_half)
                if sx + tile_size < 0 or sx > sw or sy + tile_size < 0 or sy > sh + tile_size:
                    continue
                if hover_cell and hover_cell == (col, row):
                    self._diamond_outline(int(sx), int(sy), tile_size,
                                          HOVER_GOLD)

            for e in ent_by_diag.get(diag, []):
                ex = int((e['col'] - e['row']) * step_x - _cam_x + _sw_half)
                ey = int((e['col'] + e['row']) * step_y - _cam_y + _sh_half)
                self._draw_entity(e, ex, ey, tile_size)

        for e in (overlay_entities or []):
            ex = int((e['col'] - e['row']) * step_x - _cam_x + _sw_half)
            ey = int((e['col'] + e['row']) * step_y - _cam_y + _sh_half)
            self._draw_entity(e, ex, ey, tile_size)

    def _draw_entity_flipped(self, e: dict, sx: int, sy: int, tile_size: int):
        """Draw an entity mirrored vertically — the planar reflection of the
        sprite inside a puddle surface (mirror line = the caller's scissored
        puddle diamond). Mirrors via a negative-height source rect."""
        direct_tex = e.get('texture')
        tint       = e.get('tint', rl.WHITE)
        base        = ENTITY_BASE * self.scale if e.get('big_art') else tile_size
        entity_size = base * e.get('scale', 1.2)
        half        = tile_size * 0.5
        dst_x = float(sx + half - entity_size * 0.5)
        dst_y = float(sy + half - entity_size * 0.5)

        def _flipped(tex):
            src = rl.Rectangle(0.0, float(tex.height),
                               float(tex.width), -float(tex.height))
            _MUTABLE_DST.x = dst_x
            _MUTABLE_DST.y = dst_y
            _MUTABLE_DST.width  = float(entity_size)
            _MUTABLE_DST.height = float(entity_size)
            rl.draw_texture_pro(tex, src, _MUTABLE_DST, _ZERO_VEC, 0.0, tint)

        if direct_tex and direct_tex.id > 0:
            _flipped(direct_tex)
            return
        sprite: IsoSprite = e.get('sprite')
        if not sprite:
            return
        direction = e.get('direction', 'S')
        anim_time = e.get('time', 0.0)
        tex = sprite.get(direction, anim_time) if not e.get('idle') else sprite.get_idle(direction)
        if not tex or tex.id == 0:
            return
        _flipped(tex)

    # ── Tile primitives ───────────────────────────────────────────────

    def _draw_floor_base(self, sx: int, sy: int, tile_size: int, tint=None):
        if self._floor_tex and self._floor_tex.id > 0:
            _MUTABLE_DST.x = float(sx); _MUTABLE_DST.y = float(sy)
            _MUTABLE_DST.width = float(tile_size); _MUTABLE_DST.height = float(tile_size)
            rl.draw_texture_pro(self._floor_tex, _FULL_SRC, _MUTABLE_DST, _ZERO_VEC,
                                0.0, tint or rl.WHITE)
        else:
            self._diamond(sx, sy, tile_size, tint or FLOOR_COL)

    # ── Prop helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _prop_hash(col: int, row: int) -> int:
        hash_val = (col * 0x45D9F3B) ^ (row * 0x119DE1F3) ^ (col + row * 7)
        hash_val = ((hash_val ^ (hash_val >> 14)) * 0xC2B2AE35) & 0xFFFFFFFF
        hash_val = ((hash_val ^ (hash_val >> 15)) * 0x9E3779B9) & 0xFFFFFFFF
        return (hash_val ^ (hash_val >> 13)) & 0xFFFFFFFF

    _PROP_DIRS = ('SE', 'SW')

    def _rebuild_any_prop_cells(self):
        self._any_prop_cells = (self._tile_cells
                                | set(self._floor_prop_cells.keys())
                                | self._path_cells)

    def clear_props_around(self, col: float, row: float, radius: float):
        """Remove any floor props within `radius` tiles so a spawn point is never trapped."""
        cc, cr = int(col), int(row)
        r2 = radius * radius
        for cell in [c for c in self._floor_prop_cells
                     if (c[0] - cc) ** 2 + (c[1] - cr) ** 2 <= r2]:
            del self._floor_prop_cells[cell]
        self._tile_cells = {c for c in self._tile_cells
                            if (c[0] - cc) ** 2 + (c[1] - cr) ** 2 > r2}
        self._puddle_cells = frozenset(
            c for c in self._puddle_cells
            if (c[0] - cc) ** 2 + (c[1] - cr) ** 2 > r2)
        if not self._puddle_cells:
            self._puddle_bounds = None
        self._rebuild_any_prop_cells()

    def set_path_cells(self, cells):
        """Set (col, row) cells that draw the tiles sprite at full tile size as hub floor paths."""
        self._path_cells = set(cells)
        self._rebuild_any_prop_cells()

    def _draw_floor_prop(self, col: int, row: int, sx: int, sy: int, tile_size: int):
        if (col, row) in self._path_cells:
            sprite = self._prop_sprites.get('tiles')
            if sprite:
                tex = sprite.get_idle('SE')
                if tex and tex.id > 0:
                    _MUTABLE_DST.x = float(sx); _MUTABLE_DST.y = float(sy)
                    _MUTABLE_DST.width = float(tile_size); _MUTABLE_DST.height = float(tile_size)
                    rl.draw_texture_pro(tex, _tex_src(tex), _MUTABLE_DST, _ZERO_VEC, 0.0, rl.WHITE)
            return
        # scatter props are tileset art on 256 canvases — sized against the
        # (small) tile cell, centred on the tile anchor
        prop_size     = tile_size * self.PROP_TILE_SCALE
        center_offset = (tile_size - prop_size) / 2
        prop_x        = center_offset + tile_size * self.PROP_TILE_OFFSET[0]
        prop_y        = center_offset + tile_size * self.PROP_TILE_OFFSET[1]
        _MUTABLE_DST.x = float(sx + prop_x); _MUTABLE_DST.y = float(sy + prop_y)
        _MUTABLE_DST.width = float(prop_size); _MUTABLE_DST.height = float(prop_size)
        if (col, row) in self._tile_cells:
            sprite = self._prop_sprites.get('tiles')
            if sprite:
                tex = sprite.get_idle(self._PROP_DIRS[self._prop_hash(col, row) % 2])
                if tex and tex.id > 0:
                    rl.draw_texture_pro(tex, _tex_src(tex), _MUTABLE_DST, _ZERO_VEC, 0.0, rl.WHITE)
        elif (col, row) in self._floor_prop_cells:
            name, direction = self._floor_prop_cells[(col, row)]
            sprite = self._prop_sprites.get(name)
            if sprite:
                tex = sprite.get_idle(direction)
                if tex and tex.id > 0:
                    # per-prop shrink for oversized art (e.g. cacti)
                    prop_size = tile_size * self.PROP_TILE_SCALE * self._PROP_EXTRA_SCALE.get(name, 1.0)
                    center_offset = (tile_size - prop_size) / 2
                    prop_x = center_offset + tile_size * self.PROP_TILE_OFFSET[0]
                    prop_y = center_offset + tile_size * self.PROP_TILE_OFFSET[1]
                    _MUTABLE_DST.x = float(sx + prop_x); _MUTABLE_DST.y = float(sy + prop_y)
                    _MUTABLE_DST.width = float(prop_size); _MUTABLE_DST.height = float(prop_size)
                    rl.draw_texture_pro(tex, _tex_src(tex), _MUTABLE_DST, _ZERO_VEC, 0.0, rl.WHITE)

    def _diamond(self, sx: int, sy: int, tile_size: int, color, pad: float = 0.0):
        k  = tile_size / TILE_SRC
        cx = sx + (DIAMOND_X + DIAMOND_W // 2) * k
        lx = sx + DIAMOND_X * k              - pad
        rx = sx + (DIAMOND_X + DIAMOND_W) * k + pad
        my = sy + (DIAMOND_Y + DIAMOND_H // 2) * k
        ty = sy + DIAMOND_Y * k              - pad
        by = sy + (DIAMOND_Y + DIAMOND_H) * k + pad
        _V0.x = cx; _V0.y = ty
        _V1.x = rx; _V1.y = my
        _V2.x = cx; _V2.y = by
        _V3.x = lx; _V3.y = my
        rl.draw_triangle(_V0, _V1, _V2, color)
        rl.draw_triangle(_V0, _V2, _V3, color)

    def _diamond_outline(self, sx: int, sy: int, tile_size: int, color,
                         pad: float = 0.0, width: float = 2.0):
        """Code-drawn hovered-tile highlight: the tile diamond stroked
        (replaces the old highlight sprite)."""
        k  = tile_size / TILE_SRC
        cx = sx + (DIAMOND_X + DIAMOND_W // 2) * k
        lx = sx + DIAMOND_X * k              - pad
        rx = sx + (DIAMOND_X + DIAMOND_W) * k + pad
        my = sy + (DIAMOND_Y + DIAMOND_H // 2) * k
        ty = sy + DIAMOND_Y * k              - pad
        by = sy + (DIAMOND_Y + DIAMOND_H) * k + pad
        top    = rl.Vector2(float(cx), float(ty))
        right  = rl.Vector2(float(rx), float(my))
        bottom = rl.Vector2(float(cx), float(by))
        left   = rl.Vector2(float(lx), float(my))
        rl.draw_line_ex(top, right, width, color)
        rl.draw_line_ex(right, bottom, width, color)
        rl.draw_line_ex(bottom, left, width, color)
        rl.draw_line_ex(left, top, width, color)

    def _draw_tex(self, tex, sx: int, sy: int, tile_size: int, tint=None):
        if tex and tex.id > 0:
            _MUTABLE_DST.x = float(sx); _MUTABLE_DST.y = float(sy)
            _MUTABLE_DST.width = float(tile_size); _MUTABLE_DST.height = float(tile_size)
            rl.draw_texture_pro(tex, _tex_src(tex), _MUTABLE_DST, _ZERO_VEC, 0.0,
                                tint or rl.WHITE)

    # ── Entity drawing ────────────────────────────────────────────────

    def _draw_entity(self, e: dict, sx: int, sy: int, tile_size: int):
        direct_tex = e.get('texture')
        # Tileset-sourced art (props, platforms, portals) is sized against
        # the tile cell; legacy character canvases (knight, enemies, npc)
        # flag `big_art` and keep their ENTITY_BASE on-screen size.
        if e.get('big_art'):
            base = ENTITY_BASE * self.scale
        else:
            base = tile_size
        if direct_tex and direct_tex.id > 0:
            entity_size = base * e.get('scale', 1.2)
            half        = tile_size * 0.5
            _MUTABLE_DST.x = float(sx + half - entity_size * 0.5)
            _MUTABLE_DST.y = float(sy + half - entity_size * 0.5)
            _MUTABLE_DST.width = float(entity_size); _MUTABLE_DST.height = float(entity_size)
            src = rl.Rectangle(0.0, 0.0, float(direct_tex.width), float(direct_tex.height))
            rl.draw_texture_pro(direct_tex, src, _MUTABLE_DST, _ZERO_VEC, 0.0, e.get('tint', rl.WHITE))
            return
        # Code-drawn attack-target ring at tile level (feet shadow)
        if e.get('shadow'):
            hl_scale       = e.get('hl_scale', 1.0)
            ring_base      = base * 0.06
            rx = ring_base * hl_scale
            ry = rx * 0.5
            # draw_ellipse_lines is 1px wide — two concentric strokes
            # double the thickness
            cx = int(sx + tile_size * 0.5)
            cy = int(sy + tile_size * 0.5)
            rl.draw_ellipse_lines(cx, cy, rx, ry, TARGET_RED)
            rl.draw_ellipse_lines(cx, cy, rx + 1.5, ry + 1.5, TARGET_RED)

        sprite: IsoSprite = e.get('sprite')
        if not sprite:
            return
        direction = e.get('direction', 'S')
        anim_time = e.get('time', 0.0)
        tex       = sprite.get(direction, anim_time) if not e.get('idle') else sprite.get_idle(direction)
        if not tex or tex.id == 0:
            return
        tint        = e.get('tint', rl.WHITE)
        entity_size = base * e.get('scale', 1.2)
        half        = tile_size * 0.5
        _MUTABLE_DST.x = float(sx + half - entity_size * 0.5)
        _MUTABLE_DST.y = float(sy + half - entity_size * 0.5)
        _MUTABLE_DST.width = float(entity_size); _MUTABLE_DST.height = float(entity_size)
        rl.draw_texture_pro(tex, _tex_src(tex), _MUTABLE_DST, _ZERO_VEC, 0.0, tint)

    # ── Minimap ───────────────────────────────────────────────────────

    def draw_minimap(self, map_data: list, px: float, py: float,
                     entities: list, sw: int, sh: int,
                     mm_size: int = 140, cell: int = 2,
                     mx: int = None, my: int = None):
        cols          = len(map_data)
        rows          = len(map_data[0]) if map_data else 0
        minimap_x     = mx if mx is not None else sw - mm_size - 10
        minimap_y     = my if my is not None else sh - mm_size - 10
        visible_cells = mm_size // cell
        tile_px       = int(px)
        tile_py       = int(py)
        start_c       = max(0, tile_px - visible_cells // 2)
        start_r       = max(0, tile_py - visible_cells // 2)

        # Rebuild tile cache only when the player crosses a tile boundary
        if (self._minimap_render_tex is None or
                tile_px != self._minimap_cached_col or tile_py != self._minimap_cached_row):

            if self._minimap_render_tex is None:
                self._minimap_render_tex = rl.load_render_texture(mm_size, mm_size)

            self._minimap_cached_col = tile_px
            self._minimap_cached_row = tile_py

            floor_color = rl.Color(40,  50,  40,  200)
            exit_color  = rl.Color(80,  220, 120, 255)
            wall_color  = rl.Color(80,  95,  85,  255)

            rl.begin_texture_mode(self._minimap_render_tex)
            rl.clear_background(rl.Color(0, 0, 0, 0))
            cx = mm_size // 2
            cy = mm_size // 2
            radius = cx
            for dc in range(visible_cells):
                for dr in range(visible_cells):
                    c = start_c + dc
                    r = start_r + dr
                    if c >= cols or r >= rows:
                        continue
                    tc = dc * cell + cell // 2
                    tr = dr * cell + cell // 2
                    if (tc - cx) ** 2 + (tr - cy) ** 2 > radius ** 2:
                        continue
                    tid = map_data[c][r]
                    if tid == 0:
                        tile_color = floor_color
                    elif tid == 248:
                        tile_color = exit_color
                    else:
                        tile_color = wall_color
                    rl.draw_rectangle(dc * cell, dr * cell, cell, cell, tile_color)
            rl.end_texture_mode()
            # EndTextureMode rebinds the default framebuffer, not an
            # enclosing render texture — reopen the outer virtual canvas
            # when the game is letterboxing the whole frame.
            outer = getattr(self, '_outer_rt', None)
            if outer is not None:
                rl.begin_texture_mode(outer)

        # Blit cached tile layer — single draw call
        src = rl.Rectangle(0.0, 0.0, float(mm_size), float(-mm_size))  # flip Y
        dst = rl.Rectangle(float(minimap_x), float(minimap_y), float(mm_size), float(mm_size))
        rl.draw_texture_pro(self._minimap_render_tex.texture, src, dst,
                            rl.Vector2(0, 0), 0.0, rl.WHITE)

        mm_cx = minimap_x + mm_size // 2
        mm_cy = minimap_y + mm_size // 2
        mm_r  = mm_size // 2

        # Entity dots (few, always current)
        for e in entities:
            ec = int(e.get('col', 0)) - start_c
            er = int(e.get('row', 0)) - start_r
            if 0 <= ec < visible_cells and 0 <= er < visible_cells:
                ex = minimap_x + ec * cell + cell // 2
                ey = minimap_y + er * cell + cell // 2
                if (ex - mm_cx) ** 2 + (ey - mm_cy) ** 2 > mm_r ** 2:
                    continue
                ecol = e.get('mm_col', rl.Color(200, 60, 60, 255))
                rl.draw_rectangle(minimap_x + ec * cell, minimap_y + er * cell,
                                  cell + 1, cell + 1, ecol)

        # Player dot
        pc = tile_px - start_c
        pr = tile_py - start_r
        px = minimap_x + pc * cell + cell // 2
        py = minimap_y + pr * cell + cell // 2
        if (px - mm_cx) ** 2 + (py - mm_cy) ** 2 <= mm_r ** 2:
            rl.draw_rectangle(minimap_x + pc * cell - 1, minimap_y + pr * cell - 1,
                              cell + 2, cell + 2, rl.Color(0xFF, 0xFF, 0xFF, 255))
