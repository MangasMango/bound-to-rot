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

"""Frame-data breakpoint math tests (systems/frames.py)."""

import math
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from systems import frames


def test_baseline_attack_cooldown_preserved():
    """0% IAS must land within ~1 tick of the legacy 1/0.6 s attack rate."""
    cd = frames.attack_seconds(frames.PLAYER_BASE_ATTACK_FRAMES, 0.0)
    assert cd == frames.frames_to_ticks(frames.PLAYER_BASE_ATTACK_FRAMES) * frames.TICK_SECONDS
    assert abs(cd - 1.0 / 0.6) <= frames.TICK_SECONDS


def test_frames_to_ticks_positive_and_whole():
    for f in [0.5, 1, 5, 13, 41.667, 250]:
        t = frames.frames_to_ticks(f)
        assert isinstance(t, int) and t >= 1
    assert frames.frames_to_ticks(5) == 6          # 5 * 1.2
    assert frames.frames_to_ticks(10) == 12


def test_intermediate_speed_values_have_no_effect():
    """Core D2 property: stats between breakpoints quantize identically."""
    base = frames.PLAYER_BASE_ATTACK_FRAMES
    t0 = frames.effective_ticks(base, 0.0)
    # tiny values below the first threshold change nothing
    for pct in (0.001, 0.005, 0.01, 0.02):
        assert frames.effective_ticks(base, pct) == t0, pct
    # and anywhere inside a breakpoint band the result is flat
    t1 = frames.effective_ticks(base, 0.10)
    for pct in (0.09, 0.095, 0.10, 0.105, 0.11):
        assert frames.effective_ticks(base, pct) == t1, pct


def test_more_speed_never_slower():
    base = frames.PLAYER_BASE_ATTACK_FRAMES
    prev = None
    for i in range(0, 3000):
        t = frames.effective_ticks(base, i / 1000.0)
        if prev is not None:
            assert t <= prev
        prev = t


def test_effective_frames_agrees_with_ticks():
    base = 13.0
    for pct in (0.0, 0.08, 0.16, 0.27, 0.42, 1.0, 2.0):
        assert frames.effective_frames(base, pct) == \
            frames.effective_ticks(base, pct) / frames.D2_FRAME_TICKS


def test_breakpoints_match_d2_formula():
    """Tick-space formula: ceil(base_ticks * 100 / (100 + EIAS))."""
    base = 13.0
    for pct in (0.0, 0.08, 0.16, 0.27, 0.42):
        eias = pct * 100.0
        expected = max(1, math.ceil(base * frames.D2_FRAME_TICKS * 100.0 / (100.0 + eias)))
        assert frames.effective_ticks(base, pct) == expected, pct


def test_breakpoint_table_shape():
    table = frames.breakpoint_table(frames.PLAYER_BASE_ATTACK_FRAMES, max_entries=6)
    assert table[0][0] == 0.0
    assert len(table) <= 6
    # strictly decreasing frame counts, increasing speed
    speeds = [row[0] for row in table]
    frs = [row[1] for row in table]
    assert frs == sorted(frs, reverse=True)
    assert speeds == sorted(speeds)
    assert all(b > a for a, b in zip(speeds, speeds[1:]))


def test_zombie_attack_cd_quantized():
    """Legacy 1.1 s zombie attack snaps to a whole-tick duration."""
    from entities.zombies import ZOMBIE_ATTACK_CD_S, SLIME_ATTACK_CD_S
    assert abs(ZOMBIE_ATTACK_CD_S - 1.1) <= frames.TICK_SECONDS
    assert abs(SLIME_ATTACK_CD_S - 10.0) <= frames.TICK_SECONDS
    # both are exact multiples of the tick length
    assert math.isclose(ZOMBIE_ATTACK_CD_S / frames.TICK_SECONDS,
                        round(ZOMBIE_ATTACK_CD_S / frames.TICK_SECONDS))
    assert math.isclose(SLIME_ATTACK_CD_S / frames.TICK_SECONDS,
                        round(SLIME_ATTACK_CD_S / frames.TICK_SECONDS))


def test_frame_tables_present():
    for key in ('player.attack.melee', 'monster.zombie.attack',
                'monster.slime.attack', 'player.hit_recovery',
                'player.block', 'player.cast.default'):
        assert key in frames.FRAME_TABLES
        assert frames.FRAME_TABLES[key]['d2_frames'] > 0
