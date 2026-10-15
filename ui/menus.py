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
        char_create, settings, tasks, stash, paused.
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
                              VESSEL_UNLOCKS)
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
def _apply_font(font_name: str):
    path = os.path.join(_FONT_DIR, font_name)
    if os.path.exists(path):
        fonts.unload()
        fonts.load(path, 64)


# ── Palette ───────────────────────────────────────────────────────────
# Remapped to the gui kit's style guide (assets/gui/Layout/Colors.png).
def _c(r, g, b, a=255): return rl.Color(r, g, b, a)
C_BG      = _c(0,   0,   0,   255)
C_PANEL   = _c(0x11, 0x11, 0x11, 0x99)                 # Main Black
C_BORDER  = _c(0x37, 0x37, 0x37, 255)                  # Grey Dark
C_ACCENT  = _c(0xA9, 0x0D, 0x01, 255)                  # Main Red
C_ACCENT_HOVER = _c(0xDA, 0x00, 0x00, 255)             # Red hover
C_WHITE   = _c(0xD2, 0xD2, 0xD2, 255)                  # Main White
C_DIM     = _c(0x99, 0x99, 0x99, 255)
C_GOLD    = _c(255, 225, 70,  255)
C_GREEN   = _c(80,  200, 80,  255)
C_RED     = _c(0xDA, 0x00, 0x00, 255)
C_DARK    = _c(0,   0,   0,   0x99)

# UI palette (BLUEPRINT §14) — kit palette, white trim, black panels
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
        self.font_name      = 'OSerif-Regular.ttf'
        self.brightness     = 50  # 0-100
        self.tarot_deck     = 'arcanum'   # active card deck id (TAROT_DECKS)
        self.tarot_skins    = []          # unlocked alternative deck ids
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
                    'tarot_deck':      self.tarot_deck,
                    'tarot_skins':     list(self.tarot_skins),
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
            self.font_name      = str(d.get('font_name',        'OSerif-Regular.ttf'))
            self.brightness     = float(d.get('brightness',     50))
            self.tarot_deck     = str(d.get('tarot_deck',       'arcanum'))
            skins               = d.get('tarot_skins', [])
            self.tarot_skins    = [str(s) for s in skins] if isinstance(skins, list) else []
        except Exception:
            print("[settings] ERROR: Failed to load settings.json")
            traceback.print_exc()
        self.debug_overlay = False  # always start with debug off


# ── Drawing helpers ───────────────────────────────────────────────────

def _cx(text: str, size: int, cw: int) -> int:
    return cw // 2 - fonts.measure(text, size) // 2


