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

"""
PoE-style Delve Map system.
Graph-based generation with depth rows, explicit edges, node states, and
uniform level scaling per depth. The chart is rendered as an interactive
popup mini-map with connection lines, node icons, and state-based visuals.
"""

import random

# ── grid constants (kept for gameplay room carving) ──────────────────
GRID_W = 200
GRID_H = 200
ROOM_MIN = 1
ROOM_MAX = 2

DIR_VEC = {
    'N': (0, -1),
    'E': (1,  0),
    'S': (0,  1),
    'W': (-1, 0),
}
_ALL_DIRS = list(DIR_VEC.keys())

# ── node definitions ──────────────────────────────────────────────────
NODE_DEFS = [
    ('combat',   'Combat Encounter',  'Faded Remains'),
    ('chest',    'Loot Cache',        'Visceral Cache'),
    ('armour',   'Organ Cache',       'Organ Rack'),
    ('breach',   'Breach',            'Rift Cache'),
]

NODE_DEFS_BOSS = [
    ('boss', 'Boss Arena', 'Vital Hoard'),
]

NODE_DEFS_CHECKPOINT = [
    ('checkpoint', 'Anima Cart', 'Cart Cache'),
]

# ── biomes ────────────────────────────────────────────────────────────
BIOMES = [
    {'name': 'Petrified Forest', 'color': (30, 50, 35),  'accent': (80, 140, 60)},
    {'name': 'Abyssal Depths',   'color': (50, 30, 20),  'accent': (200, 100, 40)},
    {'name': 'Frozen Hollow',    'color': (30, 40, 55),  'accent': (100, 180, 220)},
    {'name': 'Magma Chambers',   'color': (55, 25, 15),  'accent': (230, 120, 30)},
    {'name': 'Azurite Cavities', 'color': (20, 40, 55),  'accent': (60, 180, 255)},
    {'name': 'Rotting Warrens',  'color': (40, 35, 20),  'accent': (160, 140, 50)},
]

# Fracture zones rotate every ZONE_PERIOD depths.
ZONE_PERIOD = 15

# Zone modifiers rolled per fracture band: keys map onto systems the game
# reads at spawn/darkness time.
ZONE_MODS = {
    'Petrified Forest': {},
    'Abyssal Depths':   {'darkness_ramp_mult': 1.25, 'reward_ilvl_bonus': 2},
    'Frozen Hollow':    {'player_slow_outside_light': 0.25},
    'Magma Chambers':   {'enemy_damage_mult': 1.2, 'cracked_wall_bonus': 0.15},
    'Azurite Cavities': {'elite_chance_bonus': 0.05},
    'Rotting Warrens':  {'enemy_count_mult': 1.15},
}


def zone_for_depth(depth: int) -> dict:
    """Return the fracture-zone dict (biome + modifiers) for a depth."""
    biome = biome_for_depth(depth)
    mods = dict(ZONE_MODS.get(biome['name'], {}))
    # Zone modifier variation: depth hash picks a deterministic extra twist.
    rng = random.Random(depth * 31 + 7)
    if rng.random() < 0.35:
        mods['evasion_swap'] = True
    return {'name': biome['name'], 'color': biome['color'],
            'accent': biome['accent'], 'mods': mods}

NODE_COLORS = {
    'start':      (255, 255, 255),
    'combat':     (150, 150, 150),
    'chest':      (255, 200,  50),
    'armour':     (100, 255, 150),
    'breach':     (200,  80, 255),
    'boss':       (255,  50,  50),
    'checkpoint': (255, 220, 120),
    'hidden':     (140,  90, 200),
}

NODE_ICONS = {
    'start':      'H',
    'combat':     '!',
    'chest':      '$',
    'armour':     'A',
    'breach':     'B',
    'boss':       'S',
    'dead_end':   'X',
    'checkpoint': 'C',
    'hidden':     '?',
}

# ── chart layout (chart-world pixels, owned by the generator) ─────────
# Node positions are produced here, never by the renderer: the renderer only
# projects ('px','py') onto the screen.  The spacing is deliberately tight so
# several depth rows fit on screen at the chart's default (max) zoom.
# Owner ruling 2026-10-07: nodes sit closer together (was 380/60) while the
# node icons grew (delve_chart radius 11/14).
CHART_COL_SPACING = 300.0   # px per 1.0 of the 0-1 row column axis
CHART_ROW_SPACING = 46.0    # px per depth row (depth 1 sits at y = 0)

