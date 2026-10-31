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

"""Input dispatch for :class:`core.game.Game`."""

import pyray as rl

from systems import input as inp
from core.game import *


class InputMixin:
    def poll_frame_input(self):
        """Drain raylib's char queue once per RENDER frame (call from main loop).

        raylib clears its char-pressed queue at every PollInputEvents (once per
        render frame), so the queue must be drained here and routed to the
        active per-tick consumer: the dev console or the menu text fields.
        """
        while True:
            ch = rl.get_char_pressed()
            if not ch:
                break
            if 32 <= ch < 127:
                if self._console_open:
                    if len(self._console_pending) < 64:
                        self._console_pending.append(chr(ch))
                else:
                    self.menu_sys.char_name_input.push(chr(ch))

    def update(self, dt):
        s = self.menu_sys.settings
        self.audio.set_sfx_volume(s.volume / 100.0)
        self.audio.set_music_volume(s.music_volume / 100.0)
        self.audio.tick(dt)
        self._update_mouse_transform()

        if inp.key_pressed(self,rl.KEY_GRAVE) and self.state != STATE_EDITOR:
            self._console_open = not self._console_open
            self._console_buf = ''

        if inp.key_pressed(self,rl.KEY_F4):
            self.menu_sys.settings.debug_overlay = not self.menu_sys.settings.debug_overlay

        if inp.key_pressed(self,rl.KEY_F5):
            self._take_screenshot()

        if self._console_open:
            self._update_console()
            return

        if self.state == STATE_LOADING:
            self._handle_loading(dt)
            return

        if self.state in (STATE_MENU, STATE_PAUSED):
            prev_menu_state = self.menu_sys.state
            self.menu_sys.update(dt)
            if self.state == STATE_MENU and self.menu_sys.state in ('inventory', 'stash'):
                # The menu-context inventory/bank screens render through the
                # interactive InventoryUI art panel (drawn by frame_render).
                self.inv.open = True
                if self.menu_sys.state == 'stash' and not self.inv.stash_open:
                    self.inv.open_stash(self.char.stash)
                    self.inv.on_stash_change = self._on_stash_change
                self.inv.update(self._get_char_inventory(), self.stats)
            elif prev_menu_state in ('inventory', 'stash') \
                    and self.menu_sys.state not in ('inventory', 'stash'):
                self.inv.close()
                self.inv.close_stash()
                self.inv.on_stash_change = None
            self._handle_signal(self.menu_sys.signal())
            return

        if self.state == STATE_EDITOR:
            if self._editor:
                self._editor.update(dt)
                if self._editor.should_exit():
                    if self._editor.was_saved():
                        self._custom_map = self._editor.get_map()
                    self._editor.unload()
                    self._editor = None
                    self._go_to_menu('main')
            return

        if self.state in (STATE_DEAD, STATE_EXTRACTED):
            if inp.key_pressed(self,rl.KEY_ENTER) or inp.key_pressed(self,rl.KEY_ESCAPE):
                self._go_to_menu('main')
            return

        if self.state == STATE_HUB:
            self._update_hub(dt)
            return

        if self.state == STATE_PLAYING:
            if self._delve is not None and inp.key_pressed(self,rl.KEY_TAB):
                self._minimap_open = not self._minimap_open
            if self._minimap_open:
                if inp.key_pressed(self,rl.KEY_ESCAPE):
                    self._minimap_open = False
                chart = self._delve.get('chart')
                if chart is None:
                    self._minimap_open = False
                else:
                    from ui.delve_chart import DelveChartScreen
                    if self._minimap is None:
                        self._minimap = DelveChartScreen(self)
                    if self._minimap.chart is not chart:
                        self._minimap.open(chart, selectable_ids=(),
                                           title='Anima Chart', closable=False)
                    self._minimap.update(dt)
                return
            if inp.key_pressed(self,rl.KEY_ESCAPE):
                if self.inv.open:
                    self.inv.close()
                    self.audio.inv_close()
                else:
                    self._go_to_pause()
                return
            if inp.key_pressed(self,rl.KEY_I):
                self.inv.toggle()
                if self.inv.open:
                    self.audio.inv_open()
                else:
                    self.audio.inv_close()
            if inp.key_pressed(self,rl.KEY_C):
                self._char_stats_open = not self._char_stats_open
            if inp.key_pressed(self,rl.KEY_L):
                self._combat_log_open = not self._combat_log_open
                self._combat_log_scroll = 0
            if not self.inv.open and not self._delve_chart_is_open():
                # NOTE: the delve Q/E tool keybinds (flares, dynamite) were
                # removed. Q/W/E/R belong to the gem ability slots below and
                # T is the flask - see systems/flasks.py. Both are blocked
                # while the Anima panel is open (modal decision UI).
                for _gk in gems.GEM_SLOTS:
                    if inp.key_pressed(self,getattr(rl, 'KEY_' + _gk)):
                        self._use_gem_ability(_gk)
            if inp.key_pressed(self,rl.KEY_T) and not self.inv.open \
                    and not self._delve_chart_is_open():
                self._use_flask()
            self.inv.update(self.inventory, self.stats)
            self._update_game(dt)

    def _dispatch_game_mouse_input(self, cw, ch):
        # The Anima panel is modal: while it is open, world clicks (move /
        # attack / interact / the Pulse heart) must not fire - the panel
        # overlaps the Pulse heart on screen, and an unguarded click on the
        # panel used to re-trigger the heart (or worse, `_delve_descend`).
        if self._delve_chart_is_open():
            return
        if not self.inv.open and not self._hud_over_action(
                rl.get_mouse_x(), rl.get_mouse_y()):
            if inp.mouse_pressed(self, rl.MOUSE_BUTTON_RIGHT):
                mx, my = rl.get_mouse_x(), rl.get_mouse_y()
                tile_col, tile_row = self.iso.screen_to_world(mx, my, cw, ch)
                if math.hypot(tile_col - self.px, tile_row - self.py) >= 0.1:
                    tc, tr = int(tile_col), int(tile_row)
                    is_wall = (0 <= tc < len(self.map) and 0 <= tr < len(self.map[0])
                               and self.map[tc][tr] != 0) if self.map else False
                    if is_wall:
                        self.click_marker = {'col': tile_col, 'row': tile_row,
                                             'timer': 0.3, 'blocked': True}
                    else:
                        self.dest_col = tile_col
                        self.dest_row = tile_row
                        self.attack_target = None
                        self.interact_target = None
                        self.drop_target = None
                        self.click_marker = {'col': tile_col, 'row': tile_row, 'timer': 0.6}
                        self._flash_hud('move')
            elif rl.is_mouse_button_down(rl.MOUSE_BUTTON_RIGHT):
                mx, my = rl.get_mouse_x(), rl.get_mouse_y()
                tile_col, tile_row = self.iso.screen_to_world(mx, my, cw, ch)
                tc, tr = int(tile_col), int(tile_row)
                is_wall = (0 <= tc < len(self.map) and 0 <= tr < len(self.map[0])
                           and self.map[tc][tr] != 0) if self.map else False
                if math.hypot(tile_col - self.px, tile_row - self.py) >= 0.1 and not is_wall:
                    self.dest_col = tile_col
                    self.dest_row = tile_row
                    self.attack_target = None
                    self.interact_target = None
                    self.drop_target = None
                    self._flash_hud('move')

        if (not self.inv.open and not self._minimap_open
                and not self._hud_over_action(rl.get_mouse_x(), rl.get_mouse_y())
                and inp.mouse_pressed(self, rl.MOUSE_BUTTON_LEFT)):
            mx_s, my_s = rl.get_mouse_x(), rl.get_mouse_y()
            tile_col, tile_row = self.iso.screen_to_world(mx_s, my_s, cw, ch)
            clicked_drop = None
            for gi, rx, ry, rw, rh in self._drop_label_rects:
                if rx <= mx_s < rx + rw and ry <= my_s < ry + rh:
                    clicked_drop = gi
                    break

            if (clicked_drop is None and self._delve is not None
                    and self._delve['state'] == 'ready'):
                ts = max(1, int(ISO_W * self.iso.scale))
                ent_px = ENTITY_BASE * self.iso.scale
                raw_sx, raw_sy = self.iso.world_to_screen(
                    self._delve['pulse_x'], self._delve['pulse_y'], cw, ch)
                pulse_cx = raw_sx + ts // 2
                pulse_cy = raw_sy + ts // 4
                if math.hypot(mx_s - pulse_cx, my_s - pulse_cy) < ent_px * 0.6:
                    kids = self._delve_children()
                    if kids:
                        self._open_delve_anima_panel()
                    else:
                        self._delve_descend()
                    return True

            clicked_enemy = self._find_enemy_near(mx_s, my_s, cw, ch)
            clicked_obj = self._find_interact_object(
                tile_col, tile_row, radius=DELVE_CLICK_RADIUS)

            if clicked_drop:
                self.dest_col = clicked_drop['x']
                self.dest_row = clicked_drop['y']
                self.attack_target = None
                self.interact_target = None
                self.drop_target = clicked_drop
                self.click_marker = None
            elif clicked_obj:
                self.interact_target = clicked_obj
                self.drop_target = None
                self.attack_target = None
                self.dest_col = clicked_obj['x']
                self.dest_row = clicked_obj['y']
                self.click_marker = None
            elif clicked_enemy:
                self.attack_target = clicked_enemy
                self.interact_target = None
                self.drop_target = None
                self.dest_col = self.dest_row = None
                self.click_marker = None
                self._flash_hud('attack')
        return False

    def _update_console(self):
        if self._console_esc.pressed(rl.KEY_ESCAPE):
            self._console_open = False
            return
        if self._console_bs.pressed(rl.KEY_BACKSPACE) and self._console_buf:
            self._console_buf = self._console_buf[:-1]
        for ch in self._console_pending:
            self._console_buf += ch
        self._console_pending.clear()
        if inp.key_pressed(self,rl.KEY_UP) and self._console_history:
            self._console_history_idx = max(0, self._console_history_idx - 1)
            if self._console_history_idx < len(self._console_history):
                self._console_buf = self._console_history[self._console_history_idx]
        if inp.key_pressed(self,rl.KEY_DOWN):
            if self._console_history_idx < len(self._console_history) - 1:
                self._console_history_idx += 1
                self._console_buf = self._console_history[self._console_history_idx]
            else:
                self._console_history_idx = len(self._console_history)
                self._console_buf = ''
        if self._console_enter.pressed(rl.KEY_ENTER):
            cmd = self._console_buf.strip()
            self._console_buf = ''
            if cmd:
                self._console_history.append(cmd)
                if len(self._console_history) > 50:
                    self._console_history = self._console_history[-50:]
                self._console_history_idx = len(self._console_history)
                self._exec_console(cmd)