def _panel(x, y, w, h):
    if not gui_kit.nine_slice(gui_kit.tex('frame_bg'), x, y, w, h, corner=32):
        rl.draw_rectangle(x, y, w, h, C_PANEL)
        rl.draw_rectangle_lines(x, y, w, h, C_BORDER)


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
    red border with a pulsing glow ring (kit accent)."""
    if active:
        pulse = (math.sin(rl.get_time() * 5.0) + 1.0) / 2.0
        glow_a = int(60 + 110 * pulse)
        rl.draw_rectangle_lines_ex(rl.Rectangle(r.x - 4, r.y - 4, r.width + 8, r.height + 8), 1,
                                   _c(0xA9, 0x0D, 0x01, glow_a))
        rl.draw_rectangle_lines_ex(r, 2, gui_kit.RED_HOT)
    else:
        rl.draw_rectangle_lines_ex(r, 1, _c(0xD2, 0xD2, 0xD2, 110))


def _btn(r, text: str, size: int = 28, accent: bool = False, disabled: bool = False, gold: bool = False, lit: bool = False) -> bool:
    hovered = _hov(r) and not disabled
    rkey = (int(r.x), int(r.y), int(r.width), int(r.height))
    was_hovered = _hovered_last.get(rkey, False)
    if hovered and not was_hovered and _audio_ref:
        _audio_ref.ui_hover()
    _hovered_last[rkey] = hovered
    tw = fonts.measure(text, size)
    # Kit-textured buttons only for wide rects — stretching the wide
    # bar art into small/square rects (X close, chips) looks wrong.
    wide = r.width >= 2.0 * r.height and r.width >= 120
    tex_key = None
    if disabled:
        tex_key = 'btn_disable'
    elif hovered and not disabled and wide:
        tex_key = 'btn_red_hov' if accent else 'btn_grey_hov'
    elif wide:
        tex_key = 'btn_red' if accent else 'btn_grey'
    held = wide and hovered and rl.is_mouse_button_down(rl.MOUSE_BUTTON_LEFT)
    if held:
        tex_key = 'btn_pressed'
    if lit:
        bg = _c(0xFF, 0xFF, 0xFF, 255)
        tc = _c(0, 0, 0, 255)
    elif accent:
        tc = rl.WHITE if hovered else C_ACCENT_HOVER
    else:
        tc = rl.WHITE if hovered else gui_kit.WHITE
    if disabled:
        tc = _c(0x9A, 0x9A, 0x9A, 180)

    if wide and tex_key and not lit:
        if not gui_kit.nine_slice(gui_kit.tex(tex_key), int(r.x), int(r.y),
                                  int(r.width), int(r.height)):
            rl.draw_rectangle_rec(r, C_SLATE)
        if not hovered and not disabled:
            _hover_fx(r, False)
    else:
        if disabled:
            bg = _c(0, 0, 0, 0x99)
            rl.draw_rectangle_rec(r, bg)
            rl.draw_rectangle_lines_ex(r, 1, _c(0x88, 0x88, 0x88, 0x66))
        elif lit:
            rl.draw_rectangle_rec(r, bg)
            _hover_fx(r, hovered)
        else:
            rl.draw_rectangle_rec(r, C_SLATE)
            if accent and not hovered:
                rl.draw_rectangle_lines_ex(r, 1, C_ACCENT)
            else:
                _hover_fx(r, hovered)
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
    fonts.draw(label,   x, y, size, C_WHITE)
    fonts.draw(val_txt, x + w - fonts.measure(val_txt, size), y, size, C_DIM)
    bar_h = max(14, size // 2)
    bar_y = y + size + 4
    track = gui_kit.tex('slider_track')
    fill  = gui_kit.tex('slider_fill')
    knob  = gui_kit.tex('slider_knob')
    if track and track.id > 0:
        gui_kit.nine_slice(track, x, bar_y, w, bar_h, corner=12)
    else:
        rl.draw_rectangle(x, bar_y, w, 8, C_DARK)
    if pct > 0.02:
        fw = max(bar_h, int(w * pct))
        if fill and fill.id > 0:
            gui_kit.nine_slice(fill, x, bar_y, fw, bar_h, corner=12)
        else:
            rl.draw_rectangle(x, bar_y, int(w * pct), 8, C_ACCENT)
        # the full-art is near-black grunge — a translucent red overlay
        # keeps it readable as the filled portion of the value bar
        rl.draw_rectangle(x, bar_y, fw, bar_h, _c(0xA9, 0x0D, 0x01, 150))
    if knob and knob.id > 0:
        kh = bar_h + 10
        kw = max(4, int(kh * knob.width / knob.height))
        kx = x + int(w * pct) - kw // 2
        rl.draw_texture_pro(knob,
            rl.Rectangle(0, 0, float(knob.width), float(knob.height)),
            rl.Rectangle(float(kx), float(bar_y + bar_h // 2 - kh // 2),
                         float(kw), float(kh)),
            rl.Vector2(0, 0), 0.0, rl.WHITE)
    bar_r = rl.Rectangle(float(x), float(bar_y - 5), float(w), float(bar_h + 10))
    if rl.is_mouse_button_down(rl.MOUSE_BUTTON_LEFT) and _hov(bar_r):
        new_pct = max(0.0, min(1.0, (rl.get_mouse_x() - x) / w))
        value   = min_v + new_pct * (max_v - min_v)
    return value


def _toggle(label: str, value: bool, x: int, y: int, w: int, size: int = 27) -> bool:
    """Kit checkmark toggle: red check box when on, hollow box when off."""
    fonts.draw(label, x, y, size, C_WHITE)
    box = size + 4
    bx  = x + w - box
    box_r = rl.Rectangle(float(bx), float(y - 2), float(box), float(box + 4))
    rl.draw_rectangle_rec(box_r, C_SLATE)
    rl.draw_rectangle_lines_ex(box_r, 1, C_ACCENT if value else C_BORDER)
    ck = gui_kit.tex('checkmark')
    if value and ck and ck.id > 0:
        rl.draw_texture_pro(ck,
            rl.Rectangle(0, 0, float(ck.width), float(ck.height)),
            rl.Rectangle(float(bx + 2), float(y), float(box - 4), float(box - 4)),
            rl.Vector2(0, 0), 0.0, rl.WHITE)
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
    col = C_GOLD_HOVER if hovered else C_GOLD_TEXT
    fonts.draw(text, x, y, size, col)


def _stone_panel(x: int, y: int, w: int, h: int):
    """Kit black-grunge slab: Frame_background fill + Frame_outline
    border, red corner accents."""
    gui_kit.nine_slice(gui_kit.tex('frame_bg'), x, y, w, h, corner=32)
    if not gui_kit.nine_slice(gui_kit.tex('frame_outline'), x, y, w, h,
                              corner=32):
        rl.draw_rectangle(x, y, w, h, C_SLATE)
        rl.draw_rectangle_lines_ex(rl.Rectangle(float(x + 1), float(y + 1),
                                                float(w - 2), float(h - 2)),
                                   1, _c(0xD2, 0xD2, 0xD2, 0x88))
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
        rl.draw_triangle(_V0, _V1, _V2, C_GOLD_HOVER)
        rl.draw_triangle(_V0, _V2, _V3, C_GOLD_HOVER)


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


def _divider(x: int, y: int, w: int):
    """Grey decorative divider line with red centre diamond."""
    rl.draw_line(x, y, x + w, y, _c(0x66, 0x66, 0x66, 0xDD))
    rl.draw_line(x, y + 1, x + w, y + 1, _c(0, 0, 0, 0x88))
    # centre diamond
    mx = x + w // 2
    rl.draw_triangle(rl.Vector2(float(mx), float(y - 3)), rl.Vector2(float(mx + 4), float(y)),
                     rl.Vector2(float(mx), float(y + 3)), C_ACCENT)
    rl.draw_triangle(rl.Vector2(float(mx), float(y - 3)), rl.Vector2(float(mx), float(y + 3)),
                     rl.Vector2(float(mx - 4), float(y)), C_ACCENT)


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

        # Missing-asset notice (filled by Game.init from systems.asset_guard)
        self.missing_assets = []
        self._assets_notice_dismissed = False
        self._assets_notice_t = 0.0

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
        if self.missing_assets and not self._assets_notice_dismissed:
            self._assets_notice_t += dt
            if self._assets_notice_t > 45.0:
                self._assets_notice_dismissed = True
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
        self._d_assets_notice(cw, ch)

    def _d_assets_notice(self, cw: int, ch: int):
        """Top-of-screen banner when non-distributed asset packs are absent."""
        if not self.missing_assets or self._assets_notice_dismissed:
            return
        pw = min(980, cw - 40)
        ph = 118
        px = cw // 2 - pw // 2
        py = 12
        rl.draw_rectangle(px, py, pw, ph, rl.Color(0, 0, 0, 0xCC))
        rl.draw_rectangle_lines(px, py, pw, ph, C_ACCENT)
        title = "Some game assets are missing"
        fonts.draw(title, px + pw // 2 - fonts.measure(title, 22) // 2,
                   py + 10, 22, C_ACCENT)
        names = ', '.join(self.missing_assets)
        fonts.draw(names, px + pw // 2 - fonts.measure(names, 16) // 2,
                   py + 42, 16, C_GOLD)
        hint = ("Entities render as placeholders. See THIRD_PARTY_ASSETS.md "
                "and assets/<folder>/README.md for how to obtain them.")
        fonts.draw(hint, px + pw // 2 - fonts.measure(hint, 15) // 2,
                   py + 66, 15, C_DIM)
        ok_r = rl.Rectangle(px + pw // 2 - 55, py + ph - 36, 110, 28)
        _btn(ok_r, 'OK', 15)
        if _click(ok_r):
            self._assets_notice_dismissed = True

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

        # Panel geometry (used for centering the menu items) -- the kit's
        # grunge menu panel sits behind the menu column.
        panel_w = int(cw * 0.35)
        panel_x = (cw - panel_w) // 2
        panel_y = 60
        panel_h = ch - 120
        gui_kit.nine_slice(gui_kit.tex('frame_menu'), panel_x, panel_y,
                           panel_w, panel_h, corner=48)

        # Logo inside the slab
        logo = self.logo_tex
        logo_bottom = 0
        if logo and logo.id > 0:
            max_w = min(panel_w - 60, 260)
            sc = min(1.0, max_w / logo.width)
            lw = int(logo.width * sc)
            lh = int(logo.height * sc)
            lx = cw // 2 - lw // 2
            ly = panel_y + 28
            rl.draw_texture_pro(logo,
                rl.Rectangle(0, 0, float(logo.width), float(logo.height)),
                rl.Rectangle(float(lx), float(ly), float(lw), float(lh)),
                rl.Vector2(0, 0), 0.0, rl.WHITE)
            logo_bottom = ly + lh

        # Decorative divider below logo
        divider_y = (logo_bottom if logo_bottom > 0 else panel_y + 80) + 18
        if logo and logo.id > 0:
            _divider(panel_x + 40, divider_y, panel_w - 80)

        # Vertical menu -- white-bordered buttons over the artwork
        items = [
            ('Single Player',     'player',   'play'),
            ('Multiplayer',       'multiplayer', 'mp'),
            ('Dedicated Server',  'server',   'dedicated'),
            ('Settings',          'settings', 'settings'),
            ('Exit Bound To Rot', 'exit',     'quit'),
        ]
        item_size = 32
        item_gap  = 58
        btn_h     = 50
        start_y = divider_y + 28
        total_h = len(items) * item_gap
        top_y = start_y + (panel_y + panel_h - start_y - total_h) // 2

        for i, (label, icon_name, _) in enumerate(items):
            iy = top_y + i * item_gap
            tw = fonts.measure(label, item_size)
            btn_w = tw + 76
            bx = cw // 2 - btn_w // 2
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

            tex_key = ('btn_red_hov' if active else 'btn_red')
            if rl.is_mouse_button_down(rl.MOUSE_BUTTON_LEFT) and hovered:
                tex_key = 'btn_pressed'
            if not gui_kit.nine_slice(gui_kit.tex(tex_key), bx, by, btn_w, btn_h):
                rl.draw_rectangle_rec(btn, _c(0, 0, 0, 0x99) if active else _c(0, 0, 0, 0x35))
                _hover_fx(btn, active)

            content_w = 22 + 14 + tw
            content_x = bx + (btn_w - content_w) // 2
            if active:
                icons.draw(icon_name, content_x, by + (btn_h - 22) // 2, 22, rl.WHITE)
                _text_shadow(label, content_x + 36, by + (btn_h - item_size) // 2, item_size, rl.WHITE)
            else:
                icons.draw(icon_name, content_x, by + (btn_h - 22) // 2, 22, gui_kit.WHITE)
                _text_shadow(label, content_x + 36, by + (btn_h - item_size) // 2, item_size, gui_kit.WHITE)

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
        fonts.draw(version, panel_x + panel_w - fonts.measure(version, 16) - 8,
                   panel_y + panel_h - 24, 16, _c(80, 90, 80, 180))

        if self._confirm_quit:
            self._draw_quit_confirm(cw, ch)

    # ── PLAY ──────────────────────────────────────────────────────────

    def _u_play(self, _dt):
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

        chars = self.char_mgr.characters
        sel_idx = max(0, min(self._char_sel_idx, len(chars) - 1)) if chars else 0

        # ── Save-load failure banner (issue #126) ───────────────────────
        # A save that could not be loaded is never discarded silently; the file
        # has been backed up and the player is told where it went.
        if self.char_mgr.load_error:
            banner = self.char_mgr.load_error
            bw = fonts.measure(banner, 18)
            fonts.draw(banner, max(10, cw // 2 - bw // 2), 20, 18, C_RED)
            if self.char_mgr.load_error_backup:
                bk = self.char_mgr.load_error_backup
                bkw = fonts.measure(bk, 14)
                fonts.draw(bk, max(10, cw // 2 - bkw // 2), 42, 14, C_DIM)

        # ── Left rail: character list ──────────────────────────────────
        left_x  = cw // 2 - 380
        left_w  = 340
        left_y  = 80
        card_h  = 62
        gap     = 6

        if not chars:
            msg = 'No characters yet.  Create one to play.'
            fonts.draw(msg, _cx(msg, 24, cw), left_y + 30, 24, C_DIM)

        for i, c in enumerate(chars):
            cy = left_y + i * (card_h + gap)
            is_active = (i == self.char_mgr.active_idx)
            is_focus  = (i == sel_idx)

            cr = rl.Rectangle(left_x, cy, left_w, card_h)
            hv = rl.check_collision_point_rec(rl.get_mouse_position(), cr)

            if is_focus:
                bg = _c(0, 0, 0, 0x99)
                border = C_GOLD_HOVER
            elif hv:
                bg = _c(0, 0, 0, 0x99)
                border = _c(0xE0, 0xE0, 0xE0, 255)
            else:
                bg = _c(0, 0, 0, 0x99)
                border = C_BORDER if is_active else _c(0x66, 0x66, 0x66, 180)

            rl.draw_rectangle_rec(cr, bg)
            rl.draw_rectangle_lines_ex(cr, 1, border)
            if is_focus:
                rl.draw_rectangle_lines_ex(rl.Rectangle(left_x - 2, cy - 2, left_w + 4, card_h + 4),
                                           1, _c(255, 255, 255, 100))

            vessel_def = VESSEL_DEFS.get(c.looks, {})
            icons.draw(c.looks, left_x + 8, cy + 8, 22)
            fonts.draw(c.name, left_x + 36, cy + 6, 28, C_GOLD_TEXT if is_active else C_WHITE)
            fonts.draw(vessel_def.get('name', c.looks), left_x + 36, cy + 36, 18, C_ACCENT)

            if hv and rl.is_mouse_button_pressed(rl.MOUSE_BUTTON_LEFT):
                self.char_mgr.select(i)

        # Delete button per character
        for i, c in enumerate(chars):
            cy = left_y + i * (card_h + gap)
            del_r = rl.Rectangle(left_x + left_w - 36, cy + 14, 28, card_h - 28)
            if _btn(del_r, 'X', 16):
                self._confirm_delete_idx = i

        # ── Right panel: selected character details ────────────────────
        right_x = cw // 2 + 60
        right_w = 310
        right_y = left_y
        right_h = 420 if chars else 0

        if chars:
            _stone_panel(right_x, right_y, right_w, right_h)

        if chars and 0 <= sel_idx < len(chars):
            c = chars[sel_idx]
            vessel_def = VESSEL_DEFS.get(c.looks, {})
            rx = right_x + 20
            ry = right_y + 22

            _text_shadow(c.name, rx, ry, 30, C_GOLD_TEXT)
            ry += 30
            icons.draw(c.looks, rx, ry + 2, 22)
            fonts.draw(vessel_def.get('name', c.looks), rx + 28, ry, 20, C_WHITE)
            ry += 26
            ry += 8

            _divider(right_x + 18, ry, right_w - 36)
            ry += 16

            fonts.draw('Attributes', rx, ry, 17, C_WHITE)
            ry += 24

            for attr_key in DESCEND_ATTRIBUTES:
                icon_name = attr_key
                bar_col = _c(0xE0, 0xE0, 0xE0, 255)
                label = ATTR_LABEL.get(attr_key, attr_key.title())
                val = c.descend.get(attr_key, 0)
                icons.draw(icon_name, rx, ry + 2, 14, bar_col)
                fonts.draw(label[:4], rx + 18, ry, 14, bar_col)
                fonts.draw(str(val), rx + 52, ry, 14, C_WHITE)
                bar_x = rx + 68
                bar_w = right_w - 108
                bar_h = 5
                rl.draw_rectangle(bar_x, ry + 5, bar_w, bar_h, _c(0, 0, 0, 0x99))
                rl.draw_rectangle(bar_x, ry + 5, int(bar_w * min(val, ATTR_CAP) / ATTR_CAP), bar_h, bar_col)
                ry += 18

            ry += 10
            _divider(right_x + 18, ry, right_w - 36)
            ry += 16

            derived = compute_derived_stats(c.descend, looks=c.looks)
            for stat_label, icon_name, stat_val in [
                ('Life',    'hp',       derived['max_health']),
                ('Evasion', 'evasion',  derived['evasion']),
                ('Acc.',    'accuracy', derived['accuracy']),
            ]:
                icons.draw(icon_name, rx, ry + 3, 14)
                fonts.draw(stat_label, rx + 18, ry, 16, C_DIM)
                fonts.draw(str(stat_val), rx + 90, ry, 16, C_WHITE)
                ry += 22

        # ── Bottom buttons ─────────────────────────────────────────────
        btn_y = right_y + right_h + 16
        btn_h = 42
        btn_w = 130

        if chars:
            ok_r = rl.Rectangle(right_x, btn_y, btn_w, btn_h)
            if _btn(ok_r, 'Play', 24, accent=True):
                self.char_mgr.select(sel_idx)
                self._signal = 'start_solo'

        new_r = rl.Rectangle(right_x + btn_w + 12, btn_y, btn_w, btn_h) if chars else \
            rl.Rectangle(cw // 2 - btn_w // 2, left_y + 190, btn_w, btn_h)
        can_create = len(chars) < CharacterManager.MAX_CHARS
        if _btn(new_r, 'Create New', 20, disabled=not can_create):
            self._char_name = ''
            self.char_name_input.clear()
            self._char_looks = 'knight'
            self.state = 'char_create'

        if chars and sel_idx < len(chars):
            del_btn = rl.Rectangle(right_x + (btn_w + 12) * 2, btn_y, btn_w, btn_h)
            if _btn(del_btn, 'Delete', 20):
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
        warn = 'All characters, unlocks, and delve progress will be lost.'
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

        avail = [lk for lk in LOOKS_OPTIONS if self.char_mgr.is_vessel_unlocked(lk)]
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
        self._draw_menu_background(cw, ch)

        panel_w = 740
        panel_h = 520
        panel_x = (cw - panel_w) // 2
        panel_y = 60

        rx = panel_x + 28
        ry = panel_y + 28

        _text_shadow('Create Character', rx, ry, 36, C_GOLD_TEXT)
        ry += 48

        # ── Name ─────────────────────────────────────────────────────────
        fonts.draw('Character Name', rx, ry, 18, C_DIM)
        ry += 22
        box_r = rl.Rectangle(rx, ry, 260, 36)
        hv = _hov(box_r)
        rl.draw_rectangle_rec(box_r, _c(0, 0, 0, 0x99))
        rl.draw_rectangle_lines_ex(box_r, 1, C_ACCENT if hv else C_BORDER)
        cursor = '|' if int(_time.time() * 2) % 2 == 0 else ' '
        fonts.draw(self._char_name + cursor, int(rx + 10), int(ry + 6), 26, C_WHITE)
        ry += 52

        # ── Vessel ────────────────────────────────────────────────────────
        fonts.draw('Vessel', rx, ry, 18, C_DIM)
        ry += 24
        card_w = 216
        card_h = 216
        gap    = 14
        cx = rx
        for lk in LOOKS_OPTIONS:
            vdef  = VESSEL_DEFS.get(lk, {})
            vun   = VESSEL_UNLOCKS.get(lk, {})
            unlocked = self.char_mgr.is_vessel_unlocked(lk)
            selected = (self._char_looks == lk)
            card = rl.Rectangle(cx, ry, card_w, card_h)

            rl.draw_rectangle_rec(card, _c(0, 0, 0, 0x99))
            border = C_GOLD_HOVER if selected else (C_ACCENT if _hov(card) and unlocked else C_BORDER)
            rl.draw_rectangle_lines_ex(card, 2 if selected else 1, border)

            pic = rl.Rectangle(cx + 8, ry + 8, card_w - 16, 118)
            rl.draw_rectangle_rec(pic, _c(0, 0, 0, 0x99))
            self._draw_preview_frame(self._preview_sprites.get(lk), pic, self._preview_anim_time)

            name = vdef.get('name', LOOKS_LABELS[lk])
            nw = fonts.measure(name, 18)
            fonts.draw(name, int(cx + (card_w - nw) / 2), int(ry + 134), 18,
                       C_GOLD_TEXT if unlocked else C_DIM)

            passive = vdef.get('passive', '')
            pw = fonts.measure(passive, 12)
            fonts.draw(passive, int(cx + (card_w - pw) / 2), int(ry + 160), 12, C_DIM)

            if not unlocked:
                rl.draw_rectangle_rec(pic, rl.Color(0, 0, 0, 0x99))
                lock_txt = 'LOCKED'
                lk_sz = 16
                lk_w = fonts.measure(lock_txt, lk_sz)
                fonts.draw(lock_txt, int(cx + (card_w - lk_w) / 2), int(ry + 66), lk_sz, C_GOLD_TEXT)

                veil = vun.get('veil') or ''
                vw = fonts.measure(veil, 12)
                fonts.draw(veil, int(cx + (card_w - vw) / 2), int(ry + 180), 12, C_GOLD_TEXT)

                req  = vun.get('depth', 0)
                best = self.char_mgr.best_depth
                pct  = min(1.0, best / req) if req else 0.0
                bar_x = cx + 12
                bar_w = card_w - 24
                bar_y = ry + 198
                rl.draw_rectangle(bar_x, bar_y, bar_w, 6, _c(0, 0, 0, 0x99))
                rl.draw_rectangle(bar_x, bar_y, int(bar_w * pct), 6, C_GOLD_TEXT)
                prog = f'Best Depth {best}/{req}'
                pw2 = fonts.measure(prog, 11)
                fonts.draw(prog, int(cx + (card_w - pw2) / 2), int(bar_y + 10), 11, C_DIM)
            elif _click(card):
                self._char_looks = lk
            cx += card_w + gap

        sel_un  = VESSEL_UNLOCKS.get(self._char_looks, {})
        flavor  = sel_un.get('flavor', '')
        fl_w    = fonts.measure(flavor, 13)
        fonts.draw(flavor, panel_x + 28, ry + card_h + 14, 13, C_DIM)

        ry += card_h + 44

        # ── Bottom buttons ───────────────────────────────────────────────
        btn_y = panel_y + panel_h - 52
        can = bool(self._char_name.strip()) and self.char_mgr.is_vessel_unlocked(self._char_looks)
        next_r = rl.Rectangle(panel_x + panel_w - 230, btn_y, 100, 38)
        cx_r = rl.Rectangle(panel_x + panel_w - 120, btn_y, 100, 38)

        if _btn(next_r, 'Start', 22, accent=can, disabled=not can):
            self._do_create()
        if _btn(cx_r, 'Cancel', 22):
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

        title = 'Codex — Vessels of the Anima'
        tw = fonts.measure(title, 40)
        fonts.draw(title, cw // 2 - tw // 2, 80, 40, C_GOLD_TEXT)

        sub = f'Best Descent: Depth {self.char_mgr.best_depth}'
        sw = fonts.measure(sub, 20)
        fonts.draw(sub, cw // 2 - sw // 2, 130, 20, C_ACCENT)

        card_w = 300
        card_h = 420
        gap    = 24
        total  = 3 * card_w + 2 * gap
        x0 = cw // 2 - total // 2
        y0 = 185
        for lk in LOOKS_OPTIONS:
            vdef  = VESSEL_DEFS.get(lk, {})
            vun   = VESSEL_UNLOCKS.get(lk, {})
            unlocked = self.char_mgr.is_vessel_unlocked(lk)
            cx = x0

            _stone_panel(cx, y0, card_w, card_h)

            pic = rl.Rectangle(cx + 10, y0 + 14, card_w - 20, 190)
            rl.draw_rectangle_rec(pic, _c(0, 0, 0, 0x99))
            self._draw_preview_frame(self._preview_sprites.get(lk), pic, self._preview_anim_time)
            if not unlocked:
                rl.draw_rectangle_rec(pic, rl.Color(0, 0, 0, 0x99))
                lock_txt = 'LOCKED'
                lk_sz = 22
                lk_w = fonts.measure(lock_txt, lk_sz)
                fonts.draw(lock_txt, int(cx + (card_w - lk_w) / 2), int(y0 + 100), lk_sz, C_GOLD_TEXT)

            name = vdef.get('name', LOOKS_LABELS[lk])
            nw = fonts.measure(name, 24)
            fonts.draw(name, int(cx + (card_w - nw) / 2), int(y0 + 214), 24,
                       C_GOLD_TEXT if unlocked else C_DIM)

            passive = vdef.get('passive', '')
            pw = fonts.measure(passive, 14)
            fonts.draw(passive, int(cx + (card_w - pw) / 2), int(y0 + 252), 14,
                       C_ACCENT if unlocked else C_DIM)

            flavor = vun.get('flavor', '')
            _divider(cx + 14, y0 + 282, card_w - 28)
            fw = fonts.measure(flavor, 13)
            fonts.draw(flavor, int(cx + (card_w - fw) / 2), int(y0 + 294), 13, C_DIM)

            if unlocked:
                st = 'AVAILABLE'
                stw = fonts.measure(st, 15)
                fonts.draw(st, int(cx + (card_w - stw) / 2), int(y0 + 342), 15, C_GREEN)
            else:
                veil = vun.get('veil') or ''
                vw = fonts.measure(veil, 15)
                fonts.draw(veil, int(cx + (card_w - vw) / 2), int(y0 + 332), 15, C_GOLD_TEXT)

                req  = vun.get('depth', 0)
                best = self.char_mgr.best_depth
                pct  = min(1.0, best / req) if req else 0.0
                bar_x = cx + 20
                bar_w = card_w - 40
                bar_y = y0 + 360
                rl.draw_rectangle(bar_x, bar_y, bar_w, 8, _c(0, 0, 0, 0x99))
                rl.draw_rectangle(bar_x, bar_y, int(bar_w * pct), 8, C_GOLD_TEXT)
                prog = f'Best Depth {best} / {req}'
                pw2 = fonts.measure(prog, 12)
                fonts.draw(prog, int(cx + (card_w - pw2) / 2), int(bar_y + 14), 12, C_DIM)
            x0 += card_w + gap

    def _do_create(self):
        name = self._char_name.strip()
        if not name or len(self.char_mgr.characters) >= CharacterManager.MAX_CHARS:
            return
        if not self.char_mgr.is_vessel_unlocked(self._char_looks):
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
        self._draw_menu_background(cw, ch)
        _text_shadow('Settings', _cx('Settings', 48, cw), 52, 48, C_GOLD_TEXT)
        _divider(cw // 4 + 40, 108, cw // 2 - 80)

        back_r = rl.Rectangle(36, 48, 88, 32)
        if _btn(back_r, '< Back', 23):
            self.settings.save()
            self._settings_toast_timer = 2.0
            self.state = self._prev

        tabs   = ['Audio', 'Graphics', 'Controls', 'Save']
        tab_icons = ['audio', 'graphics', 'controls', 'server']
        TAB_W  = 132
        tab_ox = cw // 2 - (len(tabs) * TAB_W + (len(tabs) - 1) * 4) // 2
        for i, tab in enumerate(tabs):
            r     = rl.Rectangle(tab_ox + i * (TAB_W + 4), 124, TAB_W, 30)
            actv  = i == self._settings_tab
            bg    = _c(0, 0, 0, 0x99)
            tc    = C_GOLD_HOVER if actv else C_DIM
            bcol  = C_GOLD_TEXT if actv else C_BORDER
            rl.draw_rectangle_rec(r, bg)
            rl.draw_rectangle_lines_ex(r, 1, bcol)
            icons.draw(tab_icons[i], int(r.x + 14), int(r.y + 7), 18,
                       tc if actv else C_DIM)
            fonts.draw(tab, int(r.x + 36), int(r.y + 8), 22, tc if actv else C_DIM)
            if _click(r):
                self._settings_tab = i

        PW = 420
        px = cw // 2 - PW // 2
        panel_x = px - 22
        panel_y = 166
        panel_h = 320

        oy = panel_y + 22

        if self._settings_tab == 0:
            icons.draw('audio', px, oy + 2, 24, C_GOLD_TEXT)
            old_vol = self.settings.volume
            self.settings.volume = _slider(
                'SFX Volume', self.settings.volume, 0, 100, px + 32, oy, PW - 36)
            if self.settings.volume != old_vol and _audio_ref:
                _audio_ref.ui_click()
            oy += 50
            old_mv = self.settings.music_volume
            self.settings.music_volume = _slider(
                'Music Volume', self.settings.music_volume, 0, 100, px + 32, oy, PW - 36)
            if self.settings.music_volume != old_mv and _audio_ref:
                _audio_ref.ui_click()

        elif self._settings_tab == 1:
            icons.draw('graphics', px, oy, 24, C_GOLD_TEXT)
            self.settings.brightness = _slider(
                'Brightness', self.settings.brightness, 0, 100, px + 32, oy, PW - 36)
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
            fonts.draw("Show FPS, frame times, and draw call metrics", px + 4, oy + 28, 14,
                       rl.Color(0xCC, 0xCC, 0xCC, 200))
            oy += 48
            self.settings.crt_effect = _toggle(
                'CRT Effect', self.settings.crt_effect, px, oy, PW)
            fonts.draw("Simulate CRT monitor scanlines and vignette", px + 4, oy + 28, 14,
                       rl.Color(0xCC, 0xCC, 0xCC, 200))
            oy += 48
            self.settings.debug_overlay = _toggle(
                'Debug Overlay', self.settings.debug_overlay, px, oy, PW)
            fonts.draw("Show tile coordinates, entity IDs, and collision data", px + 4, oy + 28, 14,
                       rl.Color(0xCC, 0xCC, 0xCC, 200))
            oy += 44
            self.settings.hud_scale = _slider(
                'HUD Scale', self.settings.hud_scale * 100, 50, 150, px, oy, PW) / 100.0
            oy += 44
            # Font picker
            fonts.draw('Font', px, oy, 27, C_WHITE)
            cur_name = self.settings.font_name
            cur_idx  = FONT_NAMES.index(cur_name) if cur_name in FONT_NAMES else 0
            disp     = cur_name.replace('.ttf', '')
            arr_w    = 32
            lft_r    = rl.Rectangle(px + PW - arr_w * 2 - fonts.measure(disp, 27) - 16, oy - 2, arr_w, 31)
            rgt_r    = rl.Rectangle(px + PW - arr_w, oy - 2, arr_w, 31)
            mid_x    = int(lft_r.x + arr_w + 4)
            fonts.draw(disp, mid_x, oy, 27, C_ACCENT)
            if _btn(lft_r, '<', 23):
                new_idx = (cur_idx - 1) % len(FONT_NAMES)
                self.settings.font_name = FONT_NAMES[new_idx]
                _apply_font(self.settings.font_name)
            if _btn(rgt_r, '>', 23):
                new_idx = (cur_idx + 1) % len(FONT_NAMES)
                self.settings.font_name = FONT_NAMES[new_idx]
                _apply_font(self.settings.font_name)

        elif self._settings_tab == 2:
            icons.draw('controls', px, oy + 2, 24, C_GOLD_TEXT)
            self.settings.sensitivity = _slider(
                'Mouse Sensitivity', self.settings.sensitivity, 10, 100, px + 32, oy, PW - 36)

        elif self._settings_tab == 3:
            icons.draw('server', px, oy + 2, 24, C_GOLD_TEXT)
            fonts.draw('Save Data', px + 32, oy + 2, 27, C_WHITE)
            oy += 48

            n_chars = len(self.char_mgr.characters)
            fonts.draw(f'Characters: {n_chars}/{CharacterManager.MAX_CHARS}', px + 4, oy, 18, C_ACCENT)
            oy += 26
            fonts.draw(f'Best Depth: {self.char_mgr.best_depth}', px + 4, oy, 18, C_ACCENT)
            oy += 44

            fonts.draw('Erases all characters, account-wide vessel',
                       px + 4, oy, 15, C_DIM)
            oy += 20
            fonts.draw('unlocks, and delve progress. This cannot be undone.',
                       px + 4, oy, 15, C_DIM)
            oy += 30

            del_r = rl.Rectangle(px + 8, oy, PW - 16, 44)
            hv = _hov(del_r)
            rl.draw_rectangle_rec(del_r, rl.Color(70, 20, 20, 230) if hv else rl.Color(45, 16, 16, 230))
            rl.draw_rectangle_lines_ex(del_r, 1,
                                       rl.Color(170, 70, 70, 255) if hv else rl.Color(110, 50, 50, 255))
            del_txt = 'Delete Save'
            dt_w = fonts.measure(del_txt, 22)
            fonts.draw(del_txt, int(del_r.x + del_r.width // 2 - dt_w // 2),
                       int(del_r.y + (del_r.height - 22) // 2), 22,
                       rl.Color(255, 150, 150, 255) if hv else rl.Color(220, 120, 120, 255))
            if _click(del_r):
                self._confirm_delete_save = True

        if self._confirm_delete_save:
            self._draw_delete_save_confirm(cw, ch)

        # Settings saved toast
        if self._settings_toast_timer > 0:
            toast = "Settings saved"
            tw = fonts.measure(toast, 20) + 40
            th = 36
            tx = cw // 2 - tw // 2
            ty = ch - 80
            rl.draw_rectangle(tx, ty, tw, th, _c(0, 0, 0, 0x99))
            rl.draw_rectangle_lines(tx, ty, tw, th, C_ACCENT)
            tw = fonts.measure(toast, 20)
            fonts.draw(toast, cw // 2 - tw // 2, ty + 8, 20, C_GREEN)

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
        _text_shadow('Stash', _cx('Stash', 48, cw), 52, 48, C_GOLD_TEXT)
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
                _text_shadow(label, ix, iy, item_size, C_GOLD_HOVER)
                icons.draw(icon_name, ix - 28, iy + 2, 22, C_GOLD_HOVER)
            else:
                _text_shadow(label, ix, iy, item_size, C_GOLD_TEXT)
                icons.draw(icon_name, ix - 28, iy + 2, 22, C_GOLD_TEXT)

        hint = 'ESC to resume'
        fonts.draw(hint, _cx(hint, 15, cw), panel_y + panel_h - 22, 15, C_DIM)
