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

from config import ASSETS
"""
PoE-style inventory panel — right-side overlay, toggle with I.
Rendered on the itsmars_Inventory art: organ slots left of the torso,
tarot card slots + flask right, 8x4 backpack grid centre, 7 DESCEND
attribute tiles below the grid, gems in the base.
Right-click any filled slot for context actions.
"""

import os
import math
import pyray as rl
import ui.fonts as fonts
import ui.icons as icons
import systems.itemgen as itemgen
from systems import input as inp
import systems.abilities as _abilities_mod
import systems.gems as gems_mod
import systems.currency as currency_mod
from entities.descend import ATTR_LABEL as _TILE_LABEL
from ui.menus import _btn, _ATTR_BLURBS
from systems.items import (ITEMS, GRID_COLS, GRID_ROWS, INV_COLS, INV_ROWS,
                   grid_build_map, grid_auto_place, grid_auto_place_instance,
                   format_equip_stat, equip_from_grid, EQUIP_SLOT_LABELS,
                   socket_gem_from_grid)
import systems.items as items_mod

_ASSETS = ASSETS
_UI_ASSETS = os.path.join(ASSETS, 'ui')

# ── layout ────────────────────────────────────────────────────────────
# (554×1080); the panel is drawn at scale s = screen_h / BG_H, anchored to
# the right screen edge.
BG_W   = 554
BG_H   = 1080

# Left column: 5 organ (equipment) slots
ORG_AX, ORG_AY, ORG_AW, ORG_AH = 27, 32, 78, 80
ORG_PITCH = 91
ORG_ORDER = ('lungs', 'heart', 'liver', 'intestine', 'kidney')

# Right column: 4 QWER gem sockets (position-mapped) + 1 potion (flask) slot
SOCK_AX, SOCK_AW = 447, 80
SOCK_ROWS = 4          # sockets 0-3 = Q W E R, flask takes row 4

# Middle grid: 8×4 painted cells
GRID_AX, GRID_AY, GRID_ACELL = 24, 541, 64

# Below the grid: 2 rows of vessel attribute tiles
TILE_AX, TILE_AW, TILE_AH = 20, 126, 42
TILE_PITCH = 132
TILE_ROW_AY = (810, 855)

# ── gem sockets (right column) — keys & colours ───────────────────────
GEM_KEYS = ('Q', 'W', 'E', 'R')
GEM_KEY_COLOR = {
    'Q': (90, 140, 255, 255),    # blue
    'W': (60, 200, 90, 255),     # green
    'E': (230, 70, 70, 255),     # red
    'R': (240, 240, 240, 255),   # white
}
# Owner rule: the Q/W/E/R key LABEL is always gray. The colour is carried by
# the gem art itself (and the slot border), never by the letter.
GEM_KEY_GRAY = (200, 200, 200, 230)
# An EMPTY socket shows a ghost of the gem that belongs in it, at this alpha.
GHOST_ALPHA = 0.3
# The T slot's empty state ghosts the flask art.
GHOST_FLASK_ITEM = 'flask_health'

# ── stash/bank panel (left side, drawn when stash_open is True) ────────
# The bank is drawn on its own panel art (BankStash.png, same 554×1080 canvas
# as itsmars_Inventory): skull-arch header, single 8×8 painted slot grid.
# Grid rects below are in native asset pixels; the art is drawn at
# scale sb_s = screen_h / STASH_BG_H anchored to the LEFT screen edge.
STASH_BG_W = 554
STASH_BG_H = 1080
SBG_AX, SBG_AY, SBG_ACELL = 15, 285, 64   # painted grid origin + pitch


def stash_panel_scale(screen_h: int) -> float:
    """Scale of the BankStash art for the given screen height."""
    return screen_h / STASH_BG_H


def stash_panel_w(screen_h: int) -> int:
    """On-screen pixel width of the bank panel for the given screen height."""
    return int(round(STASH_BG_W * stash_panel_scale(screen_h)))


def stash_cell_px(screen_h: int) -> int:
    """On-screen pixel size of one bank grid cell (covers a full 64px pitch)."""
    return max(8, int(round(SBG_ACELL * stash_panel_scale(screen_h))))


def stash_cell_xy(screen_h: int, col: int, row: int):
    """Top-left screen pixel of bank cell (col,row) with the art anchored left."""
    sb_s = stash_panel_scale(screen_h)
    return (int(round(SBG_AX * sb_s)) + col * stash_cell_px(screen_h),
            int(round(SBG_AY * sb_s)) + row * stash_cell_px(screen_h))

_ORGAN_LABELS = {
    'lungs':     'Lungs',
    'heart':     'Heart',
    'liver':     'Liver',
    'intestine': 'Intestine',
    'kidney':    'Kidney',
}

_TILE_ICONS = {
    'dexterity': 'dexterity', 'endurance': 'endurance', 'strength': 'strength',
    'cunning': 'cunning', 'essence': 'essence', 'nerve': 'nerve',
    'destiny': 'destiny',
}
_TILE_ORDER = ('dexterity', 'endurance', 'strength', 'cunning',
               'essence', 'nerve', 'destiny')

# ── palette ───────────────────────────────────────────────────────────
def _c(r, g, b, a=255): return rl.Color(r, g, b, a)

C_DIM      = _c(0,   0,   0,   90)
C_BG       = _c(0, 0, 0, 0x99)
C_SLOT     = _c(0, 0, 0, 0x99)
C_SLOT_HV  = _c(0xE0, 0xE0, 0xE0, 255)
C_SLOT_FL  = _c(0, 0, 0, 0x99)
C_BORDER   = _c(0xB8, 0xB8, 0xB8, 255)
C_BORDER2  = _c(0x66, 0x66, 0x66, 180)
C_TITLE    = _c(0xFF, 0xFF, 0xFF, 255)
C_LABEL    = _c(0xCC, 0xCC, 0xCC, 255)
C_TEXT     = _c(200, 200, 200, 255)
C_COUNT    = _c(255, 255, 255, 255)
C_GOLD     = _c(255, 200, 50,  255)
C_CTX_BG   = _c(0, 0, 0, 0x99)
C_CTX_HV   = _c(0xFF, 0xFF, 0xFF, 40)
C_IMPLICIT = _c(150, 170, 200, 255)   # base item implicit
C_AFFIX    = _c(120, 160, 255, 255)   # rolled affix
C_ROTTEN   = _c(198, 176, 66,  255)   # rotten-flesh yellow (BLUEPRINT §22)
C_UNIQUE   = _c(230, 120, 60,  255)   # legendary red-text
C_CMP_UP   = _c(80,  220, 90,  255)   # comparison upgrade
C_CMP_DOWN = _c(230, 70,  70,  255)   # comparison downgrade


def _rot_col(pct):
    """Green → rotten-yellow ramp for the organ rot meter (0% fresh,
    100% ROTTEN — matches C_ROTTEN, not red)."""
    t = max(0.0, min(1.0, float(pct) / 100.0))
    return _c(int(90 + (C_ROTTEN.r - 90) * t),        # 90  → 198
              int(210 + (C_ROTTEN.g - 210) * t),       # 210 → 176
              int(60 + (C_ROTTEN.b - 60) * t),         # 60  → 66
              255)


def _cmp_sign(col):
    """Comparison-row colours carry the sign: +1 up, -1 down, 0 otherwise."""
    if (col.r, col.g, col.b) == (C_CMP_UP.r, C_CMP_UP.g, C_CMP_UP.b):
        return 1
    if (col.r, col.g, col.b) == (C_CMP_DOWN.r, C_CMP_DOWN.g, C_CMP_DOWN.b):
        return -1
    return 0

# ── panel ornament colours ─────────────────────────────────────────────
C_PANEL_SLATE = _c(0, 0, 0, 0x99)
C_PANEL_OUTER = _c(0, 0, 0, 255)
C_GOLD_TRIM   = _c(0xE0, 0xE0, 0xE0, 0xCC)
C_GOLD_EDGE   = _c(0xFF, 0xFF, 0xFF, 0x88)
C_GOLD_TEXT   = _c(0xFF, 0xFF, 0xFF, 0xFF)
C_GOLD_DIM    = _c(0xE0, 0xE0, 0xE0, 0xFF)
C_GOLD_FAINT  = _c(0xFF, 0xFF, 0xFF, 0x66)

