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
Full menu system for Bound To Rot -- Python/Raylib port.

Screens: intro, cinematic, main, play, characters,
        char_create, settings, stash, paused.
"""

import os
import json
import math
import traceback
import time as _time
import pyray as rl
import ui.fonts as fonts
import ui.icons as icons
import ui.gui_kit as gui_kit
import config

from core.iso_engine import IsoSprite

from entities.progression import (CharacterManager, clear_delve_data,
                         compute_derived_stats)
from entities.descend import (DESCEND_ATTRIBUTES, ATTR_CAP,
                              ATTR_LABEL,
                              VESSEL_DEFS, LOOKS_OPTIONS, LOOKS_LABELS,
                              VESSEL_UNLOCKS, WIP_VESSELS)
from systems.items import ITEMS, add_to_stash
from systems import input as _inp

# ── Settings persistence ──────────────────────────────────────────────
_SAVE_DIR      = os.path.join(os.environ.get('APPDATA', os.path.expanduser('~')), 'BTR')
_SETTINGS_PATH = os.path.join(_SAVE_DIR, 'settings.json')
_FONT_DIR  = os.path.join(config.ASSETS, 'fonts')
FONT_NAMES = []
try:
    FONT_NAMES = sorted(f for f in os.listdir(_FONT_DIR) if f.lower().endswith('.ttf'))
except FileNotFoundError:
    pass

# ── Font helpers ──────────────────────────────────────────────────────
DEFAULT_FONT = 'Sancreek-Regular.ttf'

def _apply_font(font_name: str):
    path = os.path.join(_FONT_DIR, font_name)
    if not os.path.exists(path):
        # deleted/unknown font in an old settings.json — fall back
        font_name = DEFAULT_FONT
        path = os.path.join(_FONT_DIR, font_name)
        if not os.path.exists(path):
            return
    fonts.load(path, fonts.CRISP_SIZES.get(font_name))


# ── Palette ───────────────────────────────────────────────────────────
# Red/black/grey values shared with ui.gui_kit (original design guide).
def _c(r, g, b, a=255): return rl.Color(r, g, b, a)
C_BG      = _c(0,   0,   0,   255)
C_BORDER  = _c(0x37, 0x37, 0x37, 255)                  # Grey Dark
C_ACCENT  = _c(0xA9, 0x0D, 0x01, 255)                  # Main Red
C_ACCENT_HOVER = _c(0xDA, 0x00, 0x00, 255)             # Red hover
C_WHITE   = _c(0xD2, 0xD2, 0xD2, 255)                  # Main White
C_DIM     = _c(0x99, 0x99, 0x99, 255)
C_GOLD    = _c(255, 225, 70,  255)
C_GREEN   = _c(80,  200, 80,  255)
C_RED     = _c(0xDA, 0x00, 0x00, 255)

# UI palette (BLUEPRINT §14) — red accents, white trim, black panels
C_GOLD_HOVER = _c(0xD2, 0xD2, 0xD2)                    # Main White
C_GOLD_TEXT  = _c(0x99, 0x99, 0x99)
C_SLATE      = _c(0x11, 0x11, 0x11, 0x99)
C_DARK_RED   = _c(0x5A, 0x0A, 0x0A)

# ── Attribute blurbs & descriptions (D.E.S.C.E.N.D. sheet) ──────────────
_ATTR_BLURBS = {
    'dexterity': 'Move speed, evasion, attack speed',
    'endurance': 'Max HP, energy shield, darkness resist',
    'strength': 'Melee damage, max HP, physical damage',
    'cunning': 'Cooldown recovery, magic damage, fire damage',
    'essence': 'Entropy grace, ability crit',
    'nerve': 'Accuracy, light radius, critical strike',
    'destiny': 'Entropy grace, luck, loot quality',
}
_ATTR_DESC = {
    'dexterity': 'Dexterity governs agility and reflexes. Each point raises move speed, evasion, and attack speed.',
    'endurance': 'Endurance is raw resilience. Each point increases max HP, energy shield, and resistance to the darkness.',
    'strength': 'Strength is raw physical power. Each point increases melee damage, max HP, and physical damage.',
    'cunning': 'Cunning is sharp intellect and wit. Each point raises cooldown recovery, magic damage, and fire damage.',
    'essence': 'Essence is soul-presence. Each point improves entropy grace and ability critical strikes.',
    'nerve': 'Nerve is composure under fire. Each point sharpens accuracy, light radius, and critical strikes.',
    'destiny': 'Destiny is the hand of fate. Each point improves entropy grace, luck, and loot quality.',
}


# ── Settings ──────────────────────────────────────────────────────────

class Settings:
    def __init__(self):
        self.volume         = 40
        self.music_volume   = 40
        self.sensitivity    = 50
        self.fullscreen     = False
        self.perf_overlay   = False
        self.crt_effect     = True
        self.hud_scale      = 1.0
        self.debug_overlay  = False
        self.font_name      = 'Sancreek-Regular.ttf'
        self.brightness     = 50  # 0-100
        self.item_labels    = True  # always show ground-loot labels
        self.load()

    def save(self):
        os.makedirs(_SAVE_DIR, exist_ok=True)
        try:
            with open(_SETTINGS_PATH, 'w') as f:
                json.dump({
                    'volume':          self.volume,
                    'music_volume':    self.music_volume,
                    'sensitivity':     self.sensitivity,
                    'fullscreen':      self.fullscreen,
                    'perf_overlay':    self.perf_overlay,
                    'crt_effect':      self.crt_effect,
                    'hud_scale':       self.hud_scale,
                    'debug_overlay':   self.debug_overlay,
                    'font_name':       self.font_name,
                    'brightness':      self.brightness,
                    'item_labels':     self.item_labels,
                }, f)
        except Exception:
            print("[settings] ERROR: Failed to save settings.json")
            traceback.print_exc()

    def load(self):
        try:
            with open(_SETTINGS_PATH) as f:
                d = json.load(f)
            self.volume         = float(d.get('volume',         40))
            self.music_volume   = float(d.get('music_volume',   40))
            self.sensitivity    = float(d.get('sensitivity',    50))
            self.fullscreen     = bool(d.get('fullscreen',      False))
            self.perf_overlay   = bool(d.get('perf_overlay',    False))
            self.crt_effect     = bool(d.get('crt_effect',      True))
            self.hud_scale      = float(d.get('hud_scale',      1.0))
            self.font_name      = str(d.get('font_name',        'Sancreek-Regular.ttf'))
            self.brightness     = float(d.get('brightness',     50))
            self.item_labels    = bool(d.get('item_labels',     True))
        except Exception:
            print("[settings] ERROR: Failed to load settings.json")
            traceback.print_exc()
        self.debug_overlay = False  # always start with debug off


# ── Drawing helpers ───────────────────────────────────────────────────

def _cx(text: str, size: int, cw: int) -> int:
    return cw // 2 - fonts.measure(text, size) // 2


def _panel(x, y, w, h):
    gui_kit.panel(x, y, w, h, corner=32)


def _title(text: str, y: int, cw: int, size: int = 64):
    fonts.draw(text, _cx(text, size, cw), y, size, C_ACCENT)


def _rule(y: int, cw: int, pad: int = 40):
    rl.draw_line(pad, y, cw - pad, y, C_BORDER)


def _hov(r) -> bool:
    return rl.check_collision_point_rec(rl.get_mouse_position(), r)


def _click(r) -> bool:
    return _hov(r) and rl.is_mouse_button_pressed(rl.MOUSE_BUTTON_LEFT)


_audio_ref = None   # set by MenuSystem after audio is ready

_hovered_last = {}  # rect id → bool for hover-enter detection


def _hover_fx(r, active: bool):
    """Shared hover effect: fragile white idle border; when active a bold
    red border with a pulsing glow ring (accent colour)."""
    if active:
        pulse = (math.sin(rl.get_time() * 5.0) + 1.0) / 2.0
        glow_a = int(60 + 110 * pulse)
        rl.draw_rectangle_lines_ex(rl.Rectangle(r.x - 4, r.y - 4, r.width + 8, r.height + 8), 1,
                                   _c(0xA9, 0x0D, 0x01, glow_a))
        rl.draw_rectangle_lines_ex(r, 2, gui_kit.RED_HOT)
    else:
        rl.draw_rectangle_lines_ex(r, 1, _c(0xD2, 0xD2, 0xD2, 110))


def _btn(r, text: str, size: int = 28, accent: bool = False, disabled: bool = False, gold: bool = False, lit: bool = False, wood: bool = False, danger: bool = False) -> bool:
    hovered = _hov(r) and not disabled
    rkey = (int(r.x), int(r.y), int(r.width), int(r.height))
    was_hovered = _hovered_last.get(rkey, False)
    if hovered and not was_hovered and _audio_ref:
        _audio_ref.ui_hover()
    _hovered_last[rkey] = hovered
    tw = fonts.measure(text, size)
    if wood:
        # imageless text button: no fill, colour carries the state
        tc = (C_RED if hovered else _c(0xE0, 0x60, 0x60, 255)) if danger \
             else (gui_kit.GOLD if hovered else rl.WHITE)
        if disabled:
            tc = C_DIM
    else:
        if lit:
            bg = _c(0xFF, 0xFF, 0xFF, 255)
            tc = _c(0, 0, 0, 255)
        elif accent:
            tc = rl.WHITE if hovered else C_ACCENT_HOVER
        else:
            tc = rl.WHITE
        if disabled:
            tc = _c(0x9A, 0x9A, 0x9A, 180)

        if lit:
            rl.draw_rectangle_rec(r, bg)
            _hover_fx(r, hovered)
        else:
            if disabled:
                state = 'disabled'
            elif hovered and rl.is_mouse_button_down(rl.MOUSE_BUTTON_LEFT):
                state = 'pressed'
            elif hovered:
                state = 'hover'
            else:
                state = 'default'
            gui_kit.button(r, 'red' if accent else 'grey', state)
    fonts.draw(text, int(r.x + r.width  // 2 - tw // 2),
                       int(r.y + r.height // 2 - size // 2), size, tc)
    clicked = _click(r) and not disabled
    if clicked and _audio_ref:
        _audio_ref.ui_click()
    return clicked


def _slider(label: str, value: float, min_v: float, max_v: float,
            x: int, y: int, w: int, size: int = 27) -> float:
    pct     = (value - min_v) / (max_v - min_v)
    val_txt = f"{int(value)}%"
    fonts.draw(label,   x, y, size, rl.WHITE)
    fonts.draw(val_txt, x + w - fonts.measure(val_txt, size), y, size,
               gui_kit.MUTED)
    bar_h = max(14, size // 2)
    bar_y = y + size + 4
    gui_kit.kit_slider(x, bar_y, w, bar_h, pct)
    bar_r = rl.Rectangle(float(x), float(bar_y - 5), float(w), float(bar_h + 10))
    if rl.is_mouse_button_down(rl.MOUSE_BUTTON_LEFT) and _hov(bar_r):
        new_pct = max(0.0, min(1.0, (rl.get_mouse_x() - x) / w))
        value   = min_v + new_pct * (max_v - min_v)
    return value


def _toggle(label: str, value: bool, x: int, y: int, w: int, size: int = 27) -> bool:
    """Kit checkbox toggle: labelled box, checked/unchecked sprites."""
    fonts.draw(label, x, y, size, rl.WHITE)
    box = size + 4
    bx  = x + w - box
    box_r = rl.Rectangle(float(bx), float(y - 2), float(box), float(box + 4))
    gui_kit.kit_check(bx, int(y - 2), box, value)
    if _click_off_box(box_r):
        value = not value
        if _audio_ref:
            _audio_ref.ui_click()
    return value


def _click_off_box(r) -> bool:
    return _hov(r) and rl.is_mouse_button_pressed(rl.MOUSE_BUTTON_LEFT)


class _KeyEdge:
    """Rising-edge latch for a single key, safe under the 30 Hz fixed timestep.

    is_key_pressed is only true for the single render frame a key goes down,
    but fixed-timestep stepping (PR #75) makes game.update run zero ticks on many render
    frames, so per-tick is_key_pressed scans get dropped (same defect as the
    splash press-any-key bug fixed in eb1f369). is_key_down persists while the
    key is held, so every press is seen by at least one tick; the latch
    guarantees exactly one rising edge per physical press even when a render
    frame runs multiple ticks.
    """

    def __init__(self):
        self._down = False

    def pressed(self, key: int) -> bool:
        down = bool(rl.is_key_down(key))
        edge = down and not self._down
        self._down = down
        return edge


class _TextInput:
    """Text-entry buffer fed from a per-render-frame char queue.

    raylib clears its char-pressed queue at every PollInputEvents (once per
    RENDER frame), but text fields are polled per SIM tick — and with the
    30 Hz fixed timestep, many render frames run zero ticks, so
    characters typed on a zero-tick frame were dropped and typing did not
    work. Game.poll_frame_input() drains the raylib char queue once per
    render frame into a pending list; the tick-rate text field consumes from
    that list instead.
    """

    def __init__(self, max_len: int = 20):
        self.max_len = max_len
        self.buf     = ''
        self.pending: list[str] = []   # per-render-frame chars, consumed per tick
        self._bs     = _KeyEdge()

    def push(self, ch: str):
        if len(self.pending) < 64:
            self.pending.append(ch)

    def clear(self, buf: bool = True):
        if buf:
            self.buf = ''
        self.pending.clear()

    def update(self) -> str:
        for ch in self.pending:
            if len(self.buf) < self.max_len and 32 <= ord(ch) < 127:
                self.buf += ch
        self.pending.clear()
        if self._bs.pressed(rl.KEY_BACKSPACE) and self.buf:
            self.buf = self.buf[:-1]
        return self.buf


def _menu_item(text: str, x: int, y: int, size: int = 28, hovered: bool = False):
    """D2-style text-only menu entry -- no box, just colour on hover."""
    col = gui_kit.GOLD if hovered else rl.WHITE
    fonts.draw(text, x, y, size, col)


def _stone_panel(x: int, y: int, w: int, h: int):
    """Rounded dark slab with red corner accents."""
    gui_kit.panel(x, y, w, h, corner=32)
    # Corner accents -- small red L-shapes
    corner_len, corner_gap = 18, 6
    for cx, cy, dx, dy in [
        (x + corner_gap, y + corner_gap,  1,  1),
        (x + w - corner_gap, y + corner_gap, -1,  1),
        (x + corner_gap, y + h - corner_gap,  1, -1),
        (x + w - corner_gap, y + h - corner_gap, -1, -1),
    ]:
        rl.draw_line(cx, cy, cx + dx * corner_len, cy, C_ACCENT)
        rl.draw_line(cx, cy, cx, cy + dy * corner_len, C_ACCENT)
        rl.draw_line(cx + 1, cy + 1, cx + 1 + dx * (corner_len - 4), cy + 1,
                     _c(0xDA, 0x00, 0x00, 0x66))
        rl.draw_line(cx + 1, cy + 1, cx + 1, cy + 1 + dy * (corner_len - 4),
                     _c(0xDA, 0x00, 0x00, 0x66))


def _menu_select_markers(cx: int, cy: int, spacing: int, size: int = 8):
    """Two small gold diamond markers flanking a selected menu item."""
    for sx in (cx - spacing, cx + spacing):
        half = size // 2
        _V0 = rl.Vector2(float(sx), float(cy - half))
        _V1 = rl.Vector2(float(sx + half), float(cy))
        _V2 = rl.Vector2(float(sx), float(cy + half))
        _V3 = rl.Vector2(float(sx - half), float(cy))
        rl.draw_triangle(_V0, _V1, _V2, gui_kit.GOLD)
        rl.draw_triangle(_V0, _V2, _V3, gui_kit.GOLD)


def _text_shadow(text: str, x: int, y: int, size: int, color):
    """Draw text with a dark offset shadow for depth."""
    fonts.draw(text, x + 1, y + 2, size, _c(0, 0, 0, 180))
    fonts.draw(text, x, y, size, color)


def _wrap_text(text: str, size: int, max_width: int) -> list:
    """Wrap text to fit max_width pixels at the given font size."""
    words = text.split()
    lines, cur = [], ''
    for w in words:
        test = (cur + ' ' + w).strip()
        if fonts.measure(test, size) <= max_width:
            cur = test
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def _divider(x: int, y: int, w: int, color=None):
    """Decorative divider line with a centre diamond."""
    line  = color or _c(0x66, 0x66, 0x66, 0xDD)
    dia   = color or C_ACCENT
    rl.draw_line(int(x), int(y), int(x + w), int(y), line)
    rl.draw_line(int(x), int(y) + 1, int(x + w), int(y) + 1, _c(0, 0, 0, 0x88))
    # centre diamond
    mx = x + w // 2
    rl.draw_triangle(rl.Vector2(float(mx), float(y - 3)), rl.Vector2(float(mx + 4), float(y)),
                     rl.Vector2(float(mx), float(y + 3)), dia)
    rl.draw_triangle(rl.Vector2(float(mx), float(y - 3)), rl.Vector2(float(mx), float(y + 3)),
                     rl.Vector2(float(mx - 4), float(y)), dia)


# ── MenuSystem ────────────────────────────────────────────────────────

class MenuSystem:
    def __init__(self, char_mgr: CharacterManager, audio=None):
        self.state    = 'intro'
        self.char_mgr = char_mgr
        self.settings = Settings()
        self._audio   = audio   # set after AudioSystem is ready

        self._prev       = 'main'
        self._signal     = None
        self._guard      = 2        # ignore input for first N frames
        self._last_state = None     # previous state, for entry detection
        self.popup_mode  = False    # True when drawn as in-hub overlay
        self.scene_bg_tex = None    # pre-rendered isometric scene background
        self._fade_timer   = 0.0    # transition fade-in countdown
        self._fade_duration = 0.35  # seconds
        self.item_icons  = {}       # filled by Game after InventoryUI.load()

        # Per-screen state
        self.char_name_input = _TextInput(20)   # character-creation name field
        self._char_name       = ''
        self._char_looks      = 'knight'
        self._char_sel_idx    = 0    # keyboard nav index for character select
        self._settings_tab    = 0    # 0=audio 1=graphics 2=controls
        self._paused_sel_idx = 0    # D2-style keyboard nav in pause menu

        # Loadout screen state
        self.raid_cargo = None      # set on DEPLOY, consumed by Game

        # Confirmation state
        self._confirm_delete_idx = -1
        self._confirm_delete_save = False
        self._confirm_quit = False
        self._pause_click_armed = False  # ignore pause-menu clicks until mouse released

        # Intro / cinematic timers
        self._intro_t  = 0.0
        self._cin_t    = 0.0
        self._cin_phase = 0
        self._any_down_prev = False   # edge latch for splash press-any-key

        # key edge latches for per-tick key scans (see _KeyEdge)
        self._ck_left  = _KeyEdge()
        self._ck_right = _KeyEdge()
        self._ck_tab   = _KeyEdge()
        self._ck_enter = _KeyEdge()
        self._ck_esc   = _KeyEdge()

        # Settings toast notification
        self._settings_toast_timer = 0.0

        # UI textures -- set by Game.init() after window is open
        self.panel_tex  = None
        self.header_tex = None
        self.logo_tex   = None
        self.bg_tex     = None
        self.headerB_tex = None

        # Character creation sprite preview
        self._preview_sprites   = {}   # looks_key -> {S: Texture2D}
        self._preview_loaded    = False
        self._preview_anim_time = 0.0


    # ── Public API ────────────────────────────────────────────────────

    def signal(self):
        s = self._signal
        self._signal = None
        return s

    def set_state(self, state: str, prev: str | None = None):
        if prev is not None:
            self._prev = prev
        if state == 'paused':
            self._paused_sel_idx = 0   # keyboard nav always starts on Resume
            self._pause_click_armed = False  # ignore clicks until mouse released
        if self.state != state:
            self._fade_timer = self._fade_duration
        self.state = state

    def reset_cinematic(self):
        self._cin_t     = 0.0
        self._cin_phase = 0

    def update(self, dt: float):
        self._fade_timer = max(0.0, self._fade_timer - dt)
        if self._guard > 0:
            self._guard -= 1
            return
        if self.state != self._last_state:
            # Don't let chars typed on one screen leak into another field
            # (e.g. keys tapped on the character list before opening create).
            self.char_name_input.clear(buf=False)
        fn = getattr(self, f'_u_{self.state}', None)
        if fn:
            fn(dt)
        self._last_state = self.state

    def draw(self, cw: int, ch: int):
        fn = getattr(self, f'_d_{self.state}', None)
        if fn:
            fn(cw, ch)
        if self._fade_timer > 0:
            alpha = int(255 * self._fade_timer / self._fade_duration)
            rl.draw_rectangle(0, 0, cw, ch, rl.Color(0, 0, 0, alpha))

    def draw_popup(self, state: str, cw: int, ch: int):
        """Draw a hub popup overlay -- hub renders behind, this draws on top."""
        rl.draw_rectangle(0, 0, cw, ch, rl.Color(0, 0, 0, 180))
        old_state = self.state
        self.popup_mode = True
        self.state = state
        fn = getattr(self, f'_d_{state}', None)
        if fn:
            fn(cw, ch)
        # X close button (top-right corner of every popup)
        x_sz = 34
        x_r = rl.Rectangle(cw - x_sz - 12, 12, x_sz, x_sz)
        rl.draw_rectangle_rec(x_r, rl.Color(40, 30, 30, 220))
        rl.draw_rectangle_lines_ex(x_r, 1, rl.Color(200, 120, 120, 200))
        xl = "X"
        xw = fonts.measure(xl, 22)
        fonts.draw(xl, int(x_r.x + x_sz // 2 - xw // 2), int(x_r.y + 6), 22,
                   rl.Color(255, 180, 180, 240))
        if _click(x_r):
            self.state = self._prev
            self._signal = 'return_to_hub'
        # If the draw function changed the state (e.g. back button), keep it
        if self.state == state:
            self.state = old_state
        self.popup_mode = False

    def _go(self, state: str, prev: str | None = None):
        if prev is not None:
            self._prev = prev
        self.state = state

    # ── INTRO ─────────────────────────────────────────────────────────

    def _any_key_edge(self) -> bool:
        """True on the rising edge of "any key / left click".

        Uses is_key_down + a latch instead of is_key_pressed: with the
        30 Hz fixed-timestep sim, update() runs zero times on
        many render frames, so is_key_pressed (true for exactly one
        render frame) gets dropped and the splash needed multiple
        presses. is_key_down stays true while held, so every press is
        seen by at least one tick.
        """
        down = (any(rl.is_key_down(k) for k in range(32, 350))
                or rl.is_mouse_button_down(rl.MOUSE_BUTTON_LEFT))
        pressed = down and not self._any_down_prev
        self._any_down_prev = down
        return pressed

    def _u_intro(self, dt: float):
        self._intro_t += dt
        if self._intro_t > 1.2:
            if self._any_key_edge():
                self.state = 'main'

    def _d_intro(self, cw: int, ch: int):
        rl.clear_background(rl.BLACK)
        alpha = min(255, int(self._intro_t * 140))

        bg = self.bg_tex
        if bg and bg.id > 0:
            scale = max(cw / bg.width, ch / bg.height)
            bw = int(bg.width * scale)
            bh = int(bg.height * scale)
            bx = (cw - bw) // 2
            by = (ch - bh) // 2
            rl.draw_texture_pro(bg,
                rl.Rectangle(0, 0, float(bg.width), float(bg.height)),
                rl.Rectangle(float(bx), float(by), float(bw), float(bh)),
                rl.Vector2(0, 0), 0.0, rl.Color(255, 255, 255, alpha))

        logo = self.logo_tex
        if logo and logo.id > 0:
            MAX_W = 500
            scale = min(1.0, MAX_W / logo.width)
            lw = int(logo.width * scale)
            lh = int(logo.height * scale)
            lx = (cw - lw) // 2
            ly = (ch - lh) // 2
            rl.draw_texture_pro(logo,
                rl.Rectangle(0, 0, float(logo.width), float(logo.height)),
                rl.Rectangle(float(lx), float(ly), float(lw), float(lh)),
                rl.Vector2(0, 0), 0.0, rl.Color(255, 255, 255, alpha))

        sub = "MangasMango Studios"
        fonts.draw(sub, _cx(sub, 24, cw), ch - 100, 24,
                     _c(180, 180, 180, min(200, alpha)))

        if self._intro_t > 1.2:
            blink = int(self._intro_t * 2) % 2 == 0
            if blink:
                hint = "Press Any Key"
                fonts.draw(hint, _cx(hint, 30, cw), ch - 50, 30, C_DIM)

    # ── CINEMATIC ─────────────────────────────────────────────────────

    def _u_cinematic(self, dt: float):
        self._cin_t += dt
        if self._cin_phase == 0 and self._cin_t > 1.6:
            self._cin_phase = 1
        if self._any_key_edge() and self._cin_phase >= 1:
            self._signal = 'start_game'

    def _d_cinematic(self, cw: int, ch: int):
        rl.clear_background(rl.BLACK)
        a1 = min(255, int(self._cin_t * 220))
        a2 = min(255, int((self._cin_t - 1.6) * 220)) if self._cin_phase >= 1 else 0

        l1, l2 = "You are...", "...bound to rot."
        fonts.draw(l1, _cx(l1, 53, cw), ch // 2 - 50, 53, _c(220, 220, 220, max(0, a1)))
        fonts.draw(l2, _cx(l2, 53, cw), ch // 2 + 10, 53, _c(220, 220, 220, max(0, a2)))

        if self._cin_phase >= 1:
            skip = "click to skip"
            fonts.draw(skip, _cx(skip, 23, cw), ch - 60, 23, _c(80, 80, 80, 180))

    # ── MAIN ──────────────────────────────────────────────────────────

    def _u_main(self, _dt):
        if self._confirm_quit and _inp.key_pressed(self, rl.KEY_ESCAPE):
            self._confirm_quit = False
            return

        _MAIN_ITEMS = ['play', 'mp', 'dedicated', 'settings', 'quit']
        if _inp.key_pressed(self, rl.KEY_UP):
            self._paused_sel_idx = (self._paused_sel_idx - 1) % len(_MAIN_ITEMS)
            if _audio_ref:
                _audio_ref.ui_hover()
        if _inp.key_pressed(self, rl.KEY_DOWN):
            self._paused_sel_idx = (self._paused_sel_idx + 1) % len(_MAIN_ITEMS)
            if _audio_ref:
                _audio_ref.ui_hover()
        if _inp.key_pressed(self, rl.KEY_ENTER):
            action = _MAIN_ITEMS[self._paused_sel_idx]
            if _audio_ref:
                _audio_ref.ui_click()
            if action == 'settings':
                self._prev = 'main'
                self.state = 'settings'
            elif action == 'quit':
                self._confirm_quit = True
            elif action == 'play':
                self.state = 'play'

    def _draw_menu_background(self, cw: int, ch: int):
        """Full-screen menu backdrop: the main-menu artwork, or a dark fill."""
        bg = self.bg_tex
        if bg and bg.id > 0:
            scale = max(cw / bg.width, ch / bg.height)
            bw = int(bg.width * scale)
            bh = int(bg.height * scale)
            bx = (cw - bw) // 2
            by = (ch - bh) // 2
            rl.draw_texture_pro(bg,
                rl.Rectangle(0, 0, float(bg.width), float(bg.height)),
                rl.Rectangle(float(bx), float(by), float(bw), float(bh)),
                rl.Vector2(0, 0), 0.0, rl.WHITE)
        else:
            rl.clear_background(C_BG)

    def _d_main(self, cw: int, ch: int):
        self._draw_menu_background(cw, ch)
        left, right = gui_kit.board_page(cw, ch)

        # Logo on the left page
        logo = self.logo_tex
        logo_bottom = 0
        if logo and logo.id > 0:
            max_w = min(left.width * 0.7, 260)
            sc = min(1.0, max_w / logo.width)
            lw = int(logo.width * sc)
            lh = int(logo.height * sc)
            lx = int(left.x + (left.width - lw) / 2)
            ly = int(left.y + 30)
            rl.draw_texture_pro(logo,
                rl.Rectangle(0, 0, float(logo.width), float(logo.height)),
                rl.Rectangle(float(lx), float(ly), float(lw), float(lh)),
                rl.Vector2(0, 0), 0.0, rl.WHITE)
            logo_bottom = ly + lh

        # Decorative divider under the logo
        divider_y = (logo_bottom if logo_bottom > 0 else left.y + 90) + 16
        _divider(left.x + 50, divider_y, left.width - 100,
                 color=gui_kit.MUTED)

        # Vertical menu -- wooden kit buttons on the right page
        items = [
            ('Single Player',     'player',   'play'),
            ('Multiplayer',       'multiplayer', 'mp'),
            ('Dedicated Server',  'server',   'dedicated'),
            ('Settings',          'settings', 'settings'),
            ('Exit Bound To Rot', 'exit',     'quit'),
        ]
        item_size = 28
        item_gap  = 54
        btn_h     = 48
        start_y = divider_y + 20
        total_h = len(items) * item_gap
        top_y = int(start_y + (right.y + right.height - 50 - start_y
                               - total_h) / 2)

        for i, (label, icon_name, _) in enumerate(items):
            iy = top_y + i * item_gap
            tw = fonts.measure(label, item_size)
            btn_w = int(tw + 64)
            bx = right.x + (right.width - btn_w) / 2
            by = iy - 8
            btn = rl.Rectangle(bx, by, btn_w, btn_h)
            hovered = _hov(btn)
            is_key = (i == self._paused_sel_idx)
            active = hovered or is_key

            # hover sound (fire once when the pointer enters a button)
            rkey = (int(bx), int(by), int(btn_w), int(btn_h))
            was_hovered = _hovered_last.get(rkey, False)
            if hovered and not was_hovered and _audio_ref:
                _audio_ref.ui_hover()
            _hovered_last[rkey] = hovered

            if _ == 'quit':
                tcol = C_RED if active else _c(0xE0, 0x60, 0x60, 255)
            else:
                tcol = gui_kit.GOLD if active else rl.WHITE
            fonts.draw(label, int(bx + (btn_w - tw) / 2),
                       int(by + (btn_h - item_size) / 2), item_size, tcol)

            if hovered and rl.is_mouse_button_pressed(rl.MOUSE_BUTTON_LEFT):
                if _audio_ref:
                    _audio_ref.ui_click()
                if _ == 'settings':
                    self._prev = 'main'
                    self.state = 'settings'
                elif _ == 'quit':
                    self._confirm_quit = True
                elif _ == 'play':
                    self.state = 'play'

        version = 'v0.1.0'
        fonts.draw(version, int(right.x + right.width
                                - fonts.measure(version, 15) - 10),
                   int(right.y + right.height - 26), 15, gui_kit.MUTED)

        if self._confirm_quit:
            self._draw_quit_confirm(cw, ch)

    # ── PLAY ──────────────────────────────────────────────────────────

    def _u_play(self, _dt):
        self._prev = 'main'
        self.state = 'characters'

    def _d_play(self, cw: int, ch: int):
        pass  # handled in _u_play, no drawing needed

    # ── CHARACTERS ────────────────────────────────────────────────────

    def _u_characters(self, _dt):
        if _inp.key_pressed(self, rl.KEY_ESCAPE):
            if self._confirm_delete_idx >= 0:
                self._confirm_delete_idx = -1
            else:
                self._hub_back()
            return
        chars = self.char_mgr.characters
        if chars:
            n = len(chars)
            if _inp.key_pressed(self, rl.KEY_UP):
                self._char_sel_idx = (self._char_sel_idx - 1) % n
            if _inp.key_pressed(self, rl.KEY_DOWN):
                self._char_sel_idx = (self._char_sel_idx + 1) % n
            if _inp.key_pressed(self, rl.KEY_ENTER):
                self.char_mgr.select(self._char_sel_idx)
                self._signal = 'start_solo'

    def _d_characters(self, cw: int, ch: int):
        if not self.popup_mode:
            self._draw_menu_background(cw, ch)
        left, right = gui_kit.board_page(cw, ch)

        chars = self.char_mgr.characters
        sel_idx = max(0, min(self._char_sel_idx, len(chars) - 1)) if chars else 0

        # ── Save-load failure banner (issue #126) ───────────────────────
        # A save that could not be loaded is never discarded silently; the file
        # has been backed up and the player is told where it went.
        if self.char_mgr.load_error:
            banner = self.char_mgr.load_error
            bw = fonts.measure(banner, 14)
            fonts.draw(banner, int(left.x + 10), int(left.y + 4), 14, C_RED)
            if self.char_mgr.load_error_backup:
                bk = self.char_mgr.load_error_backup
                fonts.draw(bk, int(left.x + 10), int(left.y + 22), 11,
                           gui_kit.MUTED)

        pad    = 20
        px_    = left.x + pad
        pw_    = left.width - 2 * pad
        py_    = left.y + 12
        card_h = 54
        gap    = 6

        if not chars:
            msg = 'No characters yet.'
            fonts.draw(msg, int(left.x + (left.width
                                - fonts.measure(msg, 18)) / 2),
                       int(left.y + 40), 18, gui_kit.MUTED)

        # Back button -- always visible so the screen is never a dead end
        back_r = rl.Rectangle(left.x + 4, left.y + left.height - 52, 130, 40)
        if _btn(back_r, '< Back', 18, wood=True):
            self._hub_back()

        for i, c in enumerate(chars):
            cy = py_ + i * (card_h + gap)
            is_active = (i == self.char_mgr.active_idx)
            is_focus  = (i == sel_idx)

            cr = rl.Rectangle(px_, cy, pw_, card_h)
            hv = rl.check_collision_point_rec(rl.get_mouse_position(), cr)

            gui_kit.paper_panel(px_, cy, pw_, card_h, border=False)
            border = (gui_kit.GOLD if is_focus
                      else gui_kit.MUTED if hv
                      else _c(0xD2, 0xD2, 0xD2, 130) if is_active
                      else _c(0x4A, 0x3E, 0x28, 140))
            rl.draw_rectangle_lines_ex(cr, 2 if is_focus else 1, border)

            vessel_def = VESSEL_DEFS.get(c.looks, {})
            icons.draw(c.looks, int(px_ + 8), int(cy + 8), 22, white=True)
            fonts.draw(c.name, int(px_ + 38), int(cy + 4), 22,
                       C_RED if is_active else rl.WHITE)
            fonts.draw(vessel_def.get('name', c.looks), int(px_ + 38),
                       int(cy + 30), 14, gui_kit.MUTED)

            if hv and rl.is_mouse_button_pressed(rl.MOUSE_BUTTON_LEFT):
                self.char_mgr.select(i)

        # Delete button per character
        for i, c in enumerate(chars):
            cy = py_ + i * (card_h + gap)
            del_r = rl.Rectangle(px_ + pw_ - 34, cy + 12, 26, card_h - 24)
            if _btn(del_r, 'X', 14, wood=True, danger=True):
                self._confirm_delete_idx = i

        # ── Right page: selected character details ─────────────────────
        btn_h = 42
        btn_y = right.y + right.height - btn_h - 14
        btn_w = min(140, (right.width - 40 - 24) / 3)
        rx = right.x + pad
        rw = right.width - 2 * pad
        d_h = btn_y - 16 - (right.y + 12)

        if chars and 0 <= sel_idx < len(chars):
            c = chars[sel_idx]
            vessel_def = VESSEL_DEFS.get(c.looks, {})
            gui_kit.paper_panel(right.x + 12, right.y + 12,
                                right.width - 24, d_h)
            ry = right.y + 24

            fonts.draw(c.name, rx, ry, 24, rl.WHITE)
            fonts.draw(vessel_def.get('name', c.looks),
                       rx + fonts.measure(c.name, 24) + 14,
                       ry + 6, 15, gui_kit.MUTED)
            ry += 34
            _divider(rx, ry, rw - 0, color=gui_kit.MUTED)
            ry += 10

            # attributes — one per line
            for attr_key in DESCEND_ATTRIBUTES:
                label = ATTR_LABEL.get(attr_key, attr_key.title())
                val = c.descend.get(attr_key, 0)
                icons.draw(attr_key, int(rx), int(ry), 20, white=True)
                fonts.draw(label, int(rx + 28), int(ry + 1), 17, rl.WHITE)
                bar_x = rx + 160
                bar_w = max(60, rw - 160 - 46)
                rl.draw_rectangle(int(bar_x), int(ry + 6), int(bar_w), 5,
                                  _c(0x40, 0x40, 0x40, 160))
                rl.draw_rectangle(int(bar_x), int(ry + 6),
                                  int(bar_w * min(val, ATTR_CAP) / ATTR_CAP), 5,
                                  gui_kit.GOLD)
                vx_ = int(rx + 140 - fonts.measure(str(val), 17))
                fonts.draw(str(val), vx_, int(ry + 1), 17, rl.WHITE)
                ry += 36
            ry += 2
            _divider(rx, ry, rw, color=gui_kit.MUTED)
            ry += 8

            derived = compute_derived_stats(c.descend, looks=c.looks)
            sx = rx
            for stat_label, icon_name, stat_val in [
                ('Life',    'hp',       derived['max_health']),
                ('Evasion', 'evasion',  derived['evasion']),
                ('Acc.',    'accuracy', derived['accuracy']),
            ]:
                icons.draw(icon_name, int(sx), int(ry), 20, white=True)
                fonts.draw(f'{stat_label} {stat_val}', int(sx + 26), int(ry + 1),
                           17, rl.WHITE)
                sx += (rw - 40) / 3.0

        # ── Bottom buttons (right page) ─────────────────────────────────
        if chars:
            ok_r = rl.Rectangle(rx, btn_y, btn_w, btn_h)
            if _btn(ok_r, 'Play', 20, wood=True):
                self.char_mgr.select(sel_idx)
                self._signal = 'start_solo'

        new_r = rl.Rectangle(rx + (btn_w + 12) * (1 if chars else 0),
                             btn_y if chars else right.y + right.height * 0.55,
                             btn_w, btn_h)
        can_create = len(chars) < CharacterManager.MAX_CHARS
        if _btn(new_r, 'Create New', 18, wood=True, disabled=not can_create):
            self._char_name = ''
            self.char_name_input.clear()
            self._char_looks = 'knight'
            self.state = 'char_create'

        if chars and sel_idx < len(chars):
            del_btn = rl.Rectangle(rx + (btn_w + 12) * 2, btn_y, btn_w, btn_h)
            if _btn(del_btn, 'Delete', 18, wood=True, danger=True):
                self._confirm_delete_idx = sel_idx

        if self._confirm_delete_idx >= 0:
            self._draw_delete_confirm(cw, ch)

    def _draw_delete_confirm(self, cw, ch):
        """Draw the character deletion confirmation popup."""
        mx, my = rl.get_mouse_x(), rl.get_mouse_y()
        pw, ph = 300, 130
        px = cw // 2 - pw // 2
        py = ch // 2 - ph // 2
        # Dim background
        rl.draw_rectangle(0, 0, cw, ch, rl.Color(0, 0, 0, 180))
        rl.draw_rectangle(px, py, pw, ph, rl.Color(0, 0, 0, 0x99))
        rl.draw_rectangle_lines(px, py, pw, ph, rl.Color(0xE0, 0xE0, 0xE0, 255))
        idx = self._confirm_delete_idx
        if 0 <= idx < len(self.char_mgr.characters):
            cname = self.char_mgr.characters[idx].name
            msg = f"Delete '{cname}'?"
            fw = fonts.measure(msg, 20)
            fonts.draw(msg, px + pw // 2 - fw // 2, py + 18, 20, rl.Color(220, 180, 180, 255))
            warn = "This cannot be undone!"
            fw2 = fonts.measure(warn, 14)
            fonts.draw(warn, px + pw // 2 - fw2 // 2, py + 50, 14, rl.Color(200, 100, 100, 200))
        yes_r = rl.Rectangle(px + 30, py + ph - 45, 100, 32)
        no_r  = rl.Rectangle(px + pw - 130, py + ph - 45, 100, 32)
        _btn(yes_r, 'Yes, Delete', 15, accent=True)
        _btn(no_r, 'Cancel', 15)
        if _click(yes_r):
            self.char_mgr.delete(self._confirm_delete_idx)
            self._confirm_delete_idx = -1
        elif _click(no_r):
            self._confirm_delete_idx = -1

    def _draw_delete_save_confirm(self, cw, ch):
        """Draw the wipe-save-data confirmation popup."""
        mx, my = rl.get_mouse_x(), rl.get_mouse_y()
        pw, ph = 360, 160
        px = cw // 2 - pw // 2
        py = ch // 2 - ph // 2
        rl.draw_rectangle(0, 0, cw, ch, rl.Color(0, 0, 0, 180))
        rl.draw_rectangle(px, py, pw, ph, rl.Color(0, 0, 0, 0x99))
        rl.draw_rectangle_lines(px, py, pw, ph, rl.Color(0xE0, 0xE0, 0xE0, 255))

        msg = 'Delete all save data?'
        fw = fonts.measure(msg, 20)
        fonts.draw(msg, px + pw // 2 - fw // 2, py + 16, 20, rl.Color(220, 180, 180, 255))
        warn = 'All characters, unlocks, and Anima progress will be lost.'
        fw2 = fonts.measure(warn, 14)
        fonts.draw(warn, px + pw // 2 - fw2 // 2, py + 48, 14, rl.Color(200, 100, 100, 220))
        warn2 = 'This cannot be undone!'
        fw3 = fonts.measure(warn2, 14)
        fonts.draw(warn2, px + pw // 2 - fw3 // 2, py + 68, 14, rl.Color(200, 100, 100, 220))

        yes_r = rl.Rectangle(px + 30, py + ph - 45, 130, 32)
        no_r  = rl.Rectangle(px + pw - 160, py + ph - 45, 130, 32)
        _btn(yes_r, 'Yes, Delete', 15, accent=True)
        _btn(no_r, 'Cancel', 15)
        if _click(yes_r):
            for c in list(self.char_mgr.characters):
                clear_delve_data(c.id)
            self.char_mgr.characters = []
            self.char_mgr.active_idx = 0
            self.char_mgr.unlocked_vessels = ['knight']
            self.char_mgr.best_depth = 0
            self.char_mgr.save()
            self._confirm_delete_save = False
            self._signal = 'main_menu'
        elif _click(no_r):
            self._confirm_delete_save = False

    def _draw_quit_confirm(self, cw, ch):
        """Draw the quit confirmation popup on the main menu."""
        mx, my = rl.get_mouse_x(), rl.get_mouse_y()
        pw, ph = 300, 130
        px = cw // 2 - pw // 2
        py = ch // 2 - ph // 2
        rl.draw_rectangle(px, py, pw, ph, rl.Color(0, 0, 0, 0x99))
        rl.draw_rectangle_lines(px, py, pw, ph, rl.Color(0xE0, 0xE0, 0xE0, 255))
        msg = "Quit Bound To Rot?"
        fw = fonts.measure(msg, 20)
        fonts.draw(msg, px + pw // 2 - fw // 2, py + 18, 20, rl.Color(220, 220, 200, 255))
        warn = "Unsaved progress will be lost."
        fw2 = fonts.measure(warn, 14)
        fonts.draw(warn, px + pw // 2 - fw2 // 2, py + 50, 14, rl.Color(200, 160, 100, 200))
        yes_r = rl.Rectangle(px + 30, py + ph - 45, 100, 32)
        no_r  = rl.Rectangle(px + pw - 130, py + ph - 45, 100, 32)
        _btn(yes_r, 'Yes, Quit', 15, accent=True)
        _btn(no_r, 'Cancel', 15)
        if _click(yes_r):
            self._signal = 'quit'
        elif _click(no_r):
            self._confirm_quit = False

    # ── CHAR_CREATE (identity screen) ────────────────────────────────

    def _u_char_create(self, _dt):
        self._char_name = self.char_name_input.update()

        avail = [lk for lk in LOOKS_OPTIONS
                 if lk not in WIP_VESSELS and self.char_mgr.is_vessel_unlocked(lk)]
        if not avail:
            avail = ['knight']
        if self._char_looks not in avail:
            self._char_looks = avail[0]
        li = avail.index(self._char_looks)
        # these screens run per sim tick, so is_key_pressed (true for
        # exactly one render frame) is dropped on zero-tick frames. Use the
        # same is_key_down edge-latch pattern as the splash fix (eb1f369).
        if self._ck_left.pressed(rl.KEY_LEFT):
            self._char_looks = avail[(li - 1) % len(avail)]
        if self._ck_right.pressed(rl.KEY_RIGHT):
            self._char_looks = avail[(li + 1) % len(avail)]
        if self._ck_tab.pressed(rl.KEY_TAB):
            self._char_looks = avail[(li + 1) % len(avail)]

        if self._ck_enter.pressed(rl.KEY_ENTER) and self._char_name.strip():
            self._do_create()
        if self._ck_esc.pressed(rl.KEY_ESCAPE):
            self._unload_preview_sprites()
            self.state = 'characters'

    def _load_preview_sprites(self):
        if self._preview_loaded:
            return
        for lk in LOOKS_OPTIONS:
            base = os.path.join(config.ASSETS, f'playable character/{lk}/{lk}_special_select')
            name = f'{lk}_special_select'
            spr = IsoSprite(base, name, 8, 4.0)
            spr.load(dirs=['S'])
            self._preview_sprites[lk] = spr
        self._preview_loaded = True

    def _unload_preview_sprites(self):
        for spr in self._preview_sprites.values():
            if spr:
                spr.unload()
        self._preview_sprites = {}
        self._preview_loaded = False

    def _draw_preview_frame(self, spr, box, anim_time: float):
        """Draw the animated vessel portrait ('S' frames) centered in a box."""
        frames = spr._textures.get('S', []) if spr else []
        if not frames:
            return
        idx = int(anim_time * 4.0) % len(frames)
        tex = frames[idx]
        if tex is None or getattr(tex, 'id', 0) <= 0:
            return
        tex_w = float(tex.width)
        tex_h = float(tex.height)
        crop = 0.3
        src_w = tex_w * crop
        src_h = tex_h * crop
        src_x = (tex_w - src_w) / 2
        src_y = (tex_h - src_h) / 2 - tex_h * 0.03
        scale = min(box.width / src_w, box.height / src_h)
        dw = src_w * scale
        dh = src_h * scale
        dx = box.x + (box.width - dw) / 2
        dy = box.y + (box.height - dh) / 2
        rl.draw_texture_pro(tex,
            rl.Rectangle(src_x, src_y, src_w, src_h),
            rl.Rectangle(dx, dy, dw, dh),
            rl.Vector2(0, 0), 0.0, rl.WHITE)

    def _d_char_create(self, cw: int, ch: int):
        self._preview_anim_time += rl.get_frame_time()
        self._load_preview_sprites()
        if not self.popup_mode:
            self._draw_menu_background(cw, ch)
        left, right = gui_kit.board_page(cw, ch)
        pad = 24

        # ── Left page: identity ──────────────────────────────────────────
        lx = left.x + pad
        lw_ = left.width - 2 * pad
        ly = left.y + 18

        fonts.draw('Create Character', lx, ly, 26, rl.WHITE)
        ly += 40

        fonts.draw('Character Name', lx, ly, 14, gui_kit.MUTED)
        ly += 18
        box_r = rl.Rectangle(lx, ly, min(280, lw_), 34)
        hv = _hov(box_r)
        rl.draw_rectangle_rec(box_r, _c(0x11, 0x11, 0x11, 220))
        rl.draw_rectangle_lines_ex(box_r, 1,
                                   gui_kit.GOLD if hv else gui_kit.MUTED)
        cursor = '|' if int(_time.time() * 2) % 2 == 0 else ' '
        fonts.draw(self._char_name + cursor, int(lx + 10), int(ly + 6), 22,
                   rl.WHITE)
        ly += 52

        # selected vessel flavour text fills the rest of the left page
        sel_un = VESSEL_UNLOCKS.get(self._char_looks, {})
        flavor = sel_un.get('flavor', '')
        sel_vd = VESSEL_DEFS.get(self._char_looks, {})
        fy = ly + 16
        fonts.draw(sel_vd.get('name', LOOKS_LABELS.get(self._char_looks, '')),
                   lx, fy, 18, gui_kit.GOLD)
        fy += 26
        _divider(lx, fy, lw_, color=gui_kit.MUTED)
        fy += 14
        for line in _wrap_text(flavor, 14, int(lw_)):
            fonts.draw(line, lx, fy, 14, gui_kit.MUTED)
            fy += 18

        # ── Right page: vessel choice ────────────────────────────────────
        vx = right.x + pad
        vw_ = right.width - 2 * pad
        vy = right.y + 18

        fonts.draw('Vessel', vx, vy, 14, gui_kit.MUTED)
        vy += 20
        row_h = min(150.0, (right.y + right.height - 66 - vy - 2 * 10) / 3)
        for lk in LOOKS_OPTIONS:
            vdef  = VESSEL_DEFS.get(lk, {})
            vun   = VESSEL_UNLOCKS.get(lk, {})
            wip = lk in WIP_VESSELS
            unlocked = self.char_mgr.is_vessel_unlocked(lk) and not wip
            selected = (self._char_looks == lk)
            row = rl.Rectangle(vx, vy, vw_, row_h)

            gui_kit.paper_panel(vx, vy, vw_, row_h, border=False)
            border = gui_kit.GOLD if selected else (
                gui_kit.MUTED if _hov(row) and unlocked
                else _c(0x4A, 0x3E, 0x28, 150))
            rl.draw_rectangle_lines_ex(row, 2 if selected else 1, border)

            pic = rl.Rectangle(vx + 8, vy + 8, row_h - 16, row_h - 16)
            rl.draw_rectangle_rec(pic, _c(0x1A, 0x17, 0x14, 200))
            self._draw_preview_frame(self._preview_sprites.get(lk), pic,
                                     self._preview_anim_time)

            tx = vx + row_h
            name = vdef.get('name', LOOKS_LABELS[lk])
            fonts.draw(name, int(tx), int(vy + 10), 16,
                       rl.WHITE if unlocked else gui_kit.MUTED)
            passive = vdef.get('passive', '')
            fonts.draw(passive, int(tx), int(vy + 32), 11, gui_kit.MUTED)

            if not unlocked:
                if wip:
                    fonts.draw('WIP', int(tx), int(vy + 54), 13, rl.WHITE)
                    fonts.draw('Not available yet', int(tx), int(vy + 72),
                               10, gui_kit.MUTED)
                else:
                    lock_txt = 'LOCKED'
                    fonts.draw(lock_txt, int(tx), int(vy + 54), 13, rl.WHITE)
                    veil = vun.get('veil') or ''
                    fonts.draw(veil, int(tx), int(vy + 72), 10, gui_kit.MUTED)
                    req  = vun.get('depth', 0)
                    best = self.char_mgr.best_depth
                    pct  = min(1.0, best / req) if req else 0.0
                    bar_x = tx
                    bar_w = vw_ - row_h - 16
                    bar_y = vy + row_h - 24
                    rl.draw_rectangle(int(bar_x), int(bar_y), int(bar_w), 5,
                                      _c(0x40, 0x40, 0x40, 160))
                    rl.draw_rectangle(int(bar_x), int(bar_y), int(bar_w * pct), 5,
                                      gui_kit.GOLD)
                    prog = f'Best Depth {best}/{req}'
                    fonts.draw(prog, int(bar_x), int(bar_y + 9), 10,
                               gui_kit.MUTED)
            elif _click(row):
                self._char_looks = lk
            vy += row_h + 10

        # ── Bottom buttons (right page) ──────────────────────────────────
        btn_y = right.y + right.height - 48
        can = bool(self._char_name.strip()) and self.char_mgr.is_vessel_unlocked(self._char_looks)
        next_r = rl.Rectangle(right.x + right.width - pad - 220, btn_y, 104, 38)
        cx_r = rl.Rectangle(right.x + right.width - pad - 108, btn_y, 104, 38)

        if _btn(next_r, 'Start', 20, wood=True, disabled=not can):
            self._do_create()
        if _btn(cx_r, 'Cancel', 20, wood=True):
            self.state = 'characters'

    def _u_codex(self, _dt):
        if _inp.key_pressed(self, rl.KEY_ESCAPE):
            self._unload_preview_sprites()
            self._hub_back()

    def _d_codex(self, cw: int, ch: int):
        self._preview_anim_time += rl.get_frame_time()
        self._load_preview_sprites()
        if not self.popup_mode:
            self._draw_menu_background(cw, ch)
        left, right = gui_kit.board_page(cw, ch)

        # ── Left page: title ─────────────────────────────────────────────
        title = 'Codex'
        tw = fonts.measure(title, 30)
        fonts.draw(title, int(left.x + (left.width - tw) / 2),
                   int(left.y + 40), 30, rl.WHITE)
        sub = 'Vessels of the Anima'
        sw = fonts.measure(sub, 16)
        fonts.draw(sub, int(left.x + (left.width - sw) / 2),
                   int(left.y + 80), 16, gui_kit.MUTED)
        best = self.char_mgr.best_depth
        prog = f'Best Descent: Depth {best}'
        pw2 = fonts.measure(prog, 14)
        fonts.draw(prog, int(left.x + (left.width - pw2) / 2),
                   int(left.y + 110), 14, gui_kit.GOLD)

        # ── Right page: one row per vessel ───────────────────────────────
        pad = 16
        vx = right.x + pad
        vw_ = right.width - 2 * pad
        vy = right.y + 14
        row_h = (right.height - 28 - 2 * 10) / 3
        for lk in LOOKS_OPTIONS:
            vdef  = VESSEL_DEFS.get(lk, {})
            vun   = VESSEL_UNLOCKS.get(lk, {})
            wip = lk in WIP_VESSELS
            unlocked = self.char_mgr.is_vessel_unlocked(lk) and not wip

            gui_kit.paper_panel(vx, vy, vw_, row_h)

            pic = rl.Rectangle(vx + 10, vy + 10, row_h - 20, row_h - 20)
            rl.draw_rectangle_rec(pic, _c(0x1A, 0x17, 0x14, 200))
            self._draw_preview_frame(self._preview_sprites.get(lk), pic,
                                     self._preview_anim_time)
            if not unlocked:
                rl.draw_rectangle_rec(pic, rl.Color(0, 0, 0, 0x99))
                lock_txt = 'WIP' if wip else 'LOCKED'
                lk_w = fonts.measure(lock_txt, 12)
                fonts.draw(lock_txt, int(pic.x + (pic.width - lk_w) / 2),
                           int(pic.y + pic.height / 2 - 8), 12, rl.WHITE)

            tx = vx + row_h + 6
            tw_ = vw_ - row_h - 22
            name = vdef.get('name', LOOKS_LABELS[lk])
            fonts.draw(name, int(tx), int(vy + 10), 16,
                       rl.WHITE if unlocked else gui_kit.MUTED)
            passive = vdef.get('passive', '')
            fonts.draw(passive, int(tx), int(vy + 30), 11, gui_kit.MUTED)

            flavor = vun.get('flavor', '')
            fy = vy + 50
            for line in _wrap_text(flavor, 11, int(tw_)):
                fonts.draw(line, int(tx), int(fy), 11, gui_kit.MUTED)
                fy += 14

            if unlocked:
                st = 'AVAILABLE'
                fonts.draw(st, int(tx), int(vy + row_h - 22), 12, C_GREEN)
            elif wip:
                st = 'WIP — COMING LATER'
                fonts.draw(st, int(tx), int(vy + row_h - 22), 12,
                           gui_kit.MUTED)
            else:
                veil = vun.get('veil') or ''
                fonts.draw(veil, int(tx), int(vy + row_h - 40), 11,
                           rl.WHITE)
                req  = vun.get('depth', 0)
                pct  = min(1.0, best / req) if req else 0.0
                bar_x = tx
                bar_w = tw_ * 0.7
                bar_y = vy + row_h - 20
                rl.draw_rectangle(int(bar_x), int(bar_y), int(bar_w), 4,
                                  _c(0x40, 0x40, 0x40, 160))
                rl.draw_rectangle(int(bar_x), int(bar_y), int(bar_w * pct), 4,
                                  gui_kit.GOLD)
                prog = f'Best Depth {best} / {req}'
                fonts.draw(prog, int(bar_x + bar_w + 10), int(bar_y - 2), 10,
                           gui_kit.MUTED)
            vy += row_h + 10

    def _do_create(self):
        name = self._char_name.strip()
        if not name or len(self.char_mgr.characters) >= CharacterManager.MAX_CHARS:
            return
        if self._char_looks in WIP_VESSELS \
                or not self.char_mgr.is_vessel_unlocked(self._char_looks):
            return
        self.char_mgr.create(name=name, looks=self._char_looks)
        self._char_name = ''
        self.char_name_input.clear()
        self.state = 'characters'

    def _u_settings(self, _dt):
        if _inp.key_pressed(self, rl.KEY_LEFT):
            self._settings_tab = (self._settings_tab - 1) % 4
        if _inp.key_pressed(self, rl.KEY_RIGHT):
            self._settings_tab = (self._settings_tab + 1) % 4
        if _inp.key_pressed(self, rl.KEY_ESCAPE):
            if self._confirm_delete_save:
                self._confirm_delete_save = False
            else:
                self.settings.save()
                self._settings_toast_timer = 2.0
                self.state = self._prev
        if self._settings_toast_timer > 0:
            self._settings_toast_timer = max(0.0, self._settings_toast_timer - _dt)

    def _d_settings(self, cw: int, ch: int):
        if not self.popup_mode:
            self._draw_menu_background(cw, ch)
        left, right = gui_kit.board_page(cw, ch)

        # ── Left page: title + tabs ──────────────────────────────────────
        lx = left.x + 24
        lw_ = left.width - 48
        ly = left.y + 22

        fonts.draw('Settings', lx, ly, 30, rl.WHITE)
        ly += 44
        _divider(lx, ly, lw_, color=gui_kit.MUTED)
        ly += 18

        tabs   = ['Audio', 'Graphics', 'Controls', 'Save']
        for i, tab in enumerate(tabs):
            r = rl.Rectangle(lx, ly, lw_, 44)
            actv = i == self._settings_tab
            tcol = gui_kit.GOLD if actv else rl.WHITE
            if not actv and _hov(r):
                tcol = gui_kit.GOLD
            fonts.draw(tab, int(r.x + (r.width - fonts.measure(tab, 20)) / 2),
                       int(r.y + 11), 20, tcol)
            if actv:
                # gold underline marks the active tab (no more plank image)
                ttw = fonts.measure(tab, 20)
                rl.draw_rectangle(int(r.x + (r.width - ttw) / 2),
                                  int(r.y + 34), int(ttw), 2, gui_kit.GOLD)
            if _click(r):
                self._settings_tab = i
                if _audio_ref:
                    _audio_ref.ui_click()
            ly += 54

        back_r = rl.Rectangle(lx, left.y + left.height - 52, 120, 40)
        if _btn(back_r, '< Back', 20, wood=True):
            self.settings.save()
            self._settings_toast_timer = 2.0
            self.state = self._prev

        # ── Right page: tab content ──────────────────────────────────────
        px = right.x + 20
        PW = right.width - 40
        oy = right.y + 22

        if self._settings_tab == 0:
            old_vol = self.settings.volume
            self.settings.volume = _slider(
                'SFX Volume', self.settings.volume, 0, 100, px, oy, PW)
            if self.settings.volume != old_vol and _audio_ref:
                _audio_ref.ui_click()
            oy += 50
            old_mv = self.settings.music_volume
            self.settings.music_volume = _slider(
                'Music Volume', self.settings.music_volume, 0, 100, px, oy, PW)
            if self.settings.music_volume != old_mv and _audio_ref:
                _audio_ref.ui_click()

        elif self._settings_tab == 1:
            self.settings.brightness = _slider(
                'Brightness', self.settings.brightness, 0, 100, px, oy, PW)
            oy += 50
            new_fs = _toggle('Fullscreen', self.settings.fullscreen, px, oy, PW)
            if new_fs != self.settings.fullscreen:
                self.settings.fullscreen = new_fs
                if new_fs:
                    if not rl.is_window_fullscreen():
                        rl.toggle_fullscreen()
                else:
                    if rl.is_window_fullscreen():
                        rl.toggle_fullscreen()
            oy += 34
            self.settings.perf_overlay = _toggle(
                'Perf Overlay', self.settings.perf_overlay, px, oy, PW)
            fonts.draw("Show FPS, frame times, and draw call metrics", px + 4, oy + 28, 13,
                       gui_kit.MUTED)
            oy += 48
            self.settings.crt_effect = _toggle(
                'CRT Effect', self.settings.crt_effect, px, oy, PW)
            fonts.draw("Simulate CRT monitor scanlines and vignette", px + 4, oy + 28, 13,
                       gui_kit.MUTED)
            oy += 48
            self.settings.item_labels = _toggle(
                'Always Show Item Labels', self.settings.item_labels, px, oy, PW)
            fonts.draw("Item names above ground loot; hold Alt when off", px + 4, oy + 28, 13,
                       gui_kit.MUTED)
            oy += 48
            self.settings.debug_overlay = _toggle(
                'Debug Overlay', self.settings.debug_overlay, px, oy, PW)
            fonts.draw("Show tile coordinates, entity IDs, and collision data", px + 4, oy + 28, 13,
                       gui_kit.MUTED)
            oy += 44
            self.settings.hud_scale = _slider(
                'HUD Scale', self.settings.hud_scale * 100, 50, 150, px, oy, PW) / 100.0
            oy += 44
            # Font picker
            fonts.draw('Font', px, oy, 24, rl.WHITE)
            cur_name = self.settings.font_name
            cur_idx  = FONT_NAMES.index(cur_name) if cur_name in FONT_NAMES else 0
            disp     = cur_name.replace('.ttf', '')
            arr_w    = 32
            lft_r    = rl.Rectangle(px + PW - arr_w * 2 - fonts.measure(disp, 24) - 16, oy - 2, arr_w, 31)
            rgt_r    = rl.Rectangle(px + PW - arr_w, oy - 2, arr_w, 31)
            mid_x    = int(lft_r.x + arr_w + 4)
            fonts.draw(disp, mid_x, oy, 24, gui_kit.GOLD)
            if _btn(lft_r, '<', 23, wood=True):
                new_idx = (cur_idx - 1) % len(FONT_NAMES)
                self.settings.font_name = FONT_NAMES[new_idx]
                _apply_font(self.settings.font_name)
            if _btn(rgt_r, '>', 23, wood=True):
                new_idx = (cur_idx + 1) % len(FONT_NAMES)
                self.settings.font_name = FONT_NAMES[new_idx]
                _apply_font(self.settings.font_name)

        elif self._settings_tab == 2:
            self.settings.sensitivity = _slider(
                'Mouse Sensitivity', self.settings.sensitivity, 10, 100, px, oy, PW)

        elif self._settings_tab == 3:
            fonts.draw('Save Data', px, oy, 22, rl.WHITE)
            oy += 48

            n_chars = len(self.char_mgr.characters)
            fonts.draw(f'Characters: {n_chars}/{CharacterManager.MAX_CHARS}', px + 4, oy, 16, gui_kit.GOLD)
            oy += 26
            fonts.draw(f'Best Depth: {self.char_mgr.best_depth}', px + 4, oy, 16, gui_kit.GOLD)
            oy += 44

            fonts.draw('Erases all characters, account-wide vessel',
                       px + 4, oy, 14, gui_kit.MUTED)
            oy += 20
            fonts.draw('unlocks, and Anima progress. This cannot be undone.',
                       px + 4, oy, 14, gui_kit.MUTED)
            oy += 30

            del_r = rl.Rectangle(px + 8, oy, PW - 16, 44)
            if _btn(del_r, 'Delete Save', 20, wood=True, danger=True):
                self._confirm_delete_save = True

        if self._confirm_delete_save:
            self._draw_delete_save_confirm(cw, ch)

        # Settings saved toast
        if self._settings_toast_timer > 0:
            toast = "Settings saved"
            tw = fonts.measure(toast, 18) + 40
            th = 36
            tx = int(cw // 2 - tw // 2)
            ty = ch - 80
            gui_kit.paper_panel(tx, ty, tw, th, border=False)
            rl.draw_rectangle_lines_ex(rl.Rectangle(float(tx), float(ty),
                                                    float(tw), float(th)),
                                       1, gui_kit.GOLD)
            tw = fonts.measure(toast, 18)
            fonts.draw(toast, int(cw // 2 - tw // 2), ty + 9, 18, C_GREEN)

    # ── INVENTORY (persistent character inventory) ────────────────────

    def _u_inventory(self, _dt):
        if _inp.key_pressed(self, rl.KEY_ESCAPE):
            self.state = self._prev

    def _d_inventory(self, cw: int, ch: int):
        _title('Inventory', 56, cw)
        _rule(104, cw)

        back_r = rl.Rectangle(36, 48, 88, 32)
        if _btn(back_r, '< Back', 23):
            self.state = self._prev

        # Stash access button -- left side (inventory panel is on right)
        stash_r = rl.Rectangle(40, ch // 2 - 20, 160, 38)
        if _btn(stash_r, 'Stash', 27):
            self._go('stash', prev='inventory')

        hint = "I  toggle panels"
        fonts.draw(hint, 40, ch // 2 + 30, 21, C_DIM)

        # InventoryUI is drawn on top by Game when menu_sys.state == 'inventory'

    # ── STASH (4-tab item storage) ────────────────────────────────────

    def _hub_back(self):
        """Return to hub if opened from hub, otherwise pop to _prev screen."""
        if self._prev == '_hub':
            self._signal = 'return_to_hub'
        else:
            self.state = self._prev

    def _u_stash(self, _dt):
        if _inp.key_pressed(self, rl.KEY_ESCAPE):
            self._hub_back()

    def _d_stash(self, cw: int, ch: int):
        """Menu-context bank view -- backdrop only; the interactive InventoryUI
        art panel (skull-arch bank, 8x8 grid) is drawn on top by frame_render."""
        if not self.popup_mode:
            self._draw_menu_background(cw, ch)
        _text_shadow('Stash', _cx('Stash', 48, cw), 52, 48, rl.WHITE)
        _divider(cw // 4 + 40, 108, cw // 2 - 80)

        back_r = rl.Rectangle(36, 48, 88, 32)
        if _btn(back_r, '< Back', 23):
            self._hub_back()

    # ── BLACKSMITH (dismantle forge) ──────────────────────────────────

    def _u_blacksmith(self, _dt):
        if _inp.key_pressed(self, rl.KEY_ESCAPE):
            self._hub_back()

    def _d_blacksmith(self, cw: int, ch: int):
        """Menu-context forge view -- backdrop only; the interactive
        InventoryUI forge panel (offerings/results grids) is drawn on top by
        the hub render."""
        if not self.popup_mode:
            self._draw_menu_background(cw, ch)
        _text_shadow('Blacksmith', _cx('Blacksmith', 48, cw), 52, 48, rl.WHITE)
        _divider(cw // 4 + 40, 108, cw // 2 - 80)

        back_r = rl.Rectangle(36, 48, 88, 32)
        if _btn(back_r, '< Back', 23):
            self._hub_back()

    # ── D.E.S.C.E.N.D. ─────────────────────────────────────────────────

    def _u_paused(self, _dt):
        # Arm mouse clicks only after the button is released, so the click that
        # may have been buffered when the pause opened can't hit a menu item
        # (e.g. accidentally triggering "Save & Return to Hub").
        if not self._pause_click_armed and rl.is_mouse_button_released(rl.MOUSE_BUTTON_LEFT):
            self._pause_click_armed = True
        if _inp.key_pressed(self, rl.KEY_ESCAPE):
            self._signal = 'resume'
            return
        _PAUSE_ITEMS = ['resume', 'settings', 'save_hub', 'quit_menu']
        if _inp.key_pressed(self, rl.KEY_UP):
            self._paused_sel_idx = (self._paused_sel_idx - 1) % len(_PAUSE_ITEMS)
        if _inp.key_pressed(self, rl.KEY_DOWN):
            self._paused_sel_idx = (self._paused_sel_idx + 1) % len(_PAUSE_ITEMS)
        if _inp.key_pressed(self, rl.KEY_ENTER):
            action = _PAUSE_ITEMS[self._paused_sel_idx]
            if action == 'resume':
                self._signal = 'resume'
            elif action == 'settings':
                self._prev = 'paused'
                self.state = 'settings'
            elif action == 'save_hub':
                self._signal = 'return_to_hub'
            elif action == 'quit_menu':
                self._signal = 'main_menu'

    def _d_paused(self, cw: int, ch: int):
        rl.draw_rectangle(0, 0, cw, ch, _c(0, 0, 0, 185))

        # D2-style stone slab
        panel_w = int(cw * 0.30)
        panel_x = (cw - panel_w) // 2
        panel_y = ch // 4 - 20
        panel_h = 320
        _stone_panel(panel_x, panel_y, panel_w, panel_h)

        # Header
        hdr = 'PAUSED'
        _text_shadow(hdr, _cx(hdr, 36, cw), panel_y + 30, 36, C_GOLD_TEXT)

        _divider(panel_x + 50, panel_y + 68, panel_w - 100)

        # D2-style text menu items
        items = [
            ('Return to Game',        'player',    'resume'),
            ('Settings',              'settings',  'settings'),
            ('Save & Return to Hub',  'portal',    'save_hub'),
            ('Exit to Menu',          'exit',      'quit_menu'),
        ]
        item_size = 27
        item_gap  = 46
        total_h = len(items) * item_gap
        top_y = panel_y + 90 + (panel_h - 130 - total_h) // 2

        for i, (label, icon_name, _) in enumerate(items):
            iy = top_y + i * item_gap
            tw = fonts.measure(label, item_size)
            ix = cw // 2 - tw // 2
            hit_rect = rl.Rectangle(ix - 20, iy - 4, tw + 40, item_size + 8)
            hv = _hov(hit_rect)
            is_key = (i == self._paused_sel_idx)

            if hv and self._pause_click_armed and rl.is_mouse_button_pressed(rl.MOUSE_BUTTON_LEFT):
                if _ == 'resume':
                    self._signal = 'resume'
                elif _ == 'settings':
                    self._prev = 'paused'
                    self.state = 'settings'
                elif _ == 'save_hub':
                    self._signal = 'return_to_hub'
                elif _ == 'quit_menu':
                    self._signal = 'main_menu'

            if hv or is_key:
                _menu_select_markers(cw // 2, iy + item_size // 2, spacing=tw // 2 + 18)
                _text_shadow(label, ix, iy, item_size, gui_kit.GOLD)
                icons.draw(icon_name, ix - 28, iy + 2, 22, white=True)
            else:
                _text_shadow(label, ix, iy, item_size, rl.WHITE)
                icons.draw(icon_name, ix - 28, iy + 2, 22, white=True)

        hint = 'ESC to resume'
        fonts.draw(hint, _cx(hint, 15, cw), panel_y + panel_h - 22, 15, C_DIM)
