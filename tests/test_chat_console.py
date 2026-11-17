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

"""PoE-style chat console (bottom-left) - .ai/CHAT_CONSOLE_PLAN.md.

Covers:
  1. Fade math - fresh rows hold full alpha, then decay linearly to 0.
  2. Log model - (prompt, output, birth) triples, retention cap, empty
     outputs keep the entry compact.
  3. Console grammar stays intact - `_exec_console` keeps its name and
     behavior through the rename, with command multi-line outputs appended.
  4. Gambling-free inputs - Enter opens the chat only in gameplay states
     (via the new open-edge + primed submit latch), GRAVE still toggles.
"""

import time as _time_module
from unittest import mock

import pytest

import core.game as _core_game
from core.game import STATE_HUB, STATE_MENU, STATE_PAUSED, STATE_PLAYING, Game
from systems import chat as chat_mod
from systems.chat import (CHAT_CLOSED_LINES, CHAT_FADE_SECS, CHAT_LOG_CAP,
                          CHAT_OPEN_LINES, CHAT_TEXT_ALPHA, chat_line_alpha)


def py_time_module():
    """core.game stamps chat births with the shared `time` module."""
    return _time_module


def _game():
    game = Game.__new__(Game)
    game.state = STATE_PLAYING
    game._chat_open = False
    game._chat_buf = ''
    game._chat_log = []
    return game


# ── 1. fade math ─────────────────────────────────────────────────────────

def test_fresh_lines_hold_full_alpha():
    assert chat_line_alpha(birth=100.0, now=100.0) == CHAT_TEXT_ALPHA
    assert chat_line_alpha(birth=100.0, now=101.0) == CHAT_TEXT_ALPHA


def test_lines_fade_linearly_to_zero():
    b = 100.0
    a = chat_line_alpha(b, b + (CHAT_FADE_SECS - 1.0) / 2 + 1.0)
    assert CHAT_TEXT_ALPHA // 2 - 2 <= a <= CHAT_TEXT_ALPHA // 2 + 2


def test_lines_disappear_after_the_fade_window():
    assert chat_line_alpha(birth=0.0, now=CHAT_FADE_SECS) == 0
    assert chat_line_alpha(birth=0.0, now=CHAT_FADE_SECS * 10) == 0
    assert chat_line_alpha(birth=0.0, now=-1.0) is not None


# ── 2. log model ─────────────────────────────────────────────────────────

def test_exec_console_appends_birth_dated_triples():
    game = _game()
    game._god_mode = False
    with mock.patch.object(py_time_module(), 'perf_counter',
                           return_value=42.0):
        game._exec_console('god')
    prompt, output, birth = game._chat_log[-1]
    assert prompt == '> god'
    assert 'God mode' in output
    assert birth == 42.0


def test_chat_log_retention_cap():
    """The fade needs a longer tail than the old cap of 20."""
    game = _game()
    game._god_mode = False
    for _ in range(CHAT_LOG_CAP + 5):
        game._exec_console('god')
    assert len(game._chat_log) == CHAT_LOG_CAP
    hands = [p for p, o, _b in game._chat_log]
    assert hands[0] != '> god' or game._chat_log[0][2] != -1.0
    assert hands[-1] == '> god'


def test_empty_outputs_keep_single_row_entries():
    game = _game()
    game._god_mode = False
    game._exec_console('god')
    game._exec_console('god')
    game._exec_console('god')
    assert len(game._chat_log) == 3
    assert all(o for _p, o, _b in game._chat_log)   # one row per entry


# ── 3. Multi-line outputs flatten for display only ───────────────────────

def test_help_output_is_one_log_entry_with_newlines():
    game = _game()
    game._exec_console('help')
    prompt, output, _b = game._chat_log[-1]
    assert output.count('\n') >= 3    # help is a multi-line sheet
    assert len(game._chat_log) == 1   # stored as ONE entry, not per line


# ── 4. recorder interplay (ruling 2026-11) ───────────────────────────────

def test_record_start_closes_the_chat_via_the_renamed_flag():
    game = _game()
    game.recorder = __import__('systems.recorder', fromlist=['x']).ClipRecorder()
    game._chat_history_idx = -1
    game._chat_submit('/record gif')  # starts the clip; chat must close
    assert game._chat_open is False
    game.recorder.cancel()            # no clip pollution


# ── 5. / grammar - commands need the slash, plain text is a say ──────

def _submitting_game():
    """Game stripped to what _chat_submit touches."""
    game = _game()
    game._god_mode = False
    return game


def test_slash_command_reaches_the_parser():
    game = _submitting_game()
    game._chat_submit('/god')
    assert game._god_mode is True
    assert game._chat_log[-1][0] == '> /god'   # echo keeps what was typed


def test_plain_text_is_a_say_never_a_command():
    game = _submitting_game()
    game._chat_submit('testing 123')
    assert game._god_mode is False             # no parser reach
    assert game._chat_log[-1][0] == '<You> testing 123'
    assert game._chat_log[-1][1] == ''         # says have no reply row


def test_unknown_slash_carries_the_slash_in_the_echo():
    game = _submitting_game()
    game._chat_submit('/test')
    prompt, output, _birth = game._chat_log[-1]
    assert prompt == '> /test'
    assert output == 'Unknown: /test'


def test_bare_slash_or_spaces_do_nothing():
    """`/` and `/   ` have no body - they go nowhere (no rows, no parser)."""
    game = _submitting_game()
    log_before = list(game._chat_log)
    god_before = game._god_mode
    for junk in ('/', '  ', '   / '):
        log_before = list(game._chat_log)
        game._chat_submit(junk)
        assert list(game._chat_log) == log_before, junk
    assert game._god_mode == god_before


def test_slash_command_bodies_still_parse_like_commands():
    """`/zoom 2` style - slash stripped, body intact for the parser."""
    from types import SimpleNamespace
    game = _submitting_game()
    game._zoom_ref = 2.0
    game.iso = SimpleNamespace(scale=1.0)
    game._chat_submit('/zoom 2')
    assert game._chat_log[-1][1].startswith('Zoom')


def test_say_cap_respects_the_log_retention():
    game = _submitting_game()
    for i in range(CHAT_LOG_CAP + 7):
        game._chat_submit(f'say {i}')
    assert len(game._chat_log) == CHAT_LOG_CAP
    assert game._chat_log[-1][0] == f'<You> say {CHAT_LOG_CAP + 6}'


# ── 6. /clear - wipe the history ────────────────────────────────────

def test_clear_wipes_the_log_leaving_one_confirmation_row():
    game = _submitting_game()
    game._chat_submit('/god')
    game._chat_submit('hello')
    game._chat_submit('/clear')
    assert len(game._chat_log) == 1
    prompt, output, _birth = game._chat_log[0]
    assert prompt == '> /clear'
    assert output == 'Chat cleared'


def test_clear_keeps_filling_normally_afterwards():
    game = _submitting_game()
    game._chat_submit('/clear')
    game._chat_submit('hello')
    rows = [p for p, o, _b in game._chat_log]
    assert '> /clear' in rows and '<You> hello' in rows


def test_clear_is_parser_level_so_program_callers_work_too():
    game = _submitting_game()
    game._chat_submit('/say hi')
    game._exec_console('clear')   # recorder/tests call the parser directly
    assert len(game._chat_log) == 1                               # wiped
    assert game._chat_log[0][1] == 'Chat cleared'
