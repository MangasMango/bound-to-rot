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

"""Anima liveliness (issue #17): ambient particles, denser decor, decals.

Covers:
  1. AmbientParticles: emission from torch spots, budget caps, advance/cull,
     clear().
  2. Decal planning: deterministic (pure hash), floor-only, skips prop
     cells, cobwebs prefer corner cells.
  3. Procedural decal painting produces opaque pixels inside the splat and
     stays empty on pure floor (no decal art shipped - no AI-generated art).
  4. Decor density + pool: every decor type is croppable from the atlas and
     actually loaded; the density band is 60-80.
"""

import math
import random
import re

import pyray as rl
import pytest

from systems import ambient
import core.iso_engine as iso_engine


# ── ambient particles ──────────────────────────────────────────────────

def test_smoke_emits_from_torch_spots_and_culls():
    system = ambient.AmbientParticles()
    rng = random.Random(1)
    torch_spots = [(5.0, 5.0)]
    # run long enough for several emission phases
    for _ in range(int(ambient.SMOKE_LIFE / 0.033) + 20):
        system.update(0.033, rng, torch_spots, 5.0, 5.0)
    smoke = [p for p in system.particles if p['kind'] == 'smoke']
    assert len(smoke) > 0
    for p in smoke:
        assert 0.0 <= p['life'] <= p['max_life']
        # wisps rise
        assert p['vz'] > 0.0


def test_particle_budget_caps_hold():
    system = ambient.AmbientParticles()
    rng = random.Random(2)
    spots = [(float(i), float(i)) for i in range(24)]
    for _ in range(600):
        system.update(0.033, rng, spots, 12.0, 12.0)
        assert len(system.particles) <= ambient.MAX_SMOKE + ambient.MAX_DUST
    kinds = [p['kind'] for p in system.particles]
    assert kinds.count('smoke') <= ambient.MAX_SMOKE
    assert kinds.count('dust') <= ambient.MAX_DUST


def test_particles_cull_after_lifetime():
    system = ambient.AmbientParticles()
    rng = random.Random(3)
    system._spawn_smoke(1.0, 1.0, rng)
    assert any(p['kind'] == 'smoke' for p in system.particles)
    for _ in range(int(ambient.SMOKE_LIFE / 0.033) + 10):
        system.update(0.033, rng, [], 1.0, 1.0)
    # the spawned wisp expired (dust keeps respawning around the light on
    # purpose - the delve is never static)
    assert all(p['kind'] != 'smoke' for p in system.particles)


def test_clear_empties_pool():
    system = ambient.AmbientParticles()
    system._spawn_smoke(0.0, 0.0, random.Random(4))
    system._spawn_dust(0.0, 0.0, random.Random(4))
    system.clear()
    assert system.particles == []
    assert system.time == 0.0


def test_dust_spawns_around_lit_ground():
    system = ambient.AmbientParticles()
    rng = random.Random(5)
    for _ in range(200):
        system.update(0.05, rng, [], 3.0, 3.0)
    dust = [p for p in system.particles if p['kind'] == 'dust']
    assert dust
    for p in dust:
        # motes stay within the lit-ground radius of their anchor
        assert math.hypot(p['x'] - 3.0, p['y'] - 3.0) \
            <= ambient.DUST_RADIUS + 0.6


# ── decal planning (pure hash - BLUEPRINT rule 39) ─────────────────────

def _open_map(cols=20, rows=20):
    return [[0 for _ in range(rows)] for _ in range(cols)]


def test_decal_plan_is_deterministic():
    iso = iso_engine.IsoRenderer()
    map_a = _open_map()
    iso._any_prop_cells = set()
    iso._plan_decals(map_a)
    plan_a = dict(iso._decal_cells)
    iso._plan_decals(map_a)
    assert dict(iso._decal_cells) == plan_a


def test_decal_plan_only_on_floor_and_open_cells():
    iso = iso_engine.IsoRenderer()
    map_data = _open_map()
    map_data[3][4] = 7          # void tile
    map_data[10][10] = 9        # spawn-marker floor tile
    prop_cell = (5, 5)
    iso._any_prop_cells = {prop_cell}
    iso._plan_decals(map_data)
    for (col, row) in iso._decal_cells:
        assert map_data[col][row] in iso_engine._FLOOR_TIDS
        assert (col, row) != prop_cell


