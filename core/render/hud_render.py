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
    ANGEL_STREAK_WINDOW,
    ATTACK_RANGE,
    DARKNESS_AMBIENT,
    DELVE_PERSONAL_LIGHT,
    DESCEND_ATTRIBUTES,
    EQUIP_SLOT_LABELS,
    ITEMS,
    MELEE_RANGE,
    PULSE_OFFSET_X,
    PULSE_OFFSET_Y,
    STATE_DEAD,
    STREAK_BIG_POP_SECS,
    STREAK_LOST_FADE,
    STREAK_POP_SECS,
    STREAK_POP_TIME,
    VESSEL_DEFS,
    VESSEL_UNLOCKS,
)
from core.iso_engine import ISO_W
from entities.progression import compute_derived_stats
from entities.descend import compute_perk_bonuses
from entities.zombies import DETECT_RANGE
from systems import flasks, gems
from systems import itemgen
from ui import fonts, icons
from ui.inventory_ui import _rot_col
from ui.menus import _btn
from entities.progression import task_def
from systems.items import ITEMS, EQUIP_SLOT_LABELS


class HudRenderMixin:
    def _draw_hud_flash(self, key: str, cx: float, top_y: float, w: float):
        """active_action.png strip centred above a HUD action slot while its
        flash timer runs."""
        t = self._hud_flash.get(key, 0.0)
        if t <= 0:
            return
        at = self._ui.get('active_action')
        if not (at and at.id > 0):
            return
        ow = int(w * 0.75)
        oh = max(1, int(ow * 22.0 / 96.0))
        rl.draw_texture_pro(at,
            rl.Rectangle(0, 0, float(at.width), float(at.height)),
            rl.Rectangle(float(cx - ow / 2), float(top_y - oh - 3),
                         float(ow), float(oh)),
            rl.Vector2(0, 0), 0.0, rl.WHITE)
    def _draw_dark_danger(self, cw: int, ch: int, lights: list, dark_timer: float):
        """Red danger pulse while the player stands outside every light."""
        in_light = False
        for light in lights:
            reach = light['r'] + DELVE_PERSONAL_LIGHT
            if math.hypot(self.px - light['x'], self.py - light['y']) <= reach:
                in_light = True
                break
        if lights and not in_light:
            pulse = (math.sin(dark_timer * 4.0) + 1.0) / 2.0
            danger_alpha = int(60 * pulse)
            rl.draw_rectangle(0, 0, cw, ch, rl.Color(180, 0, 0, danger_alpha))
    def _draw_anima_panel(self, cw, ch):
        """Dim the scene (inventory-style) and draw the framed panel.

        Returns (content_rect, x_clicked). The big X sits on the panel's
        top-right corner; callers handle the close in their draw phase.
        """
        px, py, content = self._anima_layout(cw, ch)
        size = self.ANIMA_PANEL_SIZE
        rl.draw_rectangle(0, 0, cw, ch, rl.Color(0, 0, 0, 160))
        tex = self._anima_panel_tex
        if tex and tex.id > 0:
            src = rl.Rectangle(0, 0, float(tex.width), float(tex.height))
            dst = rl.Rectangle(float(px), float(py), float(size), float(size))
            rl.draw_texture_pro(tex, src, dst, rl.Vector2(0, 0), 0.0, rl.WHITE)
        else:
            rl.draw_rectangle(px, py, size, size, rl.Color(16, 14, 18, 255))
            rl.draw_rectangle_lines(px, py, size, size, rl.Color(90, 74, 28, 255))
        # big X — straddling the panel's top-right corner
        x_r = rl.Rectangle(float(px + size - 40), float(py - 12), 40.0, 40.0)
        x_clicked = _btn(x_r, 'X', 20)
        return content, x_clicked
    def _draw_character_level(self, cw: int, scale_font, pad: int = 16):
        """Top-left LEVEL readout, under the character name.

        One of the two display sites for the value. It renders
        ``itemgen.format_character_level(self.inventory)`` verbatim — the same
        accessor and the same compact ``LVL n`` string the inventory panel header
        uses — so the two sites cannot drift apart. An empty loadout renders as
        ``LVL 0`` like any other value; the accessor never divides by zero.
        """
        fs = scale_font(14)
        # sits below the name/portrait block, above the buff indicator row
        fonts.draw(itemgen.format_character_level(self.inventory),
                   pad + scale_font(26), pad + scale_font(30), fs,
                   rl.Color(220, 190, 90, 235))

    def _draw_delve_hud(self, cw: int, ch: int, scale_font):
        """Depth counter and darkness warning overlay."""
        if self._delve is None:
            return
        d = self._delve

        # Depth counter — top center
        label       = f"Anima Depth {d['depth']}"
        fs          = scale_font(20)
        label_width = fonts.measure(label, fs)
        fonts.draw(label, cw // 2 - label_width // 2, 14, fs,
                   rl.Color(80, 200, 255, 230))

        # Darkness exposure meter — top-right
        if d['dark_timer'] > 0:
            MAX_EXPOSURE = 10.0
            exposure_pct = min(1.0, d['dark_timer'] / MAX_EXPOSURE)
            meter_w = scale_font(120)
            meter_h = scale_font(14)
            meter_x = cw - meter_w - scale_font(16)
            meter_y = scale_font(48)
            exp_col = rl.Color(int(255 * exposure_pct), int(180 * (1 - exposure_pct)), 40, 220)
            rl.draw_rectangle(meter_x, meter_y, meter_w, meter_h, rl.Color(0, 0, 0, 0x99))
            rl.draw_rectangle(meter_x, meter_y, int(meter_w * exposure_pct), meter_h, exp_col)
            rl.draw_rectangle_lines(meter_x, meter_y, meter_w, meter_h, rl.Color(80, 40, 40, 180))
            exp_label = f"Darkness  {d['dark_timer']:.1f}s"
            exp_fs = scale_font(11)
            fonts.draw(exp_label, meter_x + 4, meter_y - exp_fs - 2, exp_fs, rl.Color(200, 160, 80, 200))

        # Darkness exposure is represented by the meter above; the old
        # "DARKNESS — TAKE COVER" overlay is intentionally not drawn.
        # The flare/dynamite tool indicator row was removed with the tools.
    def _draw_debug_rings(self, objects, click_r: float, cw: int, ch: int,
                          interact_r: float = None):
        """Perf-overlay visualization of the click hitbox (orange) and,
        when given, the walk-in trigger range (green) around each object."""
        step_x, step_y = self.iso._steps()
        half = int(ISO_W * self.iso.scale) / 2   # tile anchor → diamond centre
        s2 = 1.41421356237  # (cosθ − sinθ) / (cosθ + sinθ) amplitudes pick up √2

        def ring(x, y, r, col):
            px, py = self.iso.world_to_screen(x, y, cw, ch)
            cx = px + half
            cy = py + half
            rx = r * step_x * s2
            ry = r * step_y * s2
            rl.draw_ellipse_lines(int(cx), int(cy), rx, ry, col)

        for obj in objects:
            ring(obj['x'], obj['y'], click_r, rl.Color(255, 160, 60, 200))
            if interact_r is not None:
                ring(obj['x'], obj['y'], interact_r, rl.Color(120, 255, 120, 160))
    def _drop_label_info(self, gi):
        """(text, colour) for a ground drop's label: the first item's name
        in its rarity colour, plus '+ N more' when the drop holds extra
        items. Unidentified items show their base name (the tooltip does
        the spoiler-free hinting)."""
        slot = gi.get('items', [None])[0]
        if not slot:
            return None
        item_id = slot['item']
        idef    = ITEMS.get(item_id, {})
        inst    = slot.get('instance_data')
        rarity  = idef.get('rarity', 'common')
        unid    = inst is not None and not itemgen.is_identified(slot)
        if inst:
            rarity = inst.get('rarity', rarity)
        title = (idef.get('name', item_id) if unid else
                 (inst['display_name'] if inst else idef.get('name', item_id)))
        extra = len(gi.get('items', [])) - 1
        if extra > 0:
            title = f'{title} +{extra} more'
        return title, self._rarity_color(rarity)

    def _labels_visible(self) -> bool:
        """Ground labels show always (setting) or while Alt is held."""
        if self.menu_sys.settings.item_labels:
            return True
        return (rl.is_key_down(rl.KEY_LEFT_ALT)
                or rl.is_key_down(rl.KEY_RIGHT_ALT))

    def _draw_drop_labels(self, cw, ch):
        """Always-visible name labels above ground drops (item_labels
        setting, or hold Alt). Drawn in the above-darkness overlay so the
        gloom never eats them."""
        if not self._labels_visible():
            return
        tile_size = int(ISO_W * self.iso.scale)
        for gi in self.ground_items:
            if gi.get('type') != 'drop' or not gi.get('items'):
                continue
            info = self._drop_label_info(gi)
            if not info:
                continue
            text, col = info
            sx, sy = self.iso.world_to_screen(gi['x'], gi['y'], cw, ch)
            label_x = sx + tile_size // 2
            label_y = sy - 6
            fs = max(13, int(16 * (cw / 1920)))
            fonts.label(text, label_x, label_y, fs, col)

    def _draw_drop_overlay(self, cw, ch):
        """Re-drop ground sprites above the darkness mask, with name
        labels when labels are visible."""
        tile_size  = int(ISO_W * self.iso.scale)
        for gi in self.ground_items:
            if gi.get('type') != 'drop' or not gi.get('items'):
                continue
            sx, sy = self.iso.world_to_screen(gi['x'], gi['y'], cw, ch)
            tile_center_x = sx + tile_size // 2
            tile_center_y = sy + tile_size // 2
            # Ground sprite stays visible above the darkness overlay
            self._draw_ground_item_sprite(gi, tile_center_x, tile_center_y, tile_size)
        self._draw_drop_labels(cw, ch)
    def _draw_aura_range(self, cw, ch):
        """Fire Aura (E-gem active) ground ring while the buff runs — the
        radius is snapshotted at cast time."""
        if self._fire_aura_timer <= 0 or self._fire_aura_radius <= 0:
            return
        radius = self._fire_aura_radius

        step_x, step_y = self.iso._steps()
        tile_size      = int(ISO_W * self.iso.scale)
        sx, sy   = self.iso.world_to_screen(self.px, self.py, cw, ch)
        center_x = sx + tile_size // 2
        center_y = sy + tile_size // 2
        radius_x = int(radius * step_x * 2)
        radius_y = int(radius * step_y * 2)

        pulse      = (math.sin(self.raid_time * 3.0) + 1.0) / 2.0
        fill_alpha = int(4 + 4 * pulse)
        ring_alpha = int(35 + 35 * pulse)

        rl.draw_ellipse(center_x, center_y, float(radius_x), float(radius_y),
                        rl.Color(255, 100, 20, fill_alpha))
        rl.draw_ellipse_lines(center_x, center_y, float(radius_x),     float(radius_y),
                              rl.Color(255, 130, 30, ring_alpha))
        rl.draw_ellipse_lines(center_x, center_y, float(radius_x + 1), float(radius_y + 1),
                              rl.Color(255, 130, 30, ring_alpha // 2))
    def _draw_enemy_bars(self, cw, ch):
        tile_size    = int(ISO_W * self.iso.scale)
        bar_w  = max(20, tile_size // 8)
        bar_h  = 2
        ring_r = max(14, tile_size // 7)
        for z in self.zombies:
            if z['health'] <= 0 or z.get('death_timer') is not None:
                continue
            if z.get('hit_count', 0) == 0:
                continue
            sx, sy = self.iso.world_to_screen(z['x'], z['y'], cw, ch)
            center_x = sx + tile_size // 2
            center_y = sy + tile_size // 2
            pct   = max(0.0, z['health'] / z['max_health'])
            bar_x = center_x - bar_w // 2
            bar_y = sy + tile_size // 4 - bar_h - 6

            # Status effect indicator dots above HP bar
            dot_radius = 4
            dot_gap = 10
            dot_x = bar_x
            dot_y = bar_y - dot_gap
            if z.get('frozen_timer', 0) > 0:
                rl.draw_circle(dot_x, dot_y, dot_radius, rl.Color(140, 200, 255, 220))
                dot_x += dot_gap
            if z.get('burning_timer', 0) > 0:
                rl.draw_circle(dot_x, dot_y, dot_radius, rl.Color(255, 140, 40, 220))
                dot_x += dot_gap
            if z.get('rot_stacks', 0) > 0:
                stacks = z.get('rot_stacks', 0)
                rl.draw_circle(dot_x, dot_y, dot_radius, rl.Color(160, 200, 80, 220))
                fonts.draw(str(stacks), dot_x - 3, dot_y - 4, 9, rl.WHITE)
                dot_x += dot_gap
            if z.get('cold_stacks', 0) > 0 and z.get('frozen_timer', 0) <= 0:
                stacks = z.get('cold_stacks', 0)
                rl.draw_circle(dot_x, dot_y, dot_radius, rl.Color(180, 210, 255, 200))
                fonts.draw(str(stacks), dot_x - 3, dot_y - 4, 9, rl.WHITE)
                dot_x += dot_gap

            rl.draw_rectangle(bar_x, bar_y, bar_w,            bar_h, rl.Color(40, 10, 10, 200))
            rl.draw_rectangle(bar_x, bar_y, int(bar_w * pct), bar_h,
                              rl.Color(200, 50, 50, 230) if pct > 0.4 else rl.Color(240, 200, 30, 230))
            rl.draw_rectangle_lines(bar_x, bar_y, bar_w, bar_h, rl.Color(60, 20, 20, 180))
    def _draw_dmg_numbers(self, cw, ch):
        _DMG_NUM_DUR = 1.2
        tile_size = int(ISO_W * self.iso.scale)
        for n in self._dmg_numbers:
            progress = n['timer'] / _DMG_NUM_DUR
            alpha    = int(255 * (1.0 - progress ** 0.5))
            rise     = int(n['timer'] * 45)
            sx, sy   = self.iso.world_to_screen(n['x'], n['y'], cw, ch)
            center_x   = sx + tile_size // 2
            center_y   = sy + tile_size // 4 - rise
            text       = 'IMMUNE' if n['value'] < 0 else ('MISS' if n['value'] == 0 else str(n['value']))
            font_size  = max(12, int(13 * (cw / 1920)))
            text_width = fonts.measure(text, font_size)
            col        = n['color']
            fonts.draw(text, center_x - text_width // 2, center_y, font_size,
                       rl.Color(col.r, col.g, col.b, alpha))
    def _draw_click_marker(self, cw, ch):
        if not self.click_marker:
            return
        blocked = self.click_marker.get('blocked', False)
        duration = 0.3 if blocked else 0.6
        t   = self.click_marker['timer'] / duration
        col = self.click_marker['col']
        row = self.click_marker['row']
        sx, sy = self.iso.world_to_screen(col, row, cw, ch)
        tile_size = int(ISO_W * self.iso.scale)
        center_x  = sx + tile_size // 2
        center_y  = sy + tile_size // 2
        alpha = int(255 * t)
        # Code-drawn click marker: an expanding, fading ring on the tile
        # (replaces the old highlight sprites).
        ring_r = tile_size * (0.25 + 0.45 * (1.0 - t))
        ring_col = rl.Color(230, 60, 60, alpha) if blocked \
            else rl.Color(90, 170, 255, alpha)
        rl.draw_ring(rl.Vector2(float(center_x), float(center_y)),
                     max(1.0, ring_r - 3.0), ring_r + 3.0, 0, 360, 36, ring_col)
        if blocked:
            fonts.draw('BLOCKED', center_x - fonts.measure('BLOCKED', 14) // 2,
                       center_y - 28, 14, rl.Color(255, 120, 120, alpha))
    @staticmethod
    def _draw_bar_tex(fill_tex, frame_tex, bar_x, bar_y, bar_w, bar_h, pct, fill_color=None,
                      pad_top=2, pad_bottom=2, pad_left=2, pad_right=30):
        fill_x     = bar_x + pad_left
        fill_y     = bar_y + pad_top
        fill_width  = bar_w - pad_left - pad_right
        fill_height = bar_h - pad_top - pad_bottom
        rl.draw_rectangle(fill_x, fill_y, fill_width, fill_height, rl.Color(4, 4, 12, 240))
        if pct > 0.005:
            filled_px = int(fill_width * pct)
            if fill_color:
                rl.draw_rectangle(fill_x, fill_y, filled_px, fill_height, fill_color)
            elif fill_tex and fill_tex.id > 0:
                src = rl.Rectangle(0.0, 0.0, fill_tex.width * pct, float(fill_tex.height))
                dst = rl.Rectangle(float(fill_x), float(fill_y), float(filled_px), float(fill_height))
                rl.draw_texture_pro(fill_tex, src, dst, rl.Vector2(0, 0), 0.0, rl.WHITE)
        if frame_tex and frame_tex.id > 0:
            src = rl.Rectangle(0.0, 0.0, float(frame_tex.width), float(frame_tex.height))
            dst = rl.Rectangle(float(bar_x), float(bar_y), float(bar_w), float(bar_h))
            rl.draw_texture_pro(frame_tex, src, dst, rl.Vector2(0, 0), 0.0, rl.WHITE)
    @staticmethod
    def _draw_slot_frame(tex, frame_idx, sx, sy, size, tint=None):
        effective_tint = tint if tint is not None else rl.WHITE
        if tex and tex.id > 0:
            frame_width = tex.width // 5
            src = rl.Rectangle(float(frame_idx * frame_width), 0.0, float(frame_width), float(tex.height))
            dst = rl.Rectangle(float(sx), float(sy), float(size), float(size))
            rl.draw_texture_pro(tex, src, dst, rl.Vector2(0, 0), 0.0, effective_tint)
        else:
            rl.draw_rectangle(sx, sy, size, size, rl.Color(0, 0, 0, 0x99))
            rl.draw_rectangle_lines(sx, sy, size, size, rl.Color(0x99, 0x99, 0x99, 220))
    def _draw_char_stats(self, cw, ch):
        char         = self.char
        equip_fx     = self._equipped_bonuses()
        bonuses      = compute_perk_bonuses(
            char.perks, char.descend,
            item_bonuses=itemgen.aggregate_item_bonuses(self.inventory))
        item_attr    = {a: equip_fx.get(a, 0) for a in DESCEND_ATTRIBUTES}
        derived      = compute_derived_stats(
            char.descend, bonuses, item_bonuses=item_attr, looks=char.looks)

        PANEL_W = 360
        PAD     = 18
        LINE_H  = 24
        FS      = 18
        FS_HDR  = 28

        dr_pct   = int(equip_fx['damage_reduction'] * 100)
        spd_pct  = int(equip_fx['move_speed']        * 100)
        es_val   = derived.get('max_energy_shield', 0)

        atk_spd  = int((self.stats.get('_attack_speed_pct', 0.0) + equip_fx['attack_speed_pct']) * 100)
        cdr_pct  = int((self.stats.get('_cooldown_recovery_pct', 0.0) + equip_fx['cooldown_recovery_pct']) * 100)
        crit_pct = int((self.stats.get('_crit_chance', 0.0) + equip_fx['crit_chance']) * 100)
        abcrit_p = int((self.stats.get('_ability_crit_chance', 0.0) + equip_fx['ability_crit_chance']) * 100)

        # (label, value, icon_name)
        stat_rows = []
        def s(label, value, icon): stat_rows.append((label, value, icon))

        s('Health',        f"{int(self.stats['health'])} / {int(self.stats['max_health'])}", 'hp')
        if es_val > 0:
            s('Energy Shield', f"{int(self.stats.get('energy_shield', 0))} / {es_val}", 'energy_shield')
        stat_rows.append(('div', '', ''))
        s('Evasion',       str(derived['evasion']), 'evasion')
        s('Accuracy',      str(derived['accuracy']), 'accuracy')
        s('Melee Dmg',     f"+{int((derived['melee_dmg_mult'] - 1.0) * 100)}%", 'melee')
        s('Attack Speed',  f"+{atk_spd}%", 'attack_speed')
        s('Cooldown Red.', f"+{cdr_pct}%", 'cooldown_reduction')
        s('Crit Chance',   f"{crit_pct}%", 'crit_chance')
        s('Ability Crit',  f"{abcrit_p}%", 'ability_crit')
        s('Dmg Reduction', f"{dr_pct}%", 'defense')
        s('Move Speed',    f"+{spd_pct}%" if spd_pct else "—", 'move_speed')
        stat_rows.append(('div', '', ''))
        s('Fire Resist',   f"{int(derived.get('resist_pct', {}).get('fire', 0) * 100)}%", 'fire_resist')
        s('Cold Resist',   f"{int(derived.get('resist_pct', {}).get('cold', 0) * 100)}%", 'cold_resist')
        s('Lightn Resist', f"{int(derived.get('resist_pct', {}).get('lightning', 0) * 100)}%", 'lightning_resist')
        s('Rot Resist',    f"{int(derived.get('resist_pct', {}).get('rot', 0) * 100)}%", 'rot_resist')
        stat_rows.append(('div', '', ''))
        s('Vessel',       VESSEL_DEFS[char.looks]['name'], char.looks)
        for attr in ('dexterity', 'endurance', 'strength', 'cunning', 'essence', 'nerve', 'destiny'):
            # Derived total (allocation + equipped gear), not the raw
            # allocation: the allocation screen is gone, so gear is the only
            # source of attribute growth and must move this number.
            s(attr.capitalize()[:4], str(int(derived.get(attr, char.descend.get(attr, 0)))), attr)

        equipped = {slot: entry for slot, entry in self.inventory['equipped'].items() if entry}
        if equipped:
            stat_rows.append(('div', '', ''))
            for slot_key, entry in equipped.items():
                item_name = ITEMS.get(entry['item'], {}).get('name', entry['item'])
                slot_name = EQUIP_SLOT_LABELS.get(slot_key, slot_key.capitalize())
                stat_rows.append((slot_name, item_name[:22], slot_key))

        if self._incoming_dmg_by_type:
            stat_rows.append(('div', '', ''))
            total_in = sum(self._incoming_dmg_by_type.values())
            for dtype, dmg in sorted(self._incoming_dmg_by_type.items()):
                pct = dmg / total_in * 100 if total_in > 0 else 0.0
                stat_rows.append((f"  {dtype.capitalize()}", f"{int(dmg)}  ({pct:.0f}%)", dtype))
            stat_rows.append(('  Total Incoming', str(int(total_in)), 'skull'))

        panel_h = PAD * 2 + FS_HDR + 10 + (len(stat_rows) + 1) * LINE_H + 4
        panel_x = cw // 2 - PANEL_W // 2
        panel_y = ch // 2 - panel_h // 2

        # D2-style stone panel
        rl.draw_rectangle(panel_x, panel_y, PANEL_W, panel_h, rl.Color(0, 0, 0, 250))
        rl.draw_rectangle(panel_x + 2, panel_y + 2, PANEL_W - 4, panel_h - 4, rl.Color(0, 0, 0, 0x99))
        rl.draw_rectangle_lines_ex(rl.Rectangle(float(panel_x + 1), float(panel_y + 1),
                                                float(PANEL_W - 2), float(panel_h - 2)),
                                   1, rl.Color(0xE0, 0xE0, 0xE0, 200))
        rl.draw_rectangle_lines_ex(rl.Rectangle(float(panel_x), float(panel_y),
                                                float(PANEL_W), float(panel_h)),
                                   1, rl.Color(0xFF, 0xFF, 0xFF, 220))

        # Corner white accents
        cl, cg = 14, 5
        for cx, cy, dx, dy in [
            (panel_x + cg, panel_y + cg, 1, 1),
            (panel_x + PANEL_W - cg, panel_y + cg, -1, 1),
            (panel_x + cg, panel_y + panel_h - cg, 1, -1),
            (panel_x + PANEL_W - cg, panel_y + panel_h - cg, -1, -1),
        ]:
            rl.draw_line(cx, cy, cx + dx * cl, cy, rl.Color(0xE0, 0xE0, 0xE0, 200))
            rl.draw_line(cx, cy, cx, cy + dy * cl, rl.Color(0xE0, 0xE0, 0xE0, 200))

        mx, my = rl.get_mouse_x(), rl.get_mouse_y()
        hovered_label = None
        row_y = panel_y + PAD

        # Header row
        hdr_text = char.name
        icons.draw(char.looks, panel_x + PAD, row_y + 4, 22)
        tw = fonts.measure(hdr_text, FS_HDR)
        fonts.draw(hdr_text, panel_x + PANEL_W // 2 - tw // 2, row_y, FS_HDR,
                   rl.Color(0xFF, 0xFF, 0xFF, 255))
        row_y += FS_HDR + 4
        rl.draw_line(panel_x + PAD, row_y, panel_x + PANEL_W - PAD, row_y,
                     rl.Color(0xE0, 0xE0, 0xE0, 180))
        row_y += 8

        for label, value, icon_name in stat_rows:
            if label == 'div':
                rl.draw_line(panel_x + PAD, row_y + LINE_H // 2,
                             panel_x + PANEL_W - PAD, row_y + LINE_H // 2,
                             rl.Color(40, 50, 40, 160))
                row_y += LINE_H
                continue

            if icon_name:
                icons.draw(icon_name, panel_x + PAD, row_y + 3, 16)
                lx = panel_x + PAD + 24
            else:
                lx = panel_x + PAD

            fonts.draw(label, lx, row_y + (LINE_H - FS) // 2, FS,
                       rl.Color(140, 170, 140, 255))
            value_x = panel_x + PANEL_W - PAD - fonts.measure(value, FS)
            fonts.draw(value, value_x, row_y + (LINE_H - FS) // 2, FS,
                       rl.Color(220, 220, 200, 255))
            hit_rect = rl.Rectangle(float(panel_x + PAD), float(row_y),
                                    float(PANEL_W - 2 * PAD), float(LINE_H))
            if label in self._STAT_DESC and rl.check_collision_point_rec(
                    rl.Vector2(float(mx), float(my)), hit_rect):
                hovered_label = label
            row_y += LINE_H

        # Tooltip for hovered stat
        if hovered_label:
            desc = self._STAT_DESC[hovered_label]
            tw = fonts.measure(desc, 17) + 16
            th = 30
            tx = min(mx + 16, cw - tw - 8)
            ty = min(my - th - 8, ch - th - 8)
            rl.draw_rectangle(int(tx), int(ty), int(tw), int(th), rl.Color(0, 0, 0, 0x99))
            rl.draw_rectangle_lines(int(tx), int(ty), int(tw), int(th), rl.Color(0xE0, 0xE0, 0xE0, 255))
            fonts.draw(desc, int(tx + 8), int(ty + (th - 17) // 2), 17, rl.Color(0xE0, 0xE0, 0xE0, 255))

        hint = "C  close"
        fonts.draw(hint, panel_x + PANEL_W // 2 - fonts.measure(hint, 17) // 2,
                   panel_y + panel_h - PAD - 4, 17, rl.Color(0x99, 0x99, 0x99, 200))
    def _draw_combat_log(self, cw, ch):
        if not self._combat_log_open or not self._combat_log:
            return
        LOG_W = 480
        LOG_H = 340
        FS_LOG = 17
        LINE_LOG = 22
        PAD = 10
        log_x = cw - LOG_W - PAD
        log_y = PAD
        visible_lines = (LOG_H - PAD * 2) // LINE_LOG
        total_lines = len(self._combat_log)
        max_scroll = max(0, total_lines - visible_lines)

        scroll_keys = 0
        if rl.is_key_pressed(rl.KEY_UP):
            scroll_keys -= 3
        if rl.is_key_pressed(rl.KEY_DOWN):
            scroll_keys += 3
        if rl.is_key_pressed(rl.KEY_PAGE_UP):
            scroll_keys -= visible_lines
        if rl.is_key_pressed(rl.KEY_PAGE_DOWN):
            scroll_keys += visible_lines
        self._combat_log_scroll = max(0, min(max_scroll, self._combat_log_scroll + scroll_keys))

        rl.draw_rectangle(log_x, log_y, LOG_W, LOG_H, rl.Color(0, 0, 0, 0x99))
        rl.draw_rectangle_lines(log_x, log_y, LOG_W, LOG_H, rl.Color(0xE0, 0xE0, 0xE0, 255))

        header = "Combat Log  (L  toggle)"
        fs_hdr = 20
        fonts.draw(header, log_x + LOG_W // 2 - fonts.measure(header, fs_hdr) // 2,
                   log_y + PAD, fs_hdr, rl.Color(0xFF, 0xFF, 0xFF, 255))
        rl.draw_line(log_x + PAD, log_y + PAD + fs_hdr + 4,
                     log_x + LOG_W - PAD, log_y + PAD + fs_hdr + 4,
                     rl.Color(0xE0, 0xE0, 0xE0, 255))

        start = max(0, total_lines - visible_lines - self._combat_log_scroll)
        end = min(total_lines, start + visible_lines)
        log_rows = self._combat_log[start:end] if end > start else []

        row_y = log_y + PAD + fs_hdr + 10
        for entry in log_rows:
            mins = int(entry['time'] // 60)
            secs = int(entry['time'] % 60)
            ts = f"{mins}:{secs:02d}"
            ts_w = fonts.measure(ts, FS_LOG)
            fonts.draw(ts, log_x + PAD, row_y, FS_LOG, rl.Color(0x99, 0x99, 0x99, 200))

            msg_color = rl.Color(255, 60, 60, 255) if entry['type'] == 'dmg_taken' else (
                rl.Color(255, 220, 40, 255) if entry['type'] == 'crit' else (
                rl.Color(200, 200, 200, 255) if entry['type'] == 'kill' else (
                rl.Color(0xAA, 0xAA, 0xAA, 255) if entry['type'] == 'miss' else (
                rl.Color(220, 220, 200, 255)))))
            fonts.draw(entry['msg'], log_x + PAD + ts_w + PAD, row_y, FS_LOG, msg_color)
            row_y += LINE_LOG

        if max_scroll > 0:
            scroll_info = f"↑↓  ({self._combat_log_scroll}/{max_scroll})"
            si_fs = 14
            fonts.draw(scroll_info, log_x + LOG_W - PAD - fonts.measure(scroll_info, si_fs),
                       log_y + LOG_H - PAD - si_fs, si_fs, rl.Color(70, 90, 70, 200))
    def _draw_enemy_hover_info(self, cw, ch, scale_font, scale_px, PAD, ui):
        """Draw enemy name, level, and health bar at top center when hovering or in combat."""
        mx, my = rl.get_mouse_x(), rl.get_mouse_y()
        tile_size = int(ISO_W * self.iso.scale)
        hover_radius = 20
        hovered = None
        best_dist = hover_radius

        for z in self.zombies:
            if z['health'] <= 0 or z.get('death_timer') is not None:
                continue
            sx, sy = self.iso.world_to_screen(z['x'], z['y'], cw, ch)
            cx = sx + tile_size // 2
            cy = sy + tile_size // 2
            d = math.hypot(mx - cx, my - cy)
            if d < best_dist:
                best_dist = d
                hovered = z

        # Fallback: nearest enemy in combat range if nothing hovered
        if hovered is None:
            for z in self.zombies:
                if z['health'] <= 0 or z.get('death_timer') is not None:
                    continue
                if z.get('hit_count', 0) == 0:
                    continue
                pd = math.hypot(z['x'] - self.px, z['y'] - self.py)
                if pd < 8.0:
                    hovered = z

        if hovered is None:
            return

        etype = hovered.get('enemy_type', 'skeleton').capitalize()
        elevel = hovered.get('level', 1)
        hp = hovered['health']
        max_hp = hovered['max_health']
        pct = max(0.0, hp / max(1, max_hp))

        hdr_w, hdr_h = scale_px(200), scale_px(60)
        hdr_x = cw // 2 - hdr_w // 2
        hdr_y = PAD - scale_px(4)
        header_tex = ui.get('header')
        if header_tex and header_tex.id > 0:
            rl.draw_texture_pro(header_tex,
                rl.Rectangle(0, 0, float(header_tex.width), float(header_tex.height)),
                rl.Rectangle(float(hdr_x), float(hdr_y), float(hdr_w), float(hdr_h)),
                rl.Vector2(0, 0), 0.0, rl.WHITE)

        # Name & level
        info = f"Lv{elevel} {etype}"
        iw = fonts.measure(info, scale_font(16))
        fonts.draw(info, cw // 2 - iw // 2, hdr_y + scale_px(4), scale_font(16),
                   rl.Color(255, 220, 100, 255))

        # Health bar
        bar_w = scale_px(160)
        bar_h = scale_px(10)
        bar_x = cw // 2 - bar_w // 2
        bar_y = hdr_y + hdr_h - bar_h - scale_px(4)
        rl.draw_rectangle(bar_x, bar_y, bar_w, bar_h, rl.Color(0, 0, 0, 0x99))
        if pct > 0:
            rl.draw_rectangle(bar_x, bar_y, int(bar_w * pct), bar_h,
                              rl.Color(200, 50, 50, 230) if pct > 0.4 else rl.Color(240, 200, 30, 230))
        rl.draw_rectangle_lines(bar_x, bar_y, bar_w, bar_h, rl.Color(60, 30, 30, 180))
    def _draw_kill_streak(self, cw, ch):
        hud_scale = self.menu_sys.settings.hud_scale
        def scale_font_local(n): return max(1, int(n * hud_scale))
        t = rl.get_time()
        cx = cw // 2

        # "STREAK LOST" sting
        lost_age = t - self._streak_lost_t
        if 0.0 <= lost_age < STREAK_LOST_FADE and self._kill_streak < 3:
            alpha = int(220 * (1.0 - lost_age / STREAK_LOST_FADE))
            label = 'STREAK LOST'
            fs = scale_font_local(30)
            lw = fonts.measure(label, fs)
            fonts.draw(label, cx - lw // 2, int(ch * 0.28), fs,
                       rl.Color(255, 70, 70, alpha))
            return

        streak = self._kill_streak
        age = t - self._streak_pop_t
        if streak < 1 or age > STREAK_POP_TIME:
            return

        col = self._streak_color(streak)

        # Background flash behind the text (max juice)
        flash_age = min(age, STREAK_POP_SECS)
        flash_a   = int(90 * (1.0 - flash_age / STREAK_POP_SECS)) * max(1, min(streak, 6) // 2 + 1)
        pad_x, pad_y = 46, 20
        bw, bh = 260 + 14 * min(streak, 12), 64
        rl.draw_rectangle(cx - bw // 2, int(ch * 0.26) - pad_y, bw, bh,
                          rl.Color(col.r, col.g, col.b, min(flash_a, 110)))

        # Milestone title word
        title = None
        m_age = t - self._streak_milestone_t
        if self._streak_milestone and 0.0 <= m_age < STREAK_POP_TIME:
            title     = self._streak_milestone
            pop_secs  = STREAK_BIG_POP_SECS
            punch_ref = m_age
        else:
            pop_secs  = STREAK_POP_SECS
            punch_ref = age

        # Scale punch (ease-out cubic)
        k    = max(0.0, 1.0 - punch_ref / pop_secs)
        grow = 1.0 + 1.2 * k * k

        main = f'x{streak}'
        fs   = scale_font_local(int(44 * grow))
        mw   = fonts.measure(main, fs)
        sub  = 'STREAK'
        ssz  = scale_font_local(int(16 * grow))
        sw   = fonts.measure(sub, ssz)

        y_main = int(ch * 0.27)
        y_sub  = y_main - ssz - 4
        fonts.draw(sub, cx - sw // 2, y_sub, ssz,
                   rl.Color(col.r, col.g, col.b, 230))
        fonts.draw(main, cx - mw // 2, y_main, fs, col)

        if title:
            tsz = scale_font_local(int(24 * grow))
            tw  = fonts.measure(title, tsz)
            fonts.draw(title, cx - tw // 2, y_main + fs + 6, tsz, col)

        # Draining window bar — time left before the streak breaks
        remain = max(0.0, ANGEL_STREAK_WINDOW - (t - self._last_kill_t))
        frac   = remain / ANGEL_STREAK_WINDOW
        bar_w, bar_h = 180, 5
        bx = cx - bar_w // 2
        by = y_main + fs + (scale_font_local(34) if title else 10)
        rl.draw_rectangle(bx, by, bar_w, bar_h, rl.Color(0, 0, 0, 130))
        rl.draw_rectangle(bx, by, int(bar_w * frac), bar_h, col)
    def _draw_hud(self, cw, ch):
        hud_scale = self.menu_sys.settings.hud_scale
        PAD = int(16 * hud_scale)
        def scale_px(n): return max(1, int(n * hud_scale))
        def scale_font(n): return max(12, int(n * hud_scale))
        ui  = self._ui

        # CHARACTER LEVEL — top-left HUD readout, drawn with the other
        # top-left character info. Uses the same
        # itemgen.format_character_level() accessor and formatting as the
        # inventory panel header, so the two sites always show the identical
        # value. Display-only; see itemgen.character_level.
        self._draw_character_level(cw, scale_font, PAD)

        self._draw_delve_hud(cw, ch, scale_font)

        # Area name — top center
        # if self._delve is not None:
        #     area_name = f"The Anima  —  Depth {self._delve['depth']}"
        # elif self.state == STATE_HUB:
        #     area_name = "The Hub"
        # else:
        #     area_name = ""
        # if area_name:
        #     afs = scale_font(14)
        #     aw = fonts.measure(area_name, afs)
        #     fonts.draw(area_name, cw // 2 - aw // 2, scale_font(40), afs,
        #                rl.Color(160, 200, 160, 180))

        # ── enemy hover / combat info (top center) ────────────────────
        self._draw_enemy_hover_info(cw, ch, scale_font, scale_px, PAD, ui)

        # ── top-left: character info ────────────────────────────────────
        ci_x = PAD
        ci_y = PAD
        icons.draw(self.char.looks, ci_x, ci_y, scale_px(22))
        name_fs = scale_font(14)
        nm = self.char.name
        fonts.draw(nm, ci_x + scale_px(26), ci_y, name_fs, rl.Color(220, 220, 220, 255))
        # (the old unspent-points hint above the name was a dead leveling
        # leftover: points are permanently 0 and no spend keybind exists)

        # ── buff / debuff indicators (top-left below character info) ───
        buff_y = ci_y + scale_px(64)
        buff_fs = scale_font(14)
        buff_gap = scale_px(2)
        # Timed E-gem buffs — Lifesteal / Fire Aura (snapshotted at cast)
        if self._lifesteal_timer > 0:
            buf = f"Lifesteal {self._lifesteal_timer:.1f}s"
            c = rl.Color(80, 220, 100, 255)
            rl.draw_rectangle(PAD, buff_y, fonts.measure(buf, buff_fs) + scale_px(6),
                              buff_fs + scale_px(4), rl.Color(10, 40, 10, 200))
            rl.draw_rectangle_lines(PAD, buff_y, fonts.measure(buf, buff_fs) + scale_px(6),
                                    buff_fs + scale_px(4), rl.Color(50, 180, 50, 180))
            fonts.draw(buf, PAD + scale_px(3), buff_y + scale_px(2), buff_fs, c)
            buff_y += buff_fs + scale_px(4) + buff_gap
        if self._fire_aura_timer > 0:
            buf = f"Fire Aura {self._fire_aura_timer:.1f}s"
            c = rl.Color(255, 130, 40, 255)
            rl.draw_rectangle(PAD, buff_y, fonts.measure(buf, buff_fs) + scale_px(6),
                              buff_fs + scale_px(4), rl.Color(40, 15, 5, 200))
            rl.draw_rectangle_lines(PAD, buff_y, fonts.measure(buf, buff_fs) + scale_px(6),
                                    buff_fs + scale_px(4), rl.Color(200, 80, 20, 180))
            fonts.draw(buf, PAD + scale_px(3), buff_y + scale_px(2), buff_fs, c)
            buff_y += buff_fs + scale_px(4) + buff_gap
        # Angel form (temporary buff)
        if self._angel_timer > 0:
            buf = f"ANGEL FORM {self._angel_timer:.1f}s (+50%)"
            bw = fonts.measure(buf, buff_fs) + scale_px(6)
            bh = buff_fs + scale_px(4)
            pulse = int(140 + 60 * (0.5 + 0.5 * math.sin(rl.get_time() * 8.0)))
            rl.draw_rectangle(PAD, buff_y, bw, bh, rl.Color(60, 50, 15, 200))
            rl.draw_rectangle_lines(PAD, buff_y, bw, bh, rl.Color(pulse, pulse - 40, 90, 220))
            fonts.draw(buf, PAD + scale_px(3), buff_y + scale_px(2), buff_fs,
                       rl.Color(255, 240, 170, 255))
            buff_y += bh + buff_gap

        # Save indicator
        if self._save_notice_timer > 0:
            sv_alpha = int(min(255, self._save_notice_timer * 128))
            sv_msg = "Saving..."
            sv_fs = scale_font(12)
            sv_tw = fonts.measure(sv_msg, sv_fs)
            fonts.draw(sv_msg, cw - PAD - sv_tw, PAD, sv_fs,
                       rl.Color(160, 200, 160, sv_alpha))

        # Inventory full notification
        if self._inv_full_timer > 0:
            if_alpha = int(min(255, self._inv_full_timer * 85))
            if_msg = "Inventory Full!"
            if_fs = scale_font(16)
            if_tw = fonts.measure(if_msg, if_fs)
            fonts.draw(if_msg, cw // 2 - if_tw // 2, ch // 2 - 20, if_fs,
                       rl.Color(255, 180, 60, if_alpha))

        # Vessel-unlock banner
        if self._vessel_unlock_timer > 0 and self._vessel_unlock_msg:
            v_pulse = (math.sin(self.raid_time * 5.0) + 1.0) / 2.0
            v_alpha = int(200 + 55 * v_pulse)
            v_lk = self._vessel_unlock_msg
            v_name = VESSEL_DEFS.get(v_lk, {}).get('name', v_lk)
            v_veil = VESSEL_UNLOCKS.get(v_lk, {}).get('veil')
            v_fs = scale_font(28)
            v_msg = f"{v_name.upper()} UNLOCKED"
            v_tw = fonts.measure(v_msg, v_fs)
            icons.draw(v_lk, cw // 2 - v_tw // 2 - scale_px(34), ch // 2 - 44, scale_px(28))
            fonts.draw(v_msg, cw // 2 - v_tw // 2, ch // 2 - 40, v_fs,
                       rl.Color(255, 255, 255, v_alpha))
            if v_veil:
                v_sub = f"{v_veil} pierced"
                v_sf = scale_font(18)
                v_sw = fonts.measure(v_sub, v_sf)
                fonts.draw(v_sub, cw // 2 - v_sw // 2, ch // 2 - 8, v_sf,
                           rl.Color(255, 255, 255, max(0, v_alpha - 60)))

        # ── bottom: Diablo II-style action bar — mirrors assets/ui/result.png ──
        # The mockup composites the UI assets at native pixel size (1762x237), so
        # every metric below is a native asset pixel scaled by bar_s. The bar is a
        # centered container capped at HUD_MAX_W screen px; all elements anchor to
        # the container edges (hud_x / hud_x + hud_w), not the screen edges.
        # Mockup structure (owner ruling 2026-10-10): [life orb + label] │
        # [left box: organ-rot meter over 3 menu buttons] │ [centre box: five
        # CENTRED QWER+T slots] │ [right box: attack / move] │ [mana orb +
        # label] — each section in its own bronze-framed box with divider
        # strips between them, exactly like the mockup.
        HUD_MAX_W = 800                    # screen px — max width of the action bar
        hud_w = min(cw, HUD_MAX_W)
        hud_x  = (cw - hud_w) // 2
        bar_s = min(hud_scale, hud_w / 1762.0)
        def bpx(n): return max(1, int(n * bar_s))
        def bfont(n): return max(9, int(n * bar_s))

        BAR_H = bpx(130)                  # panel strip height (panel.png is 128 native)
        ORB   = bpx(200)                  # orb sphere diameter
        ORB_MARGIN = bpx(120)              # ORB only: gap from screen edge to the orb's outer edge
        ANG_CROP   = bpx(0)              # STATUE only: px of the statue cropped off the screen edge
        ORB_RAISE  = bpx(20)              # ORB only: lift off the screen bottom
        ANG_LIFT   = bpx(0)              # STATUE only: lift off the screen bottom
        PANEL_SHIFT = bpx(20)             # ORB_PANEL only: horizontal offset (+ = toward screen center)
        PANEL_DROP  = bpx(7)             # ORB_PANEL only: vertical offset (+ = down)
        BAR_INSET_L = bpx(20)             # PANEL only: bar start, px right of the container's left edge
        BAR_INSET_R = bpx(20)             # PANEL only: bar end, px left of the container's right edge
        STATUE_SCALE = 1.0               # STATUE only: size multiplier (1.0 = native 254x228 fit)
        bar_y = ch - BAR_H
        orb_top = ch - ORB - ORB_RAISE   # orb vertical position (ORB_RAISE lifts it)

        GOLD = rl.Color(255, 215, 0, 255)
        BRONZE = rl.Color(150, 118, 58, 255)      # section-box frame band
        FRAME_DARK = rl.Color(34, 27, 16, 255)     # inner line of the frame
        hp_pct = max(0.0, self.stats['health'] / max(1, self.stats['max_health']))
        mp_cur = float(self.stats.get('mana', 0.0))
        mp_max = max(1.0, float(self.stats.get('max_mana', 1.0)))
        mp_pct = max(0.0, min(1.0, mp_cur / mp_max))

        # 1) Base panel tiled across the container width (BAR_INSET_L/R pull
        # the bar's ends inward so nothing pokes out beside the statues)
        panel_tex = ui.get('panel')
        bar_l = hud_x + BAR_INSET_L
        bar_r = hud_x + hud_w - BAR_INSET_R
        if panel_tex and panel_tex.id > 0:
            pw = panel_tex.width
            x = bar_l
            while x < bar_r:
                rl.draw_texture_pro(panel_tex,
                    rl.Rectangle(0, 0, float(pw), float(panel_tex.height)),
                    rl.Rectangle(float(x), float(bar_y), float(min(pw, bar_r - x)), float(BAR_H)),
                    rl.Vector2(0, 0), 0.0, rl.WHITE)
                x += pw
        else:
            rl.draw_rectangle(int(bar_l), bar_y, int(bar_r - bar_l), BAR_H,
                              rl.Color(0, 0, 0, 210))

        def _tex(key):
            t = ui.get(key)
            return t if (t and t.id > 0) else None

        def _band(x, y, w, h, t, col):
            """Hollow rectangle outline from four bars — draw_rectangle has
            no thickness argument, and bars stay headless-safe."""
            x, y, w, h = int(x), int(y), int(w), int(h)
            t = max(1, int(t))
            if w <= 0 or h <= 0:
                return
            t = min(t, max(1, w // 2), max(1, h // 2))
            rl.draw_rectangle(x, y, w, t, col)
            rl.draw_rectangle(x, y + h - t, w, t, col)
            rl.draw_rectangle(x, y + t, t, h - 2 * t, col)
            rl.draw_rectangle(x + w - t, y + t, t, h - 2 * t, col)

        def _section_box(x, y, w, h):
            """Mockup-style section frame: darkened inset, bronze band, thin
            dark inner line (owner ruling 2026-10-10 — the three bar sections
            each sit in a framed box, like result.png)."""
            t = max(1, bpx(3))
            rl.draw_rectangle(int(x), int(y), int(w), int(h),
                              rl.Color(0, 0, 0, 100))
            _band(x, y, w, h, t, BRONZE)
            _band(x + t, y + t, w - 2 * t, h - 2 * t, max(1, bpx(1)),
                  FRAME_DARK)

        def _divider(x):
            """Vertical divider strip between bar sections — divider.png is
            shared with the menus (restored for the HUD, blueprint §15.147)."""
            dt = _tex('divider')
            dy = bar_y + bpx(6)
            dh = bpx(116)
            if dt:
                rl.draw_texture_pro(dt,
                    rl.Rectangle(0, 0, float(dt.width), float(dt.height)),
                    rl.Rectangle(float(x), float(dy), float(bpx(13)),
                                 float(dh)),
                    rl.Vector2(0, 0), 0.0, rl.WHITE)
            else:
                rl.draw_rectangle(int(x), int(dy), bpx(4), dh,
                                  rl.Color(120, 100, 70, 180))

        def _chevron(cx, top_y):
            """Static gold-tab marker (active_action.png) sitting on a
            section box's top edge — the mockup draws one over the first
            slot of the centre row and of the right cluster. Distinct from
            the dynamic cast flash in _draw_hud_flash."""
            at = _tex('active_action')
            if not at:
                return
            w = bpx(64)
            h = max(1, int(w * 22.0 / 96.0))
            rl.draw_texture_pro(at,
                rl.Rectangle(0, 0, float(at.width), float(at.height)),
                rl.Rectangle(float(int(cx) - w // 2),
                             float(int(top_y) - h // 3), float(w), float(h)),
                rl.Vector2(0, 0), 0.0, rl.WHITE)

        def _draw_orb(cx, top_y, size, pct, fill_key, r, g, b, deco_right=False, label=None):
            tint = rl.Color(r, g, b, 255)
            panel_t = ui.get('orb_panel')
            fill_t  = ui.get(fill_key)
            glass_t = ui.get('orb_glass')
            angel_t = ui.get('orb_angel')
            R  = size // 2
            ox = cx + R
            oy = top_y + R
            # ornate backdrop behind the sphere (ornament faces the belt)
            if panel_t and panel_t.id > 0:
                pw2, ph2 = bpx(246), bpx(216)
                if deco_right:
                    src = rl.Rectangle(float(panel_t.width), 0.0,
                                       -float(panel_t.width), float(panel_t.height))
                else:
                    src = rl.Rectangle(0.0, 0.0, float(panel_t.width), float(panel_t.height))
                px_off = -PANEL_SHIFT if deco_right else PANEL_SHIFT
                rl.draw_texture_pro(panel_t, src,
                    rl.Rectangle(float(ox - pw2 // 2 + px_off),
                                 float(oy - ph2 // 2 + PANEL_DROP),
                                 float(pw2), float(ph2)),
                    rl.Vector2(0, 0), 0.0, rl.WHITE)
            # dark tinted base so an empty orb still reads red/blue, never black
            rl.draw_circle(ox, oy, R - bpx(2),
                           rl.Color(int(r * 0.22), int(g * 0.22), int(b * 0.22), 240))
            # liquid fill clipped to the sphere, rising from the bottom
            if pct > 0.005 and fill_t and fill_t.id > 0:
                fill_h = int(2 * R * pct)
                bottom = oy + R
                full = rl.Rectangle(0, 0, float(fill_t.width), float(fill_t.height))
                dst  = rl.Rectangle(float(cx), float(top_y), float(size), float(size))
                for row in range(max(top_y, bottom - fill_h), bottom, 2):
                    dy = row - oy
                    half = int((R * R - dy * dy) ** 0.5)
                    if half > 0:
                        rl.begin_scissor_mode(ox - half, row, half * 2, 2)
                        rl.draw_texture_pro(fill_t, full, dst, rl.Vector2(0, 0), 0.0, tint)
                        rl.end_scissor_mode()
            # glossy glass overlay
            if glass_t and glass_t.id > 0:
                rl.draw_texture_pro(glass_t,
                    rl.Rectangle(0, 0, float(glass_t.width), float(glass_t.height)),
                    rl.Rectangle(float(cx), float(top_y), float(size), float(size)),
                    rl.Vector2(0, 0), 0.0, rl.WHITE)
            # angel statue pinned to the container edge (independent of the orb)
            if angel_t and angel_t.id > 0:
                ang_w = int(bpx(254) * STATUE_SCALE)
                ang_h = int(bpx(228) * STATUE_SCALE)
                ang_y = ch - ang_h - ANG_LIFT
                if deco_right:
                    src = rl.Rectangle(float(angel_t.width), 0.0,
                                       -float(angel_t.width), float(angel_t.height))
                    ax = hud_x + hud_w - ang_w + ANG_CROP
                else:
                    src = rl.Rectangle(0.0, 0.0, float(angel_t.width), float(angel_t.height))
                    ax = hud_x - ANG_CROP
                rl.draw_texture_pro(angel_t, src,
                    rl.Rectangle(float(ax), float(ang_y), float(ang_w), float(ang_h)),
                    rl.Vector2(0, 0), 0.0, rl.WHITE)
            if label:
                lfs = bfont(24)
                lw = fonts.measure(label, lfs)
                if deco_right:
                    lx = cx - lw - bpx(16)
                else:
                    lx = cx + size + bpx(16)
                ly = top_y + int(size * 0.30)
                fonts.draw(label, lx, ly, lfs, rl.Color(235, 235, 235, 240))

        # 2) far-left Life orb / far-right Mana orb
        hx = hud_x + ORB_MARGIN
        _draw_orb(hx, orb_top, ORB, hp_pct, 'orb_fill0', 200, 30, 30,
                  deco_right=False,
                  label=f"Life : {int(self.stats['health'])} / {int(self.stats['max_health'])}")
        mx = hud_x + hud_w - ORB_MARGIN - ORB
        _draw_orb(mx, orb_top, ORB, mp_pct, 'orb_fill1', 40, 120, 220,
                  deco_right=True,
                  label=f"Mana : {int(mp_cur)} / {int(mp_max)}")

        # 3) left cluster: bronze box with the organ-rot meter on top and the
        #    3 menu buttons underneath — the mockup's two-row rhythm
        row_top = bar_y + bpx(8)              # top row: rot meter / wide buttons
        row_bot = bar_y + bpx(66)             # bottom row: menu buttons
        PAD = bpx(6)
        lp_x = hx + ORB + bpx(48)
        mbtn = bpx(52)
        mpad = bpx(6)
        left_w = 3 * (mbtn + mpad) - mpad
        lp_right = lp_x + left_w
        left_box = (lp_x - PAD, row_top - PAD,
                    left_w + 2 * PAD,
                    (row_bot + mbtn + PAD) - (row_top - PAD))
        _section_box(*left_box)

        # organ-rot meter: icon slot + ten segments bound to itemgen.max_rot
        # (worst equipped organ; owner ruling 2026-10-10 — replaces the
        # removed stamina row of the mockup)
        rot_pct = itemgen.max_rot(self.inventory)
        icon_w, icon_h = bpx(44), bpx(48)
        bt1 = _tex('button1')
        if bt1:
            rl.draw_texture_pro(bt1,
                rl.Rectangle(0, 0, float(bt1.width), float(bt1.height)),
                rl.Rectangle(float(lp_x), float(row_top),
                             float(icon_w), float(icon_h)),
                rl.Vector2(0, 0), 0.0, rl.WHITE)
        else:
            rl.draw_rectangle(int(lp_x), int(row_top), icon_w, icon_h,
                              rl.Color(40, 40, 40, 220))
        icons.draw('rot',
                   int(lp_x + (icon_w - bpx(28)) // 2),
                   int(row_top + (icon_h - bpx(28)) // 2),
                   bpx(28), _rot_col(rot_pct))
        seg_x = lp_x + icon_w + bpx(6)
        seg_fw = lp_x + left_w - seg_x
        seg_fy = row_top + bpx(9)
        seg_fh = bpx(30)
        seg_t = max(1, bpx(3))
        rl.draw_rectangle(int(seg_x), int(seg_fy), int(seg_fw), int(seg_fh),
                          rl.Color(0, 0, 0, 160))
        _band(seg_x, seg_fy, seg_fw, seg_fh, seg_t, BRONZE)
        n_seg = 10
        seg_pct = max(0.0, min(1.0, rot_pct / itemgen.ROT_MAX))
        n_filled = int(math.ceil(seg_pct * n_seg))
        seg_col = _rot_col(rot_pct)
        seg_ix = seg_x + seg_t + bpx(3)
        seg_iy = seg_fy + seg_t + bpx(3)
        seg_iw = seg_fw - 2 * (seg_t + bpx(3))
        seg_ih = seg_fh - 2 * (seg_t + bpx(3))
        seg_gap = bpx(3)
        seg_w = max(1, int((seg_iw - seg_gap * (n_seg - 1)) / n_seg))
        seg_pt = _tex('seg_point')
        for i in range(n_seg):
            sx0 = int(seg_ix + i * (seg_w + seg_gap))
            col = seg_col if i < n_filled else rl.Color(58, 48, 26, 255)
            if seg_pt:
                rl.draw_texture_pro(seg_pt,
                    rl.Rectangle(0, 0, float(seg_pt.width), float(seg_pt.height)),
                    rl.Rectangle(float(sx0), float(seg_iy),
                                 float(seg_w), float(seg_ih)),
                    rl.Vector2(0, 0), 0.0, col)
            else:
                rl.draw_rectangle(sx0, int(seg_iy), seg_w, int(seg_ih), col)

        gbt = _tex('button0')
        for i, icn in enumerate(('player', 'help', 'magic')):
            bx = lp_x + i * (mbtn + mpad)
            if gbt:
                rl.draw_texture_pro(gbt,
                    rl.Rectangle(0, 0, float(gbt.width), float(gbt.height)),
                    rl.Rectangle(float(bx), float(row_bot), float(mbtn), float(mbtn)),
                    rl.Vector2(0, 0), 0.0, rl.WHITE)
            else:
                rl.draw_rectangle(int(bx), int(row_bot), mbtn, mbtn, rl.Color(40, 40, 40, 220))
            icons.draw(icn, int(bx + (mbtn - bpx(34)) // 2),
                       int(row_bot + (mbtn - bpx(34)) // 2), bpx(34))

        # right-cluster geometry (computed before the centre row so the
        # centre can centre itself against it). Anchored to the orb with
        # bpx(48) — mirrors the left cluster's bpx(48) gap (was bpx(30)).
        rp_w = 2 * bpx(96) + bpx(4)
        rp_x = mx - bpx(48) - rp_w
        right_box = (rp_x - PAD, row_top - PAD, rp_w + 2 * PAD,
                     (row_top + bpx(50) + PAD) - (row_top - PAD))

        act_rects = self._hud_action_rects
        act_rects.clear()
        mxp, myp = rl.get_mouse_x(), rl.get_mouse_y()

        # 4) centre: five QWER+T slots, SIZED AND CENTRED like the mockup's
        #    six-slot belt (owner ruling 2026-10-10 — no numbered hotkeys,
        #    no potion belt: the keys stay Q/W/E/R/T)
        zone_l = lp_right + bpx(14)
        zone_r = rp_x - bpx(14)
        CSLOT = bpx(96)
        cgap = bpx(6)
        slot_keys = ('Q', 'W', 'E', 'R', 'T')
        slots_w = len(slot_keys) * CSLOT + (len(slot_keys) - 1) * cgap
        # centred on the CONTAINER (screen centre), clamped into the zone so
        # an asymmetric cluster pair can never push a slot into its neighbour
        slots_x = hud_x + (hud_w - slots_w) // 2
        slots_x = max(zone_l, min(slots_x, zone_r - slots_w))
        slots_y = bar_y + bpx(15)
        centre_box = (slots_x - bpx(7), slots_y - bpx(7),
                      slots_w + bpx(14), CSLOT + bpx(14))
        _section_box(*centre_box)

        # Q/W/E/R gem ability slots — socketed ability icon, key label,
        # cooldown dim + seconds; click casts
        sk_t = _tex('skill_base')
        asz = CSLOT
        a_y = slots_y
        for i, key in enumerate(('Q', 'W', 'E', 'R')):
            sx = slots_x + i * (asz + cgap)
            srect = rl.Rectangle(float(sx), float(a_y), float(asz), float(asz))
            if sk_t:
                rl.draw_texture_pro(sk_t,
                    rl.Rectangle(0, 0, float(sk_t.width), float(sk_t.height)),
                    srect, rl.Vector2(0, 0), 0.0, rl.WHITE)
            else:
                rl.draw_rectangle(int(sx), int(a_y), asz, asz, rl.Color(30, 30, 30, 220))
            found = gems.socketed_ability(self.inventory, key)
            icon = None
            if found is not None:
                _inst, ab, _tier = found
                icon = self._ability_icons.get(ab.get('id'))
            if icon and icon.id > 0:
                rl.draw_texture_pro(icon,
                    rl.Rectangle(0, 0, float(icon.width), float(icon.height)),
                    rl.Rectangle(float(sx + bpx(10)), float(a_y + bpx(10)),
                                 float(asz - bpx(20)), float(asz - bpx(20))),
                    rl.Vector2(0, 0), 0.0, rl.WHITE)
            fonts.draw(key, sx + bpx(6), a_y + bpx(5), bfont(16),
                       rl.Color(220, 220, 220, 230))
            cd = float(self._gem_cds.get(key, 0.0))
            if cd > 0:
                shade = max(40, int(170 * min(1.0, cd / 6.0)))
                rl.draw_rectangle(int(sx), int(a_y), asz, asz, rl.Color(0, 0, 0, shade))
                cnum = str(int(math.ceil(cd)))
                cfs = bfont(13)
                cw3 = fonts.measure(cnum, cfs)
                fonts.draw(cnum, sx + asz // 2 - cw3 // 2,
                           a_y + asz // 2 - cfs // 2, cfs,
                           rl.Color(255, 220, 120, 240))
            if (rl.is_mouse_button_pressed(rl.MOUSE_BUTTON_LEFT)
                    and rl.check_collision_point_rec(
                        rl.Vector2(float(mxp), float(myp)), srect)):
                self._use_gem_ability(key)
            act_rects[key] = srect
            self._draw_hud_flash(key, sx + asz / 2, a_y, float(asz))

        # T — the equipped flask (health/mana abilities, click or T to drink);
        #    slot 5 of the centred row, drawn on the same skill_base frame
        fl_x = slots_x + 4 * (asz + cgap)
        fl_y = slots_y
        frect = rl.Rectangle(float(fl_x), float(fl_y), float(asz), float(asz))
        bst_t = sk_t                     # same skill_base frame as Q/W/E/R
        if bst_t:
            rl.draw_texture_pro(bst_t,
                rl.Rectangle(0, 0, float(bst_t.width), float(bst_t.height)),
                frect, rl.Vector2(0, 0), 0.0, rl.WHITE)
        else:
            rl.draw_rectangle(int(fl_x), int(fl_y), asz, asz, rl.Color(30, 30, 30, 210))
        fl_entry = self.inventory.get('flask_slot')
        if fl_entry:
            fdefn = ITEMS.get(fl_entry['item'], {})
            fkind = fdefn.get('isFlask')
            ftint = (rl.Color(255, 70, 70, 255) if fkind == 'health'
                     else rl.Color(90, 150, 255, 255) if fkind == 'mana'
                     else rl.Color(90, 230, 120, 255))
            icons.draw('potion', int(fl_x + (asz - bpx(44)) // 2),
                       int(fl_y + (asz - bpx(48)) // 2), bpx(44), ftint)
            fcharges = int(fl_entry.get('charges', fdefn.get('charges', 1)))
            fs = str(fcharges)
            fonts.draw(fs, fl_x + asz - fonts.measure(fs, bfont(13)) - bpx(7),
                       fl_y + asz - bfont(13) - bpx(6), bfont(13),
                       rl.Color(235, 235, 235, 235))
            if self._flask_cd > 0:
                shade = max(40, int(160 * (self._flask_cd / flasks.FLASK_CD)))
                rl.draw_rectangle(int(fl_x), int(fl_y), asz, asz,
                                  rl.Color(0, 0, 0, shade))
        else:
            fonts.draw('T', fl_x + asz // 2 - bfont(14) // 2,
                       fl_y + asz // 2 - bfont(14) // 2, bfont(14),
                       rl.Color(150, 150, 150, 200))
        fonts.draw('T', fl_x + bpx(6), fl_y + bpx(5), bfont(16),
                   rl.Color(220, 220, 220, 230))
        if (rl.is_mouse_button_pressed(rl.MOUSE_BUTTON_LEFT)
                and rl.check_collision_point_rec(
                    rl.Vector2(float(mxp), float(myp)), frect)):
            self._use_flask()
        act_rects['T'] = frect
        self._draw_hud_flash('T', fl_x + asz / 2, fl_y, float(asz))

        # 5) right cluster: bronze box with attack / move only (the mockup's
        #    four lower slots are decorative — dropped, owner ruling
        #    2026-10-10). Both buttons stay clickable and flash on use.
        _section_box(*right_box)
        wbt = _tex('button2')
        for i, (wicn, act) in enumerate((('melee', 'attack'), ('evasion', 'move'))):
            bx = rp_x + i * (bpx(96) + bpx(4))
            by = row_top
            brect = rl.Rectangle(float(bx), float(by), float(bpx(96)), float(bpx(50)))
            if wbt:
                rl.draw_texture_pro(wbt,
                    rl.Rectangle(0, 0, float(wbt.width), float(wbt.height)),
                    brect, rl.Vector2(0, 0), 0.0, rl.WHITE)
            else:
                rl.draw_rectangle(int(bx), int(by), bpx(96), bpx(50), rl.Color(40, 40, 40, 220))
            icons.draw(wicn, int(bx + (bpx(96) - bpx(34)) // 2),
                       int(by + (bpx(50) - bpx(34)) // 2), bpx(34), GOLD)
            if (rl.is_mouse_button_pressed(rl.MOUSE_BUTTON_LEFT)
                    and rl.check_collision_point_rec(
                        rl.Vector2(float(mxp), float(myp)), brect)):
                if act == 'attack':
                    self._hud_click_attack(mxp, myp)
                else:
                    self._hud_click_move(mxp, myp)
            act_rects[act] = brect
            self._draw_hud_flash(act, bx + bpx(48), by, float(bpx(96)))

        # 6) section dividers (outermost two mirror the orb gaps) + the
        #    mockup's gold chevron tabs over the centre and right boxes
        _divider(hx + ORB + bpx(20))
        _divider((left_box[0] + left_box[2] + centre_box[0]) // 2 - bpx(6))
        _divider((centre_box[0] + centre_box[2] + right_box[0]) // 2 - bpx(6))
        _divider(mx - bpx(33))
        _chevron(slots_x + CSLOT // 2, centre_box[1])
        _chevron(rp_x + bpx(48), right_box[1])

        self._draw_tasks(cw, ch, hud_scale)
        self._draw_kill_streak(cw, ch)

        mm_ents = []
        for z in self.zombies:
            if z['health'] > 0:
                mm_ents.append({'col': z['x'], 'row': z['y'],
                                'mm_col': rl.Color(200, 60, 60, 255)})
        for gi in self.ground_items:
            gtype = gi.get('type')
            if gtype == 'drop' and gi.get('items'):
                rc = self._rarity_color(self._drop_rarity(gi))
                mm_ents.append({'col': gi['x'], 'row': gi['y'], 'mm_col': rc})
            elif gtype == 'portal':
                mm_ents.append({'col': gi['x'], 'row': gi['y'],
                                'mm_col': rl.Color(180, 80, 255, 255)})
            elif gtype == 'crate' and not gi.get('breaking'):
                mm_ents.append({'col': gi['x'], 'row': gi['y'],
                                'mm_col': rl.Color(200, 140, 30, 255)})
            elif gtype == 'barrel' and not gi.get('breaking'):
                mm_ents.append({'col': gi['x'], 'row': gi['y'],
                                'mm_col': rl.Color(160, 90, 40, 255)})
            elif gtype == 'brazier' and not gi.get('breaking'):
                mm_ents.append({'col': gi['x'], 'row': gi['y'],
                                'mm_col': rl.Color(255, 150, 30, 255)})

        # Minimap — top-right, circular inside compass frame
        compass_tex = ui.get('compass')
        if compass_tex and compass_tex.id > 0:
            compass_w = 79
            compass_h = 82
            inner_sz  = 44
            mm_size   = inner_sz
            mm_cell   = 2
            mm_x = cw - compass_w - scale_px(8)
            mm_y = scale_px(8)
            inner_off = (compass_w - inner_sz) // 2
            self.iso.draw_minimap(self.map, self.px, self.py, mm_ents, cw, ch,
                                  mm_size=mm_size, cell=mm_cell,
                                  mx=mm_x + inner_off, my=mm_y + inner_off)
            rl.draw_texture_pro(compass_tex,
                rl.Rectangle(0, 0, float(compass_tex.width), float(compass_tex.height)),
                rl.Rectangle(float(mm_x), float(mm_y), float(compass_w), float(compass_h)),
                rl.Vector2(0, 0), 0.0, rl.WHITE)
        else:
            mm_size = 100
            mm_cell = 2
            mm_x = cw - mm_size - scale_px(12)
            mm_y = scale_px(12)
            self.iso.draw_minimap(self.map, self.px, self.py, mm_ents, cw, ch,
                                  mm_size=mm_size, cell=mm_cell,
                                  mx=mm_x, my=mm_y)
    def _draw_tasks(self, cw, ch, hud_scale=1.0):
        BAR_W = int(160 * hud_scale); ROW_H = int(30 * hud_scale); PAD = int(12 * hud_scale)
        task_origin_x = cw - BAR_W - PAD
        task_origin_y = ch - int(180 * hud_scale) - ROW_H * 3 - int(10 * hud_scale)
        for ref in self.char.tasks:
            defn = task_def(ref['id'])
            if not defn: continue
            cur, req = self.tracker.get_progress(ref)
            done = ref['done']
            pct  = 1.0 if done else min(1.0, cur / max(req, 1))
            name_col = rl.Color(80, 180, 80, 220) if done else rl.Color(180, 180, 180, 200)
            fonts.draw(defn['name'], task_origin_x, task_origin_y, max(16, int(20 * hud_scale)), name_col)
            rl.draw_rectangle(task_origin_x, task_origin_y + int(13 * hud_scale), BAR_W, max(3, int(5 * hud_scale)),
                              rl.Color(0, 0, 0, 0x99))
            bar_col = rl.Color(80, 200, 80, 220) if done else rl.Color(0xFF, 0xFF, 0xFF, 200)
            rl.draw_rectangle(task_origin_x, task_origin_y + int(13 * hud_scale), int(BAR_W * pct),
                              max(3, int(5 * hud_scale)), bar_col)
            task_origin_y += ROW_H
    def _draw_end_screen(self, cw, ch):
        rl.clear_background(rl.BLACK)
        results      = self._raid_results or {}
        msg          = "YOU DIED" if self.state == STATE_DEAD else "EXTRACTED"
        header_color = rl.Color(200, 40, 40, 255) if self.state == STATE_DEAD else rl.Color(0xFF, 0xFF, 0xFF, 255)
        fonts.draw(msg, cw // 2 - fonts.measure(msg, 93) // 2, 60, 93, header_color)

        PANEL_W, PANEL_H = 560, 340
        panel_x = (cw - PANEL_W) // 2
        panel_y = 130
        rl.draw_rectangle(panel_x, panel_y, PANEL_W, PANEL_H, rl.Color(0, 0, 0, 0x99))
        rl.draw_rectangle_lines(panel_x, panel_y, PANEL_W, PANEL_H, rl.Color(0xE0, 0xE0, 0xE0, 255))

        text_x, text_y = panel_x + 30, panel_y + 20
        LABEL_COLOR = rl.Color(0xCC, 0xCC, 0xCC, 255)
        VALUE_COLOR = rl.Color(220, 220, 220, 255)
        GREEN_COLOR = rl.Color(80, 200, 80, 255)

        def row(label, value, col=VALUE_COLOR):
            nonlocal text_y
            fonts.draw(label, text_x, text_y, 23, LABEL_COLOR)
            fonts.draw(str(value), text_x + 160, text_y, 23, col); text_y += 22

        mins = int(results.get('time', 0)) // 60
        secs = int(results.get('time', 0)) % 60
        row("KILLS",        results.get('kills', 0))
        row("TIME ALIVE",   f"{mins:02d}:{secs:02d}")
        row("ITEMS LOOTED", results.get('loot',  0))
        row("EXTRACTED",    "YES" if results.get('extracted') else "NO",
            GREEN_COLOR if results.get('extracted') else rl.Color(180, 60, 60, 255))

        if results.get('extracted') and results.get('completed'):
            text_y += 10; rl.draw_line(text_x, text_y, text_x + 240, text_y, rl.Color(0xE0, 0xE0, 0xE0, 255)); text_y += 12
            for defn in results.get('completed', []):
                fonts.draw(f"  {defn['name']}", text_x, text_y, 21, GREEN_COLOR)
                text_y += 18

        if self.state == STATE_DEAD:
            fonts.draw("Permanent death — this character has been deleted.",
                       cw // 2 - fonts.measure("Permanent death — this character has been deleted.", 18) // 2,
                       panel_y + PANEL_H + 8, 18, rl.Color(200, 100, 100, 200))

        hint = "PRESS ENTER TO CONTINUE"
        fonts.draw(hint, cw // 2 - fonts.measure(hint, 28) // 2,
                     ch - 40, 28, rl.Color(120, 120, 120, 255))
    def _draw_crt(self, cw, ch):
        if self._vignette_tex and self._vignette_tex.id > 0:
            src = rl.Rectangle(0, 0, float(self._vignette_tex.width), float(self._vignette_tex.height))
            dst = rl.Rectangle(0, 0, float(cw), float(ch))
            rl.draw_texture_pro(self._vignette_tex, src, dst, rl.Vector2(0, 0), 0.0, rl.WHITE)
        else:
            scanline_color = rl.Color(0, 0, 0, 38); y = 0
            while y < ch:
                rl.draw_rectangle(0, y, cw, 1, scanline_color); y += 2
    def _draw_debug(self, cw: int, ch: int):
        step_x, step_y = self.iso._steps()
        tile_size  = int(ISO_W * self.iso.scale)
        half = tile_size // 2

        def ellipse_lines(cx, cy, radius):
            rx = int(radius * step_x * 2)
            ry = int(radius * step_y * 2)
            return rx, ry

        # Enemies — detect radius (yellow) and melee radius (orange)
        for z in self.zombies:
            if z['health'] <= 0:
                continue
            sx, sy = self.iso.world_to_screen(z['x'], z['y'], cw, ch)
            center_x, center_y = sx + half, sy + half
            rx, ry = ellipse_lines(center_x, center_y, DETECT_RANGE)
            rl.draw_ellipse_lines(center_x, center_y, float(rx), float(ry), rl.Color(255, 220, 0,  140))
            rx, ry = ellipse_lines(center_x, center_y, MELEE_RANGE)
            rl.draw_ellipse_lines(center_x, center_y, float(rx), float(ry), rl.Color(255, 120, 0,  200))

        # Player — attack radius (cyan)
        sx, sy = self.iso.world_to_screen(self.px, self.py, cw, ch)
        rx, ry = ellipse_lines(sx + half, sy + half, ATTACK_RANGE)
        rl.draw_ellipse_lines(sx + half, sy + half, float(rx), float(ry), rl.Color(80, 200, 255, 200))

        # Darkness system info
        if self._delve is not None:
            d = self._delve
            has_rt = bool(self._darkness_rt is not None and self._darkness_rt.id > 0)
            has_blob = bool(self._light_blob_tex is not None and self._light_blob_tex.id > 0)
            step_x, step_y = self.iso._steps()
            iso_corr = math.hypot(step_x, step_y) / max(1, tile_size)
            lines = [
                f"path:    software (forced)",
                f"light_r: {d['light_r']:.1f} tiles ({int(d['light_r']*tile_size*iso_corr)}px corr)",
                f"iso_corr:{iso_corr:.3f} (step {step_x:.0f}/{step_y:.0f})",
                f"offset:  {PULSE_OFFSET_X},{PULSE_OFFSET_Y} | ambient:{DARKNESS_AMBIENT}",
                f"dps:     {d['darkness_dps']:.1f}/s",
                f"rt:      {'OK' if has_rt else 'FAIL'} | blob: {'OK' if has_blob else 'FAIL'}",
            ]
            for i, line in enumerate(lines):
                fonts.draw(line, cw - fonts.measure(line, 16) - 8, 8 + i * 16, 16, rl.Color(100, 255, 180, 220))
    def _draw_perf(self, cw, ch):
        fps = rl.get_fps(); frame_time_ms = rl.get_frame_time() * 1000
        lines = [f"FPS  {fps}", f"MS   {frame_time_ms:.1f}"]
        if self._god_mode: lines.append("GOD")
        for i, line in enumerate(lines):
            fonts.draw(line, cw - fonts.measure(line, 25) - 6, 6 + i * 18, 25,
                         rl.Color(255, 255, 100, 200))
    def _draw_console(self, cw, ch):
        PANEL_HEIGHT = 160; panel_y = ch - PANEL_HEIGHT
        rl.draw_rectangle(0, panel_y, cw, PANEL_HEIGHT, rl.Color(0, 0, 0, 210))
        rl.draw_line(0, panel_y, cw, panel_y, rl.Color(0xFF, 0xFF, 0xFF, 180))
        for i, line in enumerate(self._console_log[-7:]):
            col = rl.Color(0xFF, 0xFF, 0xFF, 220) if line.startswith('>') else rl.Color(0xCC, 0xCC, 0xCC, 220)
            fonts.draw(line, 10, panel_y + 6 + i * 18, 25, col)
        import time as _perf_time
        cursor = '|' if int(_perf_time.time() * 2) % 2 == 0 else ' '
        fonts.draw('> ' + self._console_buf + cursor, 10, panel_y + PANEL_HEIGHT - 24, 27, rl.WHITE)
