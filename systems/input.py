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

"""Per-tick, per-consumer input edges for the 30 Hz fixed timestep.

raylib's ``is_key_pressed`` / ``is_mouse_button_pressed`` flags are true for
exactly one RENDER frame.  With uncapped rendering (and a fast draw) most
render frames run zero simulation ticks, so sampling those raw flags once per
tick silently drops most presses.  This module instead derives edges from the
persistent ``is_*_down`` state at the next simulation tick.

State is keyed by ``(consumer, key_or_button)``.  Each consumer therefore
observes one rising/falling edge for its own physical transition, while repeated
queries by that consumer during the same physical state remain quiet.  The
consumer argument is required so competing gameplay/UI systems cannot consume
one another's input.

When the window loses focus all previous state is discarded.  On the first
focused query after regaining focus, current down-state is resynchronized, so
controls held while the application was in the background do not create phantom
presses or releases.  Raw raylib edge flags remain appropriate for draw-phase
code that runs exactly once per render frame.
"""

import pyray as rl

_key_prev: dict[tuple[object, int], bool] = {}
_mouse_prev: dict[tuple[object, int], bool] = {}
_mouse_release_prev: dict[tuple[object, int], bool] = {}
_focus_was = True

# Physical keys whose printed glyph can be a Latin letter on some layout.
# A-Z covers QWERTY/AZERTY/Colemak; punctuation covers Dvorak (W is comma).
_LAYOUT_SCAN_KEYS = (
    *range(rl.KEY_A, rl.KEY_Z + 1),
    rl.KEY_APOSTROPHE, rl.KEY_COMMA, rl.KEY_MINUS, rl.KEY_PERIOD,
    rl.KEY_SLASH, rl.KEY_SEMICOLON, rl.KEY_EQUAL,
    rl.KEY_LEFT_BRACKET, rl.KEY_RIGHT_BRACKET, rl.KEY_BACKSLASH,
    rl.KEY_GRAVE,
    *range(rl.KEY_ZERO, rl.KEY_NINE + 1),
)


def _focus_lost_or_resync() -> bool:
    """Return whether input should be suppressed while unfocused.

    On focus loss, discard stale state.  On focus regain, seed every previously
    tracked key/button with its current state before the caller samples one.
    """
    global _focus_was

    focused = rl.is_window_focused()
    if not focused:
        if _focus_was:
            for state_key in tuple(_key_prev):
                _key_prev[state_key] = False
            for state_key in tuple(_mouse_prev):
                _mouse_prev[state_key] = False
            for state_key in tuple(_mouse_release_prev):
                _mouse_release_prev[state_key] = False
        _focus_was = False
        return True

    if not _focus_was:
        for (consumer, key), _ in tuple(_key_prev.items()):
            _key_prev[(consumer, key)] = rl.is_key_down(key)
        for (consumer, button), _ in tuple(_mouse_prev.items()):
            _mouse_prev[(consumer, button)] = rl.is_mouse_button_down(button)
        for (consumer, button), _ in tuple(_mouse_release_prev.items()):
            _mouse_release_prev[(consumer, button)] = rl.is_mouse_button_down(button)
    _focus_was = True
    return False


def _key_label(key: int) -> str:
    """Unshifted glyph of ``key`` on the active OS layout, or ''."""
    try:
        name = rl.glfw_get_key_name(key, 0)
    except Exception:
        return ''
    if not name:
        return ''
    return str(name).lower()


def layout_key(key: int) -> int:
    """Physical key that types ``key``'s US letter on the active layout.

    Raylib names keys after US QWERTY positions, so ``KEY_Q`` is the key
    where Q sits on an English keyboard. Skill hotkeys are the letters
    Q/W/E/R/T: the key that types that letter must cast the skill on
    AZERTY, Dvorak, Colemak and any other Latin layout, without the player
    switching the OS language to English. A layout with no such Latin
    letter (Cyrillic, Greek, Arabic, ...) keeps the US position, which is
    the Latin legend those keyboards still print.
    """
    # KEY_A..KEY_Z are the ASCII codes, so chr(KEY_Q) == 'Q'.
    if key < rl.KEY_A or key > rl.KEY_Z:
        return key
    want = chr(key).lower()
    for candidate in _LAYOUT_SCAN_KEYS:
        if _key_label(candidate) == want:
            return candidate
    return key


def key_pressed(consumer: object, key: int) -> bool:
    """Return one rising edge for ``consumer`` and ``key``."""
    if _focus_lost_or_resync():
        return False

    state_key = (consumer, key)
    down = rl.is_key_down(key)
    prev = _key_prev.get(state_key, False)
    _key_prev[state_key] = down
    return down and not prev


def mouse_pressed(consumer: object, button: int) -> bool:
    """Return one rising edge for ``consumer`` and ``button``."""
    if _focus_lost_or_resync():
        return False

    state_key = (consumer, button)
    down = rl.is_mouse_button_down(button)
    prev = _mouse_prev.get(state_key, False)
    _mouse_prev[state_key] = down
    _mouse_release_prev[state_key] = down
    return down and not prev


def mouse_released(consumer: object, button: int) -> bool:
    """Return one falling edge for ``consumer`` and ``button``.

    A release is reported only if that consumer previously observed the button
    down, so a button already up on the consumer's first query is not spurious.
    """
    if _focus_lost_or_resync():
        return False

    state_key = (consumer, button)
    down = rl.is_mouse_button_down(button)
    prev = _mouse_release_prev.get(state_key, False)
    _mouse_release_prev[state_key] = down
    return (not down) and prev
