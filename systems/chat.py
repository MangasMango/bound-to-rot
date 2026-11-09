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

"""PoE-style chat constants + fading (issue: chat console bottom-left).

The chat replaces the old full-width `~` dev console: history floats in the
bottom-left corner and fades with age while the chat is closed (PoE look),
with a translucent box + input row only while it is open. All values live
here, module-constants-first (the systems/recorder.py precedent); no
settings UI yet.

Log entries are (prompt, output, birth) triples from Game._exec_console;
`chat_line_alpha` is the pure fade math the HUD calls per row (clock passed
in by the caller so tests do not need a window).
"""

CHAT_OPEN_LINES    = 8      # history rows visible while the chat is open
CHAT_CLOSED_LINES  = 3      # lingering rows while the chat is closed
CHAT_FADE_SECS     = 8.0    # closed rows fade 220 -> 0 across this
CHAT_TEXT_ALPHA    = 220    # full-alpha rows (matches the old console)
CHAT_LOG_CAP       = 100    # _chat_log retention (was 20 pre-fading)
CHAT_SEND_HISTORY_CAP = 50  # submitted-command recall (unchanged)

CHAT_PANEL_RATIO   = 0.3    # open-panel width as a share of window width
CHAT_PANEL_MAX_W   = 560    # ...but never wider than this
CHAT_BOX_ALPHA     = 190    # translucent black behind the open chat
CHAT_MARGIN        = 8      # left/bottom margin of the chat
CHAT_ROW_PX        = 18     # one history row at font size 25
CHAT_INPUT_PX      = 30     # the input row at font size 27


def chat_line_alpha(birth: float, now: float) -> int:
    """Per-line fade alpha for a closed chat: CHAT_TEXT_ALPHA -> 0 linearly
    across CHAT_FADE_SECS. Fresh lines (age <= 1 s) hold full alpha so the
    newest rows do not start mid-fade."""
    age = now - birth
    if age <= 1.0:
        return CHAT_TEXT_ALPHA
    if age >= CHAT_FADE_SECS:
        return 0
    return int(CHAT_TEXT_ALPHA * (1.0 - (age - 1.0) / (CHAT_FADE_SECS - 1.0)))