# ── orthogonal grid topology (BLUEPRINT §26, owner ruling 2026-10-07) ──
# Rows generate CHART_LANES nodes on fixed lane columns; a child ALWAYS
# inherits its parent's column, so every edge is vertical (down a lane) or
# horizontal (sideways in a row) — never diagonal.
CHART_LANES = 4
LANE_COLS = tuple((i + 0.5) / CHART_LANES for i in range(CHART_LANES))
LATERAL_EDGE_CHANCE = 0.70   # in-row adjacency for NEW rows; row 1 and
                             # recycled rows are always fully linked


def node_pos(depth: int, col: float) -> tuple:
    """Deterministic chart-world position for a (depth, col) coordinate."""
    return (col * CHART_COL_SPACING, (max(1, int(depth)) - 1) * CHART_ROW_SPACING)


def layout_positions(graph: dict) -> dict:
    """(Re)assign every node's chart position from its own depth/col.

    Pure function of the stored graph, so it is safe to re-run on load: charts
    persisted with older, looser spacing are re-laid out into the current
    compact layout, and the result is identical every time for a given graph.
    """
    for node in graph.get('nodes', {}).values():
        node['px'], node['py'] = node_pos(node.get('depth', 1),
                                          node.get('col', 0.0))
    return graph


STATE_CLEARED = 'cleared'
STATE_AVAILABLE = 'available'
STATE_LOCKED = 'locked'

_NEXT_ID = 0


def _next_id():
    global _NEXT_ID
    _NEXT_ID += 1
    return _NEXT_ID


def biome_for_depth(depth: int) -> dict:
    idx = (depth - 1) // 25 % len(BIOMES)
    return BIOMES[idx]


def level_for_depth(depth: int) -> int:
    return max(1, depth)


def effective_level(depth: int) -> int:
    """Super-linear monster level curve:
    depth 50 fights like ~66, depth 100 like ~166."""
    depth = max(1, int(depth))
    return max(1, int(round(depth * (1.0 + depth / 150.0))))


# ── grid carving helpers (kept for gameplay) ─────────────────────────

def _set_floor(grid, c, r):
    try:
        if 0 <= c < len(grid) and 0 <= r < len(grid[c]):
            grid[c][r] = 0
    except (IndexError, TypeError):
        pass


def _carve_room(grid, cx, cy, w, h):
    hw, hh = w // 2, h // 2
    for dc in range(-hw, hw + 1):
        for dr in range(-hh, hh + 1):
            _set_floor(grid, cx + dc, cy + dr)


def _carve_corridor(grid, start_c, start_r, end_c, end_r):
    max_c = len(grid) - 1 if grid else GRID_W - 1
    max_r = len(grid[0]) - 1 if grid and grid[0] else GRID_H - 1

    # Clamp inputs to ensure they stay within the grid
    start_c = max(1, min(max_c - 1, start_c))
    start_r = max(1, min(max_r - 1, start_r))
    end_c   = max(1, min(max_c - 1, end_c))
    end_r   = max(1, min(max_r - 1, end_r))

    # Single-tile-wide (tight) corridor.
    if start_c == end_c:
        lo, hi = max(1, min(start_r, end_r)), min(max_r - 1, max(start_r, end_r))
        for r in range(lo, hi + 1):
            _set_floor(grid, start_c, r)
    elif start_r == end_r:
        lo, hi = max(1, min(start_c, end_c)), min(max_c - 1, max(start_c, end_c))
        for c in range(lo, hi + 1):
            _set_floor(grid, c, start_r)
    else:
        # L-shaped corridor (1 tile wide): vertical then horizontal
        for r in range(min(start_r, end_r), max(start_r, end_r) + 1):
            _set_floor(grid, start_c, r)
        for c in range(min(start_c, end_c), max(start_c, end_c) + 1):
            _set_floor(grid, c, end_r)


# ── reward tables (item_id, min_count, max_count, chance) ─────────────
# These rolls are pre-rolled at chart generation and GRANTED verbatim on
# room clear (BLUEPRINT §23) — the chart label and the actual drop are the
# same single roll. Every row needs a matching ITEM_NAMES entry.
REWARD_TABLES = {
    'combat':   [('gem_blue', 1, 1, 0.10), ('gem_green', 1, 1, 0.08),
                 ('gem_red', 1, 1, 0.06),  ('gem_white', 1, 1, 0.05)],
    'chest':    [('lungs', 1, 1, 0.5),   ('heart', 1, 1, 0.4),
                 ('kidney', 1, 1, 0.3),     ('intestine', 1, 1, 0.2),
                 ('gem_white', 1, 1, 0.08)],
    'armour':   [('heart', 1, 1, 0.4), ('lungs', 1, 1, 0.5),
                 ('kidney', 1, 1, 0.25), ('gem_blue', 1, 1, 0.08)],
    'breach':   [('liver', 1, 1, 0.2)],
    'boss':     [('kidney', 1, 1, 0.35),
                 ('intestine', 1, 1, 0.25), ('liver', 1, 1, 0.2)],
}

