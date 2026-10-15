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

import pyray as rl

from ui import fonts


class ChartRenderMixin:
    def _draw_delve_choice_ui(self, cw: int, ch: int):
        if self._delve is None:
            return
        d = self._delve

        if self._delve_chart_is_open():
            content, x_clicked = self._draw_anima_panel(cw, ch)
            if x_clicked:
                self._close_delve_anima_panel()
            else:
                self._chart_screen.draw(cw, ch, origin=(content.x, content.y),
                                         view=(content.width, content.height))
            return

        if d['state'] == 'clearing':
            return

        if d['state'] == 'ready':
            hint = 'Click the Pulse to descend'
            hw = fonts.measure(hint, 18)
            rl.draw_rectangle((cw - hw - 24) // 2, ch - 55, hw + 24, 32,
                               rl.Color(8, 8, 18, 200))
            fonts.draw(hint, (cw - hw) // 2, ch - 48, 18,
                         rl.Color(200, 175, 90, 255))
            return

        if d['state'] == 'arriving':
            msg   = 'Wave approaching...'
            msg_w = fonts.measure(msg, 18)
            rl.draw_rectangle((cw - msg_w - 24) // 2, ch - 55, msg_w + 24, 32,
                               rl.Color(8, 8, 18, 200))
            fonts.draw(msg, (cw - msg_w) // 2, ch - 48, 18,
                         rl.Color(200, 160, 80, 255))
            return

        if d['state'] == 'junction':
            self._draw_delve_junction(cw, ch)
            return

        if d['state'] == 'relic':
            self._draw_delve_relics(cw, ch)
            return