# ── panel ornament helpers ─────────────────────────────────────────────

def _stone_side_panel(x: int, y: int, w: int, h: int, corner_side: str = 'right'):
    """D2-style vertical stone panel for the stash sidebar."""
    rl.draw_rectangle(x, y, w, h, C_PANEL_OUTER)
    rl.draw_rectangle(x + 2, y + 2, w - 4, h - 4, C_PANEL_SLATE)
    rl.draw_rectangle_lines_ex(rl.Rectangle(float(x + 3), float(y + 3), float(w - 6), float(h - 6)),
                               1, C_GOLD_TRIM)
    rl.draw_rectangle_lines_ex(rl.Rectangle(float(x + 1), float(y + 1), float(w - 2), float(h - 2)),
                               1, C_GOLD_EDGE)
    corner_len, corner_gap = 18, 6
    if corner_side == 'right':
        corners = [
            (x + w - corner_gap, y + corner_gap, -1, 1),
            (x + w - corner_gap, y + h - corner_gap, -1, -1),
        ]
    elif corner_side == 'left':
        corners = [
            (x + corner_gap, y + corner_gap, 1, 1),
            (x + corner_gap, y + h - corner_gap, 1, -1),
        ]
    else:
        corners = [
            (x + corner_gap, y + corner_gap, 1, 1),
            (x + w - corner_gap, y + corner_gap, -1, 1),
            (x + corner_gap, y + h - corner_gap, 1, -1),
            (x + w - corner_gap, y + h - corner_gap, -1, -1),
        ]
    for cx, cy, dx, dy in corners:
        rl.draw_line(cx, cy, cx + dx * corner_len, cy, C_GOLD_TEXT)
        rl.draw_line(cx, cy, cx, cy + dy * corner_len, C_GOLD_TEXT)
        rl.draw_line(cx + 1, cy + 1, cx + 1 + dx * (corner_len - 4), cy + 1, C_GOLD_FAINT)
        rl.draw_line(cx + 1, cy + 1, cx + 1, cy + 1 + dy * (corner_len - 4), C_GOLD_FAINT)


_RARITY_COL = {
    'common':    _c(200, 200, 200, 255),
    'uncommon':  _c(50,  210, 80,  255),
    'rare':      _c(80,  140, 255, 255),
    'epic':      _c(220, 60,  60,  255),
    'legendary': _c(255, 210, 40,  255),
    'mythic':    _c(255, 100, 255, 255),
}
_RARITY_BORDER = {
    'common':    _c(75,  75,  75,  255),
    'uncommon':  _c(30,  155, 60,  255),
    'rare':      _c(50,  95,  220, 255),
    'epic':      _c(165, 30,  30,  255),
    'legendary': _c(200, 160, 20,  255),
    'mythic':    _c(200, 60,  200, 255),
}


def _entry_dict(value):
    """Return a usable inventory entry mapping, or None for legacy raw IDs."""
    return value if isinstance(value, dict) else None


def _rarity_of(entry):
    """Instance rarity if rolled, else the base item's static rarity."""
    if not entry:
        return 'common'
    inst = entry.get('instance_data')
    if inst:
        return inst.get('rarity', 'common')
    return ITEMS.get(entry['item'], {}).get('rarity', 'common')


def _count_label(entry):
    """Corner count text; tarot card stacks read 'n/4' quarters."""
    count = entry.get('count', 1)
    if currency_mod.is_card_item(entry.get('item', '')):
        return currency_mod.stack_label(entry)
    return str(count) if count > 1 else None


