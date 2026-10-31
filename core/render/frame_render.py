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
    DEATH_DURATION,
    DELVE_CLICK_RADIUS,
    DELVE_PERSONAL_LIGHT,
    STATE_DEAD,
    STATE_EDITOR,
    STATE_EXTRACTED,
    STATE_HUB,
    STATE_LOADING,
    STATE_MENU,
    STATE_PAUSED,
    STATE_PLAYING,
)
from core.iso_engine import ISO_W, ENTITY_BASE
from systems import frames
from ui import fonts


OUTLINE_COLOR_IDLE = rl.Color(0, 0, 0, 255)
OUTLINE_COLOR_HIT = rl.Color(190, 20, 20, 255)
OUTLINE_SIZE = 1.5

# Delve actors (player + enemies) draw dimmer than the raw sprite art —
# 1.0 = unchanged, lower = darker.
SPRITE_DARKEN = 0.75


def _dim(c, factor=None):
    """Darken a tint colour by multiplying its RGB channels. Accepts both
    pyray Color objects and the plain tuples the module constants use."""
    f = SPRITE_DARKEN if factor is None else factor
    if hasattr(c, 'r'):
        r, g, b, a = c.r, c.g, c.b, c.a
    else:
        r, g, b, a = c[0], c[1], c[2], c[3]
    return rl.Color(int(r * f), int(g * f), int(b * f), a)


def _outline_color(hit_flash: float):
    """Return the world outline colour, fading red hit tint to black."""
    t = min(1.0, max(0.0, hit_flash * 1.1))
    return rl.Color(int(OUTLINE_COLOR_HIT.r * t),
                    int(OUTLINE_COLOR_HIT.g * t),
                    int(OUTLINE_COLOR_HIT.b * t), 255)


