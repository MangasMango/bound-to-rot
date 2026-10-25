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

from core.iso_engine import ISO_W
from core.game import (
    HOVER_GLOW_ALPHA,
    HUB_CLICK_RADIUS,
    HUB_INTERACT_RANGE,
    _BRAZIER_POS,
    _HEART_POS,
    _TORCH_POS,
)
from systems import frames
from ui import fonts
from ui.menus import _btn


class HubRenderMixin:
    def _draw_hub(self, cw, ch):
        self._ensure_scene_rt(cw, ch)

        rl.begin_texture_mode(self._scene_rt)
        rl.clear_background(rl.Color(0, 0, 0, 255))

        player_entity, hub_actors = self._hub_actor_entities()
        hub_entities = list(hub_actors)

        # Delve Heart — the pulse art, breathing slowly at the hub's centre
        if self._pulse_tex and self._pulse_tex.id > 0:
            breath = 1.0 + 0.06 * math.sin(self.anim_time * 2.2)
            hub_entities.append({
                'col': _HEART_POS[0], 'row': _HEART_POS[1],
                'texture': self._pulse_tex, 'scale': 1.2 * breath,
            })

        # Torch columns flanking the heart
        if self._column_spr:
            for col, row in _TORCH_POS:
                hub_entities.append({
                    'col': col, 'row': row,
                    'sprite': self._column_spr,
                    'direction': 'S', 'time': 0.0,
                    'idle': True, 'scale': 1.2, 'shadow': False,
                })

        # Braziers flanking the spawn
        if self._brazier_spr:
            for col, row in _BRAZIER_POS:
                hub_entities.append({
                    'col': col, 'row': row,
                    'sprite': self._brazier_spr,
                    'direction': 'S', 'time': self.anim_time,
                    'idle': False, 'scale': 1.2, 'shadow': False,
                })

        self.iso.draw_map(self.map, hub_entities, cw, ch, overlay_entities=[player_entity])
        # Planar reflections inside visible puddles (no-op when dry).
        self._render_puddle_reflections(cw, ch, hub_entities + [player_entity])

        # Draw ground-item drops in the hub
        tile_size = int(ISO_W * self.iso.scale)
        for gi in self.ground_items:
            if gi.get('type') != 'drop' or not gi.get('items'):
                continue
            sx, sy = self.iso.world_to_screen(gi['x'], gi['y'], cw, ch)
            cx, cy = sx + tile_size // 2, sy + tile_size // 2
            # Visible ground sprite for every dropped item (hover label on top)
            self._draw_ground_item_sprite(gi, cx, cy, tile_size)
        rl.end_texture_mode()
        self._rebind_outer_rt()

        self._apply_post_chain(cw, ch)

        # Darkness is real in the hub — torches & braziers carve the light.
        self._render_darkness(cw, ch, self._hub_lights, self._hub_dark_timer)
        self._hover_interact = self._hover_interactable(
            self._hub_objects, HUB_CLICK_RADIUS, cw, ch)
        self._draw_hub_bright(cw, ch)

        # object labels — anchored to the ART's top edge (entities are drawn
        # centred on the tile centre, i.e. half a tile below the projection
        # point), then brightened above the darkness so they read from the gloom
        if self.menu_sys.settings.debug_overlay:
            self._draw_debug_rings(self._hub_objects, HUB_CLICK_RADIUS, cw, ch,
                                   interact_r=HUB_INTERACT_RANGE)
        tile_size = int(ISO_W * self.iso.scale)
        for obj in self._hub_objects:
            sx, sy = self.iso.world_to_screen(obj['x'], obj['y'], cw, ch)
            center_x = sx + tile_size // 2
            art_h = tile_size * obj.get('scale', 1.0)
            ly = int(sy + tile_size / 2 - art_h / 2 + obj.get('label_dy', 0)) - 22
            lbl = obj['label']
            label_width = fonts.measure(lbl, 16)
            fonts.draw(lbl, center_x - label_width // 2, ly, 16,
                       rl.Color(obj['color'].r, obj['color'].g, obj['color'].b, 200))

        # Ground drop labels — same always-visible/Alt rule as in the delve
        self._draw_drop_labels(cw, ch)

        self._draw_hud(cw, ch)

        if self._hub_popup:
            if self._hub_popup == 'anima':
                content, x_clicked = self._draw_anima_panel(cw, ch)
                if x_clicked:
                    self._hub_popup = None
                elif self._chart_screen is not None:
                    self._chart_screen.draw(cw, ch,
                                            origin=(content.x, content.y),
                                            view=(content.width, content.height))
                    # Resume button (saved mid-delve snapshot)
                    if self._chart_resume:
                        import entities.progression as _prog
                        saved = (self._saved_delve
                                 or _prog.load_delve_data(self.char.id))
                        depth = (saved.get('delve') or {}).get('depth', 1) \
                            if saved else 1
                        label = f'Resume delve — Depth {depth}'
                        rect = rl.Rectangle(
                            content.x + content.width // 2 - 110,
                            content.y + content.height - 44, 220, 36)
                        self._chart_resume_rect = rect
                        _btn(rect, label, 14, accent=True)
                    else:
                        self._chart_resume_rect = None
            elif self._hub_popup == 'stash':
                rl.draw_rectangle(0, 0, cw, ch, rl.Color(0, 0, 0, 160))
                self.inv.draw(self._get_char_inventory(), cw, ch)
                # X close button for stash
                x_sz = 34
                x_r = rl.Rectangle(cw - x_sz - 12, 12, x_sz, x_sz)
                if _btn(x_r, 'X', 22):
                    self._hub_popup = None
                    self.inv.open = False
                    self.inv.close_stash()
                    self.inv.on_stash_change = None
            else:
                self.menu_sys.draw_popup(self._hub_popup, cw, ch)
        else:
            self.inv.draw(self._get_char_inventory(), cw, ch)
    def _draw_hub_bright(self, cw, ch):
        """Re-draw the hub's light sources above the darkness overlay so the
        flames and the Delve Heart stay bright instead of being dimmed by the
        multiply pass."""
        tile_size = max(1, int(ISO_W * self.iso.scale))
        half = tile_size * 0.5

        def draw_tex(col, row, tex, scale=1.0, dy=0.0, tint=None):
            if tex is None or tex.id <= 0:
                return
            sx, sy = self.iso.world_to_screen(col, row, cw, ch)
            size = tile_size * scale
            src = rl.Rectangle(0.0, 0.0, float(tex.width), float(tex.height))
            dst = rl.Rectangle(float(sx + half - size * 0.5),
                               float(sy + half - size * 0.5 + dy),
                               float(size), float(size))
            rl.draw_texture_pro(tex, src, dst, rl.Vector2(0.0, 0.0), 0.0,
                                tint or rl.WHITE)

        # Delve Heart — bright, with a subtle warm glow (the layered
        # darkness light does the heavy lifting now)
        if self._pulse_tex and self._pulse_tex.id > 0:
            pulse = (math.sin(self.anim_time * 2.2) + 1.0) / 2.0
            sx, sy = self.iso.world_to_screen(_HEART_POS[0], _HEART_POS[1], cw, ch)
            step_x, step_y = self.iso._steps()
            glow_r = tile_size * (0.07 + 0.01 * pulse)
            rl.draw_ellipse(int(sx + half), int(sy + half), glow_r, glow_r * step_y / step_x,
                            rl.Color(255, 190, 100, int(16 + 12 * pulse)))
            breath = 1.0 + 0.06 * math.sin(self.anim_time * 2.2)
            draw_tex(_HEART_POS[0], _HEART_POS[1], self._pulse_tex, 1.2 * breath)

        # Torch flames mounted on the column tops
        if self._torch_spr:
            for col, row in _TORCH_POS:
                draw_tex(col, row, self._torch_spr.get('S', self.anim_time),
                         1.0, dy=-tile_size * 0.55)

        # Brazier flames
        if self._brazier_spr:
            for col, row in _BRAZIER_POS:
                draw_tex(col, row, self._brazier_spr.get('S', self.anim_time), 1.2)

        # ── actors above the darkness ────────────────────────────────────
        # Player / stash are redrawn with a per-sprite light tint
        # (pool light, clamped to the small actor readability floor) so they
        # remain playable silhouettes rather than disappearing completely.
        tile_size = max(1, int(ISO_W * self.iso.scale))
        half = tile_size * 0.5
        player_entity, hub_actors = self._hub_actor_entities()
        for e in [player_entity] + hub_actors:
            sx, sy = self.iso.world_to_screen(e['col'], e['row'], cw, ch)
            e = dict(e)
            e['tint'] = self._actor_tint(self._hub_lights,
                                         sx + half, sy + half, cw, ch)
            e.pop('shadow', None)   # foot shadow stays baked in the gloom
            self.iso._draw_entity(e, sx, sy, tile_size)

        # ground-item drop sprites get the same treatment
        for gi in self.ground_items:
            if gi.get('type') != 'drop' or not gi.get('items'):
                continue
            sx, sy = self.iso.world_to_screen(gi['x'], gi['y'], cw, ch)
            cx, cy = sx + tile_size // 2, sy + tile_size // 2
            tint = self._actor_tint(self._hub_lights, cx, cy, cw, ch)
            self._draw_ground_item_sprite(gi, cx, cy, tile_size, tint)

        # hovered interactable pops: additive re-draw of the art itself —
        # only art pixels brighten, no floor pool
        hv = self._hover_interact
        if hv:
            if hv.get('type') in ('vendor', 'stash'):
                for e in hub_actors:
                    if e['col'] == hv['x'] and e['row'] == hv['y']:
                        sx, sy = self.iso.world_to_screen(e['col'], e['row'], cw, ch)
                        e2 = dict(e)
                        e2.pop('shadow', None)
                        e2['tint'] = rl.Color(255, 230, 170, min(255, HOVER_GLOW_ALPHA * 2))
                        rl.begin_blend_mode(rl.BLEND_ADDITIVE)
                        self.iso._draw_entity(e2, sx, sy, tile_size)
                        rl.end_blend_mode()
            elif hv.get('type') == 'delve' and self._pulse_tex and self._pulse_tex.id > 0:
                breath = 1.0 + 0.06 * math.sin(self.anim_time * 2.2)
                rl.begin_blend_mode(rl.BLEND_ADDITIVE)
                draw_tex(_HEART_POS[0], _HEART_POS[1], self._pulse_tex,
                         1.2 * breath, tint=rl.Color(255, 190, 100, min(255, HOVER_GLOW_ALPHA * 2)))
                rl.end_blend_mode()