class InventoryUI:
    def __init__(self):
        self.open         = False
        self._icons       = {}
        self._err         = None
        self._ctx         = None
        self._hovered     = None
        self.on_drop_item    = None
        self._confirm_drop   = None   # pending drop confirmation
        self.stash_open      = False
        self._stash_grid     = None   # reference to char.stash (single 8x8 bank grid)
        self.on_stash_change = None   # called after any stash mutation (triggers save)
        self._ui_frames      = {}     # slot frame spritesheets keyed by slot type
        self._ui_header      = None   # header banner
        self._pickup_flashes = {}     # id(entry) → timer for new-item glow
        self._grid_id_set    = set()  # last frame's grid item identities
        self._apply_pending  = None   # tarot card awaiting a target item
        self.on_apply_card   = None   # (card_entry, src, idx, t_src, t_idx)
        self._bg             = None   # itsmars_Inventory panel art
        self._stash_bg       = None   # BankStash panel art (left side)
        self.char_provider   = None   # () -> Character, for attribute tiles
        self.on_gear_change   = None   # called after any equip/dequip/identify
                                         # mutation so the owner can invalidate
                                         # and recompute derived stats.
        self.layout_dbg      = False  # inv_layout debug overlay
        self._notice         = None    # (text, remaining seconds) transient panel notice
        self._notice_timer   = 0.0

    def notify(self, text: str, seconds: float = 2.0):
        """Set the transient in-panel notice line ('Backpack full!' etc.)."""
        self._notice = text
        self._notice_timer = seconds

    def _tick_notice(self):
        if self._notice_timer > 0.0:
            self._notice_timer = max(0.0, self._notice_timer - rl.get_frame_time())
            if self._notice_timer <= 0.0:
                self._notice = None

    def _gear_changed(self):
        """Notify the owner that equipped gear changed (derived-stat cache)."""
        if self.on_gear_change:
            try:
                self.on_gear_change()
            except Exception:
                pass

    # ── assets ────────────────────────────────────────────────────────

    def load(self):
        err_path = os.path.join(_ASSETS, 'items', 'error.png')
        if os.path.exists(err_path):
            self._err = rl.load_texture(err_path)
        for item_id, defn in ITEMS.items():
            path = os.path.join(_ASSETS, defn['img'])
            if os.path.exists(path):
                self._icons[item_id] = rl.load_texture(path)

        def _uf(name):
            p = os.path.join(_UI_ASSETS, name)
            if not os.path.exists(p):
                return None
            t = rl.load_texture(p)
            rl.set_texture_filter(t, rl.TEXTURE_FILTER_POINT)
            return t

        self._ui_frames = {
            'empty':     _uf('20251124emptyFrameA1-Sheet.png'),
        }
        self._ui_header = _uf('20251124darkDwellersHeaderA.png')
        self._ui_slot_border = _uf('bank64x64 BagSlotBorder.png')

        bg_path = os.path.join(_UI_ASSETS, 'itsmars_Inventory.jpg')
        if os.path.exists(bg_path):
            self._bg = rl.load_texture(bg_path)   # linear filter: photo art

        stash_bg_path = os.path.join(_UI_ASSETS, 'BankStash.png')
        if os.path.exists(stash_bg_path):
            self._stash_bg = rl.load_texture(stash_bg_path)   # linear: photo art

    def unload(self):
        for t in self._icons.values():
            rl.unload_texture(t)
        if self._err:
            rl.unload_texture(self._err)
        seen = set()
        for t in self._ui_frames.values():
            if t and t.id > 0 and t.id not in seen:
                rl.unload_texture(t)
                seen.add(t.id)
        b = getattr(self, '_ui_slot_border', None)
        if b and b.id > 0 and b.id not in seen:
            rl.unload_texture(b)
            seen.add(b.id)
        for t in (self._bg, self._stash_bg):
            if t and t.id > 0 and t.id not in seen:
                rl.unload_texture(t)
                seen.add(t.id)

    # ── open / close ──────────────────────────────────────────────────

    def toggle(self):
        self.open = not self.open
        if not self.open:
            self._ctx = None

    def close(self):
        if self.open:
            self.open = False
            self._ctx = None

    def open_stash(self, stash_grid):
        self.stash_open  = True
        self._stash_grid = stash_grid   # char.stash — single 8x8 bank grid

    def close_stash(self):
        self.stash_open  = False
        self._stash_grid = None

    # ── panel geometry ────────────────────────────────────────────────

    def _panel(self, screen_w, screen_h):
        """(left edge px, scale s) of the inventory panel for this frame."""
        s = screen_h / BG_H
        return screen_w - BG_W * s, s

    def _rect(self, px, s, ax, ay, aw, ah):
        return rl.Rectangle(px + ax * s, ay * s, aw * s, ah * s)

    def _organ_rect(self, px, s, i):
        return self._rect(px, s, ORG_AX, ORG_AY + i * ORG_PITCH, ORG_AW, ORG_AH)

    def _socket_rect(self, px, s, i):
        return self._rect(px, s, SOCK_AX, ORG_AY + i * ORG_PITCH, SOCK_AW, ORG_AH)

    def _flask_rect(self, px, s):
        return self._socket_rect(px, s, SOCK_ROWS)

    def _grid_rect(self, px, s):
        return self._rect(px, s, GRID_AX, GRID_AY,
                          GRID_ACELL * INV_COLS, GRID_ACELL * INV_ROWS)

    def _tile_rect(self, px, s, i):
        row, col = divmod(i, 4)
        return self._rect(px, s, TILE_AX + col * TILE_PITCH,
                          TILE_ROW_AY[row], TILE_AW, TILE_AH)

    # inventory-grid helpers (INV dims)
    @staticmethod
    def _ap_inv(grid, slot):
        return grid_auto_place_instance(grid, slot, cols=INV_COLS, rows=INV_ROWS)

    @staticmethod
    def _place_inv(grid, item_id, count):
        return grid_auto_place(grid, item_id, count, cols=INV_COLS, rows=INV_ROWS)

    # ── update / input ────────────────────────────────────────────────

    def update(self, inventory, stats):
        if not self.open:
            return

        cw      = rl.get_screen_width()
        ch      = rl.get_screen_height()
        px, s   = self._panel(cw, ch)
        mx      = rl.get_mouse_x()
        my      = rl.get_mouse_y()
        lmb     = inp.mouse_pressed(self, rl.MOUSE_BUTTON_LEFT)
        rmb     = inp.mouse_pressed(self, rl.MOUSE_BUTTON_RIGHT)

        # Tarot card APPLY targeting mode (issue #73 phase B)
        if self._apply_pending is not None:
            if inp.key_pressed(self, rl.KEY_ESCAPE) or rmb:
                self._apply_pending = None
            elif lmb:
                hit = self._slot_at(mx, my, inventory, px, s)
                if hit and hit['slot'] and self.on_apply_card:
                    ap = self._apply_pending
                    self.on_apply_card(ap['entry'], ap['src'], ap['idx'],
                                       hit['source'], hit['index'])
                self._apply_pending = None
            return

        # Pending drop confirmation — handle yes/no clicks
        if self._confirm_drop:
            self._handle_confirm_drop(mx, my, lmb)
            return

        self._inventory_for_menu = inventory.get('grid', []) if isinstance(inventory, dict) else inventory
        # the whole inventory — the context menu needs the gem sockets to know
        # whether SOCKET is currently available (issue #94)
        self._inventory_for_ctx  = inventory
        panel_w = stash_panel_w(ch)
        in_inv   = px <= mx < cw and 0 <= my < ch
        in_stash = (self.stash_open and self._stash_grid is not None
                    and 0 <= mx < panel_w and 0 <= my < ch)

        # Context menu has priority
        if self._ctx is not None:
            if lmb:
                action = self._ctx_hit(mx, my)
                if action:
                    self._exec(action, inventory, stats)
                self._ctx = None
            elif rmb:
                self._ctx = None
            return

        # Ignore clicks outside both active panels
        if (lmb or rmb) and not in_inv and not in_stash:
            return

        # Left-click item move and drag-and-drop were removed (issue #94);
        # interactions are right-click context-menu driven.
        if rmb and in_inv:
            hit = self._slot_at(mx, my, inventory, px, s)
            if hit and hit['slot']:
                self._ctx = {'x': mx, 'y': my, **hit}
        elif rmb and in_stash and self._stash_grid is not None:
            hit = self._slot_at_stash(mx, my)
            if hit and hit['slot']:
                self._ctx = {'x': mx, 'y': my, **hit}

    # ── actions ───────────────────────────────────────────────────────

    def _exec(self, action, inventory, stats):
        atype = action['type']
        src   = action['source']
        idx   = action['index']

        if atype == 'use':
            entry = self._get_entry(inventory, src, idx)
            if not entry:
                return
            defn = ITEMS.get(entry['item'], {})
            for stat, amt in (defn.get('use') or {}).items():
                if stat in stats:
                    cap = stats.get('max_' + stat, 100)
                    stats[stat] = min(cap, stats[stat] + amt)
            entry['count'] -= 1
            if entry['count'] <= 0:
                self._clear_entry(inventory, src, idx)

        elif atype == 'equip':
            if src == 'grid' and equip_from_grid(inventory, idx):
                self._gear_changed()

        elif atype == 'socket':
            # SOCKET from the right-click menu (issue #94): place the gem into
            # its own colour's key socket. Refuses a wrong-colour or occupied
            # slot. The gear-change notification refreshes derived stats and
            # the character level readout.
            if src == 'grid' and socket_gem_from_grid(inventory, idx):
                self._gear_changed()

        elif atype == 'dequip':
            entry = inventory['equipped'].get(idx)
            if not entry:
                return
            # honour the auto-place result: on a full backpack the item
            # STAYS equipped and a notice is shown instead of vanishing
            if not self._ap_inv(inventory['grid'], entry):
                self.notify('Backpack full!')
                return
            inventory['equipped'][idx] = None
            self._gear_changed()

        elif atype == 'apply':
            entry = self._get_entry(inventory, src, idx)
            if entry and currency_mod.card_complete(entry):
                self._apply_pending = {'entry': entry, 'src': src, 'idx': idx}

        elif atype == 'identify':
            entry = self._get_entry(inventory, src, idx)
            if not entry or itemgen.is_identified(entry):
                return
            fool = next((e for e in inventory.get('grid', [])
                         if currency_mod.arcana_of(e.get('item', '')) == 0
                         and currency_mod.card_complete(e)), None)
            if fool is None:
                return
            currency_mod.consume_card(inventory, fool, 'grid',
                                      inventory['grid'].index(fool))
            itemgen.identify(entry)
            self._gear_changed()

        elif atype == 'remove_gem':
            if src != 'gems':
                return
            entry = (inventory.get('gem_sockets') or {}).get(idx)
            if entry:
                # full backpack: the gem STAYS socketed, nothing is lost
                if not self._ap_inv(inventory['grid'], entry):
                    self.notify('Backpack full!')
                    return
                inventory['gem_sockets'][idx] = None
                self._gear_changed()

        elif atype == 'remove_flask':
            if src != 'flask':
                return
            entry = inventory.get('flask_slot')
            if entry:
                if not self._ap_inv(inventory['grid'], entry):
                    self.notify('Backpack full!')
                    return
                inventory['flask_slot'] = None
                self._gear_changed()

        elif atype == 'drop':
            entry = self._get_entry(inventory, src, idx)
            self._confirm_drop = {'entry': entry, 'src': src, 'idx': idx,
                                  'inventory': inventory, 'from_ctx': True}

        elif atype == 'split':
            entry = self._get_entry(inventory, src, idx)
            if not entry or not entry.get('count', 1) > 1:
                return
            half = entry['count'] // 2
            entry['count'] -= half
            self._place_inv(inventory['grid'], entry['item'], half)

        elif atype == 'to_bank':
            # PUT IN BANK (right-click): auto-place the backpack item in the
            # bank grid and persist via the stash-change callback.
            if src != 'grid' or self._stash_grid is None:
                return
            entry = self._get_entry(inventory, src, idx)
            if not entry:
                return
            entry_clean = {k: v for k, v in entry.items() if k not in ('col', 'row')}
            if grid_auto_place_instance(self._stash_grid, entry_clean):
                self._clear_entry(inventory, src, idx)
                if self.on_stash_change:
                    self.on_stash_change()

        elif atype == 'to_inventory':
            # PUT IN BACKPACK: move a bank item into the backpack grid.
            if src != 'stash' or self._stash_grid is None:
                return
            entry = self._get_entry(inventory, src, idx)
            if not entry:
                return
            entry_clean = {k: v for k, v in entry.items() if k not in ('col', 'row')}
            if self._ap_inv(inventory['grid'], entry_clean):
                self._stash_grid.pop(idx)
                if self.on_stash_change:
                    self.on_stash_change()

    def _handle_confirm_drop(self, mx, my, lmb):
        """Handle yes/no on the drop confirmation popup."""
        if not self._confirm_drop:
            return
        cw, ch = rl.get_screen_width(), rl.get_screen_height()
        pw, ph = 260, 120
        px = cw // 2 - pw // 2
        py = ch // 2 - ph // 2
        yes_r = rl.Rectangle(px + 20, py + ph - 50, 90, 32)
        no_r  = rl.Rectangle(px + pw - 110, py + ph - 50, 90, 32)
        if lmb:
            if rl.check_collision_point_rec(rl.Vector2(float(mx), float(my)), no_r):
                self._confirm_drop = None
            elif rl.check_collision_point_rec(rl.Vector2(float(mx), float(my)), yes_r):
                cd = self._confirm_drop
                if cd.get('from_ctx'):
                    self._clear_entry(cd['inventory'], cd['src'], cd['idx'])
                if cd['entry'] and self.on_drop_item:
                    self.on_drop_item(cd['entry'])
                self._confirm_drop = None

    def _draw_confirm_drop(self, cw, ch, mx, my):
        """Draw the drop confirmation popup."""
        pw, ph = 260, 120
        px = cw // 2 - pw // 2
        py = ch // 2 - ph // 2
        rl.draw_rectangle(px, py, pw, ph, rl.Color(0, 0, 0, 0x99))
        rl.draw_rectangle_lines(px, py, pw, ph, rl.Color(0xE0, 0xE0, 0xE0, 255))
        msg = "Drop this item?"
        fw = fonts.measure(msg, 18)
        fonts.draw(msg, px + pw // 2 - fw // 2, py + 16, 18, rl.Color(220, 220, 200, 255))
        item_id = self._confirm_drop['entry']['item']
        item_name = ITEMS.get(item_id, {}).get('name', item_id)
        fw2 = fonts.measure(item_name, 14)
        fonts.draw(item_name, px + pw // 2 - fw2 // 2, py + 44, 14, rl.Color(0xCC, 0xCC, 0xCC, 200))
        yes_r = rl.Rectangle(px + 20, py + ph - 50, 90, 32)
        no_r  = rl.Rectangle(px + pw - 110, py + ph - 50, 90, 32)
        _btn(yes_r, 'Yes', 16, accent=True)
        _btn(no_r, 'No', 16)

    # ── bank hit-testing ─────────────────────────────────────────────

    def _grid_cell_at_stash(self, mx, my):
        """Return (col, row) of the bank grid cell under the cursor, or None."""
        ch = rl.get_screen_height()
        sb_s = stash_panel_scale(ch)
        rel_x = (mx - SBG_AX * sb_s)
        rel_y = (my - SBG_AY * sb_s)
        cell  = stash_cell_px(ch)
        if rel_x < 0 or rel_y < 0:
            return None
        col = int(rel_x // cell)
        row = int(rel_y // cell)
        if col >= GRID_COLS or row >= GRID_ROWS:
            return None
        return (col, row)

    def _slot_at_stash(self, mx, my):
        """Return hit dict for the bank grid item under the cursor, or None."""
        stash_grid = self._stash_grid or []
        ch = rl.get_screen_height()
        sb_s = stash_panel_scale(ch)
        cell  = stash_cell_px(ch)
        rel_x = mx - SBG_AX * sb_s
        rel_y = my - SBG_AY * sb_s
        if rel_x < 0 or rel_y < 0:
            return None
        col = int(rel_x // cell)
        row = int(rel_y // cell)
        if col >= GRID_COLS or row >= GRID_ROWS:
            return None
        gmap     = grid_build_map(stash_grid)
        item_idx = gmap[row][col]
        if item_idx is not None:
            return {'source': 'stash', 'index': item_idx, 'slot': stash_grid[item_idx]}
        return None

    def _get_entry(self, inventory, src, idx):
        if src == 'grid':
            return inventory['grid'][idx] if idx < len(inventory['grid']) else None
        if src == 'stash' and self._stash_grid is not None:
            return self._stash_grid[idx] if idx < len(self._stash_grid) else None
        if src == 'equipped':
            return inventory['equipped'].get(idx)
        if src == 'gems':
            return (inventory.get('gem_sockets') or {}).get(idx)
        if src == 'flask':
            return inventory.get('flask_slot')
        return None

    def _clear_entry(self, inventory, src, idx):
        if src == 'grid':
            if idx < len(inventory['grid']):
                inventory['grid'].pop(idx)
        elif src == 'equipped':
            inventory['equipped'][idx] = None
        elif src == 'gems':
            if idx in (inventory.get('gem_sockets') or {}):
                inventory['gem_sockets'][idx] = None
        elif src == 'flask':
            inventory['flask_slot'] = None

    # ── hit testing ───────────────────────────────────────────────────

    def _slot_at(self, mx, my, inventory, px, s):
        # T flask socket (right column, below the gem sockets)
        r = self._flask_rect(px, s)
        if r.x <= mx < r.x + r.width and r.y <= my < r.y + r.height:
            return {'source': 'flask', 'index': 'T',
                    'slot': inventory.get('flask_slot')}
        # QWER gem sockets (right column, position-mapped)
        sockets = inventory.get('gem_sockets') or {}
        for i, key in enumerate(GEM_KEYS):
            r = self._socket_rect(px, s, i)
            if r.x <= mx < r.x + r.width and r.y <= my < r.y + r.height:
                return {'source': 'gems', 'index': key, 'slot': sockets.get(key)}
        # Organs (left column)
        for i, key in enumerate(ORG_ORDER):
            r = self._organ_rect(px, s, i)
            if r.x <= mx < r.x + r.width and r.y <= my < r.y + r.height:
                return {'source': 'equipped', 'index': key,
                        'slot': inventory['equipped'].get(key)}
        # Backpack grid
        return self._grid_hit(mx, my, inventory, px, s)

    def _grid_cell_at(self, mx, my, px, s):
        """Return (col, row) of any inventory grid cell under the cursor, or None."""
        rel_x = (mx - px) / s - GRID_AX
        rel_y = my / s - GRID_AY
        if rel_x < 0 or rel_y < 0:
            return None
        col = int(rel_x // GRID_ACELL)
        row = int(rel_y // GRID_ACELL)
        if col >= INV_COLS or row >= INV_ROWS:
            return None
        return (col, row)

    def _grid_hit(self, mx, my, inventory, px, s):
        cell = self._grid_cell_at(mx, my, px, s)
        if cell is None:
            return None
        col, row = cell
        gmap = grid_build_map(inventory['grid'], cols=INV_COLS, rows=INV_ROWS)
        item_idx = gmap[row][col]
        if item_idx is not None:
            return {'source': 'grid', 'index': item_idx,
                    'slot': inventory['grid'][item_idx]}
        return None

    # ── context menu ─────────────────────────────────────────────────

    def _ctx_options(self):
        if not self._ctx:
            return []
        slot = _entry_dict(self._ctx['slot'])
        src  = self._ctx['source']
        if not slot:
            return []
        defn = ITEMS.get(slot['item'], {})
        opts = []
        if itemgen.is_identified(slot) is False and not currency_mod.is_card_item(slot.get('item', '')):
            has_fool = any(currency_mod.arcana_of(e.get('item', '')) == 0
                           and currency_mod.card_complete(e)
                           for e in (_entry_dict(x) for x in getattr(self, '_inventory_for_menu', []))
                           if e is not None)
            opts.append({'type': 'identify', 'enabled': has_fool,
                         'label': 'IDENTIFY' if has_fool else 'IDENTIFY (need Fool 4/4)'})
        if src in ('grid', 'stash'):
            if defn.get('use'):
                opts.append({'type': 'use',       'label': 'USE'})
            if currency_mod.is_card_item(slot.get('item', '')) \
                    and currency_mod.card_complete(slot):
                opts.append({'type': 'apply',     'label': 'APPLY'})
            if defn.get('equipSlot'):
                # Owner rule: unidentified items cannot be implanted — they
                # must be identified with The Joker first (#84 reversed).
                if itemgen.is_identified(slot):
                    opts.append({'type': 'equip', 'label': 'IMPLANT'})
                else:
                    opts.append({'type': 'equip', 'enabled': False,
                                 'label': 'IMPLANT (unidentified)'})
            if defn.get('stackable') and slot.get('count', 1) > 1:
                opts.append({'type': 'split',     'label': f'SPLIT ({slot["count"]})'})
            # A gem in the GRID is socketable with the right-click menu alone:
            # left-click drag and drop was removed in issue #94, so without this
            # action a gem looted in the delve could never be equipped.
            if src == 'grid':
                key = items_mod.gem_socket_target(slot)
                if key:
                    taken = bool((getattr(self, '_inventory_for_ctx', None) or {})
                                 .get('gem_sockets', {}).get(key))
                    opts.append({'type': 'socket',
                                 'enabled': not taken,
                                 'label': (f'SOCKET ({key} occupied)' if taken
                                           else f'SOCKET ({key})')})
            elif src == 'stash':
                opts.append({'type': 'to_inventory', 'label': 'PUT IN BACKPACK'})
        elif src == 'equipped':
            opts.append({'type': 'dequip',        'label': 'EXPLANT'})
        elif src == 'gems':
            opts.append({'type': 'remove_gem',    'label': 'REMOVE'})
        elif src == 'flask':
            opts.append({'type': 'remove_flask',  'label': 'REMOVE'})
        # With the bank open, a backpack item can be stored directly.
        if src == 'grid' and self.stash_open and self._stash_grid is not None:
            opts.append({'type': 'to_bank', 'label': 'PUT IN BANK'})
        opts.append({'type': 'drop', 'label': 'DROP'})
        return opts

    def _ctx_hit(self, mx, my):
        if not self._ctx:
            return None
        cx, cy  = self._ctx['x'], self._ctx['y']
        opts    = self._ctx_options()
        item_h  = 26
        menu_w  = 220
        for i, opt in enumerate(opts):
            ry = cy + 2 + i * item_h
            if cx <= mx < cx + menu_w and ry <= my < ry + item_h:
                if not opt.get('enabled', True):
                    return None
                return {**opt, 'source': self._ctx['source'], 'index': self._ctx['index']}
        return None

    # ── sprite-sheet frame helper ─────────────────────────────────────

    @staticmethod
    def _draw_frame(tex, frame_idx, sx, sy, size, tint=None):
        t = tint if tint is not None else rl.WHITE
        if tex and tex.id > 0:
            fw  = tex.width // 5
            src = rl.Rectangle(float(frame_idx * fw), 0.0, float(fw), float(tex.height))
            dst = rl.Rectangle(float(sx), float(sy), float(size), float(size))
            rl.draw_texture_pro(tex, src, dst, rl.Vector2(0, 0), 0.0, t)
        else:
            rl.draw_rectangle(sx, sy, size, size, rl.Color(0, 0, 0, 230))
            rl.draw_rectangle_lines(sx, sy, size, size, rl.Color(0x99, 0x99, 0x99, 220))

    @staticmethod
    def _icon_dst(icon, r: rl.Rectangle, pad: float):
        """Aspect-fit destination rect for an icon inside screen rect r.

        Portrait art (e.g. 300×527 tarot cards) keeps its shape and is
        centred in the square slot instead of being stretched to a square.
        """
        iw, ih = float(icon.width), float(icon.height)
        bw, bh = r.width - pad * 2, r.height - pad * 2
        if bw <= 0 or bh <= 0:
            return r
        k = min(bw / iw, bh / ih)
        w, h = iw * k, ih * k
        return rl.Rectangle(r.x + (r.width - w) / 2, r.y + (r.height - h) / 2, w, h)

    def _draw_icon_in_rect(self, entry, r: rl.Rectangle, pad_ratio=0.08):
        """Draw an item icon aspect-fit and centred inside a screen rect."""
        icon = self._icons.get(entry['item']) or self._err
        if not icon:
            return
        pad = min(r.width, r.height) * pad_ratio
        rl.draw_texture_pro(icon,
            rl.Rectangle(0, 0, float(icon.width), float(icon.height)),
            self._icon_dst(icon, r, pad),
            rl.Vector2(0, 0), 0.0, rl.WHITE)

    def _in_rect(self, mx, my, r: rl.Rectangle):
        return r.x <= mx < r.x + r.width and r.y <= my < r.y + r.height

    # ── draw ──────────────────────────────────────────────────────────

    def draw(self, inventory, screen_w, screen_h):
        if not self.open:
            return

        px, s = self._panel(screen_w, screen_h)
        mx  = rl.get_mouse_x()
        my  = rl.get_mouse_y()
        self._hovered = None

        # Stash panel (left side) — draw first so inventory panel renders on top
        if self.stash_open and self._stash_grid is not None:
            self._draw_stash_panel(screen_w, screen_h, mx, my)
            # Dim only the center area between the two panels
            panel_w = stash_panel_w(screen_h)
            center_w = px - panel_w
            if center_w > 0:
                rl.draw_rectangle(panel_w, 0, int(center_w), screen_h, C_DIM)
        else:
            # Dim everything to the left of the inventory panel
            rl.draw_rectangle(0, 0, int(px), screen_h, C_DIM)

        # Panel background art
        if self._bg and self._bg.id > 0:
            rl.draw_texture_pro(self._bg,
                rl.Rectangle(0, 0, float(self._bg.width), float(self._bg.height)),
                rl.Rectangle(px, 0, BG_W * s, BG_H * s),
                rl.Vector2(0, 0), 0.0, rl.WHITE)
        else:
            rl.draw_rectangle(int(px), 0, int(BG_W * s), screen_h, C_SLOT)

        self._draw_organs(inventory, px, s, mx, my)
        self._draw_sockets(inventory, px, s, mx, my)
        self._draw_flask_socket(inventory, px, s, mx, my)
        self._draw_grid(inventory, px, s, mx, my)
        self._draw_tiles(px, s, mx, my)
        self._draw_character_level(inventory, px)

        # transient notice (e.g. 'Backpack full!')
        self._tick_notice()
        if self._notice:
            nx = px + 12 * s
            nw = fonts.measure(self._notice, 16)
            rl.draw_rectangle(int(nx - 8), int(46 * s), int(nw + 16),
                              int(24 * s), _c(0, 0, 0, 0xaa))
            fonts.draw(self._notice, int(nx), int(50 * s), 16, C_CMP_DOWN)

        if self.layout_dbg:
            self._draw_layout_dbg(px, s)

        # Apply-targeting hint banner
        if self._apply_pending:
            ap = self._apply_pending
            cname = ITEMS.get(ap['entry'].get('item', ''), {}).get('name', 'Card')
            msg = f'APPLY {cname}: click a target item (Esc cancels)'
            mw = fonts.measure(msg, 18)
            rl.draw_rectangle(rl.get_screen_width() // 2 - mw // 2 - 10, 8, mw + 20, 26, _c(0, 0, 0, 0x99))
            fonts.draw(msg, rl.get_screen_width() // 2 - mw // 2, 12, 18, C_GOLD_TEXT)

        # Tooltip — anchored to whichever panel the cursor is in
        if self._hovered:
            tooltip_anchor = (stash_panel_w(screen_h)
                              if (self.stash_open and mx < stash_panel_w(screen_h))
                              else px)
            self._draw_tooltip(self._hovered, tooltip_anchor, inventory)

        # Context menu on top
        if self._ctx:
            self._draw_ctx(mx, my)

        # Drop confirmation popup
        if self._confirm_drop:
            self._draw_confirm_drop(screen_w, screen_h, mx, my)

    # ── bank panel draw ──────────────────────────────────────────────

    def _draw_stash_panel(self, screen_w, screen_h, mx, my):
        """Draw the left-side bank panel on its BankStash art."""
        sb_s = stash_panel_scale(screen_h)
        panel_w = stash_panel_w(screen_h)

        # Panel background art (skull arch speaks for itself — no header text)
        if self._stash_bg and self._stash_bg.id > 0:
            rl.draw_texture_pro(self._stash_bg,
                rl.Rectangle(0, 0, float(self._stash_bg.width), float(self._stash_bg.height)),
                rl.Rectangle(0, 0, float(panel_w), float(screen_h)),
                rl.Vector2(0, 0), 0.0, rl.WHITE)
        else:
            _stone_side_panel(0, 0, panel_w, screen_h, corner_side='left')

        # Grid
        stash_grid = self._stash_grid if self._stash_grid is not None else []
        self._draw_stash_grid(stash_grid, sb_s, mx, my)

    def _draw_stash_grid(self, stash_grid, sb_s, mx, my):
        """Draw bank grid highlights and placed items over the painted cells."""
        cell = stash_cell_px(int(sb_s * STASH_BG_H))
        gx   = int(round(SBG_AX * sb_s))
        gy   = int(round(SBG_AY * sb_s))

        # Empty cell hover highlight only — the art provides the frames
        cell_map = grid_build_map(stash_grid)
        for row in range(GRID_ROWS):
            for col in range(GRID_COLS):
                sx = gx + col * cell
                sy = gy + row * cell
                if cell_map[row][col] is None and sx <= mx < sx + cell and sy <= my < sy + cell:
                    rl.draw_rectangle(sx, sy, cell, cell, _c(255, 255, 255, 18))

        # Items
        for item_idx, entry in enumerate(stash_grid):
            if not isinstance(entry, dict):
                continue
            idef     = ITEMS.get(entry['item'], {})
            w, h     = idef.get('size', (1, 1))
            col, row = entry['col'], entry['row']
            sx = gx + col * cell
            sy = gy + row * cell
            iw = w * cell
            ih = h * cell

            hov    = sx <= mx < sx + iw and sy <= my < sy + ih
            rarity = _rarity_of(entry)
            if hov:
                self._hovered = entry

            rl.draw_rectangle(sx, sy, iw, ih, C_SLOT_FL)
            rl.draw_rectangle_lines(sx, sy, iw, ih,
                                    _RARITY_BORDER.get(rarity, C_BORDER))

            icon = self._icons.get(entry['item']) or self._err
            if icon:
                pad = 3
                rl.draw_texture_pro(icon,
                    rl.Rectangle(0, 0, float(icon.width), float(icon.height)),
                    self._icon_dst(icon, rl.Rectangle(float(sx), float(sy),
                                                      float(iw), float(ih)), pad),
                    rl.Vector2(0, 0), 0.0, rl.WHITE)

            cnt = _count_label(entry)
            if cnt:
                fsz = max(11, int(cell * 0.25))
                fonts.draw(cnt,
                             sx + iw - fonts.measure(cnt, fsz) - 2,
                             sy + ih - fsz - 3, fsz, C_COUNT)

    # ── section draw helpers ─────────────────────────────────────────

    def _draw_organs(self, inventory, px, s, mx, my):
        for i, key in enumerate(ORG_ORDER):
            r    = self._organ_rect(px, s, i)
            slot = inventory['equipped'].get(key)
            hov  = self._in_rect(mx, my, r)
            if hov and slot:
                self._hovered = slot

            if slot:
                rl.draw_rectangle_rec(r, C_SLOT_FL)
                rl.draw_rectangle_lines_ex(r, 1, _RARITY_BORDER.get(_rarity_of(slot), C_BORDER))
                self._draw_icon_in_rect(slot, r)
            else:
                # empty: faint organ icon so the slot's purpose reads at a glance
                icons.draw(key, int(r.x + r.width / 2 - 12), int(r.y + r.height / 2 - 12),
                           24, _c(120, 120, 120, 90))
            if hov:
                rl.draw_rectangle_lines_ex(r, 2, C_SLOT_HV)

    def _draw_ghost_icon(self, item_id, r: rl.Rectangle):
        """Draw an item's art dimmed to GHOST_ALPHA inside rect r.

        Used for the EMPTY state of the QWER gem sockets and the T flask
        slot: the slot shows what belongs in it. Never drawn behind a filled
        slot — that would tint the real gem.
        """
        icon = self._icons.get(item_id) or self._err
        if not icon:
            return
        pad = min(r.width, r.height) * 0.08
        tint = rl.Color(255, 255, 255, int(round(255 * GHOST_ALPHA)))
        rl.draw_texture_pro(icon,
            rl.Rectangle(0, 0, float(icon.width), float(icon.height)),
            self._icon_dst(icon, r, pad),
            rl.Vector2(0, 0), 0.0, tint)

    def _draw_sockets(self, inventory, px, s, mx, my):
        """QWER gem sockets (right column, position-mapped, issue #73).

        Filled: the real gem at full opacity, gray key label. Empty: a 0.3
        alpha ghost of the gem that belongs in that key, so Q hints blue, W
        green, E red and R white without a coloured letter.
        """
        sockets = inventory.get('gem_sockets') or {}
        for i, key in enumerate(GEM_KEYS):
            r = self._socket_rect(px, s, i)
            entry = sockets.get(key)
            hov = self._in_rect(mx, my, r)
            if hov and entry:
                self._hovered = entry
            if entry:
                rl.draw_rectangle_rec(r, C_SLOT_FL)
                self._draw_icon_in_rect(entry, r)
            else:
                rl.draw_rectangle_rec(r, C_SLOT_FL)
                self._draw_ghost_icon(gems_mod.GEM_ITEM_FOR_SLOT[key], r)
            col = GEM_KEY_COLOR[key]
            rl.draw_rectangle_lines_ex(r, 1, col if not hov else C_SLOT_HV)
            kf = max(11, int(r.height * 0.30))
            fonts.draw(key, int(r.x + r.width - kf - 3), int(r.y + 2), kf,
                       rl.Color(*GEM_KEY_GRAY))

    def _draw_flask_socket(self, inventory, px, s, mx, my):
        r     = self._flask_rect(px, s)
        entry = inventory.get('flask_slot')
        hov   = self._in_rect(mx, my, r)
        if hov and entry:
            self._hovered = entry
        if entry:
            rl.draw_rectangle_rec(r, C_SLOT_FL)
            self._draw_icon_in_rect(entry, r)
            charges = entry.get('charges')
            if charges is not None:
                fs = max(12, int(r.height * 0.28))
                fonts.draw(f"{int(charges)}", int(r.x + 3), int(r.y + r.height - fs - 2),
                           fs, C_COUNT)
        else:
            rl.draw_rectangle_rec(r, C_SLOT_FL)
            # empty T slot: a dimmed ghost of the flask art, same rule as the
            # QWER gem sockets
            self._draw_ghost_icon(GHOST_FLASK_ITEM, r)
        rl.draw_rectangle_lines_ex(r, 1, _c(120, 220, 140, 160) if not hov else C_SLOT_HV)
        kf = max(12, int(r.height * 0.30))
        fonts.draw('T', int(r.x + r.width - kf - 3), int(r.y + 2), kf, rl.Color(*GEM_KEY_GRAY))

    def _draw_grid(self, inventory, px, s, mx, my):
        cell = max(8, int(round(GRID_ACELL * s)))
        gx   = int(round(px + GRID_AX * s))
        gy   = int(round(GRID_AY * s))

        # Pickup glow: detect new items in grid vs last frame
        cur_ids = {id(entry) for entry in inventory['grid']}
        if self._grid_id_set:  # skip first frame to avoid flashing all items
            for iid in (cur_ids - self._grid_id_set):
                self._pickup_flashes[iid] = 0.8
        self._grid_id_set = cur_ids
        # Decay flash timers
        for iid in list(self._pickup_flashes):
            self._pickup_flashes[iid] -= rl.get_frame_time()
            if self._pickup_flashes[iid] <= 0:
                del self._pickup_flashes[iid]

        # Empty cell hover highlight only — the art provides the frames
        cell_map = grid_build_map(inventory['grid'], cols=INV_COLS, rows=INV_ROWS)
        for row in range(INV_ROWS):
            for col in range(INV_COLS):
                sx = gx + col * cell
                sy = gy + row * cell
                if cell_map[row][col] is None and sx <= mx < sx + cell and sy <= my < sy + cell:
                    rl.draw_rectangle(sx, sy, cell, cell, _c(255, 255, 255, 18))

        # Items (multi-cell footprints)
        for idx, entry in enumerate(inventory['grid']):
            if not isinstance(entry, dict):
                continue
            idef     = ITEMS.get(entry['item'], {})
            w, h     = idef.get('size', (1, 1))
            col, row = entry['col'], entry['row']
            sx = gx + col * cell
            sy = gy + row * cell
            iw = w * cell - 2
            ih = h * cell - 2

            hov    = sx <= mx < sx + iw and sy <= my < sy + ih
            rarity = _rarity_of(entry)
            if hov:
                self._hovered = entry

            # Pickup glow: pulsing gold border on newly acquired items
            flash_t = self._pickup_flashes.get(id(entry), 0)
            if flash_t > 0:
                pulse = (math.sin(rl.get_time() * 8.0) + 1.0) / 2.0
                glow_a = int(200 * (flash_t / 0.8) * pulse)
                glow_r = rl.Rectangle(float(sx - 2), float(sy - 2), float(iw + 4), float(ih + 4))
                rl.draw_rectangle_lines_ex(glow_r, 2, rl.Color(255, 220, 80, glow_a))

            rl.draw_rectangle(sx, sy, iw, ih, C_SLOT_FL)
            rl.draw_rectangle_lines(sx, sy, iw, ih,
                                    _RARITY_BORDER.get(rarity, C_BORDER))
            icon = self._icons.get(entry['item']) or self._err
            if icon:
                pad = 3
                rl.draw_texture_pro(icon,
                    rl.Rectangle(0, 0, float(icon.width), float(icon.height)),
                    self._icon_dst(icon, rl.Rectangle(float(sx), float(sy),
                                                      float(iw), float(ih)), pad),
                    rl.Vector2(0, 0), 0.0, rl.WHITE)

            cnt = _count_label(entry)
            if cnt:
                fsz = max(11, int(cell * 0.25))
                fonts.draw(cnt,
                             sx + iw - fonts.measure(cnt, fsz) - 2,
                             sy + ih - fsz - 3, fsz, C_COUNT)

    def _draw_tiles(self, px, s, mx, my):
        """7 vessel attribute tiles — display-only (click-through removed)."""
        char = self.char_provider() if self.char_provider else None
        for i, attr in enumerate(_TILE_ORDER):
            r = self._tile_rect(px, s, i)
            hov = self._in_rect(mx, my, r)
            fs = max(13, int(TILE_AH * s * 0.52))
            val = char.descend.get(attr, 0) if char else 0
            col = C_GOLD_TEXT if val > 0 else C_GOLD_DIM
            icons.draw(_TILE_ICONS[attr], int(r.x + 6), int(r.y + r.height / 2 - fs / 2),
                       fs, col)
            short = _TILE_LABEL.get(attr, attr[:3]).upper()[:3]
            fonts.draw(short, int(r.x + 10 + fs), int(r.y + (r.height - fs) / 2) - 1,
                       fs, col)
            vx = r.x + r.width - fonts.measure(str(val), fs) - 8
            fonts.draw(str(val), int(vx), int(r.y + (r.height - fs) / 2) - 1, fs,
                       C_TEXT if val > 0 else C_LABEL)
            if hov:
                rl.draw_rectangle_lines_ex(r, 2, C_SLOT_HV)
                self._draw_tile_hint(r, attr)

    def _draw_tile_hint(self, r, attr):
        """Small hover panel under a vessel attribute tile."""
        label = _TILE_LABEL.get(attr, attr.title())
        lines = [(label, C_GOLD_TEXT)]
        blurb = _ATTR_BLURBS.get(attr, '')
        if blurb:
            lines.append((blurb, C_LABEL))
        fs = 16
        line_h = fs + 4
        tw = max(fonts.measure(t, fs) for t, _ in lines) + 20
        th = len(lines) * line_h + 12
        tx = r.x + r.width + 6
        ty = r.y
        sw, sh = rl.get_screen_width(), rl.get_screen_height()
        if tx + tw > sw:
            tx = r.x - tw - 6
        ty = min(ty, sh - th - 4)
        rl.draw_rectangle(int(tx), int(ty), int(tw), int(th), _c(0, 0, 0, 235))
        rl.draw_rectangle_lines(int(tx), int(ty), int(tw), int(th), C_BORDER2)
        for i, (t, col) in enumerate(lines):
            fonts.draw(t, int(tx + 10), int(ty + 6 + i * line_h), fs, col)

    def _draw_layout_dbg(self, px, s):
        """inv_layout debug overlay — outlines of every mapped slot rect."""
        cols = (rl.RED, rl.GREEN, rl.BLUE, rl.YELLOW, rl.MAGENTA, rl.SKYBLUE, rl.ORANGE, rl.LIME)
        for i in range(5):
            rl.draw_rectangle_lines_ex(self._organ_rect(px, s, i), 1, rl.SKYBLUE)
        for i in range(5):
            rl.draw_rectangle_lines_ex(self._socket_rect(px, s, i), 1, rl.MAGENTA)
        rl.draw_rectangle_lines_ex(self._grid_rect(px, s), 1, rl.GREEN)
        for row in range(INV_ROWS):
            for col in range(INV_COLS):
                rl.draw_rectangle_lines(int(px + (GRID_AX + col * GRID_ACELL) * s),
                                        int((GRID_AY + row * GRID_ACELL) * s),
                                        int(GRID_ACELL * s), int(GRID_ACELL * s), rl.LIME)
        for i in range(7):
            rl.draw_rectangle_lines_ex(self._tile_rect(px, s, i), 1, cols[i])

    # ── tooltip ───────────────────────────────────────────────────────

    def _draw_character_level(self, inventory, px):
        """Panel readout for the compact LEVEL label.

        Owner ruling 2026-10-07: it sits in the empty tile cell BESIDE the
        Destiny tile (tile grid row 1, col 3) instead of the panel header.

        Renders itemgen.format_character_level() verbatim — the same shared
        accessor and the same compact ``LVL n`` string the top-left HUD readout
        uses, so the two sites can never disagree. Display-only (see
        itemgen.character_level).
        """
        s = rl.get_screen_height() / BG_H
        r = self._tile_rect(px, s, 7)   # divmod(7, 4) = row 1, col 3 — beside Destiny
        label = itemgen.format_character_level(inventory)
        fs = max(13, int(TILE_AH * s * 0.52))   # matches the tile text size
        fonts.draw(label,
                   int(r.x + (r.width - fonts.measure(label, fs)) / 2),
                   int(r.y + (r.height - fs) / 2) - 1, fs, C_GOLD_TEXT)

    def _tooltip_lines(self, entry, inventory=None):
        """Build the tooltip line list for an entry (pure, no drawing).

        An UNIDENTIFIED item exposes no stat text: no rolled affixes, no base
        implicits, no item level, no ability and no comparison rows. The rot
        meter is a condition (like durability), not a rolled stat, so it is
        always visible on organs.
        """
        item_id  = entry['item']
        idef     = ITEMS.get(item_id, {})
        inst     = entry.get('instance_data')
        rarity   = _rarity_of(entry)

        # title (rolled name if present) + special line colours
        unid = inst is not None and not itemgen.is_identified(entry)
        title  = (idef.get('name', item_id) if unid else
                  (inst['display_name'] if inst else idef.get('name', item_id)))
        if inst is not None and itemgen.is_rotten(inst) \
                and not title.startswith('ROTTEN '):
            title = 'ROTTEN ' + title      # unidentified rotten organ
        lines  = [(title, _RARITY_COL.get(rarity, C_TEXT))]

        # organ rot meter (BLUEPRINT §22): 0-100%, ROTTEN at 100%
        if inst is not None and idef.get('equipSlot'):
            pct    = itemgen.rot_of(inst)
            rotten = itemgen.is_rotten(inst)
            label  = f"Rot: {int(round(pct))}%" + (" (ROTTEN)" if rotten else "")
            lines.append((label, _rot_col(pct)))

        # tarot currency card info (issue #73 phase B)
        card_arc = currency_mod.arcana_of(item_id)
        if card_arc is not None:
            cinfo = currency_mod.CURRENCY_CARDS.get(card_arc, {})
            if card_arc == 0:
                # the Fool is the only quarter-stacked card
                lines.append((f"Stack: {currency_mod.stack_label(entry)} "
                              f"(4/4 = usable card)", C_LABEL))
            else:
                lines.append((f"Count: {entry.get('count', 1)} card(s)", C_LABEL))
            desc = cinfo.get('description', '')
            if desc:
                lines.append((desc, C_IMPLICIT))
            if currency_mod.card_complete(entry):
                lines.append(("Right-click -> APPLY, then click a target",
                              C_GOLD_TEXT))

        # flask info (issue #73 ADDITION)
        if idef.get('isFlask'):
            lines.append((f"Flask [{idef['isFlask']}] - "
                          f"charges: {entry.get('charges', idef.get('charges', 1))}",
                          C_LABEL))
            lines.append(("One use per wave. Refills when the next wave starts.",
                          C_LABEL))

        # unidentified: rolled stats hidden until identified (The Joker)
        if unid:
            lines.append(("Unidentified", _c(190, 160, 90, 255)))

        # item level line
        if inst and not unid:
            ilvl = inst.get('ilvl', 0)
            lines.append((f"Item Level: {ilvl}", C_LABEL))

        # static implicit from the base item — hidden while unidentified too,
        # an unidentified item must expose no stat text anywhere.
        if not unid:
            for k, v in (idef.get('equip') or {}).items():
                lines.append((format_equip_stat(k, v), C_IMPLICIT))

        # organ ability info (hidden while unidentified)
        if inst and inst.get('ability') and not unid:
            ab_id  = inst['ability']
            ab     = _abilities_mod.ABILITIES.get(ab_id, {})
            tier   = _abilities_mod.tier_for_rarity(inst.get('rarity', 'common'))
            # Skills are gem-only; legacy organ abilities remain displayable
            # for old saves but must not advertise a removed item hotkey.
            bind = idef.get('isGem')
            label  = ab.get('label', ab_id)
            lines.append((f"[{label}]" + (f" [{bind}]" if bind else ""),
                          _RARITY_COL.get(rarity, C_TEXT)))
            ab_type = ab.get('type', '')
            if ab_type == 'passive':
                lines.append(("Passive ability", C_LABEL))
            else:
                cds = ab.get('cooldown')
                cd  = cds[tier] if cds and tier < len(cds) else 0
                lines.append((f"Cooldown: {cd:.1f}s", C_LABEL))
            lines.append((f"Tier {tier + 1}", C_LABEL))
        # rolled affixes (gear) — hidden while unidentified.
        # Rotten organs paint every rolled line (buffed stats + drawback)
        # in rotten-flesh yellow (§22).
        if inst and not unid:
            affix_col = C_ROTTEN if itemgen.is_rotten(inst) else C_AFFIX
            for line in itemgen.affix_lines(inst):
                lines.append((line, affix_col))
            unique = inst.get('unique')
            if unique:
                lines.append((unique['title'], C_UNIQUE))
                lines.append((unique['text'], C_UNIQUE))

        for k, v in (idef.get('use') or {}).items():
            if unid:
                break
            lines.append((f"Use: +{v} {k}", C_TEXT))

        sz = idef.get('size', (1, 1))
        if sz != (1, 1):
            lines.append((f"{sz[0]}×{sz[1]} cells", C_LABEL))
        if idef.get('stackable'):
            lines.append((f"{entry['count']}/{idef['maxStack']}", C_LABEL))

        # QoL #20 — comparison vs the currently equipped item in this slot
        if inventory and idef.get('equipSlot'):
            slot_key = idef['equipSlot']
            eq_entry = inventory['equipped'].get(slot_key)
            slot_label = EQUIP_SLOT_LABELS.get(slot_key, slot_key)
            if eq_entry is not entry:
                lines.append(("", C_LABEL))
                lines.append((f"= Equipped {slot_label} =", C_LABEL))
                if eq_entry:
                    for ctext, sign in itemgen.comparison_rows(entry, eq_entry):
                        col = C_CMP_UP if sign > 0 else (C_CMP_DOWN if sign < 0 else C_LABEL)
                        lines.append((ctext, col))
                else:
                    lines.append(("(no item equipped)", C_LABEL))

        return lines

    def _draw_tooltip(self, entry, panel_x, inventory=None):
        idef   = ITEMS.get(entry['item'], {})
        rarity = _rarity_of(entry)
        lines  = self._tooltip_lines(entry, inventory)

        font_sz = 18
        line_h  = font_sz + 5
        PAD = 14
        ARROW_W = 16   # room for the comparison arrow icon after the text
        tw = int(max(fonts.measure(t, font_sz)
                     + (ARROW_W if _cmp_sign(c) else 0)
                     for t, c in lines)) + PAD * 2
        th = len(lines) * line_h + PAD * 2

        sw = rl.get_screen_width()
        sh = rl.get_screen_height()
        tx = int(max(4, min(panel_x - tw - 8, sw - tw - 4)))
        ty = int(max(4, min(rl.get_mouse_y(), sh - th - 4)))

        # D2-style stone panel
        rl.draw_rectangle(tx, ty, tw, th, rl.Color(0, 0, 0, 245))
        rl.draw_rectangle(tx + 2, ty + 2, tw - 4, th - 4, rl.Color(0, 0, 0, 0x99))
        rl.draw_rectangle_lines_ex(rl.Rectangle(float(tx + 1), float(ty + 1), float(tw - 2), float(th - 2)),
                                   1, rl.Color(0xE0, 0xE0, 0xE0, 200))
        border_col = _RARITY_BORDER.get(rarity, C_BORDER)
        rl.draw_rectangle_lines_ex(rl.Rectangle(float(tx), float(ty), float(tw), float(th)),
                                   1, border_col)

        for i, (line, col) in enumerate(lines):
            ly = ty + PAD + i * line_h
            if i == 0:
                # title — the "ROTTEN " prefix draws in rotten yellow, the
                # rest of the name keeps the rarity colour
                ticon = icons.item_icon(idef, entry.get('item'))
                x0 = tx + PAD + 22 if ticon else tx + PAD
                if ticon:
                    icons.draw(ticon, tx + PAD, ly + 1, 16, col)
                if line.startswith(itemgen.ROTTEN_NAME_PREFIX):
                    prefix = itemgen.ROTTEN_NAME_PREFIX
                    fonts.draw(prefix, x0, ly, font_sz, C_ROTTEN)
                    fonts.draw(line[len(prefix):],
                               x0 + fonts.measure(prefix, font_sz),
                               ly, font_sz, col)
                else:
                    fonts.draw(line, x0, ly, font_sz, col)
            else:
                fonts.draw(line, tx + PAD, ly, font_sz, col)
                # comparison rows: arrow icon instead of "(up)"/"(down)" words
                sign = _cmp_sign(col)
                if sign:
                    name = 'arrow_up' if sign > 0 else 'arrow_down'
                    icons.draw(name, tx + PAD + fonts.measure(line, font_sz) + 3,
                               ly + 1, 14, col)

    # ── context menu draw ────────────────────────────────────────────

    def _draw_ctx(self, mx, my):
        cx, cy  = self._ctx['x'], self._ctx['y']
        opts    = self._ctx_options()
        item_h  = 26
        menu_w  = 220
        menu_h  = len(opts) * item_h + 4

        sw = rl.get_screen_width()
        sh = rl.get_screen_height()
        cx = max(0, min(cx, sw - menu_w))
        cy = max(0, min(cy, sh - menu_h))

        rl.draw_rectangle(cx, cy, menu_w, menu_h, C_CTX_BG)
        rl.draw_rectangle_lines(cx, cy, menu_w, menu_h, C_BORDER)

        for i, opt in enumerate(opts):
            ry  = cy + 2 + i * item_h
            hov = cx <= mx < cx + menu_w and ry <= my < ry + item_h
            if opt.get('enabled', True) and hov:
                rl.draw_rectangle(cx + 1, ry, menu_w - 2, item_h, C_CTX_HV)
            col = C_TITLE if hov else C_TEXT
            fonts.draw(opt['label'], cx + 10, ry + 6, 23, col)
