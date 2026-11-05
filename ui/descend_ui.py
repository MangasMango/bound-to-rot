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

"""The D.E.S.C.E.N.D. panel (issue #31) - replaces the old C stats overlay.

Layout mirrors the owner's art (``assets/ui/descend.jpg``, 523x1044) and the
2026-11-02 rulings. The panel occupies the left side of the screen, scaled
to the full height, width in the art's aspect.
Rows read ``ATTRIBUTE LEVEL | NAME | RANK WORD + (+)``:

- top strip band: the D.E.S.C.E.N.D. title
- narrow left sidebar: the attribute LEVEL (the effective clamped value)
- wide cell: the attribute NAME
- narrow cell: the RANK WORD, with the "+" on its right. The "+" appears
  ONLY while unspent points exist and the attribute rests below the hard
  cap of 10; otherwise the word gets the whole cell.
- band below the rows: "CharPoints available: N" (plus LEVEL and XP progress)
- the lower stone area: the character's in-depth stats.

The panel is openable anywhere (hub or delve) and pauses the game; ESC or
C closes it. All geometry lives in art space and scales to the screen.
"""

import os

import pyray as rl

from config import ASSETS
from ui import fonts
from ui.descend_rank import rank_word
from entities.descend import ATTR_CAP, DESCEND_ATTRIBUTES, ATTR_LABEL, \
    VESSEL_DEFS
from entities.progression import compute_derived_stats
from systems import itemgen

ART_W, ART_H = 523, 1044

# Art-space geometry (x, y, w, h).
TITLE_BAND = (14, 42, 495, 38)
SIDEBAR_X, SIDEBAR_W = 18, 76
GRID_X, GRID_W = 100, 394
GRID_Y, GRID_H = 96, 458
ROW_SPLIT = 272          # wide name cell width; the rest is the value cell
POINTS_BAND = (16, 616, 491, 62)
STATS_AREA = (26, 694, 471, 332)
STATS_COLS = 2

GOLD   = rl.Color(218, 165, 32, 255)
IVORY  = rl.Color(238, 230, 212, 255)
MUTED  = rl.Color(178, 168, 148, 255)
FAINT  = rl.Color(120, 112, 98, 255)
GREEN  = rl.Color(120, 200, 90, 255)

_TEX = None


def _panel_tex():
    """The descend.jpg panel art, loaded once."""
    global _TEX
    if _TEX is None:
        path = os.path.join(ASSETS, 'ui', 'descend.jpg')
        if os.path.exists(path):
            _TEX = rl.load_texture(path)   # photo art: linear filtering
    return _TEX


def derive_stats(game) -> dict:
    """Derived stats for the panel, the same way the old stats overlay did."""
    char = game.char
    bonuses = itemgen.aggregate_item_bonuses(game.inventory)
    equip = game._equipped_bonuses()
    item_attr = {a: equip.get(a, 0) for a in DESCEND_ATTRIBUTES}
    return compute_derived_stats(
        char.descend, bonuses, item_bonuses=item_attr, looks=char.looks)


def toggle(game):
    """Open/close the panel (KEY_C anywhere); pauses the game while open."""
    game._char_stats_open = not game._char_stats_open
    if game._char_stats_open:
        try:
            game.inv.close()
        except Exception:
            pass


def handle_key(game, opened_this_frame: bool = False) -> bool:
    """Key-driven close (ESC / C). Returns True while the panel stays open.

    ``opened_this_frame`` suppresses the C check on the frame that opened
    the panel (so one C press cannot close it again immediately)."""
    if rl.is_key_pressed(rl.KEY_ESCAPE) \
            or (not opened_this_frame and rl.is_key_pressed(rl.KEY_C)):
        game._char_stats_open = False
    return game._char_stats_open


