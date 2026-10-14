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

"""D2-style frame-data breakpoint math.

The simulation runs on a variable timestep (one update per rendered frame);
the 30 Hz grid in this module is only the quantization basis for gameplay
animation/cooldown durations, so all gameplay-relevant durations are
expressed as integer tick counts derived from D2-authored frame values and
community D2 frame tables remain a valid authoring reference (1 D2 frame
@25 Hz = 1.2 ticks @30 Hz).

Speed stats are quantized: `effective_ticks()` applies the D2
`ceil(base * 100 / (100 + EIAS))` formula in tick space, which means
intermediate stat values intentionally have NO effect until a threshold that
reduces the ceiling by one tick is crossed.
"""

import math

# ── Tick constants ────────────────────────────────────────────────────────
SIM_HZ        = 30
TICK_SECONDS  = 1.0 / SIM_HZ
MAX_CATCHUP_TICKS = 5          # panic budget per rendered frame

# ── D2 frame-data constants ───────────────────────────────────────────────
D2_HZ          = 25
D2_FRAME_TICKS = SIM_HZ / D2_HZ     # 1.2 ticks per D2 frame

# Base attack animation, authored in D2 frames from the legacy wall-clock rate.
# ATTACK_RATE = 0.6 attacks/s → 1/0.6 s per attack → 25/0.6 D2 frames → 50 ticks.
PLAYER_BASE_ATTACK_FRAMES = D2_HZ / 0.6          # 41.667 D2 frames

# ── Core breakpoint math ──────────────────────────────────────────────────

def effective_ticks(base_d2_frames: float, speed_pct: float = 0.0) -> int:
    """Quantized animation length in whole sim ticks.

    `speed_pct` is the summed speed stat as a fraction (0.10 = +10% IAS/FCR/...).
    Uses the D2 shape: effective = ceil(base * 100 / (100 + EIAS)) with
    EIAS = speed_pct * 100, applied to the base duration expressed in ticks
    (base_d2_frames * 1.2). Intermediate values have no effect.
    """
    if speed_pct <= -1.0:
        speed_pct = -0.99          # guard: animation can't invert
    eias = speed_pct * 100.0
    base_ticks = base_d2_frames * D2_FRAME_TICKS
    # tiny epsilon guards ceil against float noise on exact bases (e.g. 50.0)
    return max(1, math.ceil(base_ticks * 100.0 / (100.0 + eias) - 1e-9))


def effective_frames(base_d2_frames: float, speed_pct: float = 0.0) -> float:
    """Effective animation length in D2-frame units (display/authoring only).

    Derived from the tick-quantized duration, so it always agrees with
    `effective_ticks` (frames = ticks / 1.2, fractional).
    """
    return effective_ticks(base_d2_frames, speed_pct) / D2_FRAME_TICKS


def frames_to_ticks(d2_frames: float) -> int:
    """Convert D2 frames to whole sim ticks (1 D2 frame = 1.2 ticks @30 Hz)."""
    return max(1, round(d2_frames * D2_FRAME_TICKS))


def frames_to_seconds(d2_frames: float) -> float:
    """Wall-clock seconds for a (possibly fractional) D2-frame duration."""
    return frames_to_ticks(d2_frames) * TICK_SECONDS


def attack_seconds(base_d2_frames: float, speed_pct: float = 0.0) -> float:
    """Cooldown/animation duration in seconds for a speed-quantized action."""
    return effective_ticks(base_d2_frames, speed_pct) * TICK_SECONDS


def breakpoint_table(base_d2_frames: float, max_entries: int = 12) -> list:
    """Ascending speed breakpoints for a base animation (HUD/tools/QA).

    Returns [(speed_pct, effective_frames, ticks_at_30hz, seconds), ...]
    starting at 0% speed, one entry per tick-length reduction.
    """
    out = []
    t_prev = effective_ticks(base_d2_frames, 0.0)
    out.append((0.0, t_prev / D2_FRAME_TICKS, t_prev, t_prev * TICK_SECONDS))
    pct = 0.0
    step = 0.1
    while len(out) < max_entries and pct < 300.0:
        pct += step
        t = effective_ticks(base_d2_frames, pct / 100.0)
        if t < t_prev:
            t_prev = t
            out.append((pct / 100.0, t / D2_FRAME_TICKS, t, t * TICK_SECONDS))
    return out


# ── Frame tables ─────────────────────────────────────────────
# Authored in D2 frames; `event_frame` = frame at which damage/launch fires.
# Monster entries take an optional per-instance speed stat in the future.

FRAME_TABLES = {
    # Player
    'player.attack.melee':   {'d2_frames': PLAYER_BASE_ATTACK_FRAMES, 'ias_applies': True},
    'player.hit_recovery':   {'d2_frames': 5,  'fhr_applies': True},   # reserved (Phase 2b+)
    'player.block':          {'d2_frames': 7,  'fbr_applies': True},   # reserved
    'player.cast.default':   {'d2_frames': 14, 'fcr_applies': True},   # reserved
    # Monsters (base cooldowns from legacy constants; frames = seconds * 25)
    'monster.zombie.attack': {'d2_frames': 1.1 * D2_HZ},   # ATTACK_CD = 1.1 s
    'monster.slime.attack':  {'d2_frames': 10.0 * D2_HZ},  # SLIME_ATTACK_CD = 10 s
}
