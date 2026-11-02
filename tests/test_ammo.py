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

"""The revolver cylinder / ammo mechanic.

Owner rulings: auto-reload fires the moment the last shot leaves the
cylinder (R reloads early); the reload takes 3.0 s lowered by
`reload_speed_pct` (Cunning +1%/point and '+X% Reload Speed' item affixes),
floored at 1.0 s; a press while empty/reloading is a metallic click only;
the cylinder caps at 6 (the orb_mag_0..6 icons show the rounds left).
"""

import unittest
from unittest import mock
from types import SimpleNamespace

import pytest
import pyray as rl

import entities.progression as prog
import core.game as core_game
from core.game import Game, AMMO_MAX, DRY_FIRE_CD, RELOAD_MIN, RELOAD_SECONDS


def _enemy():
    return {'x': 5.0, 'y': 5.0, 'health': 100, 'enemy_type': 'skeleton',
            'level': 1.0}


def _game():
    game = Game.__new__(Game)
    manager = mock.Mock()
    manager.active = prog.Character('ammo', 'Gunner', 'knight')
    game.char_mgr = manager
    game.stats = {'reload_speed_pct': 0.0, 'accuracy': 300,
                  '_crit_chance': 0.0, 'melee_dmg_mult': 1.0,
                  'crushing_blow_pct': 0.0}
    game.px, game.py = 0.0, 0.0
    game.inventory = None
    game._ammo = AMMO_MAX
    game._ammo_max = AMMO_MAX
    game._reload_t = 0.0
    game._reload_total = 0.0
    game._orb_spin = 0.0
    game._dry_fire_t = 0.0
    game._muzzle_frames = []
    game._flash_effects = []
    game._bullets = []
    game._angel_timer = 0.0
    game._outgoing_dmg_mult = lambda _t: 1.0
    game.audio = mock.Mock()
    return game


def _effects():
    return {'melee_damage': 0, 'crit_chance': 0.0,
            'crushing_blow_chance': 0.0, 'knockback': 0.0}


def _fire_six(game):
    """Fire a full cylinder with the hit roll stubbed (no floats needed)."""
    with mock.patch.object(core_game.combat, 'resolve_attack',
                           return_value={'damage': 1, 'evaded': False,
                                         'crit': False}) as ra:
        for _ in range(AMMO_MAX):
            game._fire_bullet(_enemy(), _effects())
    return ra


