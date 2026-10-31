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

"""Headless smoke tests for render paths that consume Character attributes."""

from pathlib import Path
from types import SimpleNamespace

import pyray as rl

from core.game import STATE_HUB, STATE_PLAYING
from core.render.frame_render import FrameRenderMixin
from core.render.hud_render import HudRenderMixin
from entities.progression import Character
from ui import fonts, icons


class _EmptyTextures:
    def get(self, _key):
        return None


def _current_character():
    character = Character("smoke-character", "Smoke Tester", "fighter")
    character.inventory = {}
    return character


def _game_stub():
    game = SimpleNamespace()
    game.char = _current_character()
    game.inventory = {}
    game.stats = {"health": 75.0, "max_health": 100.0, "mana": 4.0, "max_mana": 10.0}
    game._ui = _EmptyTextures()
    game._ability_icons = {}
    game._gem_cds = {}
    game._hud_action_rects = {}
    game._hud_flash = {}
    game._hit_effects = []
    game._hit_packs = []
    game._muzzle_frames = []
    game._flash_effects = []
    game._pending_shot = None
    game._flask_cd = 0.0
    game._lifesteal_timer = 0.0
    game._fire_aura_timer = 0.0
    game._fire_aura_radius = 0.0
    game._angel_timer = 0.0
    game._angel_meter = 0.0
    game.raid_time = 0.0
    game._save_notice_timer = 0.0
    game._inv_full_timer = 0.0
    game._vessel_unlock_timer = 0.0
    game._vessel_unlock_msg = ""
    game._kill_streak = 0
    game._streak_lost_t = -999.0
    game._streak_pop_t = -999.0
    game._last_kill_t = -999.0
    game._delve = None
    game.zombies = []
    game.ground_items = []
    game.px = 0.0
    game.py = 0.0
    game.map = [["0"]]
    game.iso = SimpleNamespace(draw_minimap=lambda *args, **kwargs: None)
    game._drop_rarity = lambda _item: "common"
    game._rarity_color = lambda rarity: rl.Color(255, 255, 255, 255)
    game._draw_delve_hud = lambda *args: HudRenderMixin._draw_delve_hud(game, *args)
    game._draw_character_level = lambda *args: HudRenderMixin._draw_character_level(game, *args)
    game._draw_enemy_hover_info = lambda *args: None
    game._draw_kill_streak = lambda *args: None
    game._draw_hud_flash = lambda *args: None
    game.menu_sys = SimpleNamespace(
        settings=SimpleNamespace(hud_scale=0.5, perf_overlay=False),
        draw=lambda *args: None,
    )
    game.inv = SimpleNamespace(draw=lambda *args: None)
    return game


def _install_headless_drawing(monkeypatch):
    rendered_text = []
    monkeypatch.setattr(rl, "get_mouse_x", lambda: -1)
    monkeypatch.setattr(rl, "get_mouse_y", lambda: -1)
    monkeypatch.setattr(rl, "get_time", lambda: 0.0)
    monkeypatch.setattr(rl, "is_mouse_button_pressed", lambda _button: False)
    monkeypatch.setattr(rl, "check_collision_point_rec", lambda *_args: False)
    for name in (
        "draw_rectangle", "draw_rectangle_lines", "draw_circle", "draw_ellipse",
        "draw_ellipse_lines", "draw_line", "draw_texture_pro", "begin_texture_mode",
        "end_texture_mode", "clear_background", "begin_blend_mode", "end_blend_mode",
        "begin_scissor_mode", "end_scissor_mode",
    ):
        monkeypatch.setattr(rl, name, lambda *args, **kwargs: None)
    monkeypatch.setattr(fonts, "draw", lambda text, *args, **kwargs: rendered_text.append(str(text)))
    monkeypatch.setattr(fonts, "measure", lambda text, _size: len(text) * _size)
    monkeypatch.setattr(icons, "draw", lambda *args, **kwargs: None)
    return rendered_text


def test_runtime_code_has_no_removed_character_progression_reads():
    removed_reads = (
        "self.char.level", "self.char.xp", "self.char.xp_progress",
        "self.char.xp_to_next", "self.char.add_xp", "self.char.gain_xp",
    )
    stale = []
    for path in Path('.').rglob('*.py'):
        if path.parts[0] == 'tests':
            continue
        source = path.read_text(encoding='utf-8')
        stale.extend(f"{path}: {symbol}" for symbol in removed_reads if symbol in source)
    assert stale == []


