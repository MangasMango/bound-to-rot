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
Bound To Rot — main game state.
Diablo 2-style isometric: click-to-move, click-to-attack, melee combat.
"""

from config import ASSETS

import os
import math
import time
import copy
import random as _rnd
random = _rnd
import pyray as rl

from core.iso_engine import (IsoRenderer, IsoSprite, MOVE_DIR, DIRS, DIR_ANGLE,
                    angle_to_dir, MIN_SCALE, MAX_SCALE, ISO_W, ENTITY_BASE,
                    is_walkable)
from systems.audio import AudioSystem
from ui.inventory_ui import InventoryUI
from entities.progression import (Character, CharacterManager, RaidTracker, task_def,
                         compute_derived_stats)
from entities.descend import (compute_perk_bonuses, VESSEL_DEFS, VESSEL_UNLOCKS,
                     DESCEND_ATTRIBUTES, DESCEND_PERKS, ATTR_CAP,
                     increase_attribute, purchase_perk)
from ui.menus import MenuSystem, _btn, _KeyEdge
from entities.zombies import (update_zombies, DETECT_RANGE, MELEE_RANGE,
                              default_status_fields, enemy_evasion, make_move_speed)
from entities.player_stats import create_stats, update_stats, reset_stats
from systems.items import (make_inventory, add_to_stash, add_instance_to_stash,
                   grid_auto_place, grid_auto_place_instance, ITEMS, EQUIP_SLOT_LABELS,
                   INV_COLS, INV_ROWS, format_equip_stat)
import systems.itemgen as itemgen
from systems import frames
from systems import input as inp
import ui.fonts as fonts
import systems.combat as combat
import systems.abilities as abilities
import systems.gems as gems
import systems.currency as currency
import systems.flasks as flasks
import core.map_gen as map_gen
import ui.icons as icons
from systems.shaders import ShaderManager
from systems import lightgen
from systems import asset_guard

_ASSETS = ASSETS

def _sprite(subpath, name, n_frames, fps):
    base = os.path.join(_ASSETS, subpath)
    return IsoSprite(base, name, n_frames, fps)

# ── constants ─────────────────────────────────────────────────────────
# SCREEN_W / SCREEN_H (boot resolution) live in config.py — the window opens
# at this size and the game renders at whatever size the window currently is.
MAP_SIZE        = 50
FLAT_MAP        = [[0] * MAP_SIZE for _ in range(MAP_SIZE)]

MOVE_SPEED      = 4.0       # tiles / second (walk; R toggles the run gear).
                            # Native desert tiles are ~2.7x smaller on screen
                            # than the old LoP canvas — speed is scaled up to
                            # keep the old on-screen pace (1.5 * 2.72).
ATTACK_RANGE_BASE = 5.00     # tiles — gunslinger ranged auto-attack reach
                            # (boostable later via item affixes, see
                            # _attack_range()); BULLET_SPEED_TPS sets the
                            # tracer flight time (~0.25 s for the base range)
BULLET_SPEED_TPS = 20.0     # tiles / second — bullet flight speed

# Gunslinger knockback: enemies get shoved back along the shot line on a
# damaging hit. Impulse is the initial slide speed (tiles/s), decaying with
# KNOCKBACK_DECAY_TIME; item affixes add via the classic 'knockback' key.
KNOCKBACK_IMPULSE_TPS = 6.0
KNOCKBACK_DECAY_TIME  = 0.25
ATTACK_RATE     = 0.6       # attacks / second
ATTACK_DAMAGE   = 25
DEATH_DURATION  = 1.1       # seconds death anim plays before removal
RAID_DURATION   = 1800.0

# Skeleton kill drops — (item_id, min_count, max_count, chance)
SKELETON_DROP_TABLE = [
    ('lungs',         1, 1,  0.035),
    ('heart',         1, 1,  0.035),
    ('kidney',        1, 1,  0.020),
    ('intestine',     1, 1,  0.025),
    # QWER ability gems (issue #73 DESIGN PIVOT) — rare kills-only drops
    ('gem_blue',      1, 1,  0.010),
    ('gem_green',     1, 1,  0.010),
    ('gem_red',       1, 1,  0.008),
    ('gem_white',     1, 1,  0.006),
    # T-slot flasks (issue #73 ADDITION)
    ('flask_health',  1, 1,  0.012),
    ('flask_mana',    1, 1,  0.010),
    ('flask_utility', 1, 1,  0.008),
]
SLIME_DROP_TABLE = []
CLICK_MARKER_RADIUS = 0.03   # marker size as fraction of tile size (increase to make bigger)

# ── Angel form (R) ────────────────────────────────────────────────────
ANGEL_METER_MAX      = 100.0
ANGEL_METER_PER_KILL = 4.0     # base meter per kill
ANGEL_STREAK_WINDOW  = 4.0     # s between kills to keep the streak alive
ANGEL_METER_PER_CAST = 6.0     # meter per ability cast
ANGEL_FORM_DURATION  = 15.0    # s of angel form once triggered

# ── Kill streak HUD banner ────────────────────────────────────────────
STREAK_POP_TIME      = 1.6     # s the banner lingers after a chained kill
STREAK_POP_SECS      = 0.25    # scale-punch duration on a normal kill
STREAK_BIG_POP_SECS  = 0.45    # scale-punch duration on a milestone
STREAK_MILESTONE_SHAKE = 0.20  # s shake pulse on a milestone kill
STREAK_KILL_SHAKE      = 0.08  # s shake pulse on every chained kill
STREAK_LOST_FADE     = 0.9     # s fade-out of the "streak lost" sting
STREAK_MILESTONES    = {3: 'RAMPAGE', 5: 'SLAUGHTER',
                        8: 'UNSTOPPABLE', 10: "ANGEL'S FURY"}

# ── Enemy damage type progression ────────────────────────────────────────
# Damage types unlock gradually as enemy level rises so early-game combat
# stays physical and elemental variety appears in mid/late game.
_DMG_TYPE_WEIGHTS_BY_LEVEL = [
    # (max_level, {type: weight})   order: physical → magic → lightning → cold → fire → rot
    (10,  {'physical': 100}),
    (20,  {'physical': 80,  'magic': 20}),
    (35,  {'physical': 50,  'magic': 30,  'lightning': 20}),
    (50,  {'physical': 35,  'magic': 25,  'lightning': 25,  'cold': 15}),
    (70,  {'physical': 25,  'magic': 20,  'lightning': 20,  'cold': 20,  'fire': 15}),
    (999, {'physical': 15,  'magic': 15,  'lightning': 15,  'cold': 15,  'fire': 20,  'rot': 20}),
]

def _pick_enemy_dmg_type(enemy_level: float) -> str:
    level = int(enemy_level)
    for max_lv, weights in _DMG_TYPE_WEIGHTS_BY_LEVEL:
        if level <= max_lv:
            types = list(weights.keys())
            wvals = list(weights.values())
            return _rnd.choices(types, weights=wvals, k=1)[0]
    return 'physical'

def _is_enemy_immune(enemy: dict, dmg_type: str) -> bool:
    """Physical is never blocked — only elemental types grant immunity."""
    if dmg_type == 'physical':
        return False
    return enemy.get('dmg_type') == dmg_type

# ── game states ───────────────────────────────────────────────────────
STATE_MENU      = 'menu'
STATE_LOADING   = 'loading'
STATE_HUB       = 'hub'
STATE_PLAYING   = 'playing'
STATE_PAUSED    = 'paused'
STATE_DEAD      = 'dead'
STATE_EXTRACTED = 'extracted'
STATE_EDITOR    = 'editor'

HUB_SIZE = 3

# Tile paths connecting spawn (100,101) to the hub waypoints — absolute
# grid coords on the 200×200 sanctuary floor (the old 3×3-era cells drew
# the path sprites off in a far corner of the world).
_HUB_PATH_CELLS = frozenset({
    (100, 101), (100, 100), (100, 99), (100, 98), (100, 97), (100, 96),
    (99, 100), (98, 100), (97, 100), (96, 100),
    (101, 100), (102, 100), (103, 100), (104, 100),
})

# ── Sanctuary anchors on the 200×200 open floor (absolute grid coords) ──
# The hub feels infinite: only the torch-lit sanctuary is ever visible; the
# rest of the floor dissolves into darkness exactly like the delve. Spread
# for the native desert tile density (tiles are ~2.7× smaller on screen
# than the old LoP canvas, so waypoints need more world tiles between them).
HUB_SPAWN    = (100.5, 101.5)
_HEART_POS   = (100.5,  96.5)
_VENDOR_POS  = ( 96.5, 100.5)
_STASH_POS   = (104.5, 100.5)
_TORCH_POS   = (( 98.5,  96.5), (102.5,  96.5))
_BRAZIER_POS = (( 98.5, 102.5), (102.5, 102.5))

# ── interactable tuning knobs ──────────────────────────────────────
# CLICK_RADIUS  = how precisely your click must land on the art (tiles).
# INTERACT_RANGE = how close the player must walk to trigger (hub only).
# HOVER_GLOW_ALPHA = additive art re-draw strength on hover (sprite only).
HOVER_GLOW_ALPHA   = 50
HUB_CLICK_RADIUS   = 0.5
HUB_INTERACT_RANGE = 0.3
DELVE_CLICK_RADIUS = 0.2

# The hub waypoints. 'scale' matches the drawn entity size (labels
# anchor to the art's top edge); 'label_dy' fine-tunes label height.
_HUB_LAYOUT = [
    {'type': 'delve',  'x': _HEART_POS[0],   'y': _HEART_POS[1],
     'label': 'Enter the Anima', 'scale': 2.6, 'label_dy': 70,
     'color': (80, 200, 255, 255)},
    {'type': 'vendor', 'x': _VENDOR_POS[0],  'y': _VENDOR_POS[1],
     'label': 'Vendor', 'scale': 1.1, 'label_dy': 240,
     'color': (255, 200, 80, 255)},
    {'type': 'stash',  'x': _STASH_POS[0],   'y': _STASH_POS[1],
     'label': 'Stash', 'scale': 1.5, 'label_dy': 45,
     'color': (180, 180, 255, 255)},
]

# Torches & braziers keep the sanctuary lit; outside their pools the
# darkness is real (same ramp + DPS as the delve). 'kind' drives the
# flicker and tint of each light. 'ax'/'ay' = flame anchor offset from the
# tile anchor, in tile fractions (x-right, y-down) — desert-slot anchors:
# pillar-top fire bowls ('torch') and ground campfires ('brazier').
# Light radii are in world tiles; native desert tiles are ~2.7× smaller on
# screen than the old LoP canvas, so the constants are scaled up to keep
# the pre-swap pool sizes (darkness reach follows automatically).
# Light radii are in world tiles and mean the VISIBLE LIGHT EDGE (the
# lighting shader fades to ambient at exactly `r` — lighting.fs EDGE_SCALE).
# They are the pre-swap pool sizes scaled for the native desert tile density
# (~2.7x smaller tiles); the ×2.2 shader-edge compensation is baked in.
_HUB_LIGHTS = [
    {'x': _HEART_POS[0],            'y': _HEART_POS[1],        'r': 4.4, 'kind': 'heart',  'phase': 0.0, 'ax': -0.35, 'ay': 0.21},
    {'x': _TORCH_POS[0][0],         'y': _TORCH_POS[0][1],     'r': 4.0, 'kind': 'torch',  'phase': 0.0, 'ax': -0.01, 'ay': -0.55},
    {'x': _TORCH_POS[1][0],         'y': _TORCH_POS[1][1],     'r': 4.0, 'kind': 'torch',  'phase': 2.1, 'ax': -0.01, 'ay': -0.55},
    {'x': _BRAZIER_POS[0][0],       'y': _BRAZIER_POS[0][1],   'r': 4.8, 'kind': 'brazier','phase': 4.2, 'ax': -0.01, 'ay': -0.10},
    {'x': _BRAZIER_POS[1][0],       'y': _BRAZIER_POS[1][1],   'r': 4.8, 'kind': 'brazier','phase': 1.3, 'ax': -0.01, 'ay': -0.10},
]

DELVE_PULSE_SPEED  = 0.9   # tiles/sec baseline
DELVE_LIGHT_RADIUS   = 5.5   # tiles illuminated by the pulse (scaled for the
                             # native tile density — visual parity with the
                             # old 2.0-tile pool on the big LoP tiles)
DELVE_PERSONAL_LIGHT = 5.5   # player's own ambient radius (same compensation)
DELVE_DARKNESS_DPS   = 10.0  # HP/sec in full darkness at depth 1

# Manual placement offsets for the pulse light in render-texture pixels (1280x720 RT)
PULSE_OFFSET_X = 0
PULSE_OFFSET_Y = 0

# Ambient darkness level — 0 = pitch black, 60 = dim grey, 255 = fully lit
DARKNESS_AMBIENT = 10   # floor dim level: unlit scene multiplied by this/255
                        # — near pitch-black in the Hub AND the Anima (owner
                        # ruling 2026-10-07; light pools still carve out of it)
# Fire-light maps render at this fraction of screen size then upscale — the
# maps are smooth, so 0.5 is visually free and cuts shader fragments 4×.
LIGHT_RT_SCALE = 0.5
# Actors are redrawn above darkness, so retain only a small readability floor.
# 0.24 keeps silhouettes/eyes visible in true darkness while allowing the
# light map to produce a clear, genuine darkening; tune here if needed.
ACTOR_MIN_LIGHT_TINT = 0.24
# Python mirrors of the lighting.fs shaping consts — the actor-tint
# evaluator must stay in sync with the shader (FALL_RATE / CORE_RATE /
# EDGE_SCALE: the light radius is the VISIBLE LIGHT EDGE).
SHADER_FALL_RATE = 0.65
SHADER_CORE_RATE = 4.2
SHADER_EDGE_SCALE = 2.2
_LIGHT_KIND_STRENGTH = {'pulse': 0.75, 'heart': 0.52, 'brazier': 0.45, 'torch': 0.40}


def _actor_tint_value(light_amount: float) -> float:
    """Map the light map's 0..1 amount to an actor tint value."""
    return ACTOR_MIN_LIGHT_TINT + (1.0 - ACTOR_MIN_LIGHT_TINT) * light_amount


# Ground sprite shown for EVERY dropped item on the floor. Owner-reported
# issue: items were invisible until hovered. Per-item-type art comes later —
# swap this constant (or _drop_sprite_for) in one place when it does.
GROUND_ITEM_SPRITE = ('prop/desert/gold_drop', 'gold_drop')

_FALLBACK_CHAR = Character()


from core.render.hub_render import HubRenderMixin
from core.render.hud_render import HudRenderMixin
from core.render.delve_render import DelveRenderMixin
from core.render.chart_render import ChartRenderMixin
from core.render.frame_render import FrameRenderMixin
from core.render.weather_render import WeatherRenderMixin
from core.hub import HubMixin
from core.delve_flow import DelveFlowMixin
from core.input import InputMixin