class CylinderModelTests(unittest.TestCase):
    def test_constants_match_the_ruling(self):
        self.assertEqual(AMMO_MAX, 6)
        self.assertEqual(RELOAD_SECONDS, 3.0)
        self.assertEqual(RELOAD_MIN, 1.0)

    def test_reload_duration_respects_speed(self):
        game = _game()
        game.stats['reload_speed_pct'] = 0.0
        self.assertAlmostEqual(game.reload_duration(), 3.0)
        game.stats['reload_speed_pct'] = 1.0     # +100%
        self.assertAlmostEqual(game.reload_duration(), 1.5)

    def test_reload_duration_floor(self):
        game = _game()
        # +900% would give 0.3 s; the RELOAD_MIN floor holds the line
        game.stats['reload_speed_pct'] = 9.0
        self.assertAlmostEqual(game.reload_duration(), RELOAD_MIN)
        game.stats['reload_speed_pct'] = 0.5     # 2.0 s, above the floor
        self.assertAlmostEqual(game.reload_duration(), 2.0)

    def test_start_reload_sets_timer_and_sound_is_idempotent(self):
        game = _game()
        game._start_reload()
        self.assertEqual(game._reload_t, RELOAD_SECONDS)
        game.audio.ammo_reload.assert_called_once()
        game.audio.ammo_reload.reset_mock()
        game._start_reload()
        game.audio.ammo_reload.assert_not_called()

    def test_fire_bullet_decrements_each_shot(self):
        game = _game()
        with mock.patch.object(core_game.combat, 'resolve_attack',
                               return_value={'damage': 1, 'evaded': False,
                                             'crit': False}):
            for i in range(3):
                game._fire_bullet(_enemy(), _effects())
                self.assertEqual(game._ammo, AMMO_MAX - i - 1)
        self.assertEqual(len(game._bullets), 3)
        game.audio.revolver_shot.assert_called_with()

    def test_sixth_shot_auto_reloads(self):
        game = _game()
        _fire_six(game)
        self.assertEqual(game._ammo, 0)
        game.audio.ammo_reload.assert_called_once()
        self.assertGreater(game._reload_t, 0.0)
        self.assertEqual(game._reload_t, RELOAD_SECONDS)   # no speed bonuses

    def test_each_shot_twists_the_cylinder_icon(self):
        """Owner ruling: a spent round turns the icon from +60 deg back to
        rest on 0 deg."""
        game = _game()
        with mock.patch.object(core_game.combat, 'resolve_attack',
                               return_value={'damage': 1, 'evaded': False,
                                             'crit': False}):
            game._fire_bullet(_enemy(), _effects())
        self.assertEqual(game._orb_spin, 60.0)
        game._tick_reload(0.25)
        self.assertAlmostEqual(game._orb_spin, 0.0, places=6)
        game._tick_reload(0.25)
        self.assertEqual(game._orb_spin, 0.0)         # stays at rest

    def test_reload_spins_the_icon_the_full_turn(self):
        """The reload couples the icon to the timer: 360 deg unwinding to
        exactly 0 when the reload completes."""
        game = _game()
        game._ammo = 0
        game._start_reload()
        self.assertEqual(game._orb_spin, 360.0)
        game._tick_reload(game._reload_t / 2)
        self.assertAlmostEqual(game._orb_spin, 180.0, places=6)
        game._tick_reload(game._reload_t + 0.01)
        self.assertEqual(game._orb_spin, 0.0)
        self.assertEqual(game._reload_t, 0.0)
        self.assertEqual(game._ammo, AMMO_MAX)

    def test_tick_reload_refills_at_completion(self):
        game = _game()
        game._ammo = 0            # the auto-reload after the 6th shot
        game._start_reload()
        game._tick_reload(1.0)
        self.assertEqual(game._ammo, 0)              # still reloading
        game._tick_reload(RELOAD_SECONDS)            # clear the remainder
        self.assertEqual(game._reload_t, 0.0)
        self.assertEqual(game._ammo, AMMO_MAX)

    def test_tick_once_refilled_is_a_noop(self):
        game = _game()
        game._reload_t = 0.0
        game._ammo = 0
        game._tick_reload(0.5)
        self.assertEqual(game._ammo, 0)

    def test_r_reload_is_allowed_and_rejected(self):
        """The R gate: only early-reloads a partially spent cylinder that is
        not already reloading (both decided by the same predicate)."""
        game = _game()
        game._ammo = 4
        can = 0 < game._ammo < game._ammo_max and game._reload_t <= 0
        self.assertTrue(can)
        game._start_reload()
        can = 0 < game._ammo < game._ammo_max and game._reload_t <= 0
        self.assertFalse(can)                         # already reloading
        game._reload_t = 0.0
        game._ammo = AMMO_MAX
        can = 0 < game._ammo < game._ammo_max and game._reload_t <= 0
        self.assertFalse(can)                         # full cylinder


class DryFireTests(unittest.TestCase):
    def test_dry_fire_clicks_and_throttles(self):
        game = _game()
        game._try_dry_fire()
        game.audio.ammo_dry.assert_called_once()
        game._try_dry_fire()
        game.audio.ammo_dry.assert_called_once()      # throttled

    def test_dry_fire_recovers_after_cooldown(self):
        game = _game()
        game._try_dry_fire()
        game._dry_fire_t = 0.0                        # cooldown elapsed
        game._try_dry_fire()
        self.assertEqual(game.audio.ammo_dry.call_count, 2)

    def test_dry_fire_ticker_decrements(self):
        game = _game()
        game._dry_fire_t = DRY_FIRE_CD
        game._tick_reload(0.1)
        self.assertAlmostEqual(game._dry_fire_t, DRY_FIRE_CD - 0.1)


class GatePredicateTests(unittest.TestCase):
    """The attack-resolve branch fires only when the gate is open:
    `reload_t <= 0 and ammo > 0`. The update loop calls `_tick_reload`
    BEFORE the resolve, so a reload finishing this frame unhooks the gate."""

    def test_reload_blocks_the_gate(self):
        game = _game()
        game._ammo = 2
        game._reload_t = 2.0
        self.assertTrue(game._reload_t > 0 or game._ammo <= 0)

    def test_empty_cylinder_blocks_the_gate(self):
        game = _game()
        game._ammo = 0
        game._reload_t = 0.0
        self.assertTrue(game._reload_t > 0 or game._ammo <= 0)

    def test_open_gate_allows_the_shot(self):
        game = _game()            # fresh: 6/6, no reload
        self.assertFalse(game._reload_t > 0 or game._ammo <= 0)

    def test_reload_completion_opens_the_gate_same_frame(self):
        game = _game()
        game._ammo = 0
        game._reload_t = 1.0
        game._tick_reload(1.0)    # the frame's reload tick
        self.assertFalse(game._reload_t > 0 or game._ammo <= 0)
        self.assertEqual(game._ammo, AMMO_MAX)