def test_runtime_code_has_no_removed_delve_tool_reads():
    """Repo guard for the removed flare/dynamite systems.

    Every leftover read of a removed field is a latent runtime crash, so this
    walks the AST of every non-test module (comments and docstrings are
    allowed to mention the removal) and fails on any live reference.
    """
    import ast

    # 'charges' is a legitimate flask field (systems/flasks.py), so it is only
    # banned in the delve/chart modules where it meant flare/dynamite charges.
    # (render modules also read *flask* charges, so they are not covered)
    chart_modules = {
        'core/delve_flow.py', 'core/delve_gen.py', 'ui/delve_chart.py',
    }
    removed = {
        # tuning constants
        'FLARE_COOLDOWN', 'FLARE_DURATION', 'FLARE_RADIUS_FRAC',
        'FLARE_MAX_ACTIVE', 'DYNAMITE_COOLDOWN', 'DYNAMITE_FUSE',
        'DYNAMITE_RADIUS', 'DYNAMITE_ENEMY_RADIUS', 'DYNAMITE_ENEMY_DMG',
        # runtime state
        '_flare_cd', '_dynamite_cd', '_delve_projectiles', 'flare_lights',
        'flare_mult',
        # behaviour
        '_throw_flare', '_throw_dynamite', '_update_delve_projectiles',
        '_dynamite_explode',
    }
    stale = []
    for path in Path('.').rglob('*.py'):
        if path.parts[0] == 'tests':
            continue
        posix = path.as_posix()
        names = set(removed)
        if posix in chart_modules:
            names.add('charges')
        tree = ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                name = node.id
            elif isinstance(node, ast.Attribute):
                name = node.attr
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                name = node.value
            else:
                continue
            if name in names:
                stale.append(f"{path}:{node.lineno}: {name}")
    assert stale == []


def test_t_flask_system_still_exists():
    """The T-slot flask is a different system and must survive the removal of
    flares/dynamite: keybind, per-wave charge and cooldown state all stay."""
    from pathlib import Path as _Path
    from systems import flasks

    assert flasks.WAVE_CHARGES == 1
    assert hasattr(flasks, 'FLASK_CD')
    input_src = _Path('core/input.py').read_text(encoding='utf-8')
    assert 'KEY_T' in input_src and '_use_flask' in input_src
    flow_src = _Path('core/delve_flow.py').read_text(encoding='utf-8')
    assert '_flask_cd' in flow_src and '_refill_flasks()' in flow_src


def test_hud_draws_with_current_character_in_hub_and_delve(monkeypatch):
    game = _game_stub()
    rendered_text = _install_headless_drawing(monkeypatch)

    HudRenderMixin._draw_hud(game, 1280, 720)
    assert not hasattr(game.char, "level")
    assert not hasattr(game.char, "xp")
    assert not hasattr(game.char, "xp_progress")
    assert not any("xp" in text.lower() for text in rendered_text)

    game._delve = {"depth": 7, "dark_timer": 2.5}
    rendered_text.clear()
    HudRenderMixin._draw_hud(game, 1280, 720)
    assert "Anima Depth 7" in rendered_text
    assert "Darkness  2.5s" in rendered_text
    assert not any("xp" in text.lower() for text in rendered_text)


def test_frame_draw_reaches_hud_in_hub_and_delve(monkeypatch):
    game = _game_stub()
    hud_calls = []
    game._ensure_virtual_rt = lambda: None
    game._update_mouse_transform = lambda: None
    game._virtual_rt = SimpleNamespace(texture=SimpleNamespace())
    game._outer_rt = None
    game.iso._outer_rt = None
    game._hover_interact = None
    game._console_open = False
    game._char_stats_open = False
    game._minimap_open = False
    game._minimap = None
    game._draw_combat_log = lambda *_args: None
    game._draw_cursor = lambda: None
    game._draw_console = lambda *_args: None
    game._draw_hub = lambda _cw, _ch: hud_calls.append("hub") or HudRenderMixin._draw_hud(game, 1280, 720)
    game._draw_game = lambda _cw, _ch: hud_calls.append("delve") or HudRenderMixin._draw_hud(game, 1280, 720)
    _install_headless_drawing(monkeypatch)

    game.state = STATE_HUB
    FrameRenderMixin._draw_frame(game)
    game.state = STATE_PLAYING
    FrameRenderMixin._draw_frame(game)

    assert hud_calls == ["hub", "delve"]