def draw(game, cw: int, ch: int):
    """Draw the whole panel; caches the + button rects on ``game``.

    Owner ruling: the panel occupies the left side of the screen, scaled to
    the FULL height (top-to-bottom, no margins), width in the art's aspect."""
    from systems import xp as _xp

    char = game.char
    derived = derive_stats(game)
    tex = _panel_tex()

    rl.draw_rectangle(0, 0, cw, ch, rl.Color(0, 0, 0, 200))

    s = ch / ART_H            # full height; width follows the art aspect
    panel_w = int(ART_W * s)

    if tex is not None and tex.id > 0:
        rl.draw_texture_pro(
            tex,
            rl.Rectangle(0.0, 0.0, float(tex.width), float(tex.height)),
            rl.Rectangle(0.0, 0.0, float(panel_w), float(ch)),
            rl.Vector2(0.0, 0.0), 0.0, rl.WHITE)
    else:
        rl.draw_rectangle(0, 0, panel_w, ch, rl.Color(20, 18, 15, 255))

    def fx(n):
        return int(n * s)

    def fy(n):
        return int(n * s)

    def fs(n):
        return max(1, int(n * s))

    # ── title strip ───────────────────────────────────────────────────
    bx, by, bw, bh = TITLE_BAND
    title = 'D.E.S.C.E.N.D.'
    tfs = fs(bh)
    tw = fonts.measure(title, tfs)
    t_center = (fx(bx) + fx(bx + bw)) // 2
    fonts.draw(title, t_center - tw // 2, fy(by) + fs(4), tfs, GOLD)

    # ── attribute rows ────────────────────────────────────────────────
    gy, gh = GRID_Y, GRID_H
    row_h = gh / 7.0
    plus_rects = []
    name_rects = []   # hover these -> "what this attribute buys" tooltip
    mouse = (rl.get_mouse_x(), rl.get_mouse_y())
    points_avail = int(getattr(char, 'available_points', 0))

    for i, attr in enumerate(DESCEND_ATTRIBUTES):
        label = ATTR_LABEL[attr]
        y0 = fy(gy + row_h * i)
        rh = int(row_h * s)
        total = int(derived.get(attr, 0))
        alloc = int(char.descend.get(attr, 0))

        # Column 1 (sidebar cell) - the ATTRIBUTE LEVEL, big number
        vfs = fs(28)
        vw = fonts.measure(str(total), vfs)
        s_center = (fx(SIDEBAR_X) + fx(GRID_X)) // 2
        fonts.draw(str(total), s_center - vw // 2,
                   y0 + (rh - vfs) // 2, vfs,
                   GOLD if alloc >= ATTR_CAP else IVORY)

        # Column 2 (wide cell) - the attribute NAME
        name_fs = fs(24)
        fonts.draw(label, fx(GRID_X + 14), y0 + (rh - name_fs) // 2,
                   name_fs, IVORY)
        name_rects.append((attr, rl.Rectangle(
            float(fx(GRID_X + 6)), float(y0),
            float(fx(ROW_SPLIT - 6) - fx(GRID_X + 6)), float(rh))))

        # Column 3 (narrow cell) - the RANK WORD ... and the (+) on the
        # right when a point can actually be spent (owner ruling: the +
        # appears ONLY with unspent points and the attribute below cap).
        word = rank_word(total)
        wl = MUTED if alloc >= ATTR_CAP else FAINT
        cell_cx = fx(GRID_X + ROW_SPLIT)
        cw_val = int((GRID_W - ROW_SPLIT) * s)
        btn_xs = int(34 * s)
        can_spend = points_avail > 0 and alloc < ATTR_CAP
        # The word keeps the left part of the cell; shrink it into the
        # space that remains (improvise when the word does not fit).
        btn_space = btn_xs if can_spend else fs(8)
        zone_px = cw_val - fs(12) - btn_space - fs(6)
        word_fs = max(9, fs(19))
        while word_fs > 9 and fonts.measure(word, word_fs) > zone_px:
            word_fs -= 1
        fonts.draw(word, cell_cx + fs(12), y0 + (rh - word_fs) // 2,
                   word_fs, wl)
        if can_spend:
            bx2 = cell_cx + cw_val - fs(8) - btn_xs
            by2 = y0 + (rh - btn_xs) // 2
            rect = rl.Rectangle(float(bx2), float(by2),
                                float(btn_xs), float(btn_xs))
            pfs = fs(22)
            pw = fonts.measure('+', pfs)
            hovered = _rect_has(rect, mouse)
            tint = rl.Color(255, 240, 180, 255) if hovered else GOLD
            rl.draw_rectangle_lines_ex(rect, max(1, fs(2)), tint)
            fonts.draw('+', bx2 + (btn_xs - pw) // 2, by2 + fs(2), pfs, tint)
            plus_rects.append((attr, rect))

    # ── points band ───────────────────────────────────────────────────
    pbx, pby, pbw, pbh = POINTS_BAND
    pf = fs(26)
    pts_txt = f'CharPoints available: {points_avail}'
    fonts.draw(pts_txt, fx(pbx) + fs(28), fy(pby) + (fs(pbh) - pf) // 2, pf,
               GREEN if points_avail > 0 else MUTED)

    lv_fs = fs(20)
    lv_txt = f'LEVEL {char.level}'
    lw = fonts.measure(lv_txt, lv_fs)
    lv_x = fx(pbx + pbw) - lw - fs(24)
    fonts.draw(lv_txt, lv_x, fy(pby) + fs(6), lv_fs, GOLD)

    cur, need = _xp.level_progress(char)
    xp_fs = fs(14)
    if need > 0:
        xp_frac = min(1.0, cur / need)
        xp_txt = f'XP {cur}/{need}'
    else:
        xp_frac = 1.0
        xp_txt = 'XP MAX'
    xw = fonts.measure(xp_txt, xp_fs)
    bar_w = fs(150)
    bar_x = fx(pbx + pbw) - fs(24) - xw - fs(10) - bar_w
    bar_y = fy(pby) + fs(8)
    bar_h = max(2, fs(7))
    rl.draw_rectangle(bar_x, bar_y, bar_w, bar_h, rl.Color(0, 0, 0, 160))
    rl.draw_rectangle(bar_x, bar_y, int(bar_w * xp_frac), bar_h, GOLD)
    fonts.draw(xp_txt, fx(pbx + pbw) - fs(24) - xw, fy(pby) + fs(38),
               xp_fs, MUTED)

    # ── in-depth stats ────────────────────────────────────────────────
    lines = _stats_lines(game, derived)
    ax, ay, aw, ah = STATS_AREA
    col_w = aw / STATS_COLS
    rows = (len(lines) + STATS_COLS - 1) // STATS_COLS
    area_h = float(ah) * s                      # art units -> screen px
    line_h = min(area_h / max(rows, 1), 30.0 * s)
    label_fs = max(1, min(fs(18), int(line_h * 0.8)))

    for i, (label, value) in enumerate(lines):
        col, row = divmod(i, rows)
        x = fx(ax + col * col_w)
        y = fy(ay) + int(row * line_h)
        if not label.startswith('---'):
            fonts.draw(label, x, y, label_fs, MUTED)
            right = fx(ax + (col + 1) * col_w) - fs(12)
            vw2 = fonts.measure(str(value), label_fs)
            fonts.draw(str(value), right - vw2, y, label_fs, IVORY)

    hint_fs = fs(13)
    hint = 'ESC / C to close'
    hw = fonts.measure(hint, hint_fs)
    fonts.draw(hint, cw - hw - fs(20), ch - hint_fs - fs(14), hint_fs,
               rl.Color(150, 140, 120, 200))

    # Hover an attribute NAME: the tooltip lists the exclusive levers one
    # point buys (plan §2.1 - each attribute owns one item-unreachable
    # domain). Drawn LAST so it floats above everything in the panel.
    hovered_attr = next(
        (a for a, r in name_rects if _rect_has(r, mouse)), None)
    if hovered_attr:
        _draw_attribute_tooltip(game, hovered_attr, mouse, cw, ch)

    game._descend_plus_rects = plus_rects


def _rect_has(rect, pt) -> bool:
    return rect.x <= pt[0] <= rect.x + rect.width and \
        rect.y <= pt[1] <= rect.y + rect.height


# Hover data (leveling rework plan §2.1): one exclusive lever set per
# attribute, written as "what ONE more point buys". Icons come from
# ICON_MAP (BLUEPRINT §42 - never bare stat text).
ATTR_EFFECT_LINES = {
    'dexterity': [
        ('move_speed', 'Move Speed', '+3%'),
        ('attack_speed', 'Attack Speed', '+3%'),
        ('evasion', 'Evasion', '+3% of base'),
        ('accuracy', 'Accuracy', '+4'),
        ('defense', 'Block Chance', '+1.5%'),
    ],
    'endurance': [
        ('hp', 'Max Health', '+6'),
        ('energy_shield', 'Max Energy Shield', '+3'),
        ('darkness_resist', 'Darkness Resistance', '+2%'),
    ],
    'strength': [
        ('melee', 'Attack Damage', '+5%'),
        ('hp', 'Max Health', '+8'),
    ],
    'cunning': [
        ('cooldown_reduction', 'Cooldown Recovery', '+3%'),
        ('refresh', 'Reload Speed', '+3%'),
    ],
    'essence': [
        ('ability_crit', 'Ability Crit Chance', '+1%'),
        ('luck', 'Entropy Grace', '+1%'),
    ],
    'nerve': [
        ('crit_chance', 'Crit Chance', '+1%'),
        ('light', 'Anima Light Radius', '+0.5 tiles'),
    ],
    'destiny': [
        ('luck', 'Entropy Grace', '+1.5%'),
        ('loot', 'Loot Rarity', '+2%'),
    ],
}


def _draw_attribute_tooltip(game, attr, mouse, cw: int, ch: int):
    """"What does another point of this attribute buy?" - a floating card
    anchored to the cursor, one iconed stat line per owned lever."""
    from ui import icons
    lines = ATTR_EFFECT_LINES.get(attr, [])
    if not lines:
        return
    
    fs_line = 15
    icon_px = 18
    head_fs = 13
    pad = 10
    icon_gap = 6
    line_h = fs_line + 6

    label = ATTR_LABEL[attr]
    head_txt = f'{label} - each point buys'
    w = fonts.measure(head_txt, head_fs)
    for _icon, stat_text, amount in lines:
        w = max(w, fonts.measure(f'{stat_text}  {amount}', fs_line)
                + icon_px + icon_gap)
    w += pad * 2
    h = pad + head_fs + 6 + line_h * len(lines) + pad - 4

    mx, my = mouse
    tx = int(mx + 22)
    ty = int(my - h // 2)
    tx = max(6, min(tx, cw - w - 6))
    ty = max(6, min(ty, ch - h - 6))

    rl.draw_rectangle(tx, ty, w, h, rl.Color(14, 14, 12, 236))
    rl.draw_rectangle_lines_ex(rl.Rectangle(float(tx), float(ty), float(w),
                                           float(h)),
                               1, rl.Color(218, 165, 32, 230))
    fonts.draw(head_txt, tx + pad, ty + pad, head_fs, GOLD)
    ly = ty + pad + head_fs + 6
    for icon_key, stat_text, amount in lines:
        icons.draw(icon_key, tx + pad, ly + 1, icon_px, white=True)
        fonts.draw(stat_text, tx + pad + icon_px + icon_gap,
                   ly, fs_line, rl.Color(238, 230, 212, 255))
        aw = fonts.measure(amount, fs_line)
        fonts.draw(amount, tx + w - pad - aw, ly, fs_line, GOLD)
        ly += line_h


def handle_click(game, mx: int, my: int, cw: int, ch: int) -> bool:
    """Spend a point via a + click while the panel is open. Returns True when
    the click belonged to the panel (consumed either way)."""
    for attr, rect in getattr(game, '_descend_plus_rects', None) or []:
        if _rect_has(rect, (mx, my)) \
                and rl.is_mouse_button_pressed(rl.MOUSE_BUTTON_LEFT):
            from entities.descend import increase_attribute
            if increase_attribute(game.char, attr):
                game._recalc_derived_stats()
                draw(game, cw, ch)   # refresh cached rects for the new value
            break
    return True


def _stats_lines(game, derived):
    """Two-column in-depth stat list for the lower stone area."""
    char = game.char
    stats = game.stats
    equip = game._equipped_bonuses()

    def pct(x):
        return f'{int(round(x * 100))}%'

    def rpct(key):
        return pct(derived.get('resist_pct', {}).get(key, 0.0))

    dmg_pct = derived.get('damage_pct', {})
    atk = int((stats.get('_attack_speed_pct', 0.0)
               + equip.get('attack_speed_pct', 0.0)) * 100)
    cdr = int((stats.get('_cooldown_recovery_pct', 0.0)
               + equip.get('cooldown_recovery_pct', 0.0)) * 100)
    crit = int((stats.get('_crit_chance', 0.0) + equip.get('crit_chance', 0.0)) * 100)
    abcrit = int((stats.get('_ability_crit_chance', 0.0)
                  + equip.get('ability_crit_chance', 0.0)) * 100)
    dr = int(equip.get('damage_reduction', 0.0) * 100)
    spd = int(equip.get('move_speed_pct', 0.0) * 100)

    es = int(derived.get('max_energy_shield', 0))
    lines = [
        ('Vessel',       VESSEL_DEFS.get(char.looks, {}).get('name', char.looks)),
        ('ILEVEL',       str(itemgen.character_level(game.inventory))),
        ('Max Health',   str(int(stats.get('max_health', 0)))),
        ('Max Mana',     str(int(stats.get('max_mana', 0)))),
    ]
    if es > 0:
        lines.append(('Max ES', str(es)))
    lines += [
        ('Evasion',      str(int(derived.get('evasion', 0)))),
        ('Accuracy',     str(int(derived.get('accuracy', 0)))),
        ('Attack Dmg',   f"+{int((derived.get('attack_damage_mult', 1.0) - 1.0) * 100)}%"),
        ('Loot Rarity',  f"+{int(derived.get('loot_rarity_mod', 0.0))}%"),
        ('Attack Speed', f'+{atk}%'),
        ('Cooldown Red.', f'+{cdr}%'),
        ('Crit Chance',  f'{crit}%'),
        ('Ability Crit', f'{abcrit}%'),
        ('Dmg Reduction', f'{dr}%'),
        ('Move Speed',   f'+{spd}%' if spd else '-'),
        ('---', ''),
        ('Phys Dmg',     pct(dmg_pct.get('physical', 0.0))),
        ('Magic Dmg',    pct(dmg_pct.get('magic', 0.0))),
        ('Light. Dmg',   pct(dmg_pct.get('lightning', 0.0))),
        ('Cold Dmg',     pct(dmg_pct.get('cold', 0.0))),
        ('Fire Dmg',     pct(dmg_pct.get('fire', 0.0))),
        ('Rot Dmg',      pct(dmg_pct.get('rot', 0.0))),
        ('---', ''),
        ('Fire Res',     rpct('fire')),
        ('Cold Res',     rpct('cold')),
        ('Light. Res',   rpct('lightning')),
        ('Rot Res',      rpct('rot')),
        ('Darkness Res', rpct('darkness')),
    ]
    return lines