class FrameRenderMixin:
    def draw(self):
        self._draw_frame()
    def _draw_frame(self):
        # Whole frame renders into a canvas matching the current window size
        # (recreated on resize), then blits 1:1 onto the window.
        self._ensure_virtual_rt()
        self._update_mouse_transform()

        rl.begin_texture_mode(self._virtual_rt)
        # Opaque clear — additive light passes composite onto this surface;
        # without it, stale frames accumulate (ghost trails, brightness creep).
        rl.clear_background(rl.Color(0, 0, 0, 255))
        self._outer_rt = self._virtual_rt
        self.iso._outer_rt = self._virtual_rt
        cw, ch = rl.get_screen_width(), rl.get_screen_height()
        # hover state is recomputed by whichever scene draws this frame;
        # reset first so it never leaks between screens (hover glow logic)
        self._hover_interact = None

        if self.state == STATE_MENU:
            self.menu_sys.scene_bg_tex = None
            if self.menu_sys.state in ('inventory', 'stash'):
                rl.clear_background(rl.Color(0, 0, 0, 255))
                self.inv.open = True
                self.inv.draw(self._get_char_inventory(), cw, ch)
            self.menu_sys.draw(cw, ch)
        elif self.state == STATE_LOADING:
            self._draw_loading(cw, ch)
        elif self.state == STATE_HUB:
            self._draw_hub(cw, ch)
        elif self.state == STATE_PAUSED:
            pre = getattr(self, '_pre_pause_state', STATE_PLAYING)
            if pre == STATE_HUB:
                self._draw_hub(cw, ch)
            else:
                self._draw_game(cw, ch)
            rl.draw_rectangle(0, 0, cw, ch, rl.Color(0, 0, 0, 160))
            self.inv.draw(self.inventory, cw, ch)
            self.menu_sys.draw(cw, ch)
        elif self.state == STATE_PLAYING:
            self._draw_game(cw, ch)
            settings = self.menu_sys.settings
            self.inv.draw(self.inventory, cw, ch)
            if self._char_stats_open:
                self._draw_char_stats(cw, ch)
            if self._minimap_open and self._minimap is not None:
                self._minimap.draw(cw, ch)
            if settings.perf_overlay: self._draw_perf(cw, ch)
        elif self.state == STATE_EDITOR:
            if self._editor: self._editor.draw(cw, ch)
        elif self.state in (STATE_DEAD, STATE_EXTRACTED):
            self._draw_end_screen(cw, ch)

        if self._console_open and self.state != STATE_EDITOR:
            self._draw_console(cw, ch)

        self._draw_combat_log(cw, ch)
        self._outer_rt = None
        self.iso._outer_rt = None
        rl.end_texture_mode()

        # 1:1 blit (RT textures are stored bottom-up in OpenGL, hence the
        # negative-height source rect to flip back).
        src = rl.Rectangle(0.0, float(ch), float(cw), -float(ch))
        dst = rl.Rectangle(0.0, 0.0, float(cw), float(ch))
        rl.draw_texture_pro(self._virtual_rt.texture, src, dst,
                            rl.Vector2(0.0, 0.0), 0.0, rl.WHITE)
    def _draw_loading(self, cw, ch):
        rl.clear_background(rl.BLACK)
        t     = rl.get_time()
        dots  = '.' * (int(t * 2.5) % 3 + 1)
        label = f'loading{dots}'
        size  = self.LOAD_TEXT_SIZE
        lw    = fonts.measure(label, size)
        tx    = int(cw - self.LOAD_TEXT_OFF_X - lw)
        ty    = int(ch - self.LOAD_TEXT_OFF_Y - size)
        tex   = self._load_runner_spr.get('E', t) if self._load_runner_spr else None
        if tex:
            w  = tex.width * self.LOAD_RUNNER_SCALE
            h  = tex.height * self.LOAD_RUNNER_SCALE
            bx = float(cw - self.LOAD_RUNNER_OFF_X - w)
            by = float(ch - self.LOAD_RUNNER_OFF_Y - h)
            src = rl.Rectangle(0, 0, float(tex.width), float(tex.height))
            dst = rl.Rectangle(bx, by, w, h)
            rl.draw_texture_pro(tex, src, dst, rl.Vector2(0, 0), 0.0, rl.WHITE)
            if self.LOAD_RUNNER_DEBUG:
                rl.draw_rectangle_lines(int(bx), int(by), int(w), int(h),
                                        rl.Color(0xFF, 0x00, 0xFF, 255))
        fonts.draw(label, tx, ty, size, rl.Color(0xAA, 0xAA, 0xAA, 255))
    def _draw_game(self, cw, ch):
        self._ensure_scene_rt(cw, ch)

        rl.begin_texture_mode(self._scene_rt)
        rl.clear_background(rl.Color(10, 8, 12, 255))
        self.iso.follow(self.px, self.py)

        # Screen shake — save clean camera, apply random offset
        _clean_cam_x = self.iso._cam_x
        _clean_cam_y = self.iso._cam_y
        if self._shake_timer > 0:
            import random as _rnd_shake
            shake_x = _rnd_shake.uniform(-self._shake_intensity, self._shake_intensity)
            shake_y = _rnd_shake.uniform(-self._shake_intensity, self._shake_intensity)
            self.iso._cam_x += shake_x
            self.iso._cam_y += shake_y

        entities = []
        mx_screen = rl.get_mouse_x()
        my_screen = rl.get_mouse_y()
        mouse_tile_col, mouse_tile_row = self.iso.screen_to_world(mx_screen, my_screen, cw, ch)

        # ── player ────────────────────────────────────────────────────
        player_sprites = self._player_sprites.get(self.char.looks,
                         self._player_sprites.get('fighter', {}))
        if self.player_state == 'attack':
            player_sprite = player_sprites.get('attack')
            atk_speed = self.stats.get('_attack_speed_pct', 0.0) + self._equipped_bonuses()['attack_speed_pct']
            # Attack animation plays over the quantized cooldown (breakpoints)
            if player_sprite is not None:
                player_sprite._fps = 8 / frames.attack_seconds(
                    frames.PLAYER_BASE_ATTACK_FRAMES, atk_speed)
        elif self.player_state == 'walk':
            player_sprite = player_sprites.get('walk')
        else:
            player_sprite = player_sprites.get('idle')

        entities.append({
            'col':       self.px,
            'row':       self.py,
            'sprite':    player_sprite,
            'direction': self.player_facing,
            'time':      self.anim_time,
            'idle':      self.player_state == 'idle',
            'scale':     1,
            'tint':      _dim(rl.WHITE),
            'shadow':    True,
            'hl_scale':  1,
            'mm_col':    rl.Color(0xFF, 0xFF, 0xFF, 255),
            'actor':     True,
            'big_art':   True,      # legacy character canvas keeps ENTITY_BASE size
        })

        # ── pulse (delve crawler) ─────────────────────────────────────
        if self._delve is not None and self._pulse_tex is not None:
            entities.append({
                'col':      self._delve['pulse_x'],
                'row':      self._delve['pulse_y'],
                'texture':  self._pulse_tex,
                'scale':    1,
                'big_art':  True,   # ENTITY canvas, same size as _draw_pulse_sprite
                'mm_col':   rl.Color(255, 210, 80, 255),
            })

        # ── enemies ───────────────────────────────────────────────────
        for z in self.zombies:
            etype       = z.get('enemy_type', 'skeleton')
            death_timer = z.get('death_timer')
            if death_timer is not None:
                spr        = self._sl_death if etype == 'slime' else self._sk_death
                alpha      = max(0, int(255 * (1.0 - death_timer / DEATH_DURATION)))
                tint       = _dim(rl.Color(255, 255, 255, alpha))
                anim_timer = death_timer
            else:
                if etype == 'slime':
                    spr        = self._sl_walk if z['state'] in ('chase', 'attack', 'return') else self._sl_idle
                    anim_timer = z.get('attack_anim_timer', z['anim_timer']) if z['state'] == 'attack' else z['anim_timer']
                else:
                    if z['state'] == 'attack':
                        spr        = self._sk_attack
                        anim_timer = z.get('attack_anim_timer', 0.0)
                    elif z['state'] in ('chase', 'return'):
                        spr        = self._sk_walk
                        anim_timer = z['anim_timer']
                    else:
                        spr        = self._sk_idle
                        anim_timer = z['anim_timer']
                is_target  = (z is self.attack_target)
                tile_size  = int(ISO_W * self.iso.scale)
                ent_px     = ENTITY_BASE * self.iso.scale
                sprite_sx, sprite_sy = self.iso.world_to_screen(z['x'], z['y'], cw, ch)
                sprite_cx  = sprite_sx + tile_size / 2
                sprite_cy  = sprite_sy + tile_size / 2
                is_hovered = (abs(mx_screen - sprite_cx) <= ent_px * 0.38
                              and abs(my_screen - sprite_cy) <= ent_px * 0.45)

                # Status-effect tint overlay
                if z.get('frozen_timer', 0) > 0:
                    s_tint = rl.Color(140, 200, 255, 200)
                elif z.get('burning_timer', 0) > 0:
                    s_tint = rl.Color(255, 160, 60, 180)
                elif z.get('rot_stacks', 0) > 0:
                    s_tint = rl.Color(160, 200, 80, 170)
                elif z.get('cold_stacks', 0) > 0:
                    s_tint = rl.Color(180, 210, 255, 140)
                else:
                    s_tint = None

                if is_target:
                    tint = _dim(rl.Color(255, 90, 90, 255))
                elif is_hovered:
                    tint = _dim(rl.Color(255, 175, 175, 255))
                else:
                    tint = _dim(rl.WHITE)
                if s_tint:
                    tint = rl.Color(
                        tint.r * s_tint.r // 255,
                        tint.g * s_tint.g // 255,
                        tint.b * s_tint.b // 255,
                        tint.a)

            is_target = death_timer is None and (z is self.attack_target)
            entities.append({
                'col':       z['x'],
                'row':       z['y'],
                'sprite':    spr,
                'direction': self._dir_to(z.get('facing_x', 1), z.get('facing_y', 0)),
                'time':      anim_timer,
                'idle':      death_timer is None and z['state'] == 'idle',
                'tint':      tint,
                'scale':     1,
                'shadow':    is_target,
                'mm_col':    rl.Color(200, 60, 60, 255),
                'actor':     True,
                'big_art':   True,      # legacy character canvas keeps ENTITY_BASE size
            })

        # ── loot (minimap blips for drops only, rarity-coloured) ─────
        for gi in self.ground_items:
            if gi.get('type') != 'drop' or not gi.get('items'):
                continue
            rarity = self._drop_rarity(gi)
            rc     = self._rarity_color(rarity)
            entities.append({
                'col':      gi['x'],
                'row':      gi['y'],
                'sprite':   None,
                'mm_col':   rc,
            })

        # ── decorations (depth-sorted with enemies via painter's algorithm) ──
        for _d in self._decor_items:
            _dspr = self._decor_sprs.get(_d['type'])
            if _dspr:
                entities.append({
                    'col':      _d['x'],
                    'row':      _d['y'],
                    'sprite':   _dspr,
                    'direction': 'S',
                    'time':     0.0,
                    'idle':     True,
                    'tint':     rl.WHITE,
                    'scale':    1.5 if 'column' in _d['type'] else 1.0,
                    'shadow':   False,
                    'mm_col':   None,
                })

        import time as _perf_time
        t_draw_map_start = _perf_time.perf_counter()
        self._delve_draw_entities = entities   # for the above-darkness actor redraw
        self.iso.draw_map(self.map, entities, cw, ch)
        t_weather_start = _perf_time.perf_counter()
        self._render_puddle_reflections(cw, ch, entities)
        t_after_weather = _perf_time.perf_counter()
        t_after_draw_map = t_weather_start
        # interactable hover (portal/crate/barrel/brazier) — shared with the
        # hub via _hover_interactable; drives glow labels + hover highlight
        self._hover_interact = self._hover_interactable(
            [gi for gi in self.ground_items
             if gi.get('type') in ('portal', 'crate', 'barrel', 'brazier')
             and not gi.get('breaking')],
            DELVE_CLICK_RADIUS, cw, ch)
        self._draw_world_objects(cw, ch)
        t_after_world_objs = _perf_time.perf_counter()
        self._weather_ms = (t_after_weather - t_weather_start) * 1000

        self._draw_glow_effects(cw, ch)
        self._draw_tracer_effects(cw, ch)
        self._draw_hit_effects(cw, ch)
        self._draw_muzzle_flashes(cw, ch)
        self._draw_swoosh_effects(cw, ch)
        self._draw_flame_effects(cw, ch)
        self._draw_glint_effects(cw, ch)
        self._draw_aura_range(cw, ch)
        self._draw_enemy_bars(cw, ch)
        # NOTE: _draw_dmg_numbers moved above the darkness overlay (drawn
        # post-darkness below) so the gloom never dims combat numbers
        self._draw_click_marker(cw, ch)
        t_after_fx = _perf_time.perf_counter()
        rl.end_texture_mode()
        self._rebind_outer_rt()

        # Post-process chain (bloom, color, wave, dream, grayscale, pixelizer, swirl)
        self._apply_post_chain(cw, ch)

        if self._delve is not None:
            self._draw_darkness(cw, ch)
            # actors above the darkness: player + monsters keep a readable
            # brightness (pool light + ACTOR_LIGHT_FLOOR), per-sprite tints
            # (target/hover/status/death-fade) still apply on top of it.
            # Same light spec as _draw_darkness (kind 'pulse', pool edge =
            # light_r + personal light, centred anchor).
            d = self._delve
            lights = [{'x': d['pulse_x'], 'y': d['pulse_y'],
                       'r': d['light_r'] + DELVE_PERSONAL_LIGHT,
                       'kind': 'pulse', 'phase': 0.0, 'ax': 0.0, 'ay': 0.0}]
            tile_size = max(1, int(ISO_W * self.iso.scale))
            half = tile_size * 0.5
            for e in getattr(self, '_delve_draw_entities', []):
                if not e.get('actor'):
                    continue
                sx, sy = self.iso.world_to_screen(e['col'], e['row'], cw, ch)
                v_tint = self._actor_tint(lights, sx + half, sy + half, cw, ch)
                base = e.get('tint', rl.WHITE)
                if not hasattr(base, 'r'):   # pyray 5.5 constants are tuples
                    base = rl.Color(base[0], base[1], base[2], base[3])
                e2 = dict(e)
                e2.pop('shadow', None)   # foot shadow stays baked in the gloom
                e2['tint'] = rl.Color(base.r * v_tint.r // 255,
                                      base.g * v_tint.g // 255,
                                      base.b * v_tint.b // 255,
                                      base.a)
                self.iso._draw_entity(e2, sx, sy, tile_size)
            self._draw_pulse_sprite(cw, ch)
            self._draw_drop_overlay(cw, ch)
            # combat numbers above the darkness — never dimmed by the gloom
            self._draw_dmg_numbers(cw, ch)
            # Ground-item tooltips are UI: resolve and draw them after the
            # darkness mask so labels/panels are never darkened or fire-tinted.
            self._hovered_ground_item = None
            mx_s, my_s = rl.get_mouse_x(), rl.get_mouse_y()
            for gi, rx, ry, rw, rh in self._drop_label_rects:
                if rx <= mx_s < rx + rw and ry <= my_s < ry + rh:
                    self._hovered_ground_item = gi
                    break
            if self._hovered_ground_item and not self.inv.open:
                self._draw_ground_tooltip(self._hovered_ground_item, cw, ch)
            self._draw_pulse_label(cw, ch)
            self._draw_delve_choice_ui(cw, ch)
        if self.menu_sys.settings.debug_overlay: self._draw_debug(cw, ch)
        if self.menu_sys.settings.debug_overlay:
            self._draw_debug_rings(
                [gi for gi in self.ground_items
                 if gi.get('type') in ('portal', 'crate', 'barrel', 'brazier')
                 and not gi.get('breaking')],
                DELVE_CLICK_RADIUS, cw, ch)
        if self.menu_sys.settings.crt_effect: self._draw_crt(cw, ch)

        # Restore clean camera (undo shake) before HUD
        self.iso._cam_x = _clean_cam_x
        self.iso._cam_y = _clean_cam_y
        t_after_crt = _perf_time.perf_counter()
        self._draw_hud(cw, ch)
        t_after_hud = _perf_time.perf_counter()
        self.profile_ms = {
            'draw_map':    (t_after_draw_map   - t_draw_map_start) * 1000,
            'world_objs':  (t_after_world_objs - t_after_draw_map) * 1000,
            'weather':     self._weather_ms,
            'bars+fx':     (t_after_fx         - t_after_world_objs) * 1000,
            'crt':         (t_after_crt        - t_after_fx) * 1000,
            'hud':         (t_after_hud        - t_after_crt) * 1000,
        }

        if self.hit_flash > 0:
            intensity = min(1.0, self.hit_flash * 1.1)
            if self.shaders and self.shaders.has('hit_flash'):
                self.shaders.set_float('hit_flash', 'u_flash_intensity', intensity)
                rl.begin_shader_mode(self.shaders.get('hit_flash'))
                rl.draw_rectangle(0, 0, cw, ch, rl.WHITE)
                rl.end_shader_mode()
            else:
                alpha = int(min(180, self.hit_flash * 200))
                rl.draw_rectangle(0, 0, cw, ch, rl.Color(200, 0, 0, alpha))

        # Low-health warning vignette
        hp_pct = self.stats['health'] / max(1, self.stats['max_health'])
        if hp_pct < 0.25 and self.state == STATE_PLAYING:
            low_pulse = (math.sin(self.raid_time * 5.0) + 1.0) / 2.0
            low_alpha = int(40 + 30 * low_pulse) if hp_pct < 0.15 else int(15 + 15 * low_pulse)
            rl.draw_rectangle(0, 0, cw, ch, rl.Color(180, 0, 0, low_alpha))