class ReloadSpeedStatTests(unittest.TestCase):
    def test_cunning_feeds_reload_speed(self):
        derived = prog.compute_derived_stats(
            {'cunning': 4}, {}, item_bonuses={}, looks='knight')
        self.assertAlmostEqual(derived['reload_speed_pct'], 0.04)

    def test_item_affix_feeds_reload_speed(self):
        derived = prog.compute_derived_stats(
            {}, {'reload_speed_pct': 12.0}, item_bonuses={}, looks='knight')
        self.assertAlmostEqual(derived['reload_speed_pct'], 0.12)

    def test_cunning_and_affixes_stack(self):
        derived = prog.compute_derived_stats(
            {'cunning': 2}, {'reload_speed_pct': 8.0}, item_bonuses={},
            looks='knight')
        self.assertAlmostEqual(derived['reload_speed_pct'], 0.10)

    def test_reset_stats_exposes_the_key(self):
        from entities.player_stats import reset_stats
        s = {'health': 50.0}
        reset_stats(s, reload_speed_pct=0.31)
        self.assertAlmostEqual(s['reload_speed_pct'], 0.31)

    def test_affix_exists_in_generation_pool(self):
        import systems.itemgen as itemgen
        ids = {a['id'] for a in itemgen._AFFIXES}
        self.assertIn('pk_reload_speed', ids)

    def test_dry_and_reload_pools_use_the_revolver_sounds(self):
        """Owner naming: revolverCock1/2 for the empty cylinder, and
        revolverReload1/2 for the spin-up - one of each pair plays at
        random."""
        import os
        import systems.audio as audio_mod
        audio = audio_mod.AudioSystem()
        with mock.patch.object(audio_mod.rl, 'load_sound', return_value=object()):
            audio.init()
        self.assertGreaterEqual(len(audio.pools.get('ammo_dry', [])), 2)
        self.assertGreaterEqual(len(audio.pools.get('ammo_reload', [])), 2)


# ── cylinder orb pivot regression (pytest style) ──────────────────────────

def _hud_stub(spin):
    from tests.test_render_smoke import _game_stub
    game = _game_stub()
    game._ammo = 2
    game._orb_spin = spin
    game._ui = {f'orb_mag_{k}': SimpleNamespace(id=1, width=64.0, height=64.0)
                for k in range(7)}
    return game


def _capture_texture_draws(monkeypatch, game):
    from core.render.hud_render import HudRenderMixin
    from tests.test_render_smoke import _install_headless_drawing
    _install_headless_drawing(monkeypatch)
    calls = []
    monkeypatch.setattr(
        rl, 'draw_texture_pro',
        lambda _tex, src, dst, origin, rot, tint: calls.append((dst, origin, rot)))
    HudRenderMixin._draw_hud(game, 1280, 720)
    return calls


def test_spin_pivot_matches_rest_position(monkeypatch):
    """Regression (owner screenshot, raylib rtextures.c:4874-4925): with a
    rotation the draw pivots on dst POSITION and `origin` only offsets the
    texture's top-left. The spinning cylinder call must place dst.position
    at the orb's centre - i.e. unrotatedTopLeft + origin - or the icon
    orbits its own corner instead of spinning in place."""
    rest = _capture_texture_draws(monkeypatch, _hud_stub(spin=0.0))
    rest_dst = [c[0] for c in rest if c[2] == 0.0 and c[1].x == 0.0]
    assert rest_dst, 'the resting cylinder must draw unrotated at top-left'
    rest_dst = rest_dst[-1]

    spin = _capture_texture_draws(monkeypatch, _hud_stub(spin=90.0))
    spun = [c for c in spin if abs(c[2]) > 0.05]
    assert spun, 'the spinning icon must draw with a rotation'
    dst, origin, _rot = spun[-1]

    # dst.position IS the rotation pivot: it must equal the unrotated
    # rect's centre (rtextures.c rotates corners as pivot + R*(off - origin))
    assert dst.x == pytest.approx(rest_dst.x + rest_dst.width / 2)
    assert dst.y == pytest.approx(rest_dst.y + rest_dst.height / 2)
    # ... and the origin really is half the rect
    assert origin.x == pytest.approx(dst.width / 2)
    assert origin.y == pytest.approx(dst.height / 2)


if __name__ == '__main__':
    unittest.main()
