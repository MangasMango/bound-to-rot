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

import math

import pyray as rl

from core.game import (
    DARKNESS_AMBIENT,
    DELVE_PERSONAL_LIGHT,
    HIT_VFX_DUR,
    HIT_VFX_SCALE,
    HOVER_GLOW_ALPHA,
    MUZZLE_VFX_DUR,
    MUZZLE_VFX_SCALE,
    PULSE_OFFSET_X,
    PULSE_OFFSET_Y,
    _LIGHT_KIND_STRENGTH,
)
from core.iso_engine import ISO_W, ENTITY_BASE
from systems import itemgen
from systems.items import EQUIP_SLOT_LABELS, ITEMS, format_equip_stat
from ui import fonts, icons


def _cmp_sign(col):
    """Comparison-row colours carry the sign: +1 up, -1 down, 0 otherwise
    (same RGB as the inventory tooltip's C_CMP_UP/C_CMP_DOWN)."""
    if (col.r, col.g, col.b) == (80, 220, 90):
        return 1
    if (col.r, col.g, col.b) == (230, 70, 70):
        return -1
    return 0


class DelveRenderMixin:
    def _draw_scene_to_screen(self, cw: int, ch: int):
        flip_src = rl.Rectangle(0.0, float(ch), float(cw), -float(ch))
        no_flip  = rl.Rectangle(0.0, 0.0, float(cw), float(ch))
        rl.draw_texture_pro(self._scene_rt.texture, flip_src, no_flip, rl.Vector2(0.0, 0.0), 0.0, rl.WHITE)
    def _ensure_darkness_rt(self):
        """Render texture for darkness compositing — recreated when the
        window is resized so it always matches the canvas."""
        if (self._darkness_rt is not None and self._darkness_rt.id > 0
                and self._darkness_rt.texture.width == rl.get_screen_width()
                and self._darkness_rt.texture.height == rl.get_screen_height()):
            return
        if self._darkness_rt is not None and self._darkness_rt.id > 0:
            rl.unload_render_texture(self._darkness_rt)
        self._darkness_rt = rl.load_render_texture(rl.get_screen_width(),
                                                   rl.get_screen_height())
        if self._darkness_rt is None or self._darkness_rt.id <= 0:
            print("[darkness] WARNING: render texture creation FAILED")
    def _draw_darkness(self, cw: int, ch: int):
        if self._delve is None:
            return
        d = self._delve
        # The Pulse is the delve's light source: kind 'pulse' — brighter than
        # the hub heart (no deep breathing dip). The radius is the VISIBLE
        # LIGHT EDGE (lighting.fs EDGE_SCALE semantics) and matches the
        # gameplay light check exactly (delve_flow: light_r + personal).
        lights = [{'x': d['pulse_x'], 'y': d['pulse_y'],
                   'r': d['light_r'] + DELVE_PERSONAL_LIGHT,
                   'kind': 'pulse', 'phase': 0.0, 'ax': 0.0, 'ay': 0.0}]
        self._render_darkness(cw, ch, lights, d.get('dark_timer', 0.0))
    def _render_darkness(self, cw: int, ch: int, lights: list, dark_timer: float):
        """Fire-light pass over arbitrary light anchors.

        lights: [{'x', 'y', 'r', 'kind', 'phase'}] in tile coords — the delve
        passes the Pulse, the hub passes torches/braziers/
        the Delve Heart. Outside every light the dark_timer drives the red
        danger pulse. Primary path is the lighting shader (Godot-style log
        falloff + noise churn); the software blob pass is the fallback.
        """
        if self._render_darkness_shader(cw, ch, lights):
            self._draw_dark_danger(cw, ch, lights, dark_timer)
            return
        self._render_darkness_software(cw, ch, lights)
        self._draw_dark_danger(cw, ch, lights, dark_timer)
    def _render_darkness_shader(self, cw: int, ch: int, lights: list) -> bool:
        """Godot-style fire-light pass. Returns False if unavailable (caller
        falls back to the software path).

        The light math is scene-independent, so both passes render into
        half-res render targets and upscale with plain texture blits — the
        expensive shader runs on a quarter of the pixels."""
        sh = self.shaders.get('lighting') if self.shaders else None
        if sh is None or self._light_noise_tex is None or self._light_curve_tex is None:
            return False
        self._ensure_light_rts(cw, ch)
        lm, gl = self._lightmap_rt, self._glow_rt
        lw, lh = lm.texture.width, lm.texture.height
        sx_ratio, sy_ratio = lw / max(1, cw), lh / max(1, ch)
        tile_size = max(1, int(ISO_W * self.iso.scale))
        step_x, step_y = self.iso._steps()
        iso_correction = math.hypot(step_x, step_y) / max(1, tile_size)

        positions = []
        datas = []
        half = tile_size * 0.5   # sprites draw centred at w2s + (tile/2, tile/2)
        for light in lights[:8]:
            sx, sy = self.iso.world_to_screen(light['x'], light['y'], cw, ch)
            f, _tint = self._light_anim(light)
            kind = light.get('kind', '')
            strength = _LIGHT_KIND_STRENGTH.get(kind, 0.50)
            r_px = light['r'] * tile_size * iso_correction * f
            # per-prop flame anchor: pool centres on the visible flame art
            ax = light.get('ax', 0.0) * tile_size
            ay = light.get('ay', 0.0) * tile_size
            cx_s, cy_s = sx + half + ax, sy + half + ay
            # cull lights whose influence (fade tail ~3×r) is fully offscreen
            if (cx_s < -r_px * 3 or cx_s > cw + r_px * 3
                    or cy_s < -r_px * 3 or cy_s > ch + r_px * 3):
                continue
            # gl_FragCoord is y-up; world_to_screen is y-down
            positions.append((float(cx_s * sx_ratio),
                              float((ch - cy_s) * sy_ratio)))
            datas.append((r_px * sx_ratio, f, strength, light.get('phase', 0.0)))
        while len(positions) < 8:
            positions.append((0.0, 0.0))
            datas.append((1.0, 1.0, 0.0, 0.0))

        self.shaders.set_float('lighting', 'u_time', rl.get_time())
        self.shaders.set_float('lighting', 'u_ambient', DARKNESS_AMBIENT / 255.0)
        self.shaders.set_float('lighting', 'u_aspect', step_y / step_x)
        self.shaders.set_float('lighting', 'u_px_scale', 1.0 / sx_ratio)
        self.shaders.set_int('lighting', 'u_light_count', len(positions))
        self.shaders.set_vec2_array('lighting', 'u_light_pos', positions)
        self.shaders.set_vec4_array('lighting', 'u_light_data', datas)
        loc_noise = self.shaders.loc('lighting', 'u_noise')
        loc_curve = self.shaders.loc('lighting', 'u_curve')

        no_dim   = getattr(self, '_light_debug_no_dim', False)
        no_glow  = getattr(self, '_light_debug_no_glow', False)
        dbg_mode = getattr(self, '_light_debug_mode', None)

        def light_pass(rt, clear_color, mode):
            # Sampler state persists in the program, but re-bind per pass:
            # batch flushes and blend-mode changes can unbind the units.
            if loc_noise >= 0 and self._light_noise_tex is not None:
                self.shaders.set_sampler('lighting', 'u_noise',
                                         self._light_noise_tex.id)
            if loc_curve >= 0 and self._light_curve_tex is not None:
                self.shaders.set_sampler('lighting', 'u_curve',
                                         self._light_curve_tex.id)
            self.shaders.set_float('lighting', 'u_mode', mode)
            rl.begin_texture_mode(rt)
            rl.clear_background(clear_color)
            rl.begin_shader_mode(sh)
            rl.draw_rectangle(0, 0, lw, lh, rl.WHITE)
            rl.end_shader_mode()
            rl.end_texture_mode()
            self._rebind_outer_rt()

        # Pass 1 — dim map: unlit world drops to the ambient dim level.
        if not no_dim:
            light_pass(lm, rl.WHITE, 0.0)
        # Pass 2 — warm glow: golden fire colour (debug modes 2/3 replace it).
        if not no_glow:
            light_pass(gl, rl.BLACK, 1.0 if dbg_mode is None else float(dbg_mode))

        # Upscale-blit the maps onto the current target with plain blending —
        # zero custom shader work per screen pixel.
        flip_src = rl.Rectangle(0.0, float(lh), float(lw), -float(lh))
        dst      = rl.Rectangle(0.0, 0.0, float(cw), float(ch))
        origin   = rl.Vector2(0.0, 0.0)
        if not no_dim:
            rl.begin_blend_mode(rl.BLEND_MULTIPLIED)
            rl.draw_texture_pro(lm.texture, flip_src, dst, origin, 0.0, rl.WHITE)
            rl.end_blend_mode()
        if not no_glow:
            rl.begin_blend_mode(rl.BLEND_ADDITIVE)
            rl.draw_texture_pro(gl.texture, flip_src, dst, origin, 0.0, rl.WHITE)
            rl.end_blend_mode()
        return True
    def _render_darkness_software(self, cw: int, ch: int, lights: list):
        """Blob-based fallback (no shader available). Layered falloff,
        flicker and per-kind tints mirror the shader pass."""
        self._ensure_darkness_rt()
        if self._darkness_rt is None or self._darkness_rt.id <= 0:
            return
        self._ensure_light_blob()

        rt  = self._darkness_rt
        rtw = rt.texture.width
        rth = rt.texture.height

        tile_size      = max(1, int(ISO_W * self.iso.scale))
        tile_half_x    = tile_size * 0.5
        tile_half_y    = tile_size * 0.5
        step_x, step_y = self.iso._steps()
        iso_per_tile   = math.hypot(step_x, step_y)
        iso_correction = iso_per_tile / max(1, tile_size)
        sx_ratio = rtw / max(1, cw)
        sy_ratio = rth / max(1, ch)

        blob = self._light_blob_tex

        def draw_blob(center_x, center_y, radius_px, tint):
            step_x, step_y = self.iso._steps()
            rx = radius_px
            ry = int(radius_px * step_y / step_x)
            src = rl.Rectangle(0.0, 0.0, 256.0, 256.0)
            dst = rl.Rectangle(float(center_x - rx), float(center_y - ry),
                                float(rx * 2), float(ry * 2))
            rl.draw_texture_pro(blob, src, dst, rl.Vector2(0.0, 0.0), 0.0, tint)

        def light_px(lx, ly):
            sx, sy = self.iso.world_to_screen(lx, ly, cw, ch)
            return (int((sx + tile_half_x) * sx_ratio) + PULSE_OFFSET_X,
                    int((sy + tile_half_y) * sy_ratio) + PULSE_OFFSET_Y)

        rl.begin_texture_mode(rt)
        rl.clear_background(rl.Color(DARKNESS_AMBIENT, DARKNESS_AMBIENT, DARKNESS_AMBIENT, 255))
        rl.begin_blend_mode(rl.BLEND_ADDITIVE)
        for light in lights:
            f, (tr, tg, tb) = self._light_anim(light)
            lx_rt, ly_rt = light_px(light['x'], light['y'])
            r_px = light['r'] * tile_size * sx_ratio * iso_correction
            # Layered falloff: faint wide halo + bright core = smooth gradient
            # instead of a hard spotlight circle.
            draw_blob(lx_rt, ly_rt, int(r_px * 1.0 * f), rl.Color(tr, tg, tb, 70))
            draw_blob(lx_rt, ly_rt, int(r_px * 0.8 * f),  rl.Color(tr, tg, tb, 185))
        rl.end_blend_mode()
        rl.end_texture_mode()
        self._rebind_outer_rt()

        src = rl.Rectangle(0.0, float(rth), float(rtw), -float(rth))
        dst = rl.Rectangle(0.0, 0.0, float(cw), float(ch))
        rl.begin_blend_mode(rl.BLEND_MULTIPLIED)
        rl.draw_texture_pro(rt.texture, src, dst, rl.Vector2(0.0, 0.0), 0.0, rl.WHITE)
        rl.end_blend_mode()
    def _draw_pulse_sprite(self, cw: int, ch: int):
        """Re-draw pulse sprite on top of the darkness overlay so it stays bright."""
        if self._delve is None or self._pulse_tex is None or self._pulse_tex.id <= 0:
            return
        d = self._delve
        sx, sy = self.iso.world_to_screen(d['pulse_x'], d['pulse_y'], cw, ch)
        tile_size = max(1, int(ISO_W * self.iso.scale))
        half = tile_size * 0.5

        # Attract pulse animation when ready; always-on hub-heart breathing
        # (1.0 + 0.06·sin, 2.2 Hz) so the pulse reads as the same heart art
        # as the hub's Delve Heart (hub_render.py:29-35).
        # The pulse is the interactive light anchor, not floor art: it keeps
        # the ENTITY canvas scale so its click target stays readable.
        tint = rl.WHITE
        breath = 1.0 + 0.06 * math.sin(self.anim_time * 2.2)
        entity_size = int(ENTITY_BASE * self.iso.scale * breath)
        if d.get('state') == 'ready':
            pulse = (math.sin(self.raid_time * 3.0) + 1.0) / 2.0
            entity_size = int(ENTITY_BASE * self.iso.scale * breath * (1.0 + pulse * 0.02))
            glow_alpha = int(8 + 12 * pulse)
            glow_r = entity_size // 4
            step_x, step_y = self.iso._steps()
            glow_ry = int(glow_r * step_y / step_x)
            rl.draw_ellipse(int(sx + half), int(sy + half), float(glow_r), float(glow_ry),
                            rl.Color(255, 210, 80, glow_alpha))
            tint = rl.Color(255, int(220 + 35 * pulse), int(140 + 80 * pulse), 255)

        src = rl.Rectangle(0.0, 0.0, float(self._pulse_tex.width), float(self._pulse_tex.height))
        dst = rl.Rectangle(float(sx + half - entity_size * 0.5),
                           float(sy + half - entity_size * 0.5),
                           float(entity_size), float(entity_size))
        rl.draw_texture_pro(self._pulse_tex, src, dst, rl.Vector2(0.0, 0.0), 0.0, tint)
    def _draw_pulse_label(self, cw: int, ch: int):
        """Draw PULSE label above the pulse sprite in world space."""
        if self._delve is None:
            return
        d = self._delve
        sx, sy = self.iso.world_to_screen(d['pulse_x'], d['pulse_y'], cw, ch)
        ts = max(1, int(ISO_W * self.iso.scale))
        cx = sx + ts // 2

        label = 'PULSE'
        lw = fonts.measure(label, 14)
        # pulse art keeps the ENTITY canvas scale — hug its visible top
        fonts.draw(label, cx - lw // 2, sy + ts // 2 - int(ENTITY_BASE * self.iso.scale * 0.3), 14,
                   rl.Color(255, 210, 80, 200))
    def _draw_delve_junction(self, cw: int, ch: int):
        """Forward-path choice, hosted inside the Anima panel frame."""
        d = self._delve
        kids = self._delve_children()
        import core.delve_gen as _dg
        from ui.delve_chart import _reward_icon

        content, x_clicked = self._draw_anima_panel(cw, ch)
        if x_clicked:
            d['state'] = 'ready'
            return

        title = 'Choose your path'
        tw = fonts.measure(title, 22)
        fonts.draw(title, int(content.x + content.width // 2 - tw // 2),
                   int(content.y + 10), 22, rl.Color(230, 220, 190, 255))

        rects = []
        row_h, gap = 96, 14
        row_w = content.width - 60
        bx = content.x + 30
        base_y = content.y + 48
        mx, my = rl.get_mouse_x(), rl.get_mouse_y()

        for i, kid in enumerate(kids):
            by = base_y + i * (row_h + gap)
            rect = rl.Rectangle(bx, by, row_w, row_h)
            col = _dg.NODE_COLORS.get(kid['type'], (200, 200, 200))
            side = 'LEFT' if kid['col'] < 0.4 else ('RIGHT' if kid['col'] > 0.6 else 'STRAIGHT')
            hovered = rl.check_collision_point_rec(rl.Vector2(float(mx), float(my)), rect)

            rl.draw_rectangle(int(bx), int(by), int(row_w), row_h,
                              rl.Color(10, 12, 20, 225))
            rl.draw_rectangle_lines(int(bx), int(by), int(row_w), row_h,
                                    rl.Color(col[0], col[1], col[2],
                                             255 if hovered else 160))

            label = kid.get('loot') or 'Undiscovered'
            fonts.draw(label, int(bx + 14), int(by + 10), 15,
                       rl.Color(col[0], col[1], col[2], 255))
            sub = f"{side}  ·  Depth {kid['depth']}  ·  Lv {kid['enemy_level']}"
            fonts.draw(sub, int(bx + 14), int(by + 34), 13,
                       rl.Color(190, 190, 205, 220))
            rewards = kid.get('rewards') or []
            rtxt = kid['label'] if rewards else 'Undiscovered'
            fonts.draw(rtxt, int(bx + 14), int(by + 58), 12,
                       rl.Color(175, 140, 215, 220))
            if rewards:
                icon = _reward_icon(rewards[0]['item'])
                if icon and icon.id > 0:
                    src = rl.Rectangle(0, 0, float(icon.width), float(icon.height))
                    dst = rl.Rectangle(float(bx + row_w - 34), float(by + 52),
                                       24.0, 24.0)
                    rl.draw_texture_pro(icon, src, dst, rl.Vector2(0, 0), 0.0,
                                        rl.WHITE)
            rects.append((rect, kid))

        d['_junction_rects'] = rects
    def _draw_delve_relics(self, cw: int, ch: int):
        """1-of-3 run-boon choice at checkpoint shrines, in the Anima panel."""
        d = self._delve
        offer = d.get('_relic_offer') or []
        content, x_clicked = self._draw_anima_panel(cw, ch)
        if x_clicked:
            d['state'] = 'ready'
            return

        title = 'The Anima Cart offers a boon'
        tw = fonts.measure(title, 20)
        fonts.draw(title, int(content.x + content.width // 2 - tw // 2),
                   int(content.y + 10), 20, rl.Color(255, 220, 140, 255))

        rects = []
        row_h, gap = 96, 14
        row_w = content.width - 60
        bx = content.x + 30
        base_y = content.y + 44
        mx, my = rl.get_mouse_x(), rl.get_mouse_y()
        for i, boon in enumerate(offer):
            by = base_y + i * (row_h + gap)
            rect = rl.Rectangle(bx, by, row_w, row_h)
            hovered = rl.check_collision_point_rec(rl.Vector2(float(mx), float(my)), rect)
            rl.draw_rectangle(int(bx), int(by), int(row_w), row_h,
                              rl.Color(10, 12, 20, 225))
            rl.draw_rectangle_lines(int(bx), int(by), int(row_w), row_h,
                                    rl.Color(255, 220, 140,
                                             255 if hovered else 150))
            fonts.draw(boon['name'], int(bx + 14), int(by + 10), 16,
                       rl.Color(255, 220, 140, 255))
            for j, line in enumerate(self._wrap_text(boon['desc'], 52)):
                fonts.draw(line, int(bx + 14), int(by + 38 + j * 16), 12,
                           rl.Color(200, 200, 215, 230))
            rects.append((rect, boon))
        d['_relic_rects'] = rects
    def _draw_ground_item_sprite(self, gi: dict, tile_center_x: int,
                                 tile_center_y: int, tile_size: int,
                                 tint=None) -> bool:
        """Draw the visible ground sprite for a drop item. Returns True when
        a sprite was drawn (used by the world layer, the delve darkness
        overlay and the hub so the item is visible at all times)."""
        drop_spr, spr_scale = self._drop_sprite_for(gi)
        if not drop_spr:
            return False
        tex = drop_spr.get('S', self.anim_time)
        if not (tex and tex.id > 0):
            return False
        draw_size = int(tile_size * 0.55 * spr_scale)
        src = rl.Rectangle(0, 0, 256.0, 256.0)
        dst = rl.Rectangle(float(tile_center_x - draw_size // 2),
                           float(tile_center_y - draw_size // 2),
                           float(draw_size), float(draw_size))
        rl.draw_texture_pro(tex, src, dst, rl.Vector2(0, 0), 0.0,
                            tint or rl.WHITE)
        return True
    def _draw_world_objects(self, cw, ch):
        tile_size  = int(ISO_W * self.iso.scale)
        # reset label rects for this frame
        self._drop_label_rects = []

        for gi in self.ground_items:
            sx, sy = self.iso.world_to_screen(gi['x'], gi['y'], cw, ch)
            tile_center_x = sx + tile_size // 2
            tile_center_y = sy + tile_size // 2
            gtype = gi.get('type', '')
            hovered = gi is self._hover_interact

            if gtype == 'portal':
                player_dist = math.hypot(gi['x'] - self.px, gi['y'] - self.py)
                if player_dist > 5.0:
                    continue
                if self._portal_frames:
                    fidx = int(self.anim_time * 8) % len(self._portal_frames)
                    tex  = self._portal_frames[fidx]
                    if tex and tex.id > 0:
                        draw_size = int(tile_size * 0.75)
                        src = rl.Rectangle(0, 0, float(tex.width), float(tex.height))
                        dst = rl.Rectangle(float(tile_center_x - draw_size // 2), float(tile_center_y - draw_size // 2),
                                           float(draw_size), float(draw_size))
                        rl.draw_texture_pro(tex, src, dst, rl.Vector2(0, 0), 0.0, rl.WHITE)
                if hovered:
                    if self._portal_frames:
                        rl.begin_blend_mode(rl.BLEND_ADDITIVE)
                        rl.draw_texture_pro(tex, src, dst, rl.Vector2(0, 0), 0.0,
                                            rl.Color(255, 230, 170, min(255, HOVER_GLOW_ALPHA * 2)))
                        rl.end_blend_mode()
                pulse = 0.6 + 0.4 * math.sin(self.anim_time * 4.0)
                alpha = int(200 * pulse)
                lbl = 'CLICK TO EXTRACT' if player_dist < 1.5 else f'PORTAL  {int(player_dist)}m AWAY'
                fonts.label(lbl, tile_center_x, sy + tile_size // 4 - 28, 26, rl.Color(200, 130, 255, alpha))

            elif gtype == 'crate':
                broken   = gi.get('broken', False)
                breaking = gi.get('breaking', False)
                if broken:
                    tex = self._crate_break_spr.get_last('S') if self._crate_break_spr else None
                elif breaking:
                    tex = self._crate_break_spr.get('S', gi.get('break_timer', 0.0)) if self._crate_break_spr else None
                else:
                    tex = self._crate_spr.get_idle('S') if self._crate_spr else None
                if tex and tex.id > 0:
                    draw_size = int(tile_size * 1.2)
                    src = rl.Rectangle(0, 0, 256.0, 256.0)
                    dst = rl.Rectangle(float(tile_center_x - draw_size // 2), float(tile_center_y - draw_size // 2),
                                       float(draw_size), float(draw_size))
                    rl.draw_texture_pro(tex, src, dst, rl.Vector2(0, 0), 0.0, rl.WHITE)
                if hovered and not breaking and not broken:
                    if tex and tex.id > 0:
                        rl.begin_blend_mode(rl.BLEND_ADDITIVE)
                        rl.draw_texture_pro(tex, src, dst, rl.Vector2(0, 0), 0.0,
                                            rl.Color(255, 230, 170, min(255, HOVER_GLOW_ALPHA * 2)))
                        rl.end_blend_mode()
                    fonts.label('Crate', tile_center_x, sy + tile_size // 4 - 24,
                                23, rl.Color(255, 210, 80, 255))

            elif gtype == 'barrel':
                broken   = gi.get('broken', False)
                breaking = gi.get('breaking', False)
                if broken:
                    tex = self._barrel_break_spr.get_last('S') if self._barrel_break_spr else None
                elif breaking:
                    tex = self._barrel_break_spr.get('S', gi.get('break_timer', 0.0)) if self._barrel_break_spr else None
                else:
                    tex = self._barrel_spr.get_idle('S') if self._barrel_spr else None
                if tex and tex.id > 0:
                    draw_size = int(tile_size * 1.1)
                    src = rl.Rectangle(0, 0, 256.0, 256.0)
                    dst = rl.Rectangle(float(tile_center_x - draw_size // 2), float(tile_center_y - draw_size // 2),
                                       float(draw_size), float(draw_size))
                    rl.draw_texture_pro(tex, src, dst, rl.Vector2(0, 0), 0.0, rl.WHITE)
                if hovered and not breaking and not broken:
                    if tex and tex.id > 0:
                        rl.begin_blend_mode(rl.BLEND_ADDITIVE)
                        rl.draw_texture_pro(tex, src, dst, rl.Vector2(0, 0), 0.0,
                                            rl.Color(255, 230, 170, min(255, HOVER_GLOW_ALPHA * 2)))
                        rl.end_blend_mode()
                    fonts.label('Barrel', tile_center_x, sy + tile_size // 4 - 24,
                                23, rl.Color(180, 120, 60, 255))

            elif gtype == 'brazier':
                broken   = gi.get('broken', False)
                breaking = gi.get('breaking', False)
                if broken:
                    tex = self._brazier_break_spr.get_last('S') if self._brazier_break_spr else None
                elif breaking:
                    tex = self._brazier_break_spr.get('S', gi.get('break_timer', 0.0)) if self._brazier_break_spr else None
                else:
                    tex = self._brazier_spr.get('S', self.anim_time) if self._brazier_spr else None
                if tex and tex.id > 0:
                    draw_size = int(tile_size * 1.2)
                    src = rl.Rectangle(0, 0, 256.0, 256.0)
                    dst = rl.Rectangle(float(tile_center_x - draw_size // 2), float(tile_center_y - draw_size // 2),
                                       float(draw_size), float(draw_size))
                    rl.draw_texture_pro(tex, src, dst, rl.Vector2(0, 0), 0.0, rl.WHITE)
                if hovered and not breaking and not broken:
                    if tex and tex.id > 0:
                        rl.begin_blend_mode(rl.BLEND_ADDITIVE)
                        rl.draw_texture_pro(tex, src, dst, rl.Vector2(0, 0), 0.0,
                                            rl.Color(255, 230, 170, min(255, HOVER_GLOW_ALPHA * 2)))
                        rl.end_blend_mode()
                    fonts.label('Brazier', tile_center_x, sy + tile_size // 4 - 24,
                                23, rl.Color(255, 160, 40, 255))

            elif gtype == 'drop' and gi.get('items'):
                rarity    = self._drop_rarity(gi)
                rc        = self._rarity_color(rarity)
                drop_spr, spr_scale = self._drop_sprite_for(gi)

                if drop_spr:
                    # Render the item model (gold pile)
                    tex = drop_spr.get('S', self.anim_time)
                    if tex and tex.id > 0:
                        draw_size = int(tile_size * 0.55 * spr_scale)
                        src = rl.Rectangle(0, 0, 256.0, 256.0)
                        dst = rl.Rectangle(float(tile_center_x - draw_size // 2), float(tile_center_y - draw_size // 2),
                                           float(draw_size), float(draw_size))
                        rl.draw_texture_pro(tex, src, dst, rl.Vector2(0, 0), 0.0, rl.WHITE)
                    else:
                        # No model texture at all: rarity dot, like non-model drops
                        rl.draw_circle(tile_center_x, tile_center_y, 5, rl.Color(rc.r, rc.g, rc.b, 200))
                else:
                    # Non-model items: small rarity dot so they stay visible
                    rl.draw_circle(tile_center_x, tile_center_y, 5, rl.Color(rc.r, rc.g, rc.b, 200))

                # Hit-test the visible drop sprite. The name is deliberately
                # omitted here and shown only by the existing hover tooltip.
                hit_size = max(18, int(tile_size * 0.65 * spr_scale))
                self._drop_label_rects.append(
                    (gi, tile_center_x - hit_size // 2,
                     tile_center_y - hit_size // 2, hit_size, hit_size))

        # ── loot sparkles ────────────────────────────────────────────────
        for s in self._loot_sparkles:
            if s['timer'] <= 0:
                continue
            sx, sy = self.iso.world_to_screen(s['x'], s['y'], cw, ch)
            sparkle_cx = sx + tile_size // 2
            sparkle_cy = sy + tile_size // 4
            alpha = min(255, int(255 * s['timer'] / 2.0))
            pulse_r = 6 + int(4 * (1 - s['timer'] / 2.0))
            rl.draw_circle(sparkle_cx, sparkle_cy, pulse_r, rl.Color(255, 255, 200, alpha))
            rl.draw_circle(sparkle_cx, sparkle_cy, pulse_r // 2, rl.Color(255, 255, 255, alpha))
    def _vfx_quad(self, shader_name, center_x, center_y, size, angle, color,
                  progress=None, seed=None):
        """Draw one procedural VFX quad: a vfx_* fragment shader over the
        shared 1x1 white texture. Silently no-ops when the shader (or the
        GL context behind it) is unavailable, matching the old behaviour
        of drawing with a missing sprite strip."""
        shaders = getattr(self, 'shaders', None)
        shader  = shaders.get(shader_name) if shaders is not None else None
        white   = getattr(self, '_vfx_white', None)
        if shader is None or white is None or white.id == 0:
            return
        if progress is not None:
            shaders.set_float(shader_name, 'u_progress', float(progress))
        if seed is not None:
            shaders.set_float(shader_name, 'u_seed', float(seed))
        dst    = rl.Rectangle(float(center_x), float(center_y),
                              float(size), float(size))
        origin = rl.Vector2(size / 2.0, size / 2.0)
        src    = rl.Rectangle(0.0, 0.0, 1.0, 1.0)
        rl.begin_shader_mode(shader)
        rl.draw_texture_pro(white, src, dst, origin, angle, color)
        rl.end_shader_mode()

    def _draw_swoosh_effects(self, cw, ch):
        tile_size = int(ISO_W * self.iso.scale)
        draw_size = int(ENTITY_BASE * self.iso.scale * 1.4)
        for e in self._swoosh_effects:
            progress = min(1.0, e['timer'] * 22.0 / 8.0)   # 8 frames @ 22 FPS
            sx, sy   = self.iso.world_to_screen(e['x'], e['y'], cw, ch)
            self._vfx_quad('vfx_swoosh',
                           sx + tile_size // 2, sy + tile_size // 2,
                           draw_size, e['angle'],
                           e.get('color', rl.WHITE), progress=progress)
    def _draw_glint_effects(self, cw, ch):
        tile_size = int(ISO_W * self.iso.scale)
        for e in self._glint_effects:
            progress = min(1.0, e['timer'] * 18.0 / 8.0)   # 8 frames @ 18 FPS
            sx, sy   = self.iso.world_to_screen(e['x'], e['y'], cw, ch)
            self._vfx_quad('vfx_glint',
                           sx + tile_size // 2, sy + tile_size // 2,
                           int(ENTITY_BASE * self.iso.scale * e.get('scale', 1.0)), 0.0,
                           e.get('color', rl.WHITE), progress=progress)
    def _draw_flame_effects(self, cw, ch):
        tile_size = int(ISO_W * self.iso.scale)
        draw_size = int(ENTITY_BASE * self.iso.scale * 1.1)
        for e in self._flame_effects:
            progress = min(1.0, e['timer'] * 12.0 / 8.0)   # 8 frames @ 12 FPS
            sx, sy   = self.iso.world_to_screen(e['x'], e['y'], cw, ch)
            seed     = (e['x'] * 13.7 + e['y'] * 7.3) % 100.0
            self._vfx_quad('vfx_flame',
                           sx + tile_size // 2, sy + tile_size // 2,
                           draw_size, 0.0,
                           e.get('color', rl.WHITE),
                           progress=progress, seed=seed)
    def _draw_glow_effects(self, cw, ch):
        _GLOW_DUR = 0.35
        tile_size = int(ISO_W * self.iso.scale)
        for e in self._glow_effects:
            progress  = e['timer'] / _GLOW_DUR
            alpha     = int(e.get('alpha', 220) * (1.0 - progress))
            base_col  = e.get('color', rl.WHITE)
            tint      = rl.Color(base_col.r, base_col.g, base_col.b, alpha)
            sx, sy    = self.iso.world_to_screen(e['x'], e['y'], cw, ch)
            # optional screen-space lift for individual effects ('lift' key
            # carries a fraction of the entity sprite height)
            lift = int(ENTITY_BASE * self.iso.scale * e.get('lift', 0.0))
            self._vfx_quad('vfx_glow',
                           sx + tile_size // 2, sy + tile_size // 2 - lift,
                           int(ENTITY_BASE * self.iso.scale * 2.2 * e.get('scale', 1.0)), 0.0, tint)

        # Angel form — persistent pulsing halo on the player
        if self._angel_timer > 0:
            pulse     = 0.5 + 0.5 * math.sin(rl.get_time() * 8.0)
            alpha     = int(120 + 90 * pulse)
            draw_size = int(ENTITY_BASE * self.iso.scale * 2.4)
            sx, sy    = self.iso.world_to_screen(self.px, self.py, cw, ch)
            self._vfx_quad('vfx_glow',
                           sx + tile_size // 2, sy + tile_size // 2,
                           draw_size, 0.0, rl.Color(255, 235, 150, alpha))

    def _draw_tracer_effects(self, cw, ch):
        """Bullet tracers for the gunslinger's ranged auto-attack: a faint
        full-path beam from the muzzle to the bullet's current position plus
        a hairline bright streak riding the bullet head (additive, so the
        post bloom picks it up)."""
        if not self._bullets:
            return
        tile_size = int(ISO_W * self.iso.scale)
        trail_len = tile_size * 0.9                  # streak length (px)
        rl.begin_blend_mode(rl.BLEND_ADDITIVE)
        for b in self._bullets:
            sx0, sy0 = self.iso.world_to_screen(b['sx'], b['sy'], cw, ch)
            hx,  hy  = self.iso.world_to_screen(b['x'],  b['y'],  cw, ch)
            mx,  my  = sx0 + tile_size // 2, sy0 + tile_size // 2
            bx,  by  = hx + tile_size // 2,  hy + tile_size // 2
            # faint full-path beam, muzzle -> bullet head
            rl.draw_line_ex((mx, my), (bx, by), 1.0, rl.Color(255, 220, 140, 24))
            # hairline streak: short segment behind the bullet head
            dx, dy = bx - mx, by - my
            dist   = math.hypot(dx, dy)
            if dist > 1.0:
                ux, uy = dx / dist, dy / dist
                k = min(trail_len, dist) / dist * 0.5
                rl.draw_line_ex((bx - dx * k, by - dy * k), (bx, by),
                                1.0, rl.Color(255, 220, 150, 130))
                rl.draw_line_ex((bx - dx * k * 0.45, by - dy * k * 0.45), (bx, by),
                                1.0, rl.Color(255, 255, 235, 210))
        rl.end_blend_mode()

    def _draw_hit_effects(self, cw: int, ch: int):
        """Bullet-impact bursts — one frame-texture list per red pack,
        cut into individual textures at load (see _build_load_steps);
        skips silently when the packs are missing."""
        if not self._hit_effects or not any(self._hit_packs):
            return
        tile_size = int(ISO_W * self.iso.scale)
        base = int(ENTITY_BASE * self.iso.scale * HIT_VFX_SCALE)
        for e in self._hit_effects:
            pack = self._hit_packs[e.get('pack', 0)] \
                if e.get('pack', 0) < len(self._hit_packs) else []
            if not pack:
                continue
            idx = min(len(pack) - 1,
                      int(e['timer'] / HIT_VFX_DUR * len(pack)))
            tex = pack[idx]
            if tex.id <= 0:
                continue
            sx, sy = self.iso.world_to_screen(e['x'], e['y'], cw, ch)
            size = base
            rl.draw_texture_pro(
                tex,
                rl.Rectangle(0.0, 0.0, float(tex.width), float(tex.height)),
                rl.Rectangle(float(sx + tile_size // 2 - size / 2),
                             float(sy + tile_size // 2 - size / 2),
                             float(size), float(size)),
                rl.Vector2(0, 0), 0.0, rl.WHITE)

    def _draw_muzzle_flashes(self, cw: int, ch: int):
        """The tiny Hit-Yellow burst at the revolver's muzzle (the yellow
        pack doubles as the muzzle art; the red packs own the impacts)."""
        if not self._flash_effects or not self._muzzle_frames:
            return
        tile_size = int(ISO_W * self.iso.scale)
        size = int(ENTITY_BASE * self.iso.scale * MUZZLE_VFX_SCALE)
        n = len(self._muzzle_frames)
        for e in self._flash_effects:
            idx = min(n - 1, int(e['timer'] / MUZZLE_VFX_DUR * n))
            tex = self._muzzle_frames[idx]
            if tex.id <= 0:
                continue
            sx, sy = self.iso.world_to_screen(e['x'], e['y'], cw, ch)
            rl.draw_texture_pro(
                tex,
                rl.Rectangle(0.0, 0.0, float(tex.width), float(tex.height)),
                rl.Rectangle(float(sx + tile_size // 2 - size / 2),
                             float(sy + tile_size // 2 - size / 2),
                             float(size), float(size)),
                rl.Vector2(0, 0), 0.0, rl.WHITE)
    def _draw_ground_tooltip(self, gi, cw, ch):
        slot = gi.get('items', [None])[0]
        if not slot:
            return
        item_id  = slot['item']
        idef     = ITEMS.get(item_id, {})
        inst     = slot.get('instance_data')
        rarity   = idef.get('rarity', 'common')
        unid     = inst is not None and not itemgen.is_identified(slot)
        if inst:
            rarity = inst.get('rarity', rarity)
        rarity_col = {
            'common': rl.Color(200, 200, 200, 255),
            'uncommon': rl.Color(50, 210, 80, 255),
            'rare': rl.Color(80, 140, 255, 255),
            'epic': rl.Color(220, 60, 60, 255),
            'legendary': rl.Color(255, 210, 40, 255),
        }.get(rarity, rl.Color(200, 200, 200, 255))
        border_col = {
            'common': rl.Color(75, 75, 75, 255),
            'uncommon': rl.Color(30, 155, 60, 255),
            'rare': rl.Color(50, 95, 220, 255),
            'epic': rl.Color(165, 30, 30, 255),
            'legendary': rl.Color(200, 160, 20, 255),
        }.get(rarity, rl.Color(75, 75, 75, 255))

        title = (idef.get('name', slot['item']) if unid else
                 (inst['display_name'] if inst else idef.get('name', slot['item'])))
        lines = [(title, rarity_col)]
        if inst and not unid:
            ilvl = inst.get('ilvl', 0)
            lines.append((f"Item Level: {ilvl}", rl.Color(0xCC, 0xCC, 0xCC, 255)))
        if unid:
            # Unidentified items expose no stat text: no implicits, no affixes.
            lines.append(("Unidentified", rl.Color(190, 160, 90, 220)))
        if idef.get('equipSlot') and not unid:
            for k, v in (idef.get('equip') or {}).items():
                lines.append((format_equip_stat(k, v), rl.Color(150, 170, 200, 255)))
        if inst and not unid:
            for line in itemgen.affix_lines(inst):
                lines.append((line, rl.Color(120, 160, 255, 255)))
            unique = inst.get('unique')
            if unique:
                lines.append((unique['title'], rl.Color(230, 120, 60, 255)))
                lines.append((unique['text'], rl.Color(230, 120, 60, 255)))
        for k, v in (idef.get('use') or {}).items():
            if unid:
                break
            lines.append((f"Use: +{v} {k}", rl.Color(200, 200, 200, 255)))
        sz = idef.get('size', (1, 1))
        if sz != (1, 1):
            lines.append((f"{sz[0]}x{sz[1]} cells", rl.Color(0xCC, 0xCC, 0xCC, 255)))

        # QoL #20 — comparison vs the currently equipped item in this slot
        if idef.get('equipSlot'):
            slot_key = idef['equipSlot']
            eq_entry = self.inventory['equipped'].get(slot_key)
            slot_label = EQUIP_SLOT_LABELS.get(slot_key, slot_key)
            if eq_entry is not slot:
                lines.append(("", rl.Color(0xCC, 0xCC, 0xCC, 255)))
                lines.append((f"= Equipped {slot_label} =", rl.Color(0xCC, 0xCC, 0xCC, 255)))
                _CMP_UP   = rl.Color(80, 220, 90, 255)
                _CMP_DOWN = rl.Color(230, 70, 70, 255)
                if eq_entry:
                    for ctext, sign in itemgen.comparison_rows(slot, eq_entry):
                        col = _CMP_UP if sign > 0 else (_CMP_DOWN if sign < 0 else rl.Color(0xCC, 0xCC, 0xCC, 255))
                        lines.append((ctext, col))
                else:
                    lines.append(("(no item equipped)", rl.Color(0xCC, 0xCC, 0xCC, 255)))

        font_sz = 18
        line_h = font_sz + 5
        PAD = 14
        ARROW_W = 16   # comparison arrow icon after the text
        tw = max(fonts.measure(t, font_sz)
                 + (ARROW_W if _cmp_sign(c) else 0)
                 for t, c in lines) + PAD * 2
        th = len(lines) * line_h + PAD * 2
        mx, my = rl.get_mouse_x(), rl.get_mouse_y()

        # clamp to screen
        tx = max(4, mx - tw - 8)
        if tx < 4:
            tx = mx + 12
        ty = max(4, min(my, ch - th - 4))

        # D2-style stone panel
        rl.draw_rectangle(tx, ty, tw, th, rl.Color(0, 0, 0, 250))
        rl.draw_rectangle(tx + 2, ty + 2, tw - 4, th - 4, rl.Color(0, 0, 0, 0x99))
        rl.draw_rectangle_lines_ex(rl.Rectangle(float(tx + 1), float(ty + 1), float(tw - 2), float(th - 2)),
                                   1, rl.Color(0xE0, 0xE0, 0xE0, 200))
        rl.draw_rectangle_lines_ex(rl.Rectangle(float(tx), float(ty), float(tw), float(th)),
                                   1, rarity_col)

        for i, (line, col) in enumerate(lines):
            ly = ty + PAD + i * line_h
            if i == 0:
                ticon = icons.item_icon(idef, item_id)
                if ticon:
                    icons.draw(ticon, tx + PAD, ly + 1, 16, col)
                    fonts.draw(line, tx + PAD + 22, ly, font_sz, col)
                else:
                    fonts.draw(line, tx + PAD, ly, font_sz, col)
            else:
                fonts.draw(line, tx + PAD, ly, font_sz, col)
                # comparison rows: arrow icon instead of "(up)"/"(down)" words
                sign = _cmp_sign(col)
                if sign:
                    name = 'arrow_up' if sign > 0 else 'arrow_down'
                    icons.draw(name, tx + PAD + fonts.measure(line, font_sz) + 3,
                               ly + 1, 14, col)