class Game(InputMixin, HubMixin, DelveFlowMixin, HubRenderMixin, HudRenderMixin, DelveRenderMixin,
           ChartRenderMixin, WeatherRenderMixin, FrameRenderMixin):
    def __init__(self):
        self.state = STATE_MENU
        self.map   = None
        self.missing_assets = []   # filled in init() from asset_guard

        # Player position (tile col / row — floats for sub-tile movement)
        self.px = self.py = 0.0

        # D2-style state machine
        self.player_state  = 'idle'   # 'idle' | 'walk' | 'attack'
        self.player_facing = 'S'
        self.anim_time     = 0.0

        # Click-to-move destination
        self.dest_col: float | None = None
        self.dest_row: float | None = None

        # Auto-attack
        self.attack_target = None
        self.attack_cd     = 0.0

        # HUD action-bar flash timers (skill casts, potion drink, attack, move)
        self._hud_flash = {}
        self._hud_action_rects = {}

        # Stats
        self.stats     = create_stats()
        self.inventory = make_inventory()

        # Entities
        self.zombies = []

        # Timer
        self.raid_time    = 0.0
        self.raid_running = False

        # Wave escalation
        self._wave_num      = 0
        self._next_wave_t   = 30.0
        self._enemy_id_seq  = 0
        self._spawn_queue   = []   # list of 'skeleton' | 'slime' to drip-spawn
        self._spawn_timer   = 0.0  # countdown to next spawn from queue

        # Hub
        self._hub_objects          = []
        self._hub_pending_interact = None
        self._hub_lights           = []
        self._hub_dark_timer       = 0.0
        self._hub_popup            = None   # 'stash' | 'characters' | None

        # Shaders
        self.shaders         = None
        self._light_noise_tex = None
        self._light_curve_tex = None

        # Post-process pipeline
        self._scene_rt       = None
        self._ping_rt        = None
        self._post_rt_size   = (0, 0)
        self._pp_enabled     = True

        # Render canvas — recreated at the current window size (on resize too)
        self._virtual_rt      = None
        self._virtual_rt_size = (0, 0)

        # Per-effect toggles & params
        self._pp_bloom       = True
        self._pp_color       = True
        self._pp_wave        = 0.0
        self._pp_dream       = 0.0
        self._pp_gray        = 0.0
        self._pp_pixel       = 0.0
        self._pp_swirl       = 0.0

        # Color correction defaults
        self._pp_contrast    = 0.0
        self._pp_saturation  = 10.0
        self._pp_brightness  = -3.0

        # Bloom params
        self._bloom_samples  = 5.0
        self._bloom_quality  = 3.0
        self._bloom_threshold = 0.55
        self._bloom_intensity = 0.6

        # Swirl params
        self._swirl_radius   = 300.0
        self._swirl_angle    = 1.2

        # Dream params
        self._dream_strength = 10.0

        # Delve
        self._delve          = None   # active delve data dict, or None
        self._saved_delve    = None   # persistent delve state saved when returning to hub
        self._darkness_rt    = None   # RenderTexture2D for darkness compositing
        self._light_blob_tex = None   # pre-baked radial gradient for light sources
        self._lightmap_rt    = None   # low-res dim map (multiplied over scene)
        self._glow_rt        = None   # low-res fire glow (added over scene)
        self._light_rt_size  = (0, 0)

        # The historical black edge look came from darkness compositing, not
        # outline.fs. Keep the pass available for experimentation, but disabled
        # by default so it does not double-darken actors or alter UI/gameplay.
        self._pp_outline = False

        # Weather (rain + puddles) — render-only, see systems/weather.py
        self._weather_init()

        # HUD effects
        self.hit_flash = 0.0
        self._second_wind_cooldown = 0.0
        self._shake_timer     = 0.0
        self._shake_intensity = 0.0

        # Delve chart screen + in-delve minimap
        self._chart_screen  = None
        self._delve_chart_open = False  # transient; never saved with delve state
        self._minimap       = None
        self._minimap_open  = False
        self._chart_entry   = None   # (chart, node_id) selected in hub chart
        self._chart_resume  = False  # saved delve can be resumed
        self._chart_resume_rect = None

        # Organ ability state (keyed by organ slot)
        self._ability_cds  = {'lungs': 0.0, 'liver': 0.0}
        self._gem_cds      = {'Q': 0.0, 'W': 0.0, 'E': 0.0, 'R': 0.0}
        self._flask_cd     = 0.0
        self.flask_effects = []
        self._angel_meter  = 0.0
        self._angel_timer  = 0.0
        self._kill_streak  = 0
        self._last_kill_t  = -999.0
        self._streak_pop_t       = -999.0
        self._streak_milestone   = None
        self._streak_milestone_t = -999.0
        self._streak_lost_t      = -999.0
        self._lifesteal_timer  = 0.0
        self._lifesteal_pct    = 0.0
        self._fire_aura_timer  = 0.0
        self._fire_aura_radius = 0.0
        self._fire_aura_dps    = 0.0
        self._aura_tick        = 0.0

        # Click-to-move indicator
        self.click_marker = None  # {'col': f, 'row': f, 'timer': f}

        # Loading
        self._load_progress   = 0.0
        self._load_stage_text = "Initializing..."
        self._textures_loaded = False
        self._load_runner_spr = None
        self._load_steps      = None

        # Subsystems
        self.audio   = AudioSystem()
        self.inv     = InventoryUI()
        self.inv.char_provider = lambda: self.char
        self.inv.on_gear_change   = self._on_gear_changed
        self.ground_items = []
        self._loot_sparkles = []

        # Progression
        self.char_mgr      = CharacterManager()
        self.tracker       = RaidTracker()
        self._raid_results = None

        # Dev console
        self._console_open = False
        self._console_buf  = ''
        self._console_pending = []      # chars drained per render frame
        self._console_bs    = _KeyEdge()
        self._console_esc   = _KeyEdge()
        self._console_enter = _KeyEdge()
        self._console_log  = []
        self._console_history     = []
        self._console_history_idx = -1
        self._god_mode          = False
        self._char_stats_open   = False

        # Combat log
        self._combat_log      = []
        self._combat_log_open = False
        self._combat_log_scroll = 0

        # Level editor
        self._editor     = None
        self._custom_map = None

        # Menus
        self.menu_sys = MenuSystem(self.char_mgr)

        # Isometric renderer
        self.iso = IsoRenderer()

        # Player sprites — keyed by looks
        self._player_sprites = {}   # looks -> {'idle': spr, 'walk': spr, 'attack': spr}

        # World prop sprites
        self._pulse_tex            = None
        self._portal_frames        = []
        self._crate_spr            = None
        self._hub_subservient_spr  = None
        self._column_spr           = None
        self._torch_spr            = None
        self._crate_break_spr   = None
        self._barrel_spr        = None
        self._barrel_break_spr  = None
        self._brazier_spr       = None
        self._brazier_break_spr = None
        self._decor_sprs        = {}
        self._decor_items       = []
        self._gold_drop_spr   = None
        self._ability_icons   = {}  # ability_id -> Texture2D
        self._swoosh_effects  = []  # active: {'x','y','angle','timer','color'}
        self._dmg_numbers     = []  # active: {'x','y','timer','value','color'}
        self._vessel_unlock_timer = 0.0
        self._vessel_unlock_msg   = ''
        self._save_timer      = 0.0
        self._save_notice_timer = 0.0
        self._inv_full_timer  = 0.0
        self._glint_effects   = []  # active: {'x','y','timer','color','scale','vel_x','vel_y'}
        self._flame_effects   = []  # active: {'x','y','timer','color'}
        self._glow_effects    = []  # active: {'x','y','timer','color','scale'}
        self._bullets         = []  # flying shots: {'x','y','tx','ty','target',
                                    # 'result','timer'} — damage delivers on
                                    # arrival (bullet travel time)
        # Procedural VFX: 1x1 white quad drawn through the vfx_* shaders
        # (assets/shaders/vfx_*.fs) — no sprite strips to load.
        self._vfx_white       = None

        # Click-to-interact target (portal / crate)
        self.interact_target = None
        # Click-to-pickup target (drop item)
        self.drop_target = None

        # Screen-space rects of visible drop labels — populated each draw frame
        self._drop_label_rects = []
        self._hovered_ground_item = None
        # Interactable currently under the mouse (hub object or delve
        # portal/crate/barrel/brazier) — drives hover glow.
        self._hover_interact = None

        # Enemy sprites
        self._sk_idle   = None
        self._sk_walk   = None
        self._sk_attack = None
        self._sk_death  = None
        self._sl_idle   = None
        self._sl_walk   = None
        self._sl_death  = None
        self._vignette_tex = None
        self._ui           = {}

    @property
    def char(self):
        return self.char_mgr.active or _FALLBACK_CHAR

    def _current_item_level(self):
        """Item level for non-delve rolls; delve rewards use effective depth."""
        depth = self._delve.get('depth', 1) if self._delve else 1
        from core.delve_gen import effective_level
        return effective_level(max(1, depth))

    # ── startup ───────────────────────────────────────────────────────

    def init(self):
        from ui.menus import Settings
        self.missing_assets = asset_guard.missing_asset_folders()
        if self.missing_assets:
            print(f"[assets] {asset_guard.missing_notice(self.missing_assets)}")
        self.menu_sys.missing_assets = self.missing_assets
        _saved = Settings()
        _fn = getattr(_saved, 'font_name', 'Sancreek-Regular.ttf')
        _font_path = os.path.join(_ASSETS, 'fonts', _fn)
        if not os.path.exists(_font_path):
            _fn = 'Sancreek-Regular.ttf'
            _font_path = os.path.join(_ASSETS, 'fonts', _fn)
        if os.path.exists(_font_path):
            fonts.load(_font_path, fonts.CRISP_SIZES.get(_fn))
        self.audio.init_music()
        self.audio.set_music_state('menu')
        import ui.menus as _m
        _m._audio_ref = self.audio
        self.menu_sys._audio = self.audio

        _ui_dir = os.path.join(_ASSETS, 'ui')
        def _utex_m(name):
            p = os.path.join(_ui_dir, name)
            if not os.path.exists(p): return None
            t = rl.load_texture(p)
            rl.set_texture_filter(t, rl.TEXTURE_FILTER_POINT)
            return t
        self.menu_sys.panel_tex  = _utex_m('20251029darkDwellers9SlicesA.png')
        self.menu_sys.header_tex = _utex_m('20251117darkDwellersHeaderA.png')
        logo_path = os.path.join(_ASSETS, 'logo', 'logo.png')
        self.menu_sys.logo_tex = rl.load_texture(logo_path) if os.path.exists(logo_path) else None
        bg_path = os.path.join(_ASSETS, 'logo', 'background.jpg')
        self.menu_sys.bg_tex = rl.load_texture(bg_path) if os.path.exists(bg_path) else None
        hb_path = os.path.join(_ASSETS, 'ui', '20251117darkDwellersHeaderB.png')
        self.menu_sys.headerB_tex = rl.load_texture(hb_path) if os.path.exists(hb_path) else None

        anima_path = os.path.join(_ASSETS, 'ui', 'anima_panel.jpg')
        self._anima_panel_tex = rl.load_texture(anima_path) if os.path.exists(anima_path) else None

        _shaders_dir = os.path.join(_ASSETS, 'shaders')
        if os.path.isdir(_shaders_dir):
            self.shaders = ShaderManager(_shaders_dir)
            for sname, fsname in (('lighting', 'lighting.fs'),
                                  ('hit_flash', 'hit_flash.fs')):
                ok = self.shaders.load(sname, fsname)
                if ok is None:
                    print(f"[shader] '{sname}' failed to load — using software path")
                else:
                    print(f"[shader] '{sname}' loaded OK")
            if self.shaders.load_fragment('gloss', 'gloss.fs') is None:
                print("[shader] 'gloss' failed to load — using software fill")
            self._load_lighting_textures()

            # Post-process shaders
            _pp_shaders = (
                ('pp_bloom',    'pp_bloom.fs'),
                ('pp_dream',    'pp_dream.fs'),
                ('pp_pixelizer', 'pp_pixelizer.fs'),
                ('pp_swirl',    'pp_swirl.fs'),
            )
            for _sn, _fn in _pp_shaders:
                if self.shaders.load_fragment(_sn, _fn) is None:
                    print(f"[shader] '{_sn}' failed to load")
                else:
                    print(f"[shader] '{_sn}' loaded OK")

            _glsl_shaders = (
                ('pp_color',   'glsl330/color_correction.fs'),
                ('pp_wave',    'glsl330/wave.fs'),
                ('pp_gray',    'glsl330/grayscale.fs'),
                ('pp_outline', 'glsl330/outline.fs'),
            )
            for _sn, _fn in _glsl_shaders:
                if self.shaders.load_fragment(_sn, _fn) is None:
                    print(f"[shader] '{_sn}' failed to load")
                else:
                    print(f"[shader] '{_sn}' loaded OK")

            # Procedural combat VFX (replaces the old vfx sprite strips)
            _vfx_shaders = (
                ('vfx_swoosh', 'vfx_swoosh.fs'),
                ('vfx_glint',  'vfx_glint.fs'),
                ('vfx_flame',  'vfx_flame.fs'),
                ('vfx_glow',   'vfx_glow.fs'),
            )
            for _sn, _fn in _vfx_shaders:
                if self.shaders.load_fragment(_sn, _fn) is None:
                    print(f"[shader] '{_sn}' failed to load — effect disabled")
                else:
                    print(f"[shader] '{_sn}' loaded OK")
            self._vfx_white = rl.load_texture_from_image(
                rl.gen_image_color(1, 1, rl.WHITE))
        rl.show_cursor()

    def _load_lighting_textures(self):
        """Generated textures for the fire-light shader: tiling value noise
        + fire gradient LUT (systems/lightgen)."""
        import tempfile
        from PIL import Image
        self._light_noise_tex = None
        self._light_curve_tex = None
        for attr, arr in (('_light_noise_tex', lightgen.make_light_noise()),
                          ('_light_curve_tex', lightgen.make_fire_curve())):
            fd, path = tempfile.mkstemp(suffix='.png')
            os.close(fd)
            try:
                Image.fromarray(arr).save(path)
                tex = rl.load_texture(path)
            finally:
                try:
                    os.remove(path)
                except OSError:
                    pass
            if tex and tex.id > 0:
                if arr.shape[0] > 1:   # noise tiles — REPEAT sampling
                    rl.set_texture_wrap(tex, rl.TEXTURE_WRAP_REPEAT)
                else:                  # gradient LUT — CLAMP (uv.x=1 must
                    # read the LAST texel, never wrap to the dark texel 0)
                    rl.set_texture_wrap(tex, rl.TEXTURE_WRAP_CLAMP)
                setattr(self, attr, tex)
            else:
                print('[lightgen] texture generation failed — software fallback')

    # ── state machine ─────────────────────────────────────────────────

    def _start_loading(self):
        self.state            = STATE_LOADING
        self._load_progress   = 0.0
        self._textures_loaded = False
        self._load_steps      = None
        self.audio.set_music_state('off')   # no music during loading
        if self._load_runner_spr is None:
            # player running sprite for the loading screen — facing right
            self._load_runner_spr = _sprite('playable character/fighter/fighter_armed_walk',
                                            'fighter_armed_walk', 8, 22.0)
            self._load_runner_spr.load(dirs=('E',))
        rl.begin_drawing()
        rl.clear_background(rl.BLACK)
        rl.end_drawing()

    def _finish_loading(self):
        self._enter_hub()

    def _go_to_menu(self, sub='main'):
        self.state = STATE_MENU
        self.menu_sys.set_state(sub)
        self.audio.set_music_state('menu')

    def _go_to_pause(self):
        self._pre_pause_state = self.state
        self.state = STATE_PAUSED
        # Flush any stale menu signal (e.g. 'return_to_hub' from an old popup)
        # so opening the pause menu can't accidentally fire it mid-delve.
        self.menu_sys.signal()
        self.menu_sys.set_state('paused')

    def _apply_tarot_card(self, card_entry, card_src, card_idx, t_src, t_idx):
        """InventoryUI callback: apply a complete (4/4) tarot currency card
        to the clicked target slot (issue #73 phase B)."""
        arc = currency.arcana_of(card_entry.get('item', ''))
        if arc is None:
            return
        self._card_apply_target = (t_src, t_idx)
        result = currency.apply_card(self, arc, card_src, card_idx)
        self._card_apply_target = None
        cname = currency.CURRENCY_CARDS.get(arc, {}).get('name', 'Card')
        if result:
            self._log_combat(f"{cname}: {result}", 'info')
            if arc == 14:   # Temperance — rot cleanse changes live affixes
                self._on_gear_changed()
        else:
            self._log_combat(f"{cname}: cannot be applied there.", 'info')

    def _build_load_steps(self):
        steps = []
        add   = steps.append

        def _queue_attr(key, subpath, name, nframes, fps):
            holder = {}
            def _mk():
                holder['spr'] = _sprite(subpath, name, nframes, fps)
                setattr(self, key, holder['spr'])
            add(_mk)
            for d in DIRS:
                def _ld(d=d):
                    holder['spr'].load(dirs=(d,))
                add(_ld)

        def _iso():
            self.iso.load()
        add(_iso)

        for lk in ('warrior', 'fighter', 'knight'):
            def _looks(lk=lk):
                idle         = _sprite(f'playable character/{lk}/{lk}_armed_idle',   f'{lk}_armed_idle',   1,  1.0)
                walk         = _sprite(f'playable character/{lk}/{lk}_armed_walk',   f'{lk}_armed_walk',   8,  22.0)
                attack       = _sprite(f'playable character/{lk}/{lk}_armed_attack', f'{lk}_armed_attack', 8, 8 * ATTACK_RATE)
                default_idle = _sprite(f'playable character/{lk}/{lk}_default_idle', f'{lk}_default_idle', 1,  1.0)
                default_walk = _sprite(f'playable character/{lk}/{lk}_default_walk', f'{lk}_default_walk', 8,  22.0)
                self._player_sprites[lk] = {
                    'idle': idle, 'walk': walk, 'attack': attack,
                    'default idle': default_idle, 'default walk': default_walk,
                }
            add(_looks)
            for skey in ('idle', 'walk', 'attack', 'default idle', 'default walk'):
                for d in DIRS:
                    def _ld(lk=lk, skey=skey, d=d):
                        self._player_sprites[lk][skey].load(dirs=(d,))
                    add(_ld)

        _queue_attr('_sk_idle',   'enemy/skeleton/skeleton_default_idle',
                    'skeleton_default_idle',   8, 4.0)
        _queue_attr('_sk_walk',   'enemy/skeleton/skeleton_default_walk',
                    'skeleton_default_walk',   8, 16.0)
        _queue_attr('_sk_attack', 'enemy/skeleton/skeleton_default_attack',
                    'skeleton_default_attack', 8, 8.0)
        _queue_attr('_sk_death',  'enemy/skeleton/skeleton_special_death',
                    'skeleton_special_death',  8, 8.0)

        _queue_attr('_sl_idle',  'enemy/slime/slime_default_idle',
                    'slime_default_idle',  1, 1.0)
        _queue_attr('_sl_walk',  'enemy/slime/slime_default_walk',
                    'slime_default_walk',  8, 16.0)
        _queue_attr('_sl_death', 'enemy/slime/slime_special_death',
                    'slime_special_death', 7, 8.0)

        def _pulse_portal():
            # Pulse sprite (delve crawler)
            pulse_p = os.path.join(_ASSETS, 'pulse', 'pulse.png')
            if os.path.exists(pulse_p):
                self._pulse_tex = rl.load_texture(pulse_p)

            # Portal frames (flat, not directional)
            for i in range(1, 8):
                p = os.path.join(_ASSETS, 'portal', f'portal1_frame_{i}.png')
                if os.path.exists(p):
                    self._portal_frames.append(rl.load_texture(p))
        add(_pulse_portal)

        def _crate_static():
            self._crate_spr = _sprite('prop/desert/crate', 'crate', 1, 1.0)
            self._crate_spr.load()
        add(_crate_static)
        _queue_attr('_crate_break_spr', 'prop/desert/crate_break', 'crate_break', 8, 10.0)

        _queue_attr('_barrel_spr',        'prop/desert/barrel',        'barrel',        1,  1.0)
        _queue_attr('_barrel_break_spr',  'prop/desert/barrel_break',  'barrel_break',  8, 10.0)
        _queue_attr('_brazier_spr',       'prop/desert/brazier_lit',   'brazier_lit',   8,  8.0)
        _queue_attr('_brazier_break_spr', 'prop/desert/brazier_break', 'brazier_break', 8, 10.0)
        _queue_attr('_column_spr',        'prop/desert/column1',       'column1',       1,  1.0)
        _queue_attr('_torch_spr',         'prop/desert/torch',         'torch',         1,  1.0)
        _queue_attr('_hub_subservient_spr',
                    'none-playable character/subservient/subservient_special_working',
                    'subservient_special_working', 8, 6.0)

        def _decor():
            for dname in ('torch', 'bones1', 'bones2', 'bones3',
                          'cactus1', 'cactus2', 'reed1', 'reed2',
                          'bush_red', 'bush_red2', 'stone_s3', 'stone_s4',
                          'pole'):
                ds = _sprite(f'prop/desert/{dname}', dname, 1, 1.0)
                ds.load(dirs=('S', 'SE'))
                self._decor_sprs[dname] = ds
        add(_decor)

        _queue_attr('_gold_drop_spr', GROUND_ITEM_SPRITE[0], GROUND_ITEM_SPRITE[1], 8, 6.0)

        def _audio_inv():
            self.audio.init()
            self.inv.load()
            self.menu_sys.item_icons = self.inv._icons
        add(_audio_inv)

        def _ability_icons():
            icon_dir = os.path.join(_ASSETS, 'ability-icons')
            icon_map = [
                ('cone',      ['cone_physical', 'cone_fire', 'cone_cold',
                               'cone_lightning', 'cone_magic']),
                ('dash',      ['dash']),
                ('blink',     ['blink']),
                ('fire-aura', ['fire_aura']),
                ('lifesteal', ['lifesteal']),
            ]
            for filename, ability_ids in icon_map:
                p = os.path.join(icon_dir, f'{filename}.png')
                if os.path.exists(p):
                    tex = rl.load_texture(p)
                    for ability_id in ability_ids:
                        self._ability_icons[ability_id] = tex
        add(_ability_icons)

        def _filters():
            vignette_path = os.path.join(_ASSETS, 'gui', 'filter_vignette.png')
            self._vignette_tex = rl.load_texture(vignette_path) if os.path.exists(vignette_path) else None
        add(_filters)

        def _ui_tex():
            ui_dir = os.path.join(_ASSETS, 'ui')
            def _utex(name):
                p = os.path.join(ui_dir, name)
                if not os.path.exists(p):
                    return None
                t = rl.load_texture(p)
                rl.set_texture_filter(t, rl.TEXTURE_FILTER_POINT)
                return t
            self._ui = {
                'panel':       _utex('panel.png'),
                'bar_hp_fill': _utex('20251118darkDwellersBarC.png'),
                'bar_mp_fill': _utex('20251118darkDwellersBarA.png'),
                'bar_frame':   _utex('20251118darkDwellersBarD.png'),
                'slot_empty':  _utex('20251124emptyFrameA1-Sheet.png'),
                'header':      _utex('20251117darkDwellersHeaderA.png'),
                'compass':     _utex('20251125compass.png'),
                'circularvbar': _utex('circularvbar.png'),
                # New ARPG HUD assets
                'orb_panel':     _utex('orb_panel.png'),
                'orb_glass':     _utex('orb_glass.png'),
                'orb_fill0':     _utex('orb_fill_0.png'),
                'orb_fill1':     _utex('orb_fill_1.png'),
                'orb_mask':      _utex('orb_mask.png'),
                'orb_angel':     _utex('orb_angel.png'),
                'skill_base':    _utex('skill_base.png'),
                'belt_slot':     _utex('belt_slot.png'),
                'golden_frame':  _utex('golden_frame.png'),
                'seg_point':     _utex('stamina_point.png'),
                'button0':       _utex('button_0.png'),
                'button1':       _utex('button_1.png'),
                'button2':       _utex('button_2.png'),
                'button0p':      _utex('button_0_pressed.png'),
                'button1p':      _utex('button_1_pressed.png'),
                'button2p':      _utex('button_2_pressed.png'),
                'divider':       _utex('divider.png'),
                'active_action': _utex('active_action.png'),
            }
        add(_ui_tex)

        return steps

    def _handle_loading(self, dt):
        if not self._textures_loaded:
            if self._load_steps is None:
                self._load_steps = self._build_load_steps()
                self._load_total = max(1, len(self._load_steps))
            deadline = time.perf_counter() + 0.025
            while self._load_steps and time.perf_counter() < deadline:
                self._load_steps.pop(0)()
                self._load_progress = 1.0 - len(self._load_steps) / float(self._load_total)
            if not self._load_steps:
                self._textures_loaded = True
                self._load_progress   = 1.0
                self._finish_loading()

    def _handle_signal(self, sig):
        if sig == 'start_solo':
            self._start_loading()
        elif sig == 'start_game':
            self._enter_hub()
        elif sig == 'return_to_hub':
            self._enter_hub()
        elif sig == 'return_to_hub_delve':
            # Chart modal "RETURN TO HUB": bank the delve snapshot, then leave.
            self._exit_delve()
        elif sig == 'enter_delve':
            self._enter_delve()
        elif sig == 'resume':
            pre = getattr(self, '_pre_pause_state', STATE_PLAYING)
            self.state = pre
            if pre == STATE_HUB:
                self.audio.set_music_state('hub')
            else:
                if self._delve is not None:
                    self.audio.set_delve_music()   # playlist continues
                else:
                    self.audio.set_music_state('off')
            if hasattr(self, '_pre_pause_state'):
                del self._pre_pause_state
        elif sig == 'main_menu':
            self.char_mgr.save()
            self._go_to_menu('main')
        elif sig == 'quit':
            rl.close_window()

    # ── update ────────────────────────────────────────────────────────

    # ── hub ───────────────────────────────────────────────────────────

    def _build_hub_map(self):
        """The hub sits on the same 200×200 open floor as the delve — the
        world dissolves into darkness beyond the torch-lit sanctuary."""
        import core.delve_gen as _dg
        return [[0] * _dg.GRID_H for _ in range(_dg.GRID_W)]

    def _sync_weather(self, strength: float = None, seed: int = None,
                      depth: int = 0):
        """Roll weather + puddle placement for a freshly loaded level.

        strength None = roll from systems/weather with `seed` (+ depth ramp).
        Deterministic per level seed; render-only — no gameplay input.
        """
        from systems import weather as _weather
        if seed is None:
            seed = int(getattr(self.char, 'seed', 0)) ^ 0x57EA
        if strength is None:
            w = _weather.roll(seed, depth)
        else:
            w = {'raining': strength > 0.001, 'intensity': min(1.0, max(0.0, strength)), 'seed': seed}
        self.weather = w
        if w['raining']:
            self.iso.generate_puddles(self.map, _weather.puddle_strength(w['intensity']))
        else:
            self.iso.generate_puddles(self.map, 0.0)



    def _permadeath(self):
        """Death is permanent — delete the character (hub or delve)."""
        self.state = STATE_DEAD
        self.audio.set_music_state('death')
        self._saved_delve = None
        self._delve = None
        import entities.progression as _prog
        _prog.clear_delve_data(self.char.id)
        self._raid_results = {
            'kills':       self.tracker.kills,
            'time':        self.tracker.time,
            'loot':        self.tracker.loot,
            'extracted':   False,
            'completed':   [],
        }
        self.char_mgr.delete(self.char_mgr.active_idx)



    # ── delve ─────────────────────────────────────────────────────────












    def _recalc_derived_stats(self):
        """Recompute self.stats from character's current level and perks."""
        from entities.progression import compute_derived_stats
        bonuses = compute_perk_bonuses(
            self.char.perks, self.char.descend,
            item_bonuses=itemgen.aggregate_item_bonuses(self.inventory))
        # Item affixes can grant +X attribute, pushing beyond the point cap.
        # Pass only the attribute keys as item_bonuses so we don't double-count
        # the pct stats that game.py already applies directly via equip_effects.
        equip_b = self._equipped_bonuses()
        item_attr = {a: equip_b.get(a, 0) for a in DESCEND_ATTRIBUTES}
        derived = compute_derived_stats(
            self.char.descend, bonuses,
            item_bonuses=item_attr, looks=self.char.looks)
        reset_stats(self.stats, **derived)

    def _on_gear_changed(self):
        """Invalidate the cached derived stats after any loadout change.

        Equipping, unequipping, gem/flask socket changes and identification all
        change the item-sourced bonuses, and the allocation screen is gone, so
        every attribute now comes from gear. Without this, self.stats kept the
        pre-change values until the next raid start.
        """
        try:
            self._recalc_derived_stats()
        except Exception:
            pass



    # ── delve chart graph ────────────────────




    # ── flares & dynamite: REMOVED (owner decision) ───────────────────










    # ── delve relics (checkpoint shrines) ─────








    def _add_item_to_inventory(self, slot: dict):
        """Add a rolled item to character inventory using auto-placement."""
        from systems.items import grid_auto_place_instance
        inv = self.char.inventory
        if inv is None:
            return
        grid_tab = inv.get('equip', [])
        grid_auto_place_instance(grid_tab, slot)

    def _ensure_scene_rt(self, cw: int, ch: int):
        if self._post_rt_size == (cw, ch) and self._scene_rt is not None:
            return
        if self._post_rt_size != (0, 0):
            if self._scene_rt is not None:
                rl.unload_render_texture(self._scene_rt)
            if self._ping_rt is not None:
                rl.unload_render_texture(self._ping_rt)
        self._scene_rt = rl.load_render_texture(cw, ch)
        self._ping_rt = rl.load_render_texture(cw, ch)
        self._post_rt_size = (cw, ch)

    def _ensure_light_rts(self, cw: int, ch: int):
        """Low-res render targets for the fire-light passes: the dim map and
        the glow are pure light math (no scene dependency), so rendering them
        small and upscaling is visually free and much cheaper."""
        lw = max(1, int(cw * LIGHT_RT_SCALE))
        lh = max(1, int(ch * LIGHT_RT_SCALE))
        if (self._light_rt_size == (lw, lh)
                and self._lightmap_rt is not None and self._glow_rt is not None):
            return
        for attr in ('_lightmap_rt', '_glow_rt'):
            rt = getattr(self, attr, None)
            if rt is not None and rt.texture.id > 0:
                rl.unload_render_texture(rt)
            setattr(self, attr, rl.load_render_texture(lw, lh))
            # smooth upscale — the maps are soft gradients
            rl.set_texture_filter(getattr(self, attr).texture,
                                  rl.TEXTURE_FILTER_BILINEAR)
        self._light_rt_size = (lw, lh)

    def _rebind_outer_rt(self):
        """raylib's EndTextureMode always rebinds the *default* framebuffer —
        it does NOT return to an enclosing begin_texture_mode (nesting is
        unsupported). The virtual canvas (draw) wraps the state
        branches, so every inner scene-RT pair must re-open the outer target
        when it closes, or everything drawn after it lands on the window."""
        outer = getattr(self, '_outer_rt', None)
        if outer is not None:
            rl.begin_texture_mode(outer)

    def _apply_post_chain(self, cw: int, ch: int):
        if not self._pp_enabled or self.shaders is None:
            self._draw_scene_to_screen(cw, ch)
            return
        if self._scene_rt is None or self._scene_rt.texture.id == 0:
            return

        rt_a = self._scene_rt
        rt_b = self._ping_rt
        flip_src = rl.Rectangle(0.0, float(ch), float(cw), -float(ch))
        no_flip  = rl.Rectangle(0.0, 0.0, float(cw), float(ch))

        def _pass(shader_name):
            nonlocal rt_a, rt_b
            shader = self.shaders.get(shader_name)
            if shader is None:
                rt_a, rt_b = rt_b, rt_a  # maintain ping-pong even on skip
                return True  # signal: skipped
            rl.begin_texture_mode(rt_b)
            rl.clear_background(rl.Color(0, 0, 0, 255))
            rl.begin_shader_mode(shader)
            rl.draw_texture_pro(rt_a.texture, flip_src, no_flip, rl.Vector2(0.0, 0.0), 0.0, rl.WHITE)
            rl.end_shader_mode()
            rl.end_texture_mode()
            self._rebind_outer_rt()
            rt_a, rt_b = rt_b, rt_a
            return False  # signal: executed

        active_count = 0
        needs_scene_pass = True

        # Outline is deliberately the first post pass: it operates on the
        # completed world layer, before any screen-space effects. HUD and
        # overlays are drawn later, outside this chain.
        if self._pp_outline and self.shaders.has('pp_outline'):
            self.shaders.set_vec2('pp_outline', 'textureSize', float(cw), float(ch))
            self.shaders.set_float('pp_outline', 'outlineSize', OUTLINE_SIZE)
            from core.render.frame_render import _outline_color
            color = _outline_color(getattr(self, 'hit_flash', 0.0))
            self.shaders.set_vec4('pp_outline', 'outlineColor',
                                   color.r / 255.0, color.g / 255.0,
                                   color.b / 255.0, color.a / 255.0)
            _pass('pp_outline')
            active_count += 1
            needs_scene_pass = False

        if self._pp_color:
            self._pp_brightness = (self.menu_sys.settings.brightness / 100.0) * 10.0 - 5.0
            self.shaders.set_float('pp_color', 'contrast', self._pp_contrast)
            self.shaders.set_float('pp_color', 'saturation', self._pp_saturation)
            self.shaders.set_float('pp_color', 'brightness', self._pp_brightness)
            _pass('pp_color')
            active_count += 1
            needs_scene_pass = False

        if self._pp_bloom:
            self.shaders.set_vec2('pp_bloom', 'u_size', float(cw), float(ch))
            self.shaders.set_float('pp_bloom', 'u_samples', self._bloom_samples)
            self.shaders.set_float('pp_bloom', 'u_quality', self._bloom_quality)
            self.shaders.set_float('pp_bloom', 'u_threshold', self._bloom_threshold)
            self.shaders.set_float('pp_bloom', 'u_intensity', self._bloom_intensity)
            _pass('pp_bloom')
            active_count += 1
            needs_scene_pass = False

        if self._pp_wave > 0.001:
            self.shaders.set_vec2('pp_wave', 'size', float(cw), float(ch))
            self.shaders.set_float('pp_wave', 'seconds', self.raid_time)
            self.shaders.set_float('pp_wave', 'freqX', 20.0)
            self.shaders.set_float('pp_wave', 'freqY', 17.0)
            self.shaders.set_float('pp_wave', 'ampX', self._pp_wave * 8.0)
            self.shaders.set_float('pp_wave', 'ampY', self._pp_wave * 6.0)
            self.shaders.set_float('pp_wave', 'speedX', 6.0)
            self.shaders.set_float('pp_wave', 'speedY', 5.0)
            _pass('pp_wave')
            active_count += 1
            needs_scene_pass = False

        if self._pp_dream > 0.001:
            self.shaders.set_vec2('pp_dream', 'u_size', float(cw), float(ch))
            self.shaders.set_float('pp_dream', 'u_strength', self._dream_strength * self._pp_dream)
            _pass('pp_dream')
            active_count += 1
            needs_scene_pass = False

        if self._pp_gray > 0.001:
            _pass('pp_gray')
            active_count += 1
            needs_scene_pass = False

        if self._pp_pixel > 0.001:
            self.shaders.set_vec2('pp_pixelizer', 'u_size', float(cw), float(ch))
            pw = max(1.0, self._pp_pixel * 16.0)
            self.shaders.set_float('pp_pixelizer', 'u_pixel_w', pw)
            self.shaders.set_float('pp_pixelizer', 'u_pixel_h', pw)
            _pass('pp_pixelizer')
            active_count += 1
            needs_scene_pass = False

        if self._pp_swirl > 0.001:
            self.shaders.set_vec2('pp_swirl', 'u_size', float(cw), float(ch))
            cx = self._pp_swirl if self._pp_swirl >= 0 else float(cw) + self._pp_swirl
            self.shaders.set_vec2('pp_swirl', 'u_center', cx, float(ch * 0.5))
            self.shaders.set_float('pp_swirl', 'u_radius', self._swirl_radius)
            self.shaders.set_float('pp_swirl', 'u_angle', self._swirl_angle)
            _pass('pp_swirl')
            active_count += 1
            needs_scene_pass = False

        if active_count == 0:
            self._draw_scene_to_screen(cw, ch)
        else:
            rl.draw_texture_pro(rt_a.texture, flip_src, no_flip, rl.Vector2(0.0, 0.0), 0.0, rl.WHITE)


    def _ensure_light_blob(self):
        """Lazily generate a 256×256 white-centre radial gradient texture."""
        if self._light_blob_tex is not None and self._light_blob_tex.id > 0:
            return
        img = rl.gen_image_gradient_radial(256, 256, 1.0, rl.WHITE, rl.BLACK)
        self._light_blob_tex = rl.load_texture_from_image(img)
        rl.unload_image(img)



    def _light_anim(self, light):
        """(flicker factor, tint) per light kind — slow breathing, no strobe:
        torches ≈0.7 Hz, braziers ≈0.4 Hz, the Delve Heart a deep slow pulse."""
        t = rl.get_time()
        kind = light.get('kind', '')
        ph   = light.get('phase', 0.0)
        if kind == 'torch':
            f = 1.0 + 0.03 * math.sin(t * 4.4 + ph) + 0.02 * math.sin(t * 2.7 + ph * 1.7)
            tint = (255, 190, 120)
        elif kind == 'brazier':
            f = 1.0 + 0.025 * math.sin(t * 2.0 + ph) + 0.015 * math.sin(t * 3.4 + ph * 2.3)
            tint = (255, 195, 125)
        elif kind == 'pulse':
            f = 1.0 + 0.025 * math.sin(t * 2.2 + ph) + 0.015 * math.sin(t * 3.7 + ph * 2.1)
            tint = (255, 200, 130)
        elif kind == 'heart':
            f = 1.0 + 0.04 * math.sin(t * 1.4 + ph)
            tint = (255, 170, 110)
        else:
            f = 1.0
            tint = (255, 210, 140)
        return max(0.85, f), tint

    def _light_amount_at(self, lights, x_px: float, y_px: float,
                         cw: int, ch: int) -> float:
        """Light amount 0..1 at a screen point, mirroring the lighting
        shader's falloff (FALL_RATE fade + CORE_RATE core). Churn animation
        is skipped (≈ its mean), so this is the steady light level."""
        tile_size = max(1, int(ISO_W * self.iso.scale))
        step_x, step_y = self.iso._steps()
        iso_correction = math.hypot(step_x, step_y) / max(1, tile_size)
        aspect = step_y / max(1, step_x)
        half = tile_size * 0.5
        best = 0.0
        for L in lights[:8]:
            sx, sy = self.iso.world_to_screen(L['x'], L['y'], cw, ch)
            f, _t = self._light_anim(L)
            strength = _LIGHT_KIND_STRENGTH.get(L.get('kind', ''), 0.50)
            r_px = max(1.0, L['r'] * tile_size * iso_correction * f)
            lx = sx + half + L.get('ax', 0.0) * tile_size
            ly = sy + half + L.get('ay', 0.0) * tile_size
            dx = (x_px - lx) * aspect
            dy = y_px - ly
            # mirror the shader's edge-radius semantics (lighting.fs)
            dd = math.hypot(dx, dy) / r_px * SHADER_EDGE_SCALE
            power = min(strength * 2.2, 1.0)
            l = min((math.exp(-dd * dd * SHADER_FALL_RATE)
                     + math.exp(-dd * dd * 10.0) * 0.3) * power, 1.0) \
                + math.exp(-dd * dd) * 0.03 * power
            shaped = min(l, 0.75) + 0.25 * math.exp(-dd * dd * SHADER_CORE_RATE)
            best = max(best, shaped)
        return best

    def _actor_tint(self, lights, x_px: float, y_px: float,
                    cw: int, ch: int) -> rl.Color:
        """Greyscale sprite tint: full brightness inside pools, with a small
        low-light floor so actors remain playable silhouettes in gloom."""
        shaped = self._light_amount_at(lights, x_px, y_px, cw, ch)
        v = _actor_tint_value(shaped)
        c = int(round(v * 255.0))
        return rl.Color(c, c, c, 255)

    # ── HUD action-bar helpers ────────────────────────────────────────

    def _hud_over_action(self, mx: int, my: int) -> bool:
        """True when the cursor is over a clickable HUD action control —
        world clicks must not fire through them."""
        for rect in getattr(self, '_hud_action_rects', {}).values():
            if (rect.x <= mx < rect.x + rect.width
                    and rect.y <= my < rect.y + rect.height):
                return True
        return False

    def _hud_click_attack(self, mx: int, my: int):
        """HUD attack button — same as a world left-click on an enemy."""
        cw, ch = rl.get_screen_width(), rl.get_screen_height()
        enemy = self._find_enemy_near(mx, my, cw, ch)
        if enemy is not None:
            self.attack_target   = enemy
            self.interact_target = None
            self.drop_target     = None
            self.dest_col = self.dest_row = None
            self.click_marker    = None
            self._flash_hud('attack')

    def _hud_click_move(self, mx: int, my: int):
        """HUD move button — same as a world right-click move order."""
        cw, ch = rl.get_screen_width(), rl.get_screen_height()
        tile_col, tile_row = self.iso.screen_to_world(mx, my, cw, ch)
        if math.hypot(tile_col - self.px, tile_row - self.py) >= 0.1:
            tc, tr = int(tile_col), int(tile_row)
            is_wall = (0 <= tc < len(self.map) and 0 <= tr < len(self.map[0])
                       and self.map[tc][tr] != 0) if self.map else False
            if is_wall:
                self.click_marker = {'col': tile_col, 'row': tile_row,
                                     'timer': 0.3, 'blocked': True}
            else:
                self.dest_col        = tile_col
                self.dest_row        = tile_row
                self.attack_target   = None
                self.interact_target = None
                self.drop_target     = None
                self.click_marker = {'col': tile_col, 'row': tile_row,
                                     'timer': 0.6}
                self._flash_hud('move')

    def _flash_hud(self, key: str, dur: float = 0.4):
        self._hud_flash[key] = dur

    def _tick_hud_flash(self, dt: float):
        for k in list(self._hud_flash):
            self._hud_flash[k] -= dt
            if self._hud_flash[k] <= 0:
                del self._hud_flash[k]















    def _wrap_text(self, text: str, width: int) -> list:
        """Wrap a string into lines of at most `width` characters."""
        if not text:
            return []
        words = text.split()
        lines = []
        current = ''
        for word in words:
            candidate = f"{current} {word}".strip()
            if len(candidate) <= width:
                current = candidate
            else:
                if current:
                    lines.append(current)
                current = word
        if current:
            lines.append(current)
        return lines

    def _get_item_summary_lines(self, slot: dict) -> list:
        """Return [(text, color), ...] summary lines for one item slot."""
        item_id = slot['item']
        idef = ITEMS.get(item_id, {})
        inst  = slot.get('instance_data')

        rar_map = {0: rl.Color(200, 200, 200, 255),
                   1: rl.Color(120, 220, 120, 255),
                   2: rl.Color(100, 160, 255, 255),
                   3: rl.Color(190, 120, 255, 255),
                   4: rl.Color(255, 190, 80, 255)}
        rarity_c = rar_map.get(inst.get('rarity', 0) if inst else 0, rl.Color(200, 200, 200, 255))

        lines = []
        unid = inst is not None and not itemgen.is_identified(slot)
        inst_for_title = None if unid else inst
        title = inst_for_title['display_name'] if inst_for_title else idef.get('name', item_id)
        count = slot.get('count', 1)
        if count > 1 and not idef.get('equipSlot'):
            title = f"{title} x{count}"
        lines.append((title, rarity_c))

        if inst:
            if unid:
                lines.append(("Unidentified", rl.Color(190, 160, 90, 220)))
            else:
                ilvl = inst.get('ilvl', 0)
                lines.append((f"iLvl {ilvl}", rl.Color(130, 140, 160, 200)))

                if inst.get('ability'):
                    import systems.abilities as _abs
                    ab = _abs.ABILITIES.get(inst['ability'], {})
                    lines.append((f"[{ab.get('label', inst['ability'])}]", rarity_c))
                import systems.itemgen
                for afline in itemgen.affix_lines(inst):
                    lines.append((afline, rl.Color(200, 180, 140, 200)))

        if not unid:
            if not inst and idef.get('equip'):
                for k, v in idef['equip'].items():
                    lines.append((format_equip_stat(k, v), rl.Color(150, 180, 220, 200)))
            for k, v in (idef.get('use') or {}).items():
                lines.append((f"Use: +{v} {k}", rl.Color(180, 180, 200, 200)))

        return lines

    # ── Anima panel — the 500x500 framed popup that hosts every node
    #    chooser (hub chart, junction paths, cart boons) ─────────────────

    ANIMA_PANEL_SIZE  = 500   # matches anima_panel.jpg
    ANIMA_PANEL_INSET = 30    # content inset inside the woven border

    def _anima_layout(self, cw, ch):
        """Centered panel position + inner content rect."""
        size = self.ANIMA_PANEL_SIZE
        px = cw // 2 - size // 2
        py = ch // 2 - size // 2
        inset = self.ANIMA_PANEL_INSET
        content = rl.Rectangle(float(px + inset), float(py + inset),
                               float(size - 2 * inset), float(size - 2 * inset))
        return px, py, content



    def _update_game(self, dt):
        cw = rl.get_screen_width()
        ch = rl.get_screen_height()

        # ── raid timer & wave escalation ─────────────────────────────
        if self.raid_running:
            self.raid_time += dt
            if self.raid_time >= self._next_wave_t:
                self._trigger_wave()
        self._drain_spawn_queue(dt)

        # Auto-save every 30s during gameplay
        self._save_timer += dt
        if self._save_timer >= 30.0:
            self._save_timer = 0.0
            self.char_mgr.save()
            self._save_notice_timer = 2.0

        # ── delve-specific logic ──────────────────────────────────────
        if self._delve is not None:
            self._update_delve(dt)
            if self.state != STATE_PLAYING:
                return

        # ── ability cooldowns & buffs ─────────────────────────────────
        for k in self._ability_cds:
            self._ability_cds[k] = max(0.0, self._ability_cds[k] - dt)
        for k in self._gem_cds:
            self._gem_cds[k] = max(0.0, self._gem_cds[k] - dt)
        self._flask_cd = max(0.0, self._flask_cd - dt)
        self._second_wind_cooldown = max(0.0, self._second_wind_cooldown - dt)
        # Flask effects (T slot): regen over time + timed haste multiplier
        self._flask_haste_mult = flasks.tick_flask_effects(
            {'flask_effects': self.flask_effects}, self.stats, dt)
        if self._lifesteal_timer > 0:
            self._lifesteal_timer = max(0.0, self._lifesteal_timer - dt)
        if self._fire_aura_timer > 0:
            self._fire_aura_timer = max(0.0, self._fire_aura_timer - dt)
        if self._angel_timer > 0:
            self._angel_timer = max(0.0, self._angel_timer - dt)

        # Streak window expiry — sting for lost 3+ streaks
        if (self._kill_streak >= 3
                and rl.get_time() - self._last_kill_t > ANGEL_STREAK_WINDOW):
            self._streak_lost_t = rl.get_time()
            self._kill_streak   = 0
        # ── stats ─────────────────────────────────────────────────────
        equip_effects = self._equipped_bonuses()
        moving  = (self.dest_col is not None) or (self.attack_target is not None)
        stat_out = update_stats(self.stats, dt, moving=moving)
        speed_mult = stat_out['speed_mult'] * (1.0 + equip_effects['move_speed'])
        speed_mult *= getattr(self, '_flask_haste_mult', 1.0)   # utility flask (T)
        # Fracture zone: slowed while standing in darkness (Frozen Hollow, §5)
        if (self._delve is not None and self._delve.get('_dark_slow')
                and 'juggernaut' not in itemgen.equipped_uniques(self.inventory)):
            speed_mult *= (1.0 - self._delve['_dark_slow'])
        if self._delve is not None:
            speed_mult *= self._relic_effects().get('speed_mult', 1.0)

        # ── apply flat equipment stat bonuses ─────────────────────────
        s = self.stats
        base_hp = s.get('_base_max_health', s['max_health'])
        new_max_hp = base_hp + equip_effects['max_health']
        # Percentage max health bonus from gear (e.g. Vigorous affix)
        if equip_effects['max_health_pct'] > 0:
            new_max_hp = int(new_max_hp * (1.0 + equip_effects['max_health_pct']))
        if new_max_hp != s['max_health']:
            pct = s['health'] / max(1, s['max_health'])
            s['max_health'] = new_max_hp
            s['health'] = min(s['max_health'], s['max_health'] * pct)
        base_ev = s.get('_base_evasion', s['evasion'])
        s['evasion'] = base_ev + equip_effects['evasion']

        # ── mouse dispatch: move / attack / interact / pickup ──────────
        if self._dispatch_game_mouse_input(cw, ch):
            return


        # ── click marker decay ────────────────────────────────────────
        self._tick_hud_flash(dt)
        if self.click_marker:
            self.click_marker['timer'] -= dt
            if self.click_marker['timer'] <= 0:
                self.click_marker = None

        # ── attack cooldown ───────────────────────────────────────────
        self.attack_cd = max(0.0, self.attack_cd - dt)

        # ── auto-acquire nearest enemy when idle ──────────────────────
        if self.attack_target is None and self.dest_col is None:
            self.attack_target = self._nearest_enemy(
                self._attack_range(equip_effects.get('attack_range', 0.0)))

        # ── resolve auto-attack or movement ───────────────────────────
        if self.attack_target is not None:
            if self.attack_target['health'] <= 0:
                self.attack_target = None
            else:
                tx, ty = self.attack_target['x'], self.attack_target['y']
                dist   = math.hypot(tx - self.px, ty - self.py)
                if dist > self._attack_range(equip_effects.get('attack_range', 0.0)):
                    self._walk_toward(tx, ty, dt, speed_mult)
                else:
                    self.dest_col = self.dest_row = None
                    self.player_state  = 'attack'
                    self.player_facing = self._dir_to(tx - self.px, ty - self.py)
                    if self.attack_cd <= 0:
                        atk_speed = (self.stats.get('_attack_speed_pct', 0.0)
                                     + equip_effects['attack_speed_pct'])
                        self.attack_cd = frames.attack_seconds(
                            frames.PLAYER_BASE_ATTACK_FRAMES, atk_speed)
                        self._fire_bullet(self.attack_target, equip_effects)

        elif self.dest_col is not None:
            self._walk_toward(self.dest_col, self.dest_row, dt, speed_mult)
        else:
            self.player_state = 'idle'

        self.anim_time = (self.anim_time + dt) % 100.0

        # ── interact target: walk until in range, then trigger ────────
        if self.interact_target is not None:
            t = self.interact_target
            dist = math.hypot(t['x'] - self.px, t['y'] - self.py)
            if dist < 0.65:
                self.dest_col = self.dest_row = None
                if t.get('type') == 'portal':
                    if t.get('delve_exit') and self._delve is not None:
                        self._exit_delve('hub')
                    else:
                        self.tracker.extracted = True
                        self._raid_results = self.tracker.finalize(self.char)
                        self.raid_running = False
                        self.audio.set_music_state('off')   # silence on the results screen
                        self.state = STATE_EXTRACTED
                self.interact_target = None

        # ── click-to-pickup: arrive at drop_target then pick it up ──────
        if self.drop_target is not None:
            dt_gi = self.drop_target
            if dt_gi not in self.ground_items or not dt_gi.get('items'):
                self.drop_target = None
            else:
                dist = math.hypot(dt_gi['x'] - self.px, dt_gi['y'] - self.py)
                if dist < 0.65:
                    self.dest_col = self.dest_row = None
                    for item in dt_gi['items']:
                        self._auto_place(item)
                    self.tracker.loot += 1
                    if dt_gi in self.ground_items:
                        self.ground_items.remove(dt_gi)
                    self.drop_target = None

        # ── loot sparkle decay ──────────────────────────────────────────
        for s in self._loot_sparkles:
            s['timer'] -= dt
        self._loot_sparkles = [s for s in self._loot_sparkles if s['timer'] > 0]

        # ── enemy updates ─────────────────────────────────────────────
        damage_reduction     = equip_effects['damage_reduction']
        flat_damage_reduction = equip_effects['flat_damage_reduction']
        block_chance = min(0.75, self.stats.get('block_chance', 0.0)
                           + equip_effects['block_chance'])
        player_ref = {'x': self.px, 'y': self.py,
                      'evasion': self.stats['evasion'],
                      'entropy_grace_pct': self.stats.get('entropy_grace_pct', 0.0)}
        players = [player_ref]
        incoming_dmg_by_type = update_zombies(dt, self.zombies, players, self.map)
        total_incoming = sum(incoming_dmg_by_type.values())
        if total_incoming > 0 and not self._god_mode:
            for dmg_type, amount in incoming_dmg_by_type.items():
                if amount > 0:
                    self._apply_damage(amount, dmg_type, damage_reduction,
                                       flat_damage_reduction, block_chance)
                    self._log_combat(f"Took {int(amount)} {dmg_type} dmg", 'dmg_taken')
            self._spawn_dmg_number(self.px, self.py - 0.4,
                                   int(total_incoming), color=rl.Color(255, 60, 60, 255))
            self.hit_flash = 0.5
            self._pp_wave   = max(self._pp_wave, 0.4)
            self.audio.zombie_attack_sound()

        self._tick_ability_buffs(dt)

        # Advance and cull swoosh effects
        _SWOOSH_DUR = 8 / 22.0
        live = []
        for e in self._swoosh_effects:
            e['timer'] += dt
            if e['timer'] < _SWOOSH_DUR:
                live.append(e)
        self._swoosh_effects = live

        # Advance and cull glint effects
        _GLINT_DUR = 8 / 18.0
        live = []
        for e in self._glint_effects:
            e['timer'] += dt
            e['x'] += e.get('vel_x', 0.0) * dt
            e['y'] += e.get('vel_y', 0.0) * dt
            if e['timer'] < _GLINT_DUR:
                live.append(e)
        self._glint_effects = live

        # Advance and cull flame effects
        _FLAME_DUR = 8 / 12.0
        live = []
        for e in self._flame_effects:
            e['timer'] += dt
            if e['timer'] < _FLAME_DUR:
                live.append(e)
        self._flame_effects = live

        # Advance and cull damage numbers
        _DMG_NUM_DUR = 1.2
        live = []
        for n in self._dmg_numbers:
            n['timer'] += dt
            if n['timer'] < _DMG_NUM_DUR:
                live.append(n)
        self._dmg_numbers = live

        # Advance and cull glow effects
        _GLOW_DUR = 0.35
        live = []
        for e in self._glow_effects:
            e['timer'] += dt
            if e['timer'] < _GLOW_DUR:
                live.append(e)
        self._glow_effects = live

        # Advance flying bullets — light homing toward the (living) target;
        # deliver the pre-rolled hit on arrival, fizzle if the target died.
        live_b = []
        for b in self._bullets:
            t = b.get('target')
            if t is not None and t.get('health', 0) > 0:
                b['tx'], b['ty'] = t['x'], t['y']
            dx = b['tx'] - b['x']
            dy = b['ty'] - b['y']
            dist = math.hypot(dx, dy)
            step = BULLET_SPEED_TPS * dt
            if dist <= max(0.15, step):
                b['x'], b['y'] = b['tx'], b['ty']
                self._spawn_glow(b['tx'], b['ty'], scale=0.7,
                                 color=rl.Color(255, 240, 180, 255))
                self._deliver_player_shot(b)
                continue
            b['x'] += dx / dist * step
            b['y'] += dy / dist * step
            live_b.append(b)
        self._bullets = live_b

        # Advance death timers; cull finished corpses
        for z in self.zombies:
            if z['health'] <= 0:
                z['death_timer'] = z.get('death_timer', 0.0) + dt
        self.zombies = [z for z in self.zombies
                        if z.get('death_timer', 0.0) < DEATH_DURATION]

        # Post-process effect decay
        self._pp_wave  = max(0.0, self._pp_wave - dt * 3.0)
        self._pp_dream = max(0.0, self._pp_dream - dt * 2.0)
        self._pp_gray  = max(0.0, self._pp_gray - dt * 2.0)

        self.hit_flash = max(0.0, self.hit_flash - dt * 2)
        self._shake_timer = max(0.0, self._shake_timer - dt)
        if self._shake_timer <= 0:
            self._shake_intensity = 0.0
        self._vessel_unlock_timer = max(0.0, self._vessel_unlock_timer - dt)
        self._save_notice_timer = max(0.0, self._save_notice_timer - dt)
        self._inv_full_timer = max(0.0, self._inv_full_timer - dt)

        # Sync post-process effects to game state
        self._pp_wave = max(self._pp_wave, self._shake_intensity * 0.3)

        if self._delve is not None:
            d_dist = math.hypot(self.px - self._delve['pulse_x'], self.py - self._delve['pulse_y'])
            if d_dist > self._delve.get('light_r', 3.0):
                darkness_pct = min(1.0, (d_dist - self._delve['light_r']) / 4.0)
                self._pp_dream = max(self._pp_dream, darkness_pct * 0.6)

        hp_pct = self.stats['health'] / max(1, self.stats['max_health'])
        if hp_pct < 0.35:
            self._pp_gray = max(self._pp_gray, (0.35 - hp_pct) * 2.0)


        # ── tracker ───────────────────────────────────────────────────
        self.tracker.time = self.raid_time
        self.tracker.check_tasks(self.char)

        if self.stats['health'] <= 0 and not self._god_mode:
            self._permadeath()
            return

        self.audio.update(dt, self.zombies, self.player_state == 'walk', False)

    # ── movement helpers ──────────────────────────────────────────────

    def _walk_toward(self, tx: float, ty: float, dt: float, speed_mult: float):
        dx   = tx - self.px
        dy   = ty - self.py
        dist = math.hypot(dx, dy)

        if dist < 0.08:
            if self.dest_col is not None:
                self.px, self.py  = self.dest_col, self.dest_row
                self.dest_col = self.dest_row = None
                self.click_marker = None
            self.player_state = 'idle'
            return

        move_step = min(MOVE_SPEED * speed_mult * dt, dist)
        new_x = self.px + dx / dist * move_step
        new_y = self.py + dy / dist * move_step

        if not is_walkable(self.map, int(new_x), int(new_y)):
            self.dest_col = self.dest_row = None
            self.click_marker = None
            self.player_state = 'idle'
            return

        self.px = new_x
        self.py = new_y

        self.player_state  = 'walk'
        self.player_facing = self._dir_to(dx, dy)

    def _dir_to(self, dx: float, dy: float) -> str:
        """World-space delta (col, row) → compass direction name."""
        screen_x = dx - dy          # project onto iso screen x
        screen_y = dx + dy          # project onto iso screen y
        angle = math.degrees(math.atan2(-screen_y, screen_x))
        return angle_to_dir(angle)

    def _find_enemy_near(self, mx: int, my: int, cw: int, ch: int):
        # enemy hitboxes ride the ENTITY canvas scale, matching their art
        tile_size   = int(ISO_W * self.iso.scale)
        ent_px      = ENTITY_BASE * self.iso.scale
        hitbox_w    = ent_px * 0.38
        hitbox_h    = ent_px * 0.45
        best, best_dist = None, float('inf')
        for z in self.zombies:
            if z['health'] <= 0:
                continue
            sx, sy = self.iso.world_to_screen(z['x'], z['y'], cw, ch)
            center_x = sx + tile_size / 2
            center_y = sy + tile_size / 2
            dx = abs(mx - center_x)
            dy = abs(my - center_y)
            if dx <= hitbox_w and dy <= hitbox_h:
                dist = math.hypot(dx, dy)
                if dist < best_dist:
                    best_dist = dist
                    best = z
        return best

    def _find_interact_object(self, tile_col: float, tile_row: float, radius: float = 1.5):
        """Nearest interactable ground item (portals; the breakable containers
        were removed with the dead cabinet/loot pipeline)."""
        best, best_d = None, radius
        for gi in self.ground_items:
            if gi.get('type') != 'portal':
                continue
            d = math.hypot(gi['x'] - tile_col, gi['y'] - tile_row)
            if d < best_d:
                best_d, best = d, gi
        return best

    def _hover_interactable(self, objects, radius: float, cw: int, ch: int):
        """Nearest interactable under the mouse, within `radius` tiles.

        `objects` is a list of dicts with world-position keys 'x'/'y'
        (hub objects and delve ground-item interactables share the shape).
        Purely visual — no player-distance check; the hover glow means
        "the art is under your cursor", not "you can use it yet".
        """
        if self.inv.open or self._hub_popup or self._delve_chart_is_open():
            return None
        mx, my = rl.get_mouse_x(), rl.get_mouse_y()
        tile_col, tile_row = self.iso.screen_to_world(mx, my, cw, ch)
        best, best_d = None, radius
        for obj in objects:
            d = math.hypot(obj['x'] - tile_col, obj['y'] - tile_row)
            if d < best_d:
                best_d, best = d, obj
        return best



    def _attack_range(self, extra: float = 0.0) -> float:
        """Ranged auto-attack reach in tiles: base + item/equip bonus."""
        return max(1.0, ATTACK_RANGE_BASE + extra)

    def _nearest_enemy(self, max_range: float):
        best, best_d = None, max_range
        for z in self.zombies:
            if z['health'] <= 0:
                continue
            d = math.hypot(z['x'] - self.px, z['y'] - self.py)
            if d < best_d:
                best, best_d = z, d
        return best

    def _get_enemy_level(self):
        """Exponential difficulty curve: level 1 at t=0, level 100 at t=30min."""
        return 1 + 99 * (self.raid_time / RAID_DURATION) ** 2

    def _enemy_hp(self, base):
        etype = 'slime' if base >= 150.0 else 'skeleton'
        return self._enemy_max_health(etype, self._get_enemy_level())



    def _spawn_enemies(self, center_col, center_row, count=6, min_r=4, max_r=10):
        enemy_level = self._get_enemy_level()
        acc         = combat.skeleton_accuracy(int(enemy_level))
        base_hp     = self._enemy_hp(100.0)
        mit         = self._enemy_mitigation(enemy_level)
        _map        = self.map
        enemies     = []
        for i in range(count):
            for _ in range(120):
                angle = random.uniform(0, math.tau)
                dist  = random.uniform(min_r, max_r)
                x = center_col + math.cos(angle) * dist
                y = center_row + math.sin(angle) * dist
                tile_col, tile_row = int(x), int(y)
                if 0 <= tile_col < MAP_SIZE and 0 <= tile_row < MAP_SIZE and _map[tile_col][tile_row] == 0:
                    enemies.append({
                        'id':               f'sk{i}',
                        'enemy_type':       'skeleton',
                        'level':            int(enemy_level),
                        'x':                x,
                        'y':                y,
                        'health':           base_hp,
                        'max_health':       base_hp,
                        'state':            'idle',
                        'anim_timer':       0.0,
                        'frame':            0,
                        'facing_x':         1.0,
                        'facing_y':         0.0,
                        'accuracy':         acc,
                        'evasion':          enemy_evasion('skeleton', enemy_level),
                        'spawn_x':          x,
                        'spawn_y':          y,
                        'move_speed':       make_move_speed('skeleton'),
                        'speed_ramp':       0.0,
                        'dmg_type':         _pick_enemy_dmg_type(enemy_level),
                        'damage_reduction': mit['damage_reduction'],
                        'resist_pct':       dict(mit['resist_pct']),
                        **default_status_fields(),
                    })
                    break
        return enemies

    def _spawn_slimes(self, center_col, center_row, count=4, min_r=6, max_r=14):
        enemy_level = self._get_enemy_level()
        _map        = self.map
        slime_hp    = self._enemy_hp(150.0)
        mit         = self._enemy_mitigation(enemy_level)
        slime_acc   = int(combat.skeleton_accuracy(int(enemy_level)) * 0.8)
        slimes      = []
        for i in range(count):
            for _ in range(120):
                angle = random.uniform(0, math.tau)
                dist  = random.uniform(min_r, max_r)
                x = center_col + math.cos(angle) * dist
                y = center_row + math.sin(angle) * dist
                tile_col, tile_row = int(x), int(y)
                if 0 <= tile_col < MAP_SIZE and 0 <= tile_row < MAP_SIZE and _map[tile_col][tile_row] == 0:
                    slimes.append({
                        'id':               f'sl{i}',
                        'enemy_type':       'slime',
                        'level':            int(enemy_level),
                        'x':                x,
                        'y':                y,
                        'health':           slime_hp,
                        'max_health':       slime_hp,
                        'state':            'idle',
                        'anim_timer':       0.0,
                        'frame':            0,
                        'facing_x':         1.0,
                        'facing_y':         0.0,
                        'accuracy':         slime_acc,
                        'evasion':          enemy_evasion('slime', enemy_level),
                        'spawn_x':          x,
                        'spawn_y':          y,
                        'move_speed':       make_move_speed('slime'),
                        'speed_ramp':       0.0,
                        'dmg_type':         _pick_enemy_dmg_type(enemy_level),
                        'damage_reduction': mit['damage_reduction'],
                        'resist_pct':       dict(mit['resist_pct']),
                        **default_status_fields(),
                    })
                    break
        return slimes

    def _spawn_delve_objects(self):
        _m = self.map

        walls_adjacent = []
        corridor_tiles = set()

        for col in range(len(_m)):
            for row in range(len(_m[0])):
                if _m[col][row] != 0:
                    continue
                wall_n = 0
                for dc, dr in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                    nc, nr = col + dc, row + dr
                    if 0 <= nc < len(_m) and 0 <= nr < len(_m[0]) and _m[nc][nr] != 0:
                        wall_n += 1
                h_line = sum(1 for dc in (-2, -1, 1, 2)
                            if 0 <= col + dc < len(_m) and _m[col + dc][row] == 0)
                v_line = sum(1 for dr in (-2, -1, 1, 2)
                            if 0 <= row + dr < len(_m[0]) and _m[col][row + dr] == 0)
                if h_line >= 3 or v_line >= 3:
                    corridor_tiles.add((col, row))
                    continue
                if wall_n >= 1:
                    walls_adjacent.append((col, row))

        _rnd.shuffle(walls_adjacent)
        candidates = walls_adjacent

        # Desert decor pool: lit campfires (torches), Anima graveyard
        # pillars (bones*), cacti/reeds/bushes/rock piles, dead telegraph
        # poles — all sliced from the desert tileset.
        _DECOR_TYPES = ['bones1', 'bones2', 'bones3',
                        'cactus1', 'cactus2', 'reed1', 'reed2',
                        'bush_red', 'bush_red2', 'stone_s3', 'stone_s4',
                        'pole']

        total = len(candidates)

        idx = 0


        for _ in range(_rnd.randint(20, 30)):
            if idx >= total:
                break
            col, row = candidates[idx]; idx += 1
            decor_type = 'torch' if _rnd.random() < 0.3 else _rnd.choice(_DECOR_TYPES)
            self._decor_items.append({
                'x': float(col) + _rnd.uniform(0.1, 0.9),
                'y': float(row) + _rnd.uniform(0.1, 0.9),
                'type': decor_type,
            })

    def _spawn_enemy_drops(self, x, y, enemy_type='skeleton'):
        table = SLIME_DROP_TABLE if enemy_type == 'slime' else SKELETON_DROP_TABLE
        for item_id, mn, mx, chance in table:
            if _rnd.random() < chance:
                count = _rnd.randint(mn, mx)
                slot  = itemgen.roll_for(item_id, count, self._current_item_level())
                # ROT ETERNAL roll (§27): 2% on organ drops at depth 1-10
                if self._delve is not None:
                    itemgen.try_rot_mythic(slot, self._delve.get('depth', 1), _rnd)
                angle = _rnd.uniform(0, 6.2832)
                dist  = _rnd.uniform(0.3, 1.2)
                self.ground_items.append({
                    'x':     x + math.cos(angle) * dist,
                    'y':     y + math.sin(angle) * dist,
                    'items': [slot],
                    'type':  'drop',
                })
        # Tarot currency fraction drop (issue #73 phase B), depth-scaled
        if _rnd.random() < 0.04:
            slot = currency.roll_card_drop_slot(max(1, self._current_item_level() // 2), _rnd)
            self._drop_slot_at(slot, x, y)

    def _drop_slot_at(self, slot, x, y):
        angle = _rnd.uniform(0, 6.2832)
        dist  = _rnd.uniform(0.3, 1.2)
        self.ground_items.append({
            'x':     x + math.cos(angle) * dist,
            'y':     y + math.sin(angle) * dist,
            'items': [slot],
            'type':  'drop',
        })


    # ── combat / item helpers ─────────────────────────────────────────

    def _drop_rarity(self, gi: dict) -> str:
        """Effective rarity of a drop ground item."""
        if not gi.get('items'):
            return 'common'
        slot = gi['items'][0]
        inst = slot.get('instance_data')
        if inst:
            return inst.get('rarity', 'common')
        return ITEMS.get(slot['item'], {}).get('rarity', 'common')

    def _rarity_color(self, rarity: str) -> rl.Color:
        if rarity == 'uncommon':  return rl.Color(50,  200, 80,  255)
        if rarity == 'rare':      return rl.Color(80,  130, 255, 255)
        if rarity == 'epic':      return rl.Color(220, 50,  50,  255)
        if rarity == 'legendary': return rl.Color(255, 210, 40,  255)
        return rl.Color(200, 200, 200, 255)  # common

    def _drop_sprite_for(self, gi: dict):
        """Returns (IsoSprite or None, scale) for rendering a ground item.

        Single lookup point for ground-item sprites: for now EVERY dropped
        item renders as the gold drop / gold pile sprite (GROUND_ITEM_SPRITE)
        so items are visible on the ground at all times. Per-item-type
        assets land here later."""
        if not gi.get('items'):
            return None, 1.0
        return self._gold_drop_spr, 0.9


    def _spawn_swoosh(self, wx: float, wy: float, dcol: float, drow: float,
                      color=None):
        sdx = dcol - drow
        sdy = dcol + drow
        angle = math.degrees(math.atan2(sdy, sdx))
        tint = color if color is not None else rl.WHITE
        self._swoosh_effects.append({'x': wx, 'y': wy, 'angle': angle, 'timer': 0.0,
                                     'color': tint})

    def _spawn_glint(self, wx: float, wy: float, color=None, scale: float = 1.0,
                     vel_x: float = 0.0, vel_y: float = 0.0):
        self._glint_effects.append({
            'x': wx, 'y': wy, 'timer': 0.0,
            'color': color if color is not None else rl.WHITE,
            'scale': scale, 'vel_x': vel_x, 'vel_y': vel_y,
        })

    def _spawn_flame(self, wx: float, wy: float, color=None):
        self._flame_effects.append({
            'x': wx, 'y': wy, 'timer': 0.0,
            'color': color if color is not None else rl.WHITE,
        })

    def _spawn_glow(self, wx: float, wy: float, color=None, scale: float = 1.0,
                    alpha: int = 220):
        self._glow_effects.append({
            'x': wx, 'y': wy, 'timer': 0.0,
            'color': color if color is not None else rl.WHITE,
            'scale': scale, 'alpha': alpha,
        })

    # ── gunslinger ranged auto-attack ─────────────────────────────────

    def _fire_bullet(self, target, equip_effects: dict):
        """Fire a shot at `target`: roll the hit NOW (so crit/accuracy use
        the firing-time stats), let the bullet fly with travel time, and
        deliver damage + popups when it arrives (_update_bullets)."""
        tx, ty = target['x'], target['y']
        # muzzle starts a bit out from the body, toward the target
        d = math.hypot(tx - self.px, ty - self.py) or 1.0
        sx = self.px + (tx - self.px) / d * 0.35
        sy = self.py + (ty - self.py) / d * 0.35
        if _is_enemy_immune(target, 'physical'):
            result = {'damage': 0, 'evaded': False, 'crit': False,
                      'crushing': False, 'strikes': None, 'immune': True}
        else:
            flat_dmg = equip_effects['melee_damage']
            if self._angel_timer > 0:
                flat_dmg = int(flat_dmg * 1.5) + 1
            ranged_dmg = int((ATTACK_DAMAGE * self.stats.get('melee_dmg_mult', 1.0)
                              + flat_dmg) * self._outgoing_dmg_mult('physical'))
            crit_chance = min(0.75, self.stats.get('_crit_chance', 0.0)
                              + equip_effects['crit_chance'])
            crushing_chance = min(0.75, self.stats.get('crushing_blow_pct', 0.0)
                                  + equip_effects['crushing_blow_chance'])
            result = combat.resolve_attack(
                self.stats['accuracy'], target, ranged_dmg,
                crit_chance=crit_chance,
                crushing_blow_chance=crushing_chance,
                double_strike='bang_bang' in itemgen.equipped_uniques(self.inventory))
        self._bullets.append({
            'sx': sx, 'sy': sy,           # muzzle (world pos)
            'x': sx,  'y': sy,            # current flight position
            'tx': tx, 'ty': ty,           # impact point (homing updates it)
            'target': target,             # living enemy ref (may die mid-flight)
            'result': result,             # pre-rolled hit
            'timer': 0.0,                 # flight time (tracer rendering)
            # knockback impulse (tiles/sec along the shot line); crits
            # shove 1.6× harder, item affixes add via 'knockback'
            'kb': (KNOCKBACK_IMPULSE_TPS + equip_effects.get('knockback', 0.0))
                  * (1.6 if result.get('crit') else 1.0),
        })
        self._spawn_glow(sx, sy, scale=0.12, alpha=60,
                         color=rl.Color(255, 240, 180, 255))
        self.audio.revolver_shot()

    def _deliver_player_shot(self, bullet):
        """Apply a pre-rolled ranged hit when its bullet reaches the enemy."""
        target = bullet.get('target')
        # the victim died before the bullet arrived — the shot fizzles
        if target is None or target.get('health', 0) <= 0:
            return
        result = bullet['result']
        etype = target.get('enemy_type', 'enemy')
        if result.get('immune'):
            self._spawn_dmg_number(target['x'], target['y'],
                                   -1, color=rl.Color(150, 150, 220, 255))
            self._log_combat(f"Immune  → {etype}", 'miss')
        elif not result['evaded']:
            pen = self.stats.get('penetration_pct', {}).get('physical', 0.0)
            strike_damages = result.get('strikes') or [result['damage']]
            dealt = sum(self._apply_damage_to_enemy(
                target, strike_damage, 'physical', pen)
                for strike_damage in strike_damages)
            self._apply_lifesteal(dealt)
            self._vampiric_heal(dealt)
            tag = 'crit' if result.get('crit') else 'hit'
            self._log_combat(f"Hit {etype}  for {dealt}"
                             f"{'  CRIT' if result.get('crit') else ''}"
                             f"{'  CRUSH' if result.get('crushing') else ''}", tag)
            if result.get('crit'):
                dmg_color = rl.Color(255, 220, 40, 255)
                self._spawn_swoosh(target['x'], target['y'],
                                   0, 0, color=rl.Color(255, 200, 50, 160))
            else:
                dmg_color = rl.Color(255, 220, 200, 255)
            self._spawn_dmg_number(target['x'], target['y'],
                                   dealt, color=dmg_color)
            self.audio.bullet_impact()
            # gunslinger knockback: shove the enemy back along the shot line
            kb = bullet.get('kb', 0.0)
            if (kb > 0.0
                    and target['health'] > 0
                    and not target.get('knockback_immune')):
                shot_d = max(0.05, math.hypot(bullet['tx'] - bullet['sx'],
                                              bullet['ty'] - bullet['sy']))
                target['kb_x'] = (bullet['tx'] - bullet['sx']) / shot_d * kb
                target['kb_y'] = (bullet['ty'] - bullet['sy']) / shot_d * kb
                target['kb_timer'] = KNOCKBACK_DECAY_TIME
        else:
            self._spawn_dmg_number(target['x'], target['y'],
                                   0, color=rl.Color(180, 180, 180, 200))
            self._log_combat(f"Missed  → {etype}", 'miss')
        if target['health'] <= 0:
            self.audio.enemy_dead()
            self._log_combat(f"Killed  {etype}", 'kill')
            self._register_enemy_kill()
            target['death_timer'] = 0.0
            self._spawn_enemy_drops(target['x'], target['y'],
                                    target.get('enemy_type', 'skeleton'))
            if self.attack_target is target:
                self.attack_target = None

    def _find_drop_near(self, tile_col: float, tile_row: float, radius: float = 0.8):
        best, best_d = None, radius
        for gi in self.ground_items:
            if gi.get('type') != 'drop' or not gi.get('items'):
                continue
            d = math.hypot(gi['x'] - tile_col, gi['y'] - tile_row)
            if d < best_d:
                best_d, best = d, gi
        return best

    def _equipped_bonuses(self):
        out = {
            'damage_reduction': 0.0, 'move_speed': 0.0,
            'max_health': 0, 'max_health_pct': 0.0,
            'evasion': 0,
            'melee_damage': 0,
            'attack_speed_pct': 0.0, 'cooldown_recovery_pct': 0.0,
            'crit_chance': 0.0, 'ability_crit_chance': 0.0,
            'crushing_blow_chance': 0.0, 'block_chance': 0.0,
            'flat_damage_reduction': 0.0, 'attack_range': 0.0, 'knockback': 0.0,
            'dexterity': 0, 'endurance': 0, 'strength': 0,
            'cunning': 0, 'essence': 0, 'nerve': 0, 'destiny': 0,
        }
        # ROT ETERNAL set (§27): while active, rot drawbacks don't apply
        nullify = ('rot_eternal' in itemgen.equipped_uniques(self.inventory)
                   and itemgen.rot_set_active(self.inventory))
        for eq_item in self.inventory['equipped'].values():
            if not eq_item: continue
            fx = ITEMS.get(eq_item['item'], {}).get('equip', {})
            for k, v in fx.items():
                if k in out:
                    out[k] += v
            inst = eq_item.get('instance_data')
            # Unidentified items (issue #73 phase B): rolled affixes stay
            # hidden AND inert until The Joker identifies the item.
            if inst and itemgen.is_identified(eq_item):
                eff = itemgen.live_effect_totals(inst,
                                                 include_drawbacks=not nullify)
                for k, v in eff.items():
                    if k in out:
                        out[k] += v
        out['damage_reduction'] = min(0.75, out['damage_reduction'])
        out['evasion'] = int(out['evasion'])
        return out

    def _apply_damage(self, raw_dmg: float, dmg_type: str, damage_reduction: float,
                      flat_damage_reduction: float = 0.0, block_chance: float = 0.0):
        """Incoming damage pipeline: block → resist → flat DR → % DR → energy shield → health.

        Physical swings can be blocked outright (gear block chance + Dexterity,
        capped at 75%). Elemental and magic damage is reduced by the player's
        per-type resist_pct; physical ignores resist and leans on armor instead.
        Flat DR shaves a fixed amount off every hit before the % multiplier."""
        # Block roll — a blocked hit is negated entirely.
        if dmg_type == 'physical' and block_chance > 0.0 and _rnd.random() < min(0.75, block_chance):
            self._log_combat(f"Blocked {int(raw_dmg)} {dmg_type} dmg", 'dmg_taken')
            self._spawn_dmg_number(self.px, self.py - 0.4, 0,
                                   color=rl.Color(160, 200, 255, 255))
            return

        # 1) Per-type resist (physical is mitigated by armor, not resist)
        if dmg_type == 'physical':
            actual = raw_dmg
        else:
            resist = min(0.75, max(0.0, self.stats.get('resist_pct', {}).get(dmg_type, 0.0)))
            actual = raw_dmg * (1.0 - resist)

        # 2) Flat damage reduction, then 3) percentage armor
        actual = max(0.0, actual - flat_damage_reduction)
        if dmg_type == 'physical':
            actual = actual * (1.0 - min(0.75, max(0.0, damage_reduction)))

        energy_shield = self.stats.get('energy_shield', 0.0)
        if energy_shield > 0.0:
            absorbed = min(energy_shield, actual)
            self.stats['energy_shield'] = energy_shield - absorbed
            actual -= absorbed
        if actual > 0.0:
            saved = combat.apply_health_damage(
                self.stats, actual,
                second_wind='second_wind' in itemgen.equipped_uniques(self.inventory),
                cooldown_remaining=self._second_wind_cooldown)
            if saved:
                self._second_wind_cooldown = 60.0
            shake_strength = min(6.0, actual * 0.08)
            if shake_strength > 1.0:
                self._shake_timer = max(self._shake_timer, min(0.3, shake_strength * 0.06))
                self._shake_intensity = max(self._shake_intensity, shake_strength)
        self._incoming_dmg_by_type[dmg_type] = (self._incoming_dmg_by_type.get(dmg_type, 0.0)
                                                + actual)

    def _vampiric_heal(self, dealt):
        """Heal 10% of actual melee damage when Vampiric is equipped."""
        if 'vampiric' not in itemgen.equipped_uniques(self.inventory):
            return 0.0
        heal = max(0.0, float(dealt)) * 0.10
        self.stats['health'] = min(self.stats['max_health'], self.stats['health'] + heal)
        return heal

    def _auto_place(self, item):
        """Route a picked-up item: gear → equip slot if free, else grid."""
        item_id = item['item']
        defn    = ITEMS.get(item_id, {})

        # Equippable organ → first available slot. Unidentified gear must be
        # manually equipped so picking it up can never change loadout state.
        equip_slot = defn.get('equipSlot')
        if equip_slot and itemgen.is_identified(item):
            target = equip_slot if self.inventory['equipped'].get(equip_slot) is None else None
            if target:
                self.inventory['equipped'][target] = item
                self.audio.item_equip()
                # Auto-equip is a loadout change: derived stats are cached in
                # self.stats, so invalidate them the same way a manual implant
                # does (see _on_gear_changed).
                self._on_gear_changed()
                return

        # Fall through to grid
        placed = False
        if item.get('instance_data'):
            placed = grid_auto_place_instance(self.inventory['grid'], item,
                                              cols=INV_COLS, rows=INV_ROWS)
        else:
            placed = grid_auto_place(self.inventory['grid'], item_id, item.get('count', 1),
                                     cols=INV_COLS, rows=INV_ROWS)
        if placed:
            self.audio.item_pickup()
        else:
            self._inv_full_timer = 3.0

    def _restore_pre_raid_inventory(self):
        if not hasattr(self, '_pre_raid_inventory'):
            return
        import copy as _copy
        self.char.inventory = _copy.deepcopy(self._pre_raid_inventory)
        self.inventory      = self.char.inventory

    def _get_char_inventory(self):
        char = self.char
        if char is None:
            return make_inventory()
        if char.inventory is None:
            char.inventory = make_inventory()
        return char.inventory

    # ── draw ──────────────────────────────────────────────────────────

    # profiler data readable by main.py
    profile_ms: dict = {}

    def _update_mouse_transform(self):
        """Window and canvas are the same surface — reset any leftover mouse
        mapping so rl.get_mouse_*() calls see raw window coordinates."""
        rl.set_mouse_offset(0, 0)
        rl.set_mouse_scale(1.0, 1.0)

    def _ensure_virtual_rt(self):
        ww, wh = rl.get_screen_width(), rl.get_screen_height()
        if (self._virtual_rt is None or self._virtual_rt.texture.id == 0
                or self._virtual_rt_size != (ww, wh)):
            if self._virtual_rt is not None and self._virtual_rt.texture.id != 0:
                rl.unload_render_texture(self._virtual_rt)
            self._virtual_rt = rl.load_render_texture(ww, wh)
            self._virtual_rt_size = (ww, wh)



    # Loading screen layout — tweak these by hand
    LOAD_RUNNER_SCALE = 3.0   # sprite zoom (frame art has transparent padding,
                              # so >1.0 often looks better)
    LOAD_RUNNER_OFF_X = -310    # px from right screen edge to sprite box
    LOAD_RUNNER_OFF_Y = -280    # px from bottom screen edge to sprite box
    LOAD_TEXT_SIZE     = 22    # "loading..." font size
    LOAD_TEXT_OFF_X    = 24    # px from right screen edge to end of text
    LOAD_TEXT_OFF_Y    = 60    # px from bottom screen edge to bottom of text
    LOAD_RUNNER_DEBUG  = False # True = draw sprite-box outline while tuning












    def _spawn_dmg_number(self, wx, wy, value, color=None):
        self._dmg_numbers.append({
            'x': wx, 'y': wy, 'timer': 0.0,
            'value': int(value),
            'color': color if color is not None else rl.WHITE,
        })

    def _log_combat(self, message, entry_type='hit'):
        now = self.raid_time
        self._combat_log.append({'time': now, 'msg': message, 'type': entry_type})
        if len(self._combat_log) > 80:
            self._combat_log.pop(0)

    def _register_enemy_kill(self):
        self.tracker.kills += 1
        now = rl.get_time()
        if now - self._last_kill_t <= ANGEL_STREAK_WINDOW:
            self._kill_streak += 1
        else:
            self._kill_streak = 0
        self._last_kill_t = now
        gain = ANGEL_METER_PER_KILL + min(self._kill_streak, 10)
        self._add_angel_meter(gain)

        # Streak banner juice
        if self._kill_streak >= 1:
            self._streak_pop_t = now
            self._shake_timer     = max(self._shake_timer, STREAK_KILL_SHAKE)
            self._shake_intensity = max(self._shake_intensity, 3.0)
            title = STREAK_MILESTONES.get(self._kill_streak)
            if title:
                self._streak_milestone   = title
                self._streak_milestone_t = now
                self._shake_timer        = max(self._shake_timer, STREAK_MILESTONE_SHAKE)
                self._shake_intensity    = max(self._shake_intensity, 6.0)

    def _add_angel_meter(self, amount):
        # Angel Form was removed in the Diablo 2-style combat rework. Kept as a
        # no-op so legacy call sites don't need to change.
        return

    def _activate_angel_form(self):
        # Angel Form was removed in the Diablo 2-style combat rework.
        return

    def _use_organ_ability(self, slot, found=None, cds=None):
        """Cast an active gem ability on a QWER slot (issue #73 DESIGN PIVOT).
        `found` is a (instance_data, ability_def, tier) tuple from
        gems.socketed_ability; `cds` is the cooldown dict to use. Returns True
        when a cast actually fired."""
        if not found:
            return False
        cds = cds if cds is not None else self._ability_cds
        inst, ab, tier = found
        ability_id = inst['ability']
        if ab['type'] != 'active':
            return False
        if cds.get(slot, 0.0) > 0:
            return False

        cd_list = ab.get('cooldown')
        if cd_list:
            cdr = self.stats.get('_cooldown_recovery_pct', 0.0) + self._equipped_bonuses()['cooldown_recovery_pct']
            cds[slot] = cd_list[tier] * (1.0 - min(0.5, cdr))

        self._add_angel_meter(ANGEL_METER_PER_CAST)

        cw = rl.get_screen_width()
        ch = rl.get_screen_height()
        mx = rl.get_mouse_x()
        my = rl.get_mouse_y()
        tile_col, tile_row = self.iso.screen_to_world(mx, my, cw, ch)
        dir_x  = tile_col - self.px
        dir_y  = tile_row - self.py

        _CONE_COLORS = {
            'physical':  rl.Color(220, 220, 200, 255),
            'fire':      rl.Color(255,  80,  20, 255),
            'cold':      rl.Color( 80, 160, 255, 255),
            'lightning': rl.Color(255, 230,  50, 255),
            'magic':     rl.Color(180,  80, 255, 255),
        }
        if ability_id.startswith('cone_'):
            hit_z, dmg = abilities.cone_targets(self.px, self.py, dir_x, dir_y,
                                           ability_id, tier, self.zombies)
            if self._angel_timer > 0:
                dmg = int(dmg * 1.5)
            dmg_type = abilities.ABILITIES[ability_id].get('dmg_type', 'physical')
            swoosh_color = _CONE_COLORS.get(dmg_type, rl.WHITE)
            self._spawn_swoosh(self.px, self.py, dir_x, dir_y, color=swoosh_color)
            ability_crit = min(0.75, self.stats.get('_ability_crit_chance', 0.0)
                               + self._equipped_bonuses()['ability_crit_chance'])
            pen = self.stats.get('penetration_pct', {}).get(dmg_type, 0.0)
            lightning_chain_targets = []
            for z in hit_z:
                if _is_enemy_immune(z, dmg_type):
                    self._log_combat(f"Immune  → {z.get('enemy_type', 'enemy')} ({ability_id})", 'miss')
                    continue
                # Lightning has high variance: random in [1, base_dmg * 2]
                actual_dmg = _rnd.randint(1, dmg * 2) if dmg_type == 'lightning' else dmg
                actual_dmg = int(actual_dmg * self._outgoing_dmg_mult(dmg_type))
                crit = _rnd.random() < ability_crit
                if crit:
                    actual_dmg = int(actual_dmg * combat.CRIT_MULT)
                dealt = self._apply_damage_to_enemy(z, actual_dmg, dmg_type, pen)
                if dealt <= 0:
                    continue
                combat.apply_status_to_enemy(z, dmg_type, dealt)
                self._log_combat(f"{ability_id} hit {z.get('enemy_type', 'enemy')} for {dealt}"
                                 f"{'  CRIT' if crit else ''}", 'crit' if crit else 'hit')
                self._spawn_dmg_number(z['x'], z['y'], dealt,
                                       color=rl.Color(255, 220, 40, 255) if crit else swoosh_color)
                if dmg_type == 'lightning':
                    lightning_chain_targets.append(z)
                if z['health'] <= 0:
                    self._log_combat(f"Killed {z.get('enemy_type', 'enemy')} ({ability_id})", 'kill')
                    self._register_enemy_kill()
                    z['death_timer'] = 0.0
                    self._spawn_enemy_drops(z['x'], z['y'], z.get('enemy_type', 'skeleton'))
            # Lightning chain: spread to up to 2 nearby enemies not in primary hit list
            if dmg_type == 'lightning' and lightning_chain_targets:
                chain_dmg = int(dmg * 0.6)
                chained = set(id(z) for z in lightning_chain_targets)
                for source in lightning_chain_targets:
                    chains_from_source = 0
                    for candidate in self.zombies:
                        if candidate['health'] <= 0 or id(candidate) in chained:
                            continue
                        if _is_enemy_immune(candidate, 'lightning'):
                            continue
                        if math.hypot(candidate['x'] - source['x'],
                                      candidate['y'] - source['y']) > 2.5:
                            continue
                        varied_chain_dmg = _rnd.randint(1, chain_dmg * 2)
                        varied_chain_dmg = int(varied_chain_dmg * self._outgoing_dmg_mult('lightning'))
                        crit = _rnd.random() < ability_crit
                        if crit:
                            varied_chain_dmg = int(varied_chain_dmg * combat.CRIT_MULT)
                        chained.add(id(candidate))
                        dealt = self._apply_damage_to_enemy(candidate, varied_chain_dmg, 'lightning', pen)
                        if dealt <= 0:
                            continue
                        combat.apply_status_to_enemy(candidate, 'lightning', dealt)
                        self._log_combat(f"Chain hit {candidate.get('enemy_type', 'enemy')} for {dealt}"
                                         f"{'  CRIT' if crit else ''}", 'crit' if crit else 'hit')
                        self._spawn_dmg_number(candidate['x'], candidate['y'],
                                               dealt,
                                               color=rl.Color(255, 220, 40, 255) if crit else rl.Color(255, 230, 50, 255))
                        if candidate['health'] <= 0:
                            self._log_combat(f"Killed {candidate.get('enemy_type', 'enemy')} (chain)", 'kill')
                            self._register_enemy_kill()
                            candidate['death_timer'] = 0.0
                            self._spawn_enemy_drops(candidate['x'], candidate['y'],
                                                     candidate.get('enemy_type', 'skeleton'))
                        chains_from_source += 1
                        if chains_from_source >= 2:
                            break
            if hit_z:
                self.audio.hitmarker()

        elif ability_id == 'dash':
            dist = ab['distance'][tier]
            dlen = math.hypot(dir_x, dir_y)
            if dlen > 0.001:
                old_px, old_py = self.px, self.py
                self.px += dir_x / dlen * dist
                self.py += dir_y / dlen * dist
                self.dest_col = self.dest_row = None
                for step in range(4):
                    t = step / 3.0
                    self._spawn_glint(
                        old_px + (self.px - old_px) * t,
                        old_py + (self.py - old_py) * t,
                        color=rl.Color(180, 220, 255, 255),
                        scale=0.5 + step * 0.15,
                    )

        elif ability_id == 'blink':
            max_r = ab['max_range'][tier]
            dlen  = math.hypot(dir_x, dir_y)
            if dlen > 0.001:
                self._spawn_glow(self.px, self.py,
                                 color=rl.Color(120, 80, 255, 200), scale=1.2)
                blink_d  = min(dlen, max_r)
                self.px += dir_x / dlen * blink_d
                self.py += dir_y / dlen * blink_d
                self.dest_col = self.dest_row = None
                self._spawn_glow(self.px, self.py,
                                 color=rl.Color(160, 120, 255, 220), scale=1.0)
                for _ in range(5):
                    angle = _rnd.uniform(0, math.tau)
                    self._spawn_glint(
                        self.px + math.cos(angle) * 0.3,
                        self.py + math.sin(angle) * 0.3,
                        color=rl.Color(200, 160, 255, 255),
                        scale=0.6,
                    )

        elif ability_id == 'lifesteal':
            self._lifesteal_timer = ab['duration'][tier]
            self._lifesteal_pct   = ab['pct'][tier]
            self._spawn_glow(self.px, self.py,
                             color=rl.Color(80, 220, 100, 200), scale=1.2)
            for i in range(6):
                angle = i * math.tau / 6
                self._spawn_glint(
                    self.px + math.cos(angle) * 0.35,
                    self.py + math.sin(angle) * 0.35,
                    color=rl.Color(120, 240, 120, 255),
                    scale=0.6,
                )

        elif ability_id == 'fire_aura':
            self._fire_aura_timer  = ab['duration'][tier]
            self._fire_aura_radius = ab['radius'][tier]
            self._fire_aura_dps    = ab['dps'][tier]
            self._spawn_glow(self.px, self.py,
                             color=rl.Color(255, 120, 30, 200), scale=1.3)
            for i in range(8):
                angle = i * math.tau / 8
                self._spawn_flame(
                    self.px + math.cos(angle) * 0.5,
                    self.py + math.sin(angle) * 0.5,
                    color=rl.Color(255, 100, 20, 255),
                )

        return True

    def _use_gem_ability(self, slot_key):
        """Cast the ability of the gem socketed in a QWER key slot
        (blue=Q, green=W, red=E, white=R). Returns True when a cast fired."""
        found = gems.socketed_ability(self.inventory, slot_key)
        if not found:
            return False
        if found[1].get('type') != 'active':
            return False   # passive gems apply their effect while socketed
        fired = self._use_organ_ability(slot_key, found=found, cds=self._gem_cds)
        if fired:
            self._flash_hud(slot_key)
        return fired

    def _use_flask(self):
        """T — drink the flask equipped in the T slot (PoE-style charges).
        Returns the flask kind when a drink actually happened."""
        kind = flasks.use_flask(self.inventory,
                                {'_flask_cd': self._flask_cd,
                                 'flask_effects': self.flask_effects},
                                self.stats)
        if kind is not None:
            # use_flask set the cooldown on its own state dict — mirror it
            self._flask_cd = flasks.FLASK_CD
            self._log_combat(f"Drank {kind} flask.", 'info')
            self._flash_hud('T')
        return kind

    def _refill_flasks(self):
        """Reset the equipped flask to its one charge per wave (tied to the
        wave/encounter lifecycle, not a timer)."""
        flasks.reset_for_wave(self.inventory)

    def _outgoing_dmg_mult(self, dmg_type: str) -> float:
        """Multiplier from D.E.S.C.E.N.D. attributes/perks for outgoing damage
        of a given type. Penetration is intentionally NOT folded in here — it is
        applied as enemy-resist reduction inside _apply_damage_to_enemy (true
        Diablo 2-style penetration)."""
        dmg_pct = self.stats.get('damage_pct', {})
        return 1.0 + dmg_pct.get(dmg_type, 0.0)

    def _apply_damage_to_enemy(self, z: dict, raw_dmg: float, dmg_type: str, pen: float = 0.0) -> int:
        """Apply player damage to an enemy through its armor (damage_reduction)
        and per-type resist_pct (reduced by the attacker's penetration).

        Returns the damage actually dealt (0 if immune). Callers remain
        responsible for kill bookkeeping via z['health']."""
        if _is_enemy_immune(z, dmg_type):
            self._spawn_dmg_number(z['x'], z['y'], -1, color=rl.Color(150, 150, 220, 255))
            self._log_combat(f"Immune  → {z.get('enemy_type', 'enemy')}", 'miss')
            return 0
        dr = z.get('damage_reduction', 0.0)
        if dmg_type == 'physical':
            eff_dr = dr
        elif dmg_type == 'magic':
            eff_dr = 0.0
        else:
            eff_dr = dr * 0.5
        dmg = raw_dmg * (1.0 - min(0.75, max(0.0, eff_dr)))
        resist = max(0.0, z.get('resist_pct', {}).get(dmg_type, 0.0) - pen)
        resist = min(0.75, resist)
        dmg = int(dmg * (1.0 - resist))
        z['health'] = max(0.0, z['health'] - dmg)
        z['hit_count'] = z.get('hit_count', 0) + 1
        return dmg

    def _apply_lifesteal(self, damage):
        """Timed Lifesteal buff (E-gem active): heal a pct of dealt melee
        damage while the buff runs. Values are snapshotted at cast time."""
        if self._lifesteal_timer <= 0 or self._lifesteal_pct <= 0:
            return
        heal = damage * self._lifesteal_pct
        self.stats['health'] = min(self.stats['max_health'],
                                   self.stats['health'] + heal)
        if heal > 0:
            self._spawn_glint(self.px, self.py,
                              color=rl.Color(80, 220, 100, 255), scale=0.9)

    def _tick_ability_buffs(self, dt):
        """Tick the timed E-gem buffs (survival actives). Fire Aura deals its
        dps in 1-second bursts while active; Lifesteal is consumed by
        _apply_lifesteal on melee hits and only needs its timer."""
        self._aura_tick += dt
        if self._aura_tick < 1.0:
            return
        self._aura_tick = 0.0
        if self._fire_aura_timer <= 0:
            return
        radius_sq = self._fire_aura_radius ** 2
        burst_dmg = self._fire_aura_dps
        for z in self.zombies:
            if z.get('health', 0) <= 0:
                continue
            dx = z['x'] - self.px
            dy = z['y'] - self.py
            if dx * dx + dy * dy > radius_sq:
                continue
            if _is_enemy_immune(z, 'fire'):
                continue
            dealt = self._apply_damage_to_enemy(
                z, burst_dmg, 'fire', self.stats.get('penetration_pct', {}).get('fire', 0.0))
            if dealt <= 0:
                continue
            combat.apply_status_to_enemy(z, 'fire', burst_dmg)
            self._log_combat(f"Fire aura hit {z.get('enemy_type', 'enemy')} for {dealt}", 'hit')
            self._spawn_flame(z['x'], z['y'], color=rl.Color(255, 100, 20, 255))
            self._spawn_dmg_number(z['x'], z['y'], dealt,
                                   color=rl.Color(255, 130, 40, 255))
            if z['health'] <= 0:
                self._log_combat(f"Killed {z.get('enemy_type', 'enemy')} (fire aura)", 'kill')
                self._register_enemy_kill()
                z['death_timer'] = 0.0
                self._spawn_enemy_drops(z['x'], z['y'], z.get('enemy_type', 'skeleton'))

    def _on_stash_change(self):
        """Called by InventoryUI after any stash grid mutation to persist the save."""
        self.char_mgr.save()

    def _on_inv_drop(self, entry):
        """Spawn an item dropped from inventory as a ground pickup near the player."""
        angle = _rnd.uniform(0, 6.2832)
        dist  = _rnd.uniform(0.5, 1.2)
        self.ground_items.append({
            'x':     self.px + math.cos(angle) * dist,
            'y':     self.py + math.sin(angle) * dist,
            'items': [entry],
            'type':  'drop',
        })
        self.audio.item_land()



    _STAT_DESC = {
        'Health': 'When health reaches 0 you die permanently.',
        'Energy Shield': 'Absorbs damage before health. Regenerates after not taking damage.',
        'Evasion': 'Chance to avoid incoming attacks entirely.',
        'Accuracy': 'Chance to hit enemies with attacks.',
        'Melee Damage': 'Bonus to physical damage dealt in melee range.',
        'Dmg Reduction': 'Percentage of incoming damage reduced by armor.',
        'Fire Resist': 'Reduces fire damage taken by this percentage.',
        'Cold Resist': 'Reduces cold damage taken by this percentage.',
        'Lightn Resist': 'Reduces lightning damage taken by this percentage.',
        'Move Speed': 'Bonus to movement speed.',
        'Class': 'Your chosen class. Determines starting stats and skill tree position.',
        'STR / DEX / INT': 'Strength, Dexterity, and Intelligence attributes.',
    }




    def _streak_color(self, streak):
        if streak >= 10: return rl.Color(200, 120, 255, 255)   # violet — angelic
        if streak >= 8:  return rl.Color(255, 90, 60, 255)     # red-hot
        if streak >= 5:  return rl.Color(255, 140, 40, 255)    # orange
        if streak >= 3:  return rl.Color(255, 210, 60, 255)    # gold
        return rl.Color(240, 240, 240, 255)                    # white








    def _exec_console(self, cmd):
        parts = cmd.lower().split()
        if not parts: return
        command = parts[0]
        in_raid = self.state == STATE_PLAYING
        output  = ''

        if command == 'god':
            self._god_mode = not self._god_mode
            output = f"God mode {'ON' if self._god_mode else 'OFF'}"
        elif command == 'heal':
            if not in_raid: output = 'Not in raid'
            else:
                self._recalc_derived_stats()
                self.stats['health'] = self.stats['max_health']
                self.stats['energy_shield'] = self.stats.get('max_energy_shield', 0.0)
                self._angel_meter = ANGEL_METER_MAX
                output = 'Stats restored (recalculated)'
        elif command == 'kill':
            if not in_raid: output = 'Not in raid'
            else:
                for z in self.zombies: z['health'] = 0
                output = 'All enemies killed'
        elif command == 'give' and len(parts) >= 2:
            if not in_raid: output = 'Not in raid'
            elif parts[1] not in ITEMS: output = f'Unknown item: {parts[1]}'
            else:
                item_id = parts[1]
                defn    = ITEMS[item_id]
                arg2    = parts[2] if len(parts) >= 3 else None
                if defn.get('equipSlot'):
                    slot = itemgen.roll_for(item_id, 1, self._current_item_level())
                    if arg2 in itemgen.M_RARITY:
                        slot['instance_data'] = itemgen.generate_instance(
                            item_id, self._current_item_level(), rarity=arg2,
                            equip_slot=defn['equipSlot'], base_name=defn.get('name', item_id))
                    if grid_auto_place_instance(self.inventory['grid'], slot,
                                                cols=INV_COLS, rows=INV_ROWS):
                        ins = slot['instance_data']
                        output = f'Gave {ins["display_name"]} [{ins["rarity"]}]'
                        self.char_mgr.save()
                    else:
                        output = 'Inventory full'
                else:
                    count = int(arg2) if (arg2 and arg2.isdigit()) else 1
                    if grid_auto_place(self.inventory['grid'], item_id, count,
                                       cols=INV_COLS, rows=INV_ROWS):
                        output = f'Gave {count}x {item_id}'
                        self.char_mgr.save()
                    else:
                        output = 'Inventory full'
        elif command == 'inv_layout':
            self.inv.layout_dbg = not self.inv.layout_dbg
            output = f'inventory layout overlay: {"ON" if self.inv.layout_dbg else "OFF"}'
        elif command == 'descend' and len(parts) >= 3:
            attr, amt = parts[1], parts[2]
            if attr not in DESCEND_ATTRIBUTES:
                output = ('Unknown attribute: %s (dexterity|endurance|strength|'
                          'cunning|essence|nerve|destiny)' % attr)
            elif not amt.isdigit():
                output = 'Usage: descend <attr> <0..10>'
            else:
                self.char.descend[attr] = max(0, min(ATTR_CAP, int(amt)))
                self._recalc_derived_stats()
                self.char_mgr.save()
                output = f'{attr} = {self.char.descend[attr]}'
        elif command == 'perk' and len(parts) >= 3:
            perk_id, rank_s = parts[1], parts[2]
            if perk_id not in DESCEND_PERKS:
                output = f'Unknown perk: {perk_id}'
            elif not rank_s.isdigit():
                output = 'Usage: perk <id> <0..max>'
            else:
                rank = max(0, min(DESCEND_PERKS[perk_id]['max_ranks'], int(rank_s)))
                if rank == 0:
                    self.char.perks.pop(perk_id, None)
                else:
                    self.char.perks[perk_id] = rank
                self._recalc_derived_stats()
                self.char_mgr.save()
                output = f'{perk_id} rank = {rank}'
        elif command == 'zoom':
            if len(parts) >= 2:
                try:
                    self.iso.scale = max(MIN_SCALE, min(MAX_SCALE, float(parts[1])))
                    output = f'Scale {self.iso.scale:.2f}'
                except ValueError:
                    output = 'Usage: zoom <1..3>'
            else:
                output = f'Zoom: {self.iso.scale:.2f}'
        elif command == 'weather':
            if len(parts) >= 2 and parts[1] in ('on', 'off'):
                self._weather_enabled = (parts[1] == 'on')
                output = f"Weather FX {parts[1].upper()}"
            else:
                output = (f"Weather FX {'ON' if self._weather_enabled else 'OFF'} "
                          f"· rain: {'yes' if self.weather.get('raining') else 'no'} "
                          f"(intensity {self.weather.get('intensity', 0.0):.2f})")
        elif command == 'help':
            output = 'god  heal  kill  give <item> [n|rarity]  money <n>  zoom <n>'
            output += '\ndescend <attr> <0..5>   perk <id> <0..max>   pp [color|bloom|wave|dream|gray|pixel|swirl] [on|off|<val>]'
            output += '\npp contrast|sat|bright <v>   pp_bloom samples|quality|threshold|intensity <v>'
            output += '\nweather [on|off] — toggle wet FX (render-only)'
        elif command == 'pp':
            if len(parts) < 2:
                status = (
                    f"color:{'on' if self._pp_color else 'off'} "
                    f"bloom:{'on' if self._pp_bloom else 'off'} "
                    f"wave:{self._pp_wave:.2f} dream:{self._pp_dream:.2f} "
                    f"gray:{self._pp_gray:.2f} pixel:{self._pp_pixel:.2f}"
                )
                output = status
            elif parts[1] in ('color', 'bloom',):
                flag = getattr(self, f'_pp_{parts[1]}')
                if len(parts) >= 3:
                    if parts[2] == 'on': setattr(self, f'_pp_{parts[1]}', True)
                    elif parts[2] == 'off': setattr(self, f'_pp_{parts[1]}', False)
                output = f"pp {parts[1]} = {'on' if getattr(self, f'_pp_{parts[1]}') else 'off'}"
            elif parts[1] in ('wave', 'dream', 'gray', 'pixel', 'swirl'):
                if len(parts) >= 3:
                    try:
                        setattr(self, f'_pp_{parts[1]}', float(parts[2]))
                    except ValueError:
                        output = f'Usage: pp {parts[1]} <0.0..1.0>'
                output = f"pp {parts[1]} = {getattr(self, f'_pp_{parts[1]}'):.2f}"
            else:
                output = f'Unknown pp param: {parts[1]}'
        elif command == 'pp_bloom' and len(parts) >= 3:
            if parts[1] == 'samples':
                try: self._bloom_samples = float(parts[2]); output = f'bloom samples = {self._bloom_samples}'
                except ValueError: output = 'Usage: pp_bloom samples <3..15>'
            elif parts[1] == 'quality':
                try: self._bloom_quality = float(parts[2]); output = f'bloom quality = {self._bloom_quality}'
                except ValueError: output = 'Usage: pp_bloom quality <1..15>'
            elif parts[1] == 'threshold':
                try: self._bloom_threshold = float(parts[2]); output = f'bloom threshold = {self._bloom_threshold}'
                except ValueError: output = 'Usage: pp_bloom threshold <0..1>'
            elif parts[1] == 'intensity':
                try: self._bloom_intensity = float(parts[2]); output = f'bloom intensity = {self._bloom_intensity}'
                except ValueError: output = 'Usage: pp_bloom intensity <0..2>'
            else:
                output = 'Usage: pp_bloom samples|quality|threshold|intensity <v>'
        elif command in ('contrast', 'sat', 'bright') and len(parts) >= 2:
            try:
                val = float(parts[1])
                if command == 'contrast': self._pp_contrast = val
                elif command == 'sat': self._pp_saturation = val
                elif command == 'bright': self._pp_brightness = val
                output = f'{command} = {val}'
            except ValueError:
                output = f'Usage: {command} <value>'
        else:
            output = f'Unknown: {cmd}'

        self._console_log.append(f'> {cmd}')
        self._console_log.append(output)
        if len(self._console_log) > 20: self._console_log = self._console_log[-20:]


    def _take_screenshot(self):
        import datetime, shutil
        ss_dir = os.path.join(os.environ.get('APPDATA', os.path.expanduser('~')), 'BTR', 'screenshots')
        os.makedirs(ss_dir, exist_ok=True)
        ts = datetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
        filename = f'screenshot_{ts}.png'
        rl.take_screenshot(filename)
        src = os.path.join(os.getcwd(), filename)
        dst = os.path.join(ss_dir, filename)
        if os.path.exists(src):
            shutil.move(src, dst)
            print(f"[SCREENSHOT] {dst}")


    # ── cleanup ───────────────────────────────────────────────────────

    def cleanup(self):
        self._save_delve()
        self.char_mgr.save()
        self.iso.unload()
        for sprs in self._player_sprites.values():
            for sprite in sprs.values():
                if sprite: sprite.unload()
        for sprite in (self._sk_idle, self._sk_walk, self._sk_attack, self._sk_death):
            if sprite: sprite.unload()
        for sprite in (self._sl_idle, self._sl_walk, self._sl_death):
            if sprite: sprite.unload()
        for tex in self._portal_frames:
            if tex and tex.id > 0: rl.unload_texture(tex)
        for tex in (self._light_noise_tex, self._light_curve_tex):
            if tex and tex.id > 0: rl.unload_texture(tex)
        for sprite in (self._crate_spr, self._crate_break_spr,
                       self._barrel_spr, self._barrel_break_spr,
                       self._hub_subservient_spr,
                       self._column_spr, self._torch_spr,
                       self._brazier_spr, self._brazier_break_spr):
            if sprite: sprite.unload()
        for sprite in self._decor_sprs.values():
            if sprite: sprite.unload()
        if self._gold_drop_spr: self._gold_drop_spr.unload()
        if self._load_runner_spr: self._load_runner_spr.unload()
        _unloaded_ids = set()
        for tex in self._ability_icons.values():
            if tex and tex.id > 0 and tex.id not in _unloaded_ids:
                rl.unload_texture(tex)
                _unloaded_ids.add(tex.id)
        if self._vfx_white and self._vfx_white.id > 0:
            rl.unload_texture(self._vfx_white)
            self._vfx_white = None
        if self._anima_panel_tex and self._anima_panel_tex.id > 0:
            rl.unload_texture(self._anima_panel_tex)
        if self._pulse_tex is not None and self._pulse_tex.id > 0:
            rl.unload_texture(self._pulse_tex)
            self._pulse_tex = None
        if self._vignette_tex and self._vignette_tex.id > 0:
            rl.unload_texture(self._vignette_tex)
        for t in self._ui.values():
            if t and t.id > 0:
                rl.unload_texture(t)
        for attr in ('panel_tex', 'header_tex', 'logo_tex', 'bg_tex', 'headerB_tex'):
            t = getattr(self.menu_sys, attr, None)
            if t and t.id > 0:
                rl.unload_texture(t)
        if self._darkness_rt is not None:
            rl.unload_render_texture(self._darkness_rt)
            self._darkness_rt = None
        if self._scene_rt is not None:
            rl.unload_render_texture(self._scene_rt)
            self._scene_rt = None
        if self._ping_rt is not None:
            rl.unload_render_texture(self._ping_rt)
            self._ping_rt = None
        self._post_rt_size = (0, 0)
        if self._lightmap_rt is not None:
            rl.unload_render_texture(self._lightmap_rt)
            self._lightmap_rt = None
        if self._glow_rt is not None:
            rl.unload_render_texture(self._glow_rt)
            self._glow_rt = None
        self._light_rt_size = (0, 0)
        if self._virtual_rt is not None:
            rl.unload_render_texture(self._virtual_rt)
            self._virtual_rt = None
        if self._light_blob_tex is not None and self._light_blob_tex.id > 0:
            rl.unload_texture(self._light_blob_tex)
            self._light_blob_tex = None
        if self.shaders is not None:
            self.shaders.unload_all()
            self.shaders = None
        fonts.unload()
        self.audio.cleanup()
        self.inv.unload()