def test_decal_plan_roughly_sparse():
    iso = iso_engine.IsoRenderer()
    iso._any_prop_cells = set()
    iso._plan_decals(_open_map(40, 40))
    share = len(iso._decal_cells) / (40 * 40)
    assert 0.01 <= share <= 0.06   # grime every ~30 tiles, not wallpaper


def test_decal_plan_uses_all_three_kinds():
    iso = iso_engine.IsoRenderer()
    iso._any_prop_cells = set()
    iso._plan_decals(_open_map(60, 60))
    kinds = set()
    for tex_idx, _a in iso._decal_cells.values():
        for name in ('DECAL_BLOOD', 'DECAL_SCORCH', 'DECAL_COBWEB'):
            lo, hi = getattr(iso_engine, name)
            if lo <= tex_idx < hi:
                kinds.add(name)
    assert kinds == {'DECAL_BLOOD', 'DECAL_SCORCH', 'DECAL_COBWEB'}


def test_decor_candidates_cover_the_node_room():
    """The wall-less anima grid must still yield a decor pool (the old
    wall-adjacent scan found zero candidates - issue #17 fix-up)."""
    game_mod = __import__('core.game', fromlist=['decor_candidates'])
    map_data = _open_map(60, 60)   # issues #24/#27: the grid is all open
    node = {'col': 30.0, 'row': 30.0, 'w': 15, 'h': 17}
    cells = game_mod.decor_candidates(map_data, node)
    assert cells, 'wall-less maps must still provide decor candidates'
    # node room area (plus margin) is fully covered
    covered = set(cells)
    for col in range(30 - 8 - 7, 30 + 8 + 8):
        for row in range(30 - 8 - 8, 30 + 8 + 9):
            if (col - 30) ** 2 + (row - 30) ** 2 <= 6.25:
                continue   # Pulse heart landing zone stays clear
            assert (col, row) in covered
    # prop-claimed cells are excluded
    cells2 = game_mod.decor_candidates(map_data, node, {(31, 31)})
    assert (31, 31) not in set(cells2)


# ── procedural decal painting ──────────────────────────────────────────

def test_decal_paint_covers_splat_and_masks_rim():
    for kind in iso_engine._DECAL_KINDS:
        for variant in (0, 1):
            img = iso_engine._decal_image(kind, variant)
            assert img.width == iso_engine._DECAL_SIZE
            opaque = 0
            for pixel_y in range(0, img.height, 4):
                for pixel_x in range(0, img.width, 4):
                    col = rl.get_image_color(img, pixel_x, pixel_y)
                    if col.a > 0:
                        opaque += 1
            assert opaque > 0, f'{kind}_{variant} painted nothing'
            # corners of the canvas are outside the diamond mask
            corner = rl.get_image_color(img, 1, 1)
            assert corner.a == 0, f'{kind}_{variant} spills past the diamond'


# ── decor density + pool ───────────────────────────────────────────────

def test_decor_pool_matches_atlas_and_loader():
    import re
    src = open('core/game.py').read()
    pool_match = re.search(r"_DECOR_TYPES = \[(.*?)\]", src, re.S)
    assert pool_match
    pool = re.findall(r"'([a-z0-9_]+)'", pool_match.group(1))
    assert 'torch' not in pool            # torch rides its own 30% roll
    assert len(pool) >= 12
    for name in pool:
        assert name in iso_engine._PROP_WINDOWS, \
            f'decor {name} has no atlas window'
    loader = re.search(r"def _decor_atlas\(\):\n(.*?)add\(_decor_atlas\)",
                       src, re.S).group(1)
    for name in pool:
        assert f"'{name}'" in loader, f'decor {name} not loaded by _decor_atlas'


def test_decor_density_band_is_10_15():
    src = open('core/game.py').read()
    match = re.search(r"for _ in range\(_rnd\.randint\((\d+), (\d+)\)\)", src)
    assert match
    low, high = int(match.group(1)), int(match.group(2))
    assert (low, high) == (10, 15)
