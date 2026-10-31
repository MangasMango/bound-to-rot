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
from systems import input as inp
from core.game import *
from core.game import (
    _HUB_LAYOUT,
    _HUB_LIGHTS,
    _HUB_PATH_CELLS,
    _STASH_POS,
    _VENDOR_POS,
    SHADER_EDGE_SCALE,
)

class HubMixin:
        def _enter_hub(self):
            self.state  = STATE_HUB
            self.map    = self._build_hub_map()
            self.zombies       = []
            self.ground_items  = []
            self._incoming_dmg_by_type = {}
            self.drop_target   = None
            self.attack_target = None
            self.interact_target = None
            self.dest_col = self.dest_row = None
            self._hub_pending_interact = None
            self.player_state  = 'idle'
            self.player_facing = 'S'
            self.anim_time     = 0.0
            self.px = HUB_SPAWN[0]
            self.py = HUB_SPAWN[1]
            # Load character stats and inventory so HUD displays correctly
            bonuses = compute_perk_bonuses(
                self.char.perks, self.char.descend,
                item_bonuses=itemgen.aggregate_item_bonuses(self.inventory))
            equip_b = self._equipped_bonuses()
            item_attr = {a: equip_b.get(a, 0) for a in DESCEND_ATTRIBUTES}
            derived = compute_derived_stats(
                self.char.descend, bonuses,
                item_bonuses=item_attr, looks=self.char.looks)
            reset_stats(self.stats, **derived)
            if self.char.inventory is None:
                self.char.inventory = make_inventory()
            self.inventory = self.char.inventory

            self._hub_popup = None
            self.inv.on_drop_item = self._on_inv_drop
            self.iso.follow(self.px, self.py)
            self.audio.set_music_state('hub')

            self._hub_objects = [dict(o) for o in _HUB_LAYOUT]
            for obj in self._hub_objects:
                obj['color'] = rl.Color(*obj['color'])
            self._hub_lights = [dict(l) for l in _HUB_LIGHTS]
            self._hub_dark_timer = 0.0
            self.iso.set_path_cells(_HUB_PATH_CELLS)
            # The hub settles into a light drizzle rather than a storm —
            # calm, reflective sanctuary look (render-only).
            self._sync_weather(strength=0.30, seed=0x4875)

        def _hub_trigger(self, obj):
            obj_type = obj['type']
            if obj_type == 'delve':
                self._open_anima_panel()
            elif obj_type == 'stash':
                self._hub_popup = 'stash'
                self.menu_sys.set_state('stash', prev='_hub')
                self.inv.open = True
                self.inv.open_stash(self.char.stash)
                self.inv.on_stash_change = self._on_stash_change
            elif obj_type == 'vendor':
                # The blacksmith's dismantle forge (BLUEPRINT §24): the same
                # walk-up-and-open flow as the stash chest.
                self._hub_popup = 'blacksmith'
                self.menu_sys.set_state('blacksmith', prev='_hub')
                self.inv.open = True
                self.inv.open_forge()
                self.inv.on_forge_change = self._on_stash_change

        def _update_hub(self, dt):
            cw = rl.get_screen_width()
            ch = rl.get_screen_height()

            # Anima panel — the node chooser popup; freeze the hub behind it
            if self._hub_popup == 'anima':
                if self._chart_screen is None:
                    self._hub_popup = None
                    return
                cw2, ch2 = rl.get_screen_width(), rl.get_screen_height()
                _, _, content = self._anima_layout(cw2, ch2)
                result = self._chart_screen.update(
                    dt, origin=(content.x, content.y),
                    view=(content.width, content.height))
                if isinstance(result, tuple) and result[0] == 'return_hub':
                    # RETURN TO HUB button: from the hub this just closes the
                    # modal (the delve path routes through the same signal).
                    self._on_chart_return_hub()
                    return
                if isinstance(result, tuple) and result[0] == 'select':
                    self._on_chart_select(result[1])
                    return
                if result == 'close' or inp.key_pressed('hub.anima.close', rl.KEY_ESCAPE):
                    self._hub_popup = None
                    return
                # Resume button (saved mid-delve snapshot) — panel bottom edge
                lmb = inp.mouse_pressed('hub.anima.resume', rl.MOUSE_BUTTON_LEFT)
                if (self._chart_resume and self._chart_resume_rect and lmb
                        and rl.check_collision_point_rec(
                            rl.Vector2(float(rl.get_mouse_x()),
                                       float(rl.get_mouse_y())),
                            self._chart_resume_rect)):
                    self._chart_resume = False
                    self._handle_signal('enter_delve')
                return

            if self._hub_popup:
                if self._hub_popup in ('stash', 'blacksmith'):
                    self.inv.update(self._get_char_inventory(), self.stats)
                else:
                    self.menu_sys.update(dt)
                sig = self.menu_sys.signal()
                if sig == 'return_to_hub' or inp.key_pressed('hub.anima.close', rl.KEY_ESCAPE):
                    if self._hub_popup == 'stash':
                        self.inv.open = False
                        self.inv.close_stash()
                        self.inv.on_stash_change = None
                    elif self._hub_popup == 'blacksmith':
                        # offerings ride back to the backpack; on a full
                        # backpack the panel STAYS open (nothing is lost)
                        if not self.inv.close_forge(self._get_char_inventory()):
                            return
                        self.inv.open = False
                        self.inv.on_forge_change = None
                    self._hub_popup = None
                return

            if inp.key_pressed('hub.anima.close', rl.KEY_ESCAPE):
                if self.inv.open:
                    self.inv.close()
                    self.audio.inv_close()
                else:
                    self._go_to_pause()
                return

            if inp.key_pressed('hub.inventory', rl.KEY_I):
                self.inv.toggle()
                if self.inv.open:
                    self.audio.inv_open()
                else:
                    self.audio.inv_close()
            if inp.key_pressed('hub.char_stats', rl.KEY_C):
                self._char_stats_open = not self._char_stats_open
            if inp.key_pressed('hub.combat_log', rl.KEY_L):
                self._combat_log_open = not self._combat_log_open
                self._combat_log_scroll = 0
            self.inv.update(self._get_char_inventory(), self.stats)

            # movement — right click / hold (blocked when inventory is open)
            if not self.inv.open:
                if inp.mouse_pressed('hub.movement', rl.MOUSE_BUTTON_RIGHT):
                    mx, my = rl.get_mouse_x(), rl.get_mouse_y()
                    tile_col, tile_row = self.iso.screen_to_world(mx, my, cw, ch)
                    if math.hypot(tile_col - self.px, tile_row - self.py) >= 0.1:
                        self.dest_col = tile_col
                        self.dest_row = tile_row
                        self._hub_pending_interact = None
                elif rl.is_mouse_button_down(rl.MOUSE_BUTTON_RIGHT):
                    mx, my = rl.get_mouse_x(), rl.get_mouse_y()
                    tile_col, tile_row = self.iso.screen_to_world(mx, my, cw, ch)
                    if math.hypot(tile_col - self.px, tile_row - self.py) >= 0.1:
                        self.dest_col = tile_col
                        self.dest_row = tile_row

            # left click on hub object — walk then interact (blocked when inventory is open)
            if not self.inv.open and inp.mouse_pressed('hub.object_click', rl.MOUSE_BUTTON_LEFT):
                mx, my = rl.get_mouse_x(), rl.get_mouse_y()
                tile_col, tile_row = self.iso.screen_to_world(mx, my, cw, ch)
                for obj in self._hub_objects:
                    if math.hypot(obj['x'] - tile_col, obj['y'] - tile_row) < HUB_CLICK_RADIUS:
                        self.dest_col = obj['x']
                        self.dest_row = obj['y']
                        self._hub_pending_interact = obj
                        break

            # walk
            if self.dest_col is not None:
                self._walk_toward(self.dest_col, self.dest_row, dt, 1.0)
            else:
                self.player_state = 'idle'

            # Free roam — no clamp. The 200×200 floor is bounded only by the
            # grid itself; outside the torch light the darkness punishes.

            # arrive at hub object
            if self._hub_pending_interact:
                obj = self._hub_pending_interact
                if math.hypot(obj['x'] - self.px, obj['y'] - self.py) < HUB_INTERACT_RANGE:
                    self.dest_col = self.dest_row = None
                    self._hub_pending_interact = None
                    self._hub_trigger(obj)

            # darkness is real in the hub too — torches keep you alive
            self._update_hub_darkness(dt)

            self.anim_time += dt
            self.iso.follow(self.px, self.py)

        def _update_hub_darkness(self, dt):
            """Same ramp + DPS as the delve, anchored to the hub's torch lights."""
            if self._god_mode:
                self._hub_dark_timer = 0.0
                return
            lights = self._hub_lights
            best = None
            for light in lights:
                dist = math.hypot(self.px - light['x'], self.py - light['y'])
                # `r` is the VISIBLE LIGHT EDGE (lighting.fs EDGE_SCALE
                # semantics, hub radii are compensated in _HUB_LIGHTS) — the
                # gameplay reach keeps its pre-compensation value
                reach = light['r'] / SHADER_EDGE_SCALE + DELVE_PERSONAL_LIGHT
                if best is None or dist - reach < best[0] - best[1]:
                    best = (dist, reach)
            dist, reach = best
            in_dim = dist > reach and dist <= reach * 1.3
            if dist <= reach:
                self._hub_dark_timer = 0.0
                return
            self._hub_dark_timer += dt * (0.5 if in_dim else 1.0)
            dps_mult = min(1.0, self._hub_dark_timer / 2.5)
            if self._hub_dark_timer > 5.0:
                dps_mult += 0.15 * (self._hub_dark_timer - 5.0)
            if in_dim:
                dps_mult = min(dps_mult, 0.5)
            self.stats['health'] = max(0.0, self.stats['health'] - DELVE_DARKNESS_DPS * dps_mult * dt)
            # the red flash rides the damage ramp — zero while the darkness
            # deals zero DPS, not the instant you step out
            self.hit_flash = max(self.hit_flash, 0.18 * min(1.0, dps_mult))
            if self.stats['health'] <= 0:
                self._permadeath()

        def _hub_actor_entities(self):
            """Player + hub NPC + stash entity specs — shared between the scene
            draw and the above-darkness actor redraw."""
            player_sprites = self._player_sprites.get(self.char.looks,
                             self._player_sprites.get('fighter', {}))
            player_entity = {
                'col': self.px, 'row': self.py,
                'sprite': player_sprites.get('default walk' if self.player_state == 'walk' else 'default idle'),
                'direction': self.player_facing,
                'time': self.anim_time,
                'idle': self.player_state == 'idle',
                'scale': 1, 'shadow': True,
                'big_art': True,      # legacy character canvas keeps ENTITY_BASE size
            }
            actors = []
            # Blacksmith anvil — inert waypoint (the vendor's shop died
            # with the gold economy); atlas prop art, tile-riding size
            if self._anvil_spr:
                actors.append({
                    'col': _VENDOR_POS[0], 'row': _VENDOR_POS[1],
                    'sprite': self._anvil_spr,
                    'direction': 'S', 'time': 0.0,
                    'idle': True, 'scale': 0.7, 'shadow': False,
                })
            # Stash chest
            if self._chest_spr:
                actors.append({
                    'col': _STASH_POS[0], 'row': _STASH_POS[1],
                    'sprite': self._chest_spr,
                    'direction': 'S', 'time': 0.0,
                    'idle': True, 'scale': 0.7, 'shadow': False,
                })
            return player_entity, actors