# Item name lookup (duplicated from items.py for chart label generation)
ITEM_NAMES = {
    'lungs': 'Lungs', 'heart': 'Heart', 'liver': 'Liver',
    'intestine': 'Intestine', 'kidney': 'Kidney',
    'gem_blue': 'Blue Gem', 'gem_green': 'Green Gem',
    'gem_red': 'Red Gem', 'gem_white': 'White Gem',
}


def _roll_rewards(rng, node_type):
    """Pick actual reward items for a node based on its type."""
    table = REWARD_TABLES.get(node_type, [])
    rewards = []
    for item_id, mn, mx, chance in table:
        if rng.random() < chance:
            count = rng.randint(mn, mx)
            rewards.append({'item': item_id, 'count': count})
    return rewards


def _reward_label(rewards):
    """Build a short label from the reward list (max 1-2 items)."""
    if not rewards:
        return 'Nothing'
    names = [ITEM_NAMES.get(r['item'], r['item']) for r in rewards[:2]]
    label = ', '.join(names)
    extra = len(rewards) - 2
    if extra > 0:
        label += f' +{extra}'
    return label


# ── graph generation ─────────────────────────────────────────────────

def _pick_node_type(rng, allow_boss=False):
    if allow_boss and rng.random() < 0.08:
        return NODE_DEFS_BOSS[0]
    pool = NODE_DEFS[:]
    rng.shuffle(pool)
    return pool[0]


