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

"""Weather rendering - planar puddle reflections.

Render-only: for every visible puddle tile, scissor-clip to that tile's
diamond bounding box and re-draw nearby entity sprites mirrored through
the tile's screen-y centre. True planar reflection per puddle, no second
scene render pass: cost is O(visible puddles × nearby entities) texture
draws, all tightly scissored. Degrades silently when dry or disabled.
"""

import pyray as rl

from core.iso_engine import (ISO_W, ENTITY_BASE, DIAMOND_X, DIAMOND_Y,
                            DIAMOND_W, DIAMOND_H, _V0, _V1, _V2, _V3)

# Reflection sprite look: cool tint, semi-transparent, drawn flipped.
_REFL_TINT     = rl.Color(185, 200, 230, 96)
_REFL_MAX_DIST = 2.6        # tiles between a puddle and a reflected actor


class WeatherRenderMixin:
    def _weather_init(self):
        self.weather          = {'raining': False, 'intensity': 0.0, 'seed': 0}
        self._weather_enabled = True    # console toggle (weather on|off)
        self._weather_ms      = 0.0     # F3 waterfall: reflection pass cost

    def _weather_raining(self) -> bool:
        return self._weather_enabled and self.weather.get('raining', False)

    # ── Planar reflections ────────────────────────────────────────────

    def _render_puddle_reflections(self, cw: int, ch: int, entities: list):
        """Mirror-draw nearby entities into every visible puddle's diamond.

        entities: the same draw_map entity dicts (world col/row + sprite).
        Must be called while the scene RT (or equivalent full-canvas target)
        is bound - draws composite straight onto the world layer.
        """
        if not self._weather_raining():
            return
        iso = self.iso
        if not iso.puddles_on_screen(self.map, cw, ch):
            return

        tile_size  = int(ISO_W * iso.scale)
        step_x, step_y = iso._steps()

        # Radius (screen px) at which an actor can still appear inside a
        # neighbouring puddle; generous - scissor discards the rest.
        radius_sx = _REFL_MAX_DIST * step_x

        # Pre-project actors once (centred on the tile like draw_map does).
        projected = []
        for e in entities:
            ex, ey = iso.world_to_screen(e['col'], e['row'], cw, ch)
            projected.append((ex, ey, e))
        if not projected:
            return

        any_drawn = False
        k = tile_size / 256.0
        # diamond bbox inside the 256px tile PNG (DIAMOND_X/Y/W/H geometry)
        d_x0 = int(DIAMOND_X * k)
        d_y0 = int(DIAMOND_Y * k)
        d_w  = int(DIAMOND_W * k)
        d_h  = int(DIAMOND_H * k)
        for col, row, sx, sy in iso.puddle_cells_in_view(self.map, cw, ch):
            mirror_y  = sy + tile_size * 0.5          # tile centre on screen
            clip_top  = sy + d_y0
            clip_h    = d_h
            p_left    = int(sx + d_x0)
            clip_w    = d_w
            # actors whose screen position can reach this puddle
            near = []
            for ex, ey, e in projected:
                if abs(ex - sx) > radius_sx:
                    continue
                if ey + tile_size < clip_top or ey > clip_top + clip_h + tile_size:
                    continue
                near.append((ex, ey, e))
            if not near:
                continue
            rl.begin_scissor_mode(p_left, clip_top, clip_w, clip_h)
            for ex, ey, e in near:
                # mirror the sprite vertically around the puddle centre
                my = 2 * mirror_y - ey
                e2 = dict(e)
                e2.pop('shadow', None)
                e2['tint'] = _REFL_TINT
                self.iso._draw_entity_flipped(e2, ex, my, tile_size)
            self._draw_puddle_shimmer(sx, sy, tile_size)
            rl.end_scissor_mode()
            any_drawn = True
        return any_drawn

    def _draw_puddle_shimmer(self, sx: int, sy: int, tile_size: int):
        """Diamond ripple rings - reads as water without spilling outside
        the puddle shape (scissor is rectangular, so the ring geometry
        itself must stay inside the diamond)."""
        t = rl.get_time()
        k  = tile_size / 256.0
        cx = sx + 128.0 * k
        cy = sy + 128.0 * k
        ph = (cx * 0.37 + cy * 0.21)          # per-puddle phase from position
        for ring in range(2):
            frac = ((t * 0.5 + ph * 0.1 + ring * 0.5) % 1.0)
            scale = 0.35 + 0.55 * frac
            alpha = int(34 * (1.0 - frac) * (1.0 - frac))
            if alpha <= 2:
                continue
            rx = (DIAMOND_W * 0.5) * k * scale
            ry = (DIAMOND_H * 0.5) * k * scale
            _V0.x, _V0.y = cx,          cy - ry
            _V1.x, _V1.y = cx + rx,     cy
            _V2.x, _V2.y = cx,          cy + ry
            _V3.x, _V3.y = cx - rx,     cy
            col = rl.Color(120, 160, 220, alpha)
            rl.draw_triangle_lines(_V0, _V1, _V2, col)
            rl.draw_triangle_lines(_V0, _V2, _V3, col)
