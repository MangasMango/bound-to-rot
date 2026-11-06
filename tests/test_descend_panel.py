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

"""The D.E.S.C.E.N.D. panel: rank words, + gating, and modal wiring (#31)."""

import pytest
from unittest import mock
from types import SimpleNamespace

import pyray as rl

import entities.progression as prog
from entities.descend import ATTR_CAP, DESCEND_ATTRIBUTES
from ui.descend_rank import RANK_WORDS, rank_word
from ui import descend_ui


def _install_headless(monkeypatch):
    for name in ('draw_rectangle', 'draw_rectangle_lines',
                 'draw_rectangle_lines_ex', 'draw_texture_pro'):
        monkeypatch.setattr(rl, name, lambda *a, **k: None)
    monkeypatch.setattr(rl, 'get_mouse_x', lambda: -1)
    monkeypatch.setattr(rl, 'get_mouse_y', lambda: -1)
    monkeypatch.setattr(rl, 'get_render_width', lambda: 1280)
    monkeypatch.setattr(rl, 'get_render_height', lambda: 720)
    from ui import fonts as fonts_mod
    monkeypatch.setattr(fonts_mod, 'draw', lambda text, *a, **k: None)
    monkeypatch.setattr(fonts_mod, 'measure', lambda text, _s: len(text) * _s)


def _panel_game(**char_kwargs):
    char = prog.Character('panel', 'P', 'knight')
    for k, v in char_kwargs.items():
        setattr(char, k, v)
    stats = {
        'health': 100.0, 'max_health': 100.0, 'max_mana': 50.0,
        'max_energy_shield': 0.0, 'energy_shield': 0.0,
        '_attack_speed_pct': 0.0, '_cooldown_recovery_pct': 0.0,
        '_crit_chance': 0.0, '_ability_crit_chance': 0.0,
    }
    game = SimpleNamespace(
        char=char, inventory=None, stats=stats,
        _equipped_bonuses=lambda: {'damage_reduction': 0.0,
                                   'attack_speed_pct': 0.0,
                                   'cooldown_recovery_pct': 0.0,
                                   'crit_chance': 0.0,
                                   'ability_crit_chance': 0.0,
                                   'move_speed_pct': 0.0},
        inv=mock.Mock(),
    )
    game._recalc_derived_stats = mock.Mock()
    return game


# The panel texture path: headless runs must never depend on the real file.
@pytest.fixture(autouse=True)
def _stub_texture(monkeypatch):
    monkeypatch.setattr(descend_ui, '_panel_tex', lambda: None)


# rank words -----------------------------------------------------------------

def test_word_ladder_matches_owner_order():
    assert [rank_word(i) for i in range(11)] == list(RANK_WORDS)
    assert rank_word(0) == 'Cowardly'
    assert rank_word(3) == 'Fair'
    assert rank_word(10) == 'Godly'


def test_out_of_range_clamps():
    assert rank_word(-5) == 'Cowardly'
    assert rank_word(99) == 'Godly'


# drawing --------------------------------------------------------------------

def test_draw_without_points_caches_no_plus_rects(monkeypatch):
    _install_headless(monkeypatch)
    game = _panel_game()
    descend_ui.draw(game, 1280, 720)
    assert game._descend_plus_rects == []


def test_draw_with_points_offers_every_below_cap_attr(monkeypatch):
    _install_headless(monkeypatch)
    game = _panel_game(available_points=3)
    descend_ui.draw(game, 1280, 720)
    offered = {attr for attr, _rect in game._descend_plus_rects}
    assert offered == {a for a in DESCEND_ATTRIBUTES}   # all start at 0


def test_unspent_hint_draws_when_points_available(monkeypatch):
    rendered = []
    _install_headless(monkeypatch)
    from ui import fonts as fonts_mod
    monkeypatch.setattr(fonts_mod, 'draw',
                        lambda text, *a, **k: rendered.append(str(text)))
    game = _panel_game(available_points=1)
    descend_ui.draw(game, 1280, 720)
    assert any('CharPoints available: 1' in t for t in rendered)
    assert any('LEVEL 1' in t for t in rendered)

    rendered.clear()
    game = _panel_game()
    descend_ui.draw(game, 1280, 720)
    assert any('CharPoints available: 0' in t for t in rendered)


# modal wiring ---------------------------------------------------------------

def test_toggle_opens_and_closes(monkeypatch):
    game = _panel_game()
    game._char_stats_open = False
    descend_ui.toggle(game)
    assert game._char_stats_open is True
    game.inv.close.assert_called_once()      # the inventory yields to the panel
    descend_ui.toggle(game)
    assert game._char_stats_open is False


def test_handle_key_closes_on_escape_and_c(monkeypatch):
    monkeypatch.setattr(rl, 'is_key_pressed',
                        lambda key: key == rl.KEY_ESCAPE)
    game = _panel_game()
    game._char_stats_open = True
    assert descend_ui.handle_key(game) is False
    assert game._char_stats_open is False

    monkeypatch.setattr(rl, 'is_key_pressed',
                        lambda key: key == rl.KEY_C)
    game._char_stats_open = True
    assert descend_ui.handle_key(game) is False

    # The frame that opened the panel must not close it again immediately.
    monkeypatch.setattr(rl, 'is_key_pressed', lambda key: key == rl.KEY_C)
    game._char_stats_open = True
    assert descend_ui.handle_key(game, opened_this_frame=True) is True


def test_handle_click_spends_point_and_recalcs(monkeypatch):
    _install_headless(monkeypatch)
    game = _panel_game(available_points=1)
    descend_ui.draw(game, 1280, 720)
    assert game._descend_plus_rects, 'a + button must be offered'
    attr, rect = game._descend_plus_rects[0]
    mx = int(rect.x + rect.width / 2)
    my = int(rect.y + rect.height / 2)
    monkeypatch.setattr(rl, 'is_mouse_button_pressed',
                        lambda b: b == rl.MOUSE_BUTTON_LEFT)
    consumed = descend_ui.handle_click(game, mx, my, 1280, 720)
    assert consumed is True
    assert game.char.descend[attr] == 1
    assert game.char.available_points == 0
    game._recalc_derived_stats.assert_called_once()

    # The refreshed rects no longer offer that attribute (points spent).
    offered = {a for a, _ in game._descend_plus_rects}
    assert attr not in offered


def test_handle_click_outside_rect_is_consumed_without_spend(monkeypatch):
    _install_headless(monkeypatch)
    game = _panel_game(available_points=1)
    descend_ui.draw(game, 1280, 720)
    monkeypatch.setattr(rl, 'is_mouse_button_pressed',
                        lambda b: b == rl.MOUSE_BUTTON_LEFT)
    assert descend_ui.handle_click(game, 5, 5, 1280, 720) is True
    assert game.char.available_points == 1
    game._recalc_derived_stats.assert_not_called()


import pytest  # noqa: E402  (fixture uses pytest below import block)