def _make_node(rng, depth, col, is_start=False, allow_boss=False,
               force_type=None, allow_dead=True):
    nid = _next_id()
    if is_start:
        return {
            'id': nid, 'depth': depth, 'col': col,
            'type': 'start',
            'label': 'Anima Entrance',
            'loot': '',
            'state': STATE_CLEARED,
            'enemy_level': level_for_depth(depth),
            'enemy_count': 0,
            'dead_end': False,
            'rewards': [],
        }
    if force_type == 'checkpoint':
        nt, lb, lt = NODE_DEFS_CHECKPOINT[0]
    else:
        nt, lb, lt = _pick_node_type(rng, allow_boss=allow_boss)
    is_dead = allow_dead and rng.random() < 0.18 and force_type != 'checkpoint'
    if is_dead:
        return {
            'id': nid, 'depth': depth, 'col': col,
            'type': 'dead_end',
            'label': 'Dead End',
            'loot': 'Collapsed Passage',   # honest — dead ends grant nothing
            'state': STATE_LOCKED,
            'enemy_level': level_for_depth(depth),
            'enemy_count': rng.randint(2, 4 + depth // 2),
            'dead_end': True,
            'rewards': [],
        }
    rewards = _roll_rewards(rng, nt)
    rlabel = _reward_label(rewards)
    return {
        'id': nid, 'depth': depth, 'col': col,
        'type': nt,
        'label': rlabel,
        'loot': lt,
        'state': STATE_LOCKED,
        'enemy_level': level_for_depth(depth),
        'enemy_count': rng.randint(2, 4 + depth // 2),
        'dead_end': False,
        'rewards': rewards,
    }


def init_delve(seed: int = 0, current_depth: int = 1) -> dict:
    rng = random.Random(seed + current_depth * 7919)
    graph = {'nodes': {}, 'edges': [], 'max_depth': 1,
             'start_node_id': None, 'current_node_id': None}

    # Depth 1: exactly CHART_LANES nodes on the fixed lane columns. Row 1
    # is ALWAYS fully alive and fully linked sideways — its lanes have no
    # up-edges, so discovery depends entirely on the lateral chain (a dead
    # end here would orphan the whole lane below it).
    d1_nodes = []
    for i, col in enumerate(LANE_COLS):
        node = _make_node(rng, 1, col, is_start=(i == 0), allow_dead=False)
        graph['nodes'][node['id']] = node
        d1_nodes.append(node)
        if i == 0:
            graph['start_node_id'] = node['id']
            graph['current_node_id'] = node['id']
    for a, b in zip(d1_nodes, d1_nodes[1:]):
        graph['edges'].append((a['id'], b['id']))
    for node in d1_nodes[1:]:
        node['state'] = STATE_AVAILABLE      # reachable sideways from the start

    for _ in range(3):
        _extend_graph(graph, rng)

    layout_positions(graph)
    return graph


def _revive_node(rng, node):
    """Turn a dead-end node into a real one (keeps id/col/edges in place)."""
    nt, lb, lt = _pick_node_type(rng)
    rewards = _roll_rewards(rng, nt)
    node.update({
        'dead_end': False, 'type': nt,
        'label': _reward_label(rewards), 'loot': lt,
        'rewards': rewards,
        'enemy_count': rng.randint(2, 4 + node.get('depth', 1) // 2),
    })


def _extend_graph(graph: dict, rng: random.Random):
    """Grow one depth row: one child per ALIVE lane, at the SAME column.

    Orthogonal topology (§26): the child inherits the parent's column so the
    edge is perfectly vertical — never diagonal. A lane whose node rolled a
    dead end simply stops (no children below it), so no unreachable node can
    ever be generated. Each batch is forced to keep at least one live lane
    (owner rule: dead ends allowed, but at least one new path always)."""
    max_d = graph['max_depth']
    next_d = max_d + 1

    prev_nodes = [n for n in graph['nodes'].values()
                  if n['depth'] == max_d and not n.get('dead_end')]
    if not prev_nodes:
        return
    prev_nodes.sort(key=lambda n: n['col'])

    # A checkpoint every 5 rows; bosses every 10 (via _make_node's allow_boss)
    checkpoint_slot = rng.randrange(len(prev_nodes)) if next_d % 5 == 0 else None
    new_nodes = []
    for i, parent in enumerate(prev_nodes):
        force = 'checkpoint' if i == checkpoint_slot else None
        node = _make_node(rng, next_d, parent['col'],
                          allow_boss=(next_d % 10 == 0), force_type=force)
        graph['nodes'][node['id']] = node
        graph['edges'].append((parent['id'], node['id']))
        if parent['state'] == STATE_CLEARED and node['state'] == STATE_LOCKED:
            node['state'] = STATE_AVAILABLE
        new_nodes.append(node)

    # Owner rule: dead ends are fine, but every batch keeps ≥1 live path.
    if all(n.get('dead_end') for n in new_nodes):
        _revive_node(rng, new_nodes[0])

    # Sideways links between consecutive nodes (~70%): flavor + alternate
    # routes; reachability never depends on them (down-lanes guarantee it).
    for a, b in zip(new_nodes, new_nodes[1:]):
        if rng.random() < LATERAL_EDGE_CHANCE:
            graph['edges'].append((a['id'], b['id']))

    graph['max_depth'] = next_d
    layout_positions(graph)


def generate_next_depth(graph: dict, rng: random.Random):
    _extend_graph(graph, rng)


def generate_chart(graph: dict, current_node_id: int,
                   visible_depths: int = 5):
    """Return (chart_nodes, chart_edges) for the UI popup.

    chart_nodes: list of dicts with cx, cy (0-1 normalized), type, label,
                 state, depth, enemy_level, is_current, dead_end
    chart_edges: list of (from_id, to_id) filtered to visible nodes
    """
    current = graph['nodes'].get(current_node_id)
    if not current:
        return [], []

    cur_depth = current['depth']
    min_d = max(1, cur_depth - 1)
    max_d = min(cur_depth + visible_depths, graph['max_depth'] + 1)

    visible = [n for n in graph['nodes'].values()
               if min_d <= n['depth'] <= max_d]
    visible_ids = {n['id'] for n in visible}

    d_range = max(1, max_d - min_d)

    chart_nodes = []
    for node in visible:
        t = (node['depth'] - min_d) / d_range
        cy = 0.08 + t * 0.84

        chart_nodes.append({
            'id': node['id'],
            'cx': node['col'],
            'cy': cy,
            'type': node['type'],
            'label': node['label'],
            'loot': node['loot'],
            'rewards': node.get('rewards', []),
            'enemy_level': node['enemy_level'],
            'depth': node['depth'],
            'state': node['state'],
            'dead_end': node.get('dead_end', False),
            'is_current': node['id'] == current_node_id,
        })

    chart_edges = [
        e for e in graph['edges']
        if e[0] in visible_ids and e[1] in visible_ids
    ]

    return chart_nodes, chart_edges


# ── gameplay room generation ─────────────────────────────────────────

def generate_start_room(grid: list, node: dict, rng: random.Random):
    cx, cy = GRID_W // 2, GRID_H // 2
    w = rng.randint(ROOM_MIN, ROOM_MAX) * 2 + 1
    h = rng.randint(ROOM_MIN, ROOM_MAX) * 2 + 1
    _carve_room(grid, cx, cy, w, h)
    node['grid_col'] = cx
    node['grid_row'] = cy
    node['w'] = w
    node['h'] = h


def generate_travel_room(grid: list, from_node: dict, to_node: dict,
                         rng: random.Random):
    """Carve a corridor + room from from_node's actual grid position
    to a new position for to_node, computed by offsetting from the parent."""
    fx = from_node.get('grid_col', GRID_W // 2)
    fy = from_node.get('grid_row', GRID_H // 2)

    direction = rng.choice(_ALL_DIRS)
    dc, dr = DIR_VEC[direction]
    dist = rng.randint(8, 15)
    tx = fx + dc * dist
    ty = fy + dr * dist
    tx = max(5, min(GRID_W - 5, tx))
    ty = max(5, min(GRID_H - 5, ty))

    _carve_corridor(grid, fx, fy, tx, ty)

    w = rng.randint(ROOM_MIN, ROOM_MAX) * 2 + 1
    h = rng.randint(ROOM_MIN, ROOM_MAX) * 2 + 1
    _carve_room(grid, tx, ty, w, h)

    bbox_c = min(fx, tx) - w
    bbox_r = min(fy, ty) - h
    bbox_w = abs(fx - tx) + w * 2
    bbox_h = abs(fy - ty) + h * 2

    to_node['grid_col'] = tx
    to_node['grid_row'] = ty
    to_node['w'] = w
    to_node['h'] = h


# ── direction-based gameplay room generation (original room-crawler) ──

CORRIDOR_LEN_MIN = 3
CORRIDOR_LEN_MAX = 6


def _opposite_dir(d):
    return {'N': 'S', 'S': 'N', 'E': 'W', 'W': 'E'}[d]


def _pick_connections(rng, exclude=None):
    dirs = _ALL_DIRS[:]
    rng.shuffle(dirs)
    result = []
    for d in dirs:
        if d != exclude:
            result.append(d)
            if len(result) >= 3:
                break
    return result


def init_delve_room(seed=0, depth=1):
    """Create a starting room w/ node+connections for direction-based delve."""
    rng = random.Random(seed + depth * 7919)
    # Open arena: the whole delve grid starts as walkable floor. Rooms are
    # still carved as distinct floor regions (their size/position recorded on
    # the node), but no wall tiles separate them — see issue #24 / #27.
    grid = [[0] * GRID_H for _ in range(GRID_W)]
    cx, cy = GRID_W // 2, GRID_H // 2
    room_w = rng.randint(ROOM_MIN, ROOM_MAX) * 2 + 1
    room_h = rng.randint(ROOM_MIN, ROOM_MAX) * 2 + 1
    _carve_room(grid, cx, cy, room_w, room_h)
    nt, lb, lt = _pick_node_type(rng)
    node = {
        'type': nt, 'label': lb, 'loot': lt,
        'col': float(cx), 'row': float(cy),
        'w': room_w, 'h': room_h,
        'enemy_level': max(1, depth),
        'enemy_count': rng.randint(2, 4 + depth // 2),
        'connections': _pick_connections(rng),
        'rewards': _roll_rewards(rng, nt),
    }
    return {'grid': grid, 'node': node}


def generate_segment(grid, current_node, direction, rng, depth):
    """Carve corridor+room in the given direction. Returns the new node."""
    cx, cy = int(current_node['col']), int(current_node['row'])
    hw, hh = current_node['w'] // 2, current_node['h'] // 2
    dc, dr = DIR_VEC[direction]
    exit_c = max(3, min(GRID_W - 3, cx + dc * (hw + 1)))
    exit_r = max(3, min(GRID_H - 3, cy + dr * (hh + 1)))
    corr_len = rng.randint(CORRIDOR_LEN_MIN, CORRIDOR_LEN_MAX)
    end_c = exit_c + dc * corr_len
    end_r = exit_r + dr * corr_len
    end_c = max(6, min(GRID_W - 6, end_c))
    end_r = max(6, min(GRID_H - 6, end_r))
    _carve_corridor(grid, exit_c, exit_r, end_c, end_r)
    room_w = rng.randint(ROOM_MIN, ROOM_MAX) * 2 + 1
    room_h = rng.randint(ROOM_MIN, ROOM_MAX) * 2 + 1
    _carve_room(grid, end_c, end_r, room_w, room_h)
    bbox_c = max(0, min(exit_c, end_c) - room_w)
    bbox_r = max(0, min(exit_r, end_r) - room_h)
    bbox_w = abs(end_c - exit_c) + room_w * 2
    bbox_h = abs(end_r - exit_r) + room_h * 2
    nt, lb, lt = _pick_node_type(rng)
    new_node = {
        'type': nt, 'label': lb, 'loot': lt,
        'col': float(end_c), 'row': float(end_r),
        'w': room_w, 'h': room_h,
        'enemy_level': max(1, depth),
        'enemy_count': rng.randint(2, 4 + depth // 2),
        'connections': _pick_connections(rng, exclude=_opposite_dir(direction)),
        'rewards': _roll_rewards(rng, nt),
    }
    return new_node

# ── chart navigation helpers ─────────────────

def chart_children(graph: dict, node_id: int) -> list:
    """Return child nodes one depth row below the given node."""
    children = []
    for parent_id, child_id in graph['edges']:
        if parent_id == node_id:
            child = graph['nodes'].get(child_id)
            if child is not None:
                children.append(child)
    return children


def cleared_ids(chart: dict) -> set:
    """Node ids permanently done. `visited` is the record; a node may also
    carry the cleared state flag, so honour both (old saves)."""
    graph = chart.get('graph', {})
    out = {nid for nid in chart.get('visited', []) if nid in graph.get('nodes', {})}
    for nid, node in graph.get('nodes', {}).items():
        if node.get('state') == STATE_CLEARED:
            out.add(nid)
    return out


def discovered_ids(graph: dict, cleared: set) -> set:
    """Nodes the player has laid bare: the cleared ones plus everything
    adjacent to them. Recomputed from the stored graph rather than persisted,
    so a node left behind stays enterable across saves and older charts."""
    out = set(cleared)
    for parent_id, child_id in graph.get('edges', []):
        if parent_id in cleared:
            out.add(child_id)
        if child_id in cleared:
            out.add(parent_id)
    return out


def enterable_node_ids(graph: dict, chart: dict) -> list:
    """Nodes the player may enter right now (chart navigation rework).

    - cleared nodes are permanently done — never enterable
    - discovered-but-uncleared nodes you walked away from stay enterable
      (retreating lowers depth, so it must be a legal move)
    - forward children of the current node stay enterable
    The node you are standing on is never enterable. Dead ends are excluded
    everywhere.
    """
    current_id = chart.get('current_node_id')
    cleared = cleared_ids(chart)
    if current_id in cleared:
        cleared.discard(current_id)      # standing here: not yet finished
    enterable = (discovered_ids(graph, cleared) - cleared) & set(graph.get('nodes', {}))
    # Direct children of the standing node are live options — but NEVER a
    # beaten one: a retreat to this node used to force-add its cleared
    # children back, letting the player redo a finished node (owner fix
    # 2026-10-07).
    for kid in chart_children(graph, current_id):
        if kid['id'] in cleared or kid.get('dead_end'):
            continue
        enterable.add(kid['id'])
    enterable.discard(current_id)   # you are already standing on it
    return sorted(nid for nid in enterable
                  if not graph['nodes'][nid].get('dead_end'))


def ensure_row_supply(graph: dict, rng: random.Random, current_id) -> int:
    """Depth rows never run out (BLUEPRINT §26.236): when the standing row
    has no live option left, a fresh batch is appended to the LEFT or RIGHT
    side of the row (owner ruling 2026-10-07 — nothing is ever deleted; the
    beaten history stays on the chart). Fresh nodes are never dead ends,
    chain laterally, and are bridged from a CLEARED row extremity so the
    batch is discoverable (rng picks the side when both qualify; the
    standing node bridges when neither tail is cleared). Returns nodes
    added (0 when the row still has options)."""
    current = graph.get('nodes', {}).get(current_id)
    if current is None:
        return 0
    depth = current['depth']

    # discoverability: cleared nodes plus everything adjacent to them
    # (mirrors discovered_ids) — a cleared bridge extremity makes the
    # fresh batch discoverable through its edge.
    cleared = {nid for nid, n in graph['nodes'].items()
               if n.get('state') == STATE_CLEARED}
    discovered = set(cleared)
    for pid, cid in graph['edges']:
        if pid in cleared:
            discovered.add(cid)
        if cid in cleared:
            discovered.add(pid)
    # Direct neighbours of the standing node are live options even before
    # the anchor is marked cleared — the same rule enterable_node_ids
    # applies via its force-children loop (point 2: direct connections only).
    current_neighbors = {cid if pid == current_id else pid
                         for pid, cid in graph['edges']
                         if pid == current_id or cid == current_id}

    siblings = [n for n in graph['nodes'].values()
                if n['depth'] == depth and n['id'] != current_id
                and n.get('state') != STATE_CLEARED and not n.get('dead_end')
                and (n['id'] in discovered or n['id'] in current_neighbors)]
    if siblings:
        return 0

    row = sorted((n for n in graph['nodes'].values() if n['depth'] == depth),
                 key=lambda n: n['col'])

    # pick the append side: prefer a CLEARED extremity — its bridge edge is
    # what makes the fresh batch discoverable; rng when both qualify, the
    # standing node bridges when neither tail is cleared (edge stays in-row,
    # i.e. horizontal — never diagonal).
    right, left = row[-1], row[0]
    if right['id'] in cleared and left['id'] in cleared:
        side = rng.choice(('right', 'left'))
    elif right['id'] in cleared:
        side = 'right'
    elif left['id'] in cleared:
        side = 'left'
    else:
        side = None
    anchor = current if side is None else (right if side == 'right' else left)

    # fresh batch: contiguous beyond the chosen extremity (LANE step = 0.25)
    n_new = rng.randint(2, 3)
    if side == 'left':
        base = min(n['col'] for n in row)
        cols = [base - 0.25 * i for i in range(1, n_new + 1)]
    else:
        base = max(n['col'] for n in row)
        cols = [base + 0.25 * i for i in range(1, n_new + 1)]

    fresh = []
    for col in cols:
        node = _make_node(rng, depth, col, allow_dead=False)
        node['state'] = STATE_AVAILABLE
        graph['nodes'][node['id']] = node
        fresh.append(node)

    # bridge + lateral chain — every edge stays inside the row (horizontal)
    graph['edges'].append((anchor['id'], fresh[0]['id']))
    for a, b in zip(fresh, fresh[1:]):
        graph['edges'].append((a['id'], b['id']))

    layout_positions(graph)
    return len(fresh)


def chart_best_depth(chart: dict) -> int:
    """The depth record. It only ever grows: it is the deepest node ever
    visited, never the current node, so retreating cannot farm it."""
    depths = [chart.get('best_depth', 0) or 0]
    graph = chart.get('graph', {})
    for nid in chart.get('visited', []):
        node = graph.get('nodes', {}).get(nid)
        if node:
            depths.append(node.get('depth', 0))
    current = graph.get('nodes', {}).get(chart.get('current_node_id'))
    if current:
        depths.append(current.get('depth', 0))
    return max(depths + [1])


def ensure_depth_rows(graph: dict, rng: random.Random, target_depth: int,
                      lookahead: int = 2):
    """Lazily extend the chart until target_depth + lookahead rows exist."""
    while graph['max_depth'] < target_depth + lookahead:
        generate_next_depth(graph, rng)
    layout_positions(graph)


def find_route(graph: dict, from_id: int, to_id: int) -> list:
    """BFS shortest path of node ids from from_id to to_id ([] if none).

    Edges are walked in EITHER direction: the golden route must survive
    retreats (up a lane) and sideways moves, which run against the stored
    parent→child direction."""
    if from_id == to_id:
        return [from_id]
    parents = {from_id: None}
    queue = [from_id]
    while queue:
        nid = queue.pop(0)
        for p_id, c_id in graph['edges']:
            if p_id == nid:
                neighbours = (c_id,)
            elif c_id == nid:
                neighbours = (p_id,)
            else:
                continue
            for nxt in neighbours:
                if nxt in parents:
                    continue
                parents[nxt] = nid
                if nxt == to_id:
                    route = [to_id]
                    while parents[route[-1]] is not None:
                        route.append(parents[route[-1]])
                    route.reverse()
                    return route
                queue.append(nxt)
    return []


def rebuild_graph_from_save(seed: int, max_depth: int) -> dict:
    """Deterministically rebuild a chart graph from its seed + depth count.

    Used as a corruption fallback only — the normal path persists the full
    (JSON-safe) nodes/edges graph in the delve snapshot. For determinism the
    node-id counter is reset so ids regenerate identically.
    """
    global _NEXT_ID
    _saved_counter = _NEXT_ID
    _NEXT_ID = 0
    try:
        graph = init_delve(seed)
        rng = random.Random(seed ^ 0x5EED)
        while graph['max_depth'] < max(1, max_depth):
            generate_next_depth(graph, rng)
        return graph
    finally:
        _NEXT_ID = max(_NEXT_ID, _saved_counter)


def restore_chart_flags(graph: dict, visited: list, looted: list,
                        checkpoints: list):
    """Replay persisted visit/loot flags onto a rebuilt graph."""
    for nid in visited:
        node = graph['nodes'].get(nid)
        if node is not None:
            node['state'] = STATE_CLEARED
    for nid in looted:
        node = graph['nodes'].get(nid)
        if node is not None:
            node['looted'] = True
    for nid in checkpoints:
        node = graph['nodes'].get(nid)
        if node is not None:
            node['touched'] = True

# ── hidden reward wings ─────────────────────────

HIDDEN_WING_CHANCE = 0.35   # chance a carved room attaches a hidden wing
HIDDEN_WING_MIN_DIST = 6    # pocket center distance from room edge (tiles)
HIDDEN_WING_MAX_DIST = 9

# Depth-tiered hidden loot table (§4): (equip chance, ambush chance,
# rarity floor). Currency/organ rolls scale with depth in game.py.
HIDDEN_LOOT_TIERS = [
    # (max_depth, equip_guaranteed, ambush_chance, rarity_floor)
    (9,   False, 0.00, 0),  # common+
    (19,  True,  0.00, 1),  # uncommon+
    (34,  True,  0.15, 2),  # rare+
    (999, True,  0.20, 3),  # epic chance scales +2%/depth in game.py
]


def hidden_tier_for_depth(depth: int) -> dict:
    for max_depth, equip, ambush, rarity in HIDDEN_LOOT_TIERS:
        if depth <= max_depth:
            return {'equip_guaranteed': equip, 'ambush_chance': ambush,
                    'rarity_floor': rarity, 'epic_scale': depth >= 35}
    return {'equip_guaranteed': True, 'ambush_chance': 0.2,
            'rarity_floor': 3, 'epic_scale': True}


def generate_hidden_wing(grid: list, node: dict, rng: random.Random,
                         wing_id: int):
    """Attach a rubble-sealed pocket room to a carved room.

    The delve grid is an open arena, so the wing is built as a wall ring
    (tile value 1) enclosing a small pocket, with a single cracked cell
    facing the room. The cracked cell marks the seal (its old opener, the
    dynamite tool, was removed — the wing is currently unreachable content).
    Returns a wing descriptor dict, or None if there is no space.
    """
    cx, cy = int(node['col']), int(node['row'])
    hw = max(2, node.get('w', 5) // 2)
    hh = max(2, node.get('h', 5) // 2)

    for _attempt in range(6):
        direction = rng.choice(_ALL_DIRS)
        dc, dr = DIR_VEC[direction]
        dist = rng.randint(HIDDEN_WING_MIN_DIST, HIDDEN_WING_MAX_DIST)
        px = cx + dc * (hw + dist)
        py = cy + dr * (hh + dist)

        # 5x5 interior pocket, 7x7 rubble ring
        if not (6 <= px - 3 and px + 3 < len(grid) - 1
                and 6 <= py - 3 and py + 3 < len(grid[0]) - 1):
            continue

        # Don't overlap the parent room
        if abs(px - cx) < hw + 5 and abs(py - cy) < hh + 5:
            continue

        cracked = []
        for cc in range(px - 3, px + 4):
            for rr in range(py - 3, py + 4):
                interior = (px - 1 <= cc <= px + 1 and py - 1 <= rr <= py + 1)
                if interior:
                    grid[cc][rr] = 0
                else:
                    grid[cc][rr] = 1
        # Cracked cell: ring midpoint on the side facing the parent room
        sc = px - dc * 3
        sr = py - dr * 3
        grid[sc][sr] = 1
        cracked.append({'c': sc, 'r': sr, 'wing': wing_id})

        return {
            'id': wing_id, 'cx': float(px), 'cy': float(py),
            'cracked': cracked,
            'direction': direction,
        }
    return None
