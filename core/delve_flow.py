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

import math
import pyray as rl
from systems import input as inp
from core.game import *
from core.game import _rnd, _pick_enemy_dmg_type

class DelveFlowMixin:
        def _open_anima_panel(self):
            """Open the Anima panel (node chooser popup) from the Hub heart."""
            import entities.progression as _prog
            from ui.delve_chart import DelveChartScreen

            saved = self._saved_delve
            if saved is None:
                saved = _prog.load_delve_data(self.char.id)
            chart = None
            if saved is not None:
                chart = (saved.get('delve') or {}).get('chart')
                self._chart_resume = bool(saved.get('delve'))
            if chart is None:
                import core.delve_gen as _dg
                # Character-bound layout: the seed is derived from the character,
                # so the same chart regenerates on every visit. Death deletes the
                # character → new id → fresh layout.
                seed = int(self.char.seed)
                graph = _dg.init_delve(seed)
                chart = {
                    'seed':            seed,
                    'graph':           graph,
                    'current_node_id': graph['start_node_id'],
                    'visited':         [graph['start_node_id']],
                    'looted':          [],
                    'checkpoints':     [],
                    'route':           [],
                    'best_depth':      1,
                }
                self._chart_resume = False

            graph = chart['graph']
            # Re-lay out charts persisted under the older, looser spacing.
            # layout_positions is a pure function of the stored graph, so
            # every load produces the same compact layout for a given chart.
            import core.delve_gen as _dg
            _dg.layout_positions(graph)
            # Depth rows are infinite (§26) — refresh an exhausted row
            _dg.ensure_row_supply(graph, self._delve_chart_rng(),
                                  chart.get('current_node_id'))
            if self._chart_resume:
                # Ongoing journey: forward children plus any discovered
                # node you walked away from (cleared nodes are excluded).
                selectable = _dg.enterable_node_ids(graph, chart)
                if not selectable:
                    selectable = [chart.get('current_node_id',
                                            graph['start_node_id'])]
            else:
                selectable = [graph['start_node_id']] + [
                    nid for nid in chart.get('checkpoints', []) if nid in graph['nodes']]
            if self._chart_screen is None:
                self._chart_screen = DelveChartScreen(self)
            self._chart_screen.open(chart, selectable_ids=selectable,
                                    on_select=self._on_chart_select,
                                    title='Anima Chart', closable=True)
            self._hub_popup = 'anima'

        def _on_chart_return_hub(self):
            """RETURN TO HUB button on the chart modal: leave the delve and
            bank the run. Wired through the existing signal/flow handling so
            both the hub and in-delve chart share one path."""
            self._close_delve_anima_panel()
            self._hub_popup = None
            self._chart_screen = None
            if self._delve is not None:
                self._handle_signal('return_to_hub_delve')

        def _on_chart_select(self, node_id):
            """Chart node picked in the hub.

            Resume: clicking the node you're on continues the journey exactly
            where it left off — the saved layout is never wiped. Picking another
            reachable node travels the same chart (the graph persists; only the
            room state resets at the new node).
            """
            chart = self._chart_screen.chart
            self._hub_popup = None
            if self._chart_resume and node_id == chart.get('current_node_id'):
                self._chart_entry = None
                self._handle_signal('enter_delve')
                return
            self._chart_entry = (chart, node_id)
            self._chart_resume = False
            self._saved_delve = None
            import entities.progression as _prog
            _prog.clear_delve_data(self.char.id)
            self._handle_signal('enter_delve')

        def _enter_delve(self):
            self._close_delve_anima_panel()
            self.iso.set_path_cells([])
            # Clear any stale menu signal (e.g. 'return_to_hub' leaked from a Hub
            # popup) so it can't fire later and yank the player out of the delve.
            self.menu_sys.signal()

            # ── Resume saved delve, or start fresh ────────────────────────
            saved = self._saved_delve
            self._saved_delve = None
            if saved is None:
                import entities.progression as _prog
                saved = _prog.load_delve_data(self.char.id)
            if saved is not None:
                try:
                    self.map          = saved['map']
                    self._delve       = saved['delve']
                    self.zombies      = saved['zombies']
                    self.ground_items = saved['ground_items']
                    self._decor_items = saved['decor_items']
                    self.px, self.py  = float(self._delve['pulse_x']), float(self._delve['pulse_y'])
                    if 'node' not in self._delve or 'enemy_ids' not in self._delve:
                        raise KeyError('old format')
                    if self._delve['state'] == 'dirs':
                        self._delve['state'] = 'ready'
                    # Old saves predate the chart graph — attach a fresh one.
                    if 'chart' not in self._delve:
                        self._init_delve_chart()
                    import core.delve_gen as _dg
                    # Re-lay out any chart saved under the older, looser
                    # spacing (deterministic from the stored graph).
                    _dg.layout_positions(self._delve['chart']['graph'])
                    _dg.ensure_depth_rows(
                        self._delve['chart']['graph'],
                        self._delve_chart_rng(), self._delve['depth'])
                    _dg.ensure_row_supply(
                        self._delve['chart']['graph'],
                        self._delve_chart_rng(),
                        self._delve['chart'].get('current_node_id'))
                    self._delve.setdefault('_cracked_cells', [])
                    self._delve.setdefault('hidden_wings', {})
                    self._delve.setdefault('relics', [])
                except Exception:
                    saved = None

            if saved is None:
                import entities.progression as _prog
                _prog.clear_delve_data(self.char.id)
                entry = self._chart_entry
                self._chart_entry = None
                if entry is not None:
                    entry_chart, entry_node_id = entry
                    entry_node = entry_chart['graph']['nodes'].get(entry_node_id)
                    depth = entry_node['depth'] if entry_node is not None else 1
                else:
                    depth = 1
                import core.delve_gen as _dg
                data = _dg.init_delve_room(self.char.seed, depth)
                self.map = data['grid']
                node = data['node']
                self.px, self.py = node['col'], node['row']
                self.ground_items = []
                self.zombies      = []
                self._decor_items = []

                self._delve = {
                    'state':           'clearing',
                    'depth':           depth,
                    'node':            node,
                    'enemy_ids':       set(),
                    'pending_rewards': [],
                    'pulse_x':         node['col'],
                    'pulse_y':         node['row'],
                    'light_r':         DELVE_LIGHT_RADIUS,
                    'darkness_dps':    DELVE_DARKNESS_DPS * (1.0 + depth * 0.3),
                    'dark_timer':      0.0,
                    'relics':          [],
                }
                if entry is not None:
                    # Resume the chart from the node picked on the chart screen.
                    self._delve['chart'] = entry_chart
                    entry_node['state'] = _dg.STATE_CLEARED
                    if entry_node.get('type') == 'checkpoint':
                        entry_node['touched'] = True
                        if entry_node_id not in entry_chart['checkpoints']:
                            entry_chart['checkpoints'].append(entry_node_id)
                    if entry_node_id not in entry_chart['visited']:
                        entry_chart['visited'].append(entry_node_id)
                    entry_chart['current_node_id'] = entry_node_id
                    entry_chart['route'] = [entry_node_id]
                    entry_chart['best_depth'] = max(
                        entry_chart.get('best_depth', 0) or 0, depth)
                else:
                    self._init_delve_chart()
                self._delve_spawn_wave(depth)

            self.player_state  = 'idle'
            self.player_facing = 'S'
            self.anim_time     = 0.0
            self.dest_col = self.dest_row = None
            self.attack_target = None
            self.interact_target = None
            self.drop_target   = None
            self.attack_cd     = 0.0
            self.raid_time     = 0.0

            bonuses = compute_perk_bonuses(
                self.char.perks, self.char.descend,
                item_bonuses=itemgen.aggregate_item_bonuses(self.inventory))
            equip_b = self._equipped_bonuses()
            item_attr = {a: equip_b.get(a, 0) for a in DESCEND_ATTRIBUTES}
            derived = compute_derived_stats(
                self.char.descend, bonuses,
                item_bonuses=item_attr, looks=self.char.looks)
            reset_stats(self.stats, **derived)
            if saved is None:
                # A FRESH run starts at full pools (owner ruling
                # 2026-10-07); resumes keep their pools — reset_stats
                # preserves them, so no refill happens there.
                self.stats['health'] = self.stats['max_health']
                self.stats['mana'] = self.stats['max_mana']
                self.stats['energy_shield'] = self.stats.get('max_energy_shield', 0.0)

            # Apply passive-tree bonuses to delve lighting
            if self._delve is not None:
                self._delve['light_r'] = max(1.0, DELVE_LIGHT_RADIUS + derived.get('delve_light_radius', 0))
                self._delve['_base_light_r'] = self._delve['light_r']
                self._delve.setdefault('_enemy_hp_mult', 1.0)
                self._delve.setdefault('_enemy_count_bonus', 0)
                resist = derived.get('darkness_resist_pct', 0.0)
                self._delve['darkness_dps'] *= max(0.0, 1.0 - resist)

            if self.char.inventory is None:
                self.char.inventory = make_inventory()
            self.inventory = self.char.inventory

            self._enemy_id_seq = 0
            self.inv.on_drop_item = self._on_inv_drop
            self._ensure_darkness_rt()

            self.iso.generate_props(self.map)
            self.iso.clear_props_around(self.px, self.py, 3)
            self._sync_weather(depth=self._delve.get('depth', 1) if self._delve else 1)
            self._spawn_delve_objects()
            self.iso.follow(self.px, self.py)

            self.raid_running  = True

            # The flask is the only consumable (T slot); refill its charges per run.
            self._refill_flasks()
            self._wave_num     = 0
            self._next_wave_t  = 99999.0
            self._spawn_queue  = []
            self._spawn_timer  = 0.0
            self._ability_cds  = {'lungs': 0.0, 'liver': 0.0}
            self._gem_cds      = {'Q': 0.0, 'W': 0.0, 'E': 0.0, 'R': 0.0}
            self._flask_cd     = 0.0
            self.flask_effects = []
            self._angel_meter  = 0.0
            self._angel_timer  = 0.0
            self._kill_streak  = 0
            self._last_kill_t  = -999.0
            self._streak_pop_t       = -999.0
            self._streak_milestone   = None
            self._streak_milestone_t = -999.0
            self._streak_lost_t      = -999.0
            self._lifesteal_timer  = 0.0
            self._lifesteal_pct    = 0.0
            self._fire_aura_timer  = 0.0
            self._fire_aura_radius = 0.0
            self._fire_aura_dps    = 0.0
            self._aura_tick        = 0.0
            self._incoming_dmg_by_type: dict[str, float] = {}
            self.tracker.reset()
            self._raid_results = None
            self.audio.reset()

            self.state = STATE_PLAYING
            self.audio.set_delve_music()   # continuous western playlist (restarts at track 1)

        def _enemy_max_health(self, enemy_type, level, hp_mult: float = 1.0) -> int:
            """Level-1 enemies are a guaranteed one-shot (HP below the player's
            minimum level-1 hit of 25, regardless of D.E.S.C.E.N.D. investment);
            from level 2 upward HP scales gradually so fights take more hits."""
            level = max(1, int(level))
            if level <= 1:
                base = 18.0 if enemy_type != 'slime' else 22.0
            else:
                per  = 20.0 if enemy_type != 'slime' else 30.0
                base = (18.0 if enemy_type != 'slime' else 22.0) + (level - 1) * per
            return int(round(base * hp_mult))

        def _enemy_mitigation(self, level):
            """Per-level armor (damage_reduction) and resist_pct. Zero at level 1
            (guaranteeing the one-shot); grows gradually and is hard-capped."""
            level = max(1, int(level))
            dr   = min(0.50, (level - 1) * 0.01)
            res  = min(0.60, (level - 1) * 0.03)
            return {
                'damage_reduction': dr,
                'resist_pct': {
                    'fire': res, 'cold': res, 'lightning': res, 'physical': res,
                    'magic': res, 'rot': res, 'darkness': res,
                },
            }

        def _delve_enemy_hp(self, base: float, enemy_level: int = 1) -> float:
            # Retained for existing callers; maps the old base onto the new curve.
            etype = 'slime' if base >= 150.0 else 'skeleton'
            return self._enemy_max_health(etype, enemy_level)

        @staticmethod
        def _build_delve_snapshot(delve, map_, zombies, ground_items, decor_items):
            """Build a fully isolated snapshot of the live delve state.

            Every nested object is deep-copied so that any later mutation of the
            live game objects (``self._delve``, ``self.map``, ...) cannot leak into
            the snapshot. This guarantees isolation for both the in-memory resume
            snapshot (``_saved_delve``) and the on-disk save. See QoL #113 /
            GitHub issue #16.
            """
            return {
                'delve':        copy.deepcopy(delve),
                'map':          copy.deepcopy(map_),
                'zombies':      copy.deepcopy(zombies),
                'ground_items': copy.deepcopy(ground_items),
                'decor_items':  copy.deepcopy(decor_items),
            }

        def _save_delve(self):
            """Save current delve state to disk so it survives a crash or restart."""
            if self._delve is None:
                return
            import entities.progression as _prog
            snapshot = self._build_delve_snapshot(
                self._delve, self.map, self.zombies, self.ground_items, self._decor_items)
            _prog.save_delve_data(self.char.id, snapshot)

        def _exit_delve(self, destination='hub'):
            self._close_delve_anima_panel()
            self.raid_running = False
            # Save delve state so we can resume later. The snapshot is a deep copy
            # (see _build_delve_snapshot) so later mutations of the live delve
            # objects cannot leak into the saved data.
            self._saved_delve = self._build_delve_snapshot(
                self._delve, self.map, self.zombies, self.ground_items, self._decor_items)
            self._save_delve()
            self._delve = None
            self.char_mgr.save()
            self._enter_hub()

        def _update_delve(self, dt: float):
            d = self._delve

            # Checkpoint relic shrine — offer 1-of-3 run boons (§6/§7)
            if d.get('_pending_relic_offer') and d['state'] == 'ready':
                d['_pending_relic_offer'] = False
                self._open_relic_offer()
                return
            if d['state'] == 'relic':
                self._update_relic_choice()
                return

            # ── pulse arriving (slide to new position, then spawn wave) ──
            if d['state'] == 'arriving':
                tx = d.get('_arrive_to_x', d['pulse_x'])
                ty = d.get('_arrive_to_y', d['pulse_y'])
                dx = tx - d['pulse_x']
                dy = ty - d['pulse_y']
                dist = math.hypot(dx, dy)
                if dist < 0.15:
                    d['pulse_x'] = tx
                    d['pulse_y'] = ty
                    d.pop('_arrive_timer', None)
                    d.pop('_arrive_from_x', None)
                    d.pop('_arrive_from_y', None)
                    d.pop('_arrive_to_x', None)
                    d.pop('_arrive_to_y', None)
                    self._delve_spawn_wave(d['depth'])
                    d['state'] = 'clearing'
                else:
                    speed = DELVE_PULSE_SPEED + d['depth'] * 0.05
                    step = speed * dt / dist
                    d['pulse_x'] += dx * step
                    d['pulse_y'] += dy * step
                return

            # ── clearing enemies ─────────────────────────────────────────
            if d['state'] == 'clearing':
                all_clear = all(
                    z['health'] <= 0
                    for z in self.zombies
                    if z['id'] in d.get('enemy_ids', set())
                )
                if all_clear:
                    d['enemy_ids'] = set()
                    # Drop pending rewards as ground loot
                    for slot in d.get('pending_rewards', []):
                        item_id = slot['item']
                        count = slot.get('count', 1)
                        angle = _rnd.uniform(0, 6.2832)
                        dist = _rnd.uniform(0.4, 2.0)
                        drop_x = d['pulse_x'] + math.cos(angle) * dist
                        drop_y = d['pulse_y'] + math.sin(angle) * dist
                        self.ground_items.append({
                            'x':     drop_x,
                            'y':     drop_y,
                            'items': [slot],
                            'type':  'drop',
                        })
                        self._loot_sparkles.append({'x': drop_x, 'y': drop_y, 'timer': 2.0})
                    d['pending_rewards'] = []

                    self._delve_mark_cleared()
                    self._apply_organ_rot()
                    d['state'] = 'ready'
                    self._save_delve()

            # ── junction choice mode (chart branching) ─
            if d['state'] == 'junction':
                if inp.key_pressed(self, rl.KEY_ESCAPE):
                    d['state'] = 'ready'
                    return
                if inp.mouse_pressed(self, rl.MOUSE_BUTTON_LEFT):
                    mx, my = rl.get_mouse_x(), rl.get_mouse_y()
                    for rect, kid in d.get('_junction_rects', []):
                        if rl.check_collision_point_rec(rl.Vector2(float(mx), float(my)), rect):
                            d['_junction_rects'] = []
                            self._delve_descend(kid['id'])
                            return
                return

            # Anima chart opened from the delve heart.  Keep the same chart
            # component as the hub, with the current wave's children as choices.
            # Open state is transient runtime state, never part of the saved delve
            # snapshot; every close path funnels through one helper.
            if self._delve_chart_is_open():
                if inp.key_pressed(self, rl.KEY_ESCAPE):
                    self._close_delve_anima_panel()
                    return
                _, _, content = self._anima_layout(rl.get_screen_width(), rl.get_screen_height())
                result = self._chart_screen.update(
                    dt, origin=(content.x, content.y), view=(content.width, content.height))
                if result == 'close':
                    self._close_delve_anima_panel()
                    return
                if isinstance(result, tuple) and result[0] == 'return_hub':
                    self._on_chart_return_hub()
                    return
                if isinstance(result, tuple) and result[0] == 'select':
                    child_id = result[1]
                    self._close_delve_anima_panel()
                    self._delve_descend(child_id)
                return

            # Escalating darkness DoT: inside 100% of the
            # light radius is safe; 100-130% is a "dim" band (slow ramp, capped
            # DPS); beyond that the ramp builds to full DPS and keeps growing
            # after 5s of continuous darkness. Checkpoint braziers count as
            # extra light sources.
            import core.delve_gen as _dg
            zone = _dg.zone_for_depth(d['depth'])
            ramp_mult = zone['mods'].get('darkness_ramp_mult', 1.0)

            dist_to_pulse = math.hypot(self.px - d['pulse_x'],
                                         self.py - d['pulse_y'])
            light_r = d['light_r'] + DELVE_PERSONAL_LIGHT
            in_light = dist_to_pulse <= light_r
            in_dim = (not in_light) and dist_to_pulse <= light_r * 1.3
            d['_dark_slow'] = (zone['mods'].get('player_slow_outside_light', 0.0)
                               if not in_light else 0.0)

            if in_light or self._god_mode:
                d['dark_timer'] = 0.0
            else:
                # Ramp: 0 → 100% over 2.5s in the dark; +15%/s after 5s.
                d['dark_timer'] += dt * (0.5 if in_dim else 1.0) * ramp_mult
                dps_mult = min(1.0, d['dark_timer'] / 2.5)
                if d['dark_timer'] > 5.0:
                    dps_mult += 0.15 * (d['dark_timer'] - 5.0)
                if in_dim:
                    dps_mult = min(dps_mult, 0.5)
                self.stats['health'] = max(0.0, self.stats['health'] - d['darkness_dps'] * dps_mult * dt)
                self.hit_flash       = max(self.hit_flash, 0.18)
                if self.stats['health'] <= 0:
                    self.raid_running = False
                    self._permadeath()
                    return

        def _delve_spawn_wave(self, depth: int):
            """Spawn a wave of enemies around the pulse at the given depth."""
            import core.delve_gen as _dg
            # Owner's tuning rule: the T flask gets exactly one use per wave.
            # Charges reset to 1 here (wave lifecycle), never mid-wave.
            self._refill_flasks()
            d = self._delve
            zone = _dg.zone_for_depth(depth)
            zone_mods = zone['mods']

            # Super-linear depth curve (§5): depth 50 fights like ~66
            enemy_level = _dg.effective_level(depth)
            enemy_count = min(20, 5 + depth) + d.get('_enemy_count_bonus', 0)
            enemy_count = int(enemy_count * zone_mods.get('enemy_count_mult', 1.0))
            enemy_count = max(1, enemy_count)
            enemy_hp_mult = (d.get('_enemy_hp_mult', 1.0)
                             * self._relic_effects()['enemy_hp_mult'])
            pulse_x = d['pulse_x']
            pulse_y = d['pulse_y']

            # Elite affixes from depth 10 (1/wave scaling to 3 at depth 40, §5)
            elite_budget = 0
            if depth >= 10:
                elite_chance = min(0.9, 0.10 + depth * 0.005
                                   + zone_mods.get('elite_chance_bonus', 0.0))
                elite_budget = min(3, int(depth / 10)) if _rnd.random() < elite_chance else 0

            # Spawn inside the current room rectangle so even tiny (3-5 tile) rooms
            # work, and pack enemies in for chaotic, close-quarters fights. We
            # collect the actual floor tiles in the room and sample from those so
            # positions always land on walkable floor.
            room_w = d['node'].get('w', 5)
            room_h = d['node'].get('h', 5)
            hw = max(0, (room_w - 1) // 2)
            hh = max(0, (room_h - 1) // 2)
            cx, cy = int(round(pulse_x)), int(round(pulse_y))
            candidates = []
            for dc in range(-hw, hw + 1):
                for dr in range(-hh, hh + 1):
                    tc, tr = cx + dc, cy + dr
                    if (0 <= tc < len(self.map) and 0 <= tr < len(self.map[0])
                            and self.map[tc][tr] == 0 and math.hypot(dc, dr) >= 0.9):
                        candidates.append((tc, tr))
            if not candidates:
                candidates = [(cx, cy)]

            _rnd.shuffle(candidates)
            for i in range(enemy_count):
                tc, tr = candidates[i % len(candidates)]
                ex, ey = float(tc), float(tr)
                etype = _rnd.choice(['skeleton', 'skeleton', 'slime'])
                if etype == 'slime':
                    hp = self._delve_enemy_hp(150.0, enemy_level) * enemy_hp_mult
                else:
                    hp = self._delve_enemy_hp(100.0, enemy_level) * enemy_hp_mult
                is_elite = elite_budget > 0
                if is_elite:
                    elite_budget -= 1
                    hp *= 2.0
                self._enemy_id_seq += 1
                mit = self._enemy_mitigation(enemy_level)
                accuracy = (int(combat.skeleton_accuracy(enemy_level) * 0.8)
                            if etype == 'slime' else combat.skeleton_accuracy(enemy_level))
                if is_elite:
                    accuracy = int(accuracy * 1.3)
                enemy = {
                    'id':               f'dse{self._enemy_id_seq}',
                    'enemy_type':       etype,
                    'level':            enemy_level,
                    'elite':            is_elite,
                    'x':                ex,
                    'y':                ey,
                    'health':           hp,
                    'max_health':       hp,
                    'state':            'idle',
                    'anim_timer':       0.0,
                    'frame':            0,
                    'facing_x':         1.0,
                    'facing_y':         0.0,
                    'accuracy':         accuracy,
                    'evasion':          enemy_evasion(etype, enemy_level),
                    'spawn_x':          ex,
                    'spawn_y':          ey,
                    'move_speed':       make_move_speed(etype),
                    'speed_ramp':       0.0,
                    'dmg_type':         _pick_enemy_dmg_type(enemy_level),
                    'damage_reduction': mit['damage_reduction'],
                    'resist_pct':       dict(mit['resist_pct']),
                    **default_status_fields(),
                }
                self.zombies.append(enemy)
                d['enemy_ids'].add(enemy['id'])

        def _room_reward_slots(self, node, base_ilvl: int) -> list:
            """Room-clear reward: EXACTLY what the chart promised for this
            node (pre-rolled at chart generation, shown on the chart and the
            room labels — BLUEPRINT §23) plus the tarot card roll on top.
            Legacy charts whose nodes lack a 'rewards' key fall back to the
            old random roll."""
            rewards = node.get('rewards')
            if rewards is None:   # old save without pre-rolled rewards
                rewards = self._legacy_random_reward(base_ilvl)
            slots = [itemgen.roll_for(reward['item'], reward.get('count', 1),
                                      max(1, base_ilvl))
                     for reward in rewards]
            # ROT ETERNAL roll (§27): 2% on organ drops at depth 1-10
            for slot in slots:
                itemgen.try_rot_mythic(slot, max(1, base_ilvl))
            # Tarot card roll, depth-scaled arcana (§19) — whole-card drops
            if _rnd.random() < 0.10:
                slots.append(currency.roll_card_drop_slot(max(1, base_ilvl), _rnd))
            return slots

        def _legacy_random_reward(self, base_ilvl: int) -> list:
            """Pre-§24 fallback: one random organ or gem (never empty)."""
            pool = ['liver', 'lungs', 'kidney', 'intestine', 'heart',
                    'gem_blue', 'gem_green', 'gem_red', 'gem_white']
            return [{'item': _rnd.choice(pool), 'count': 1}]

        def _init_delve_chart(self):
            """Create the persistent branching chart for a fresh delve."""
            import core.delve_gen as _dg
            seed = int(getattr(self.char, 'seed', 0)) ^ int(_rnd.getrandbits(24))
            graph = _dg.init_delve(seed)
            self._delve['chart'] = {
                'seed':            seed,
                'graph':           graph,
                'current_node_id': graph['start_node_id'],
                'visited':         [graph['start_node_id']],
                'looted':          [],
                'checkpoints':     [],
                'route':           [graph['start_node_id']],
                'best_depth':      1,
            }
            rng = _rnd.Random(seed ^ 0x5EED)
            _dg.ensure_depth_rows(graph, rng, 1)
            self._sync_chart_rng(rng)

        def _sync_chart_rng(self, rng=None):
            """Keep a persistent RNG for lazy chart extension. Its state is not
            serialized — the full graph is, so determinism comes from the save."""
            if rng is None:
                rng = _rnd.Random()
            self._delve['_chart_rng_state'] = True
            self._chart_rng = rng

        def _delve_chart_rng(self):
            rng = getattr(self, '_chart_rng', None)
            if rng is None:
                rng = _rnd.Random()
                self._chart_rng = rng
            return rng

        def _mouse_world_pos(self):
            """World (tile) position under the mouse cursor."""
            cw = rl.get_screen_width()
            ch = rl.get_screen_height()
            mx, my = rl.get_mouse_x(), rl.get_mouse_y()
            col, row = self.iso.screen_to_world(mx, my, cw, ch)
            return float(col), float(row)

        def _attach_hidden_wing(self):
            """Roll a hidden reward wing for the freshly carved room (§4)."""
            import core.delve_gen as _dg
            d = self._delve
            d.setdefault('hidden_wings', {})
            d.setdefault('_cracked_cells', [])
            rng = _rnd.Random()
            zone = _dg.zone_for_depth(d['depth'])
            wing_chance = (_dg.HIDDEN_WING_CHANCE
                           + zone['mods'].get('cracked_wall_bonus', 0.0))
            if rng.random() > wing_chance:
                return
            wing_id = len(d['hidden_wings'])
            while wing_id in d['hidden_wings']:
                wing_id += 1
            wing = _dg.generate_hidden_wing(self.map, d['node'], rng, wing_id)
            if wing is None:
                return
            d['hidden_wings'][wing_id] = {
                'id': wing_id, 'cx': wing['cx'], 'cy': wing['cy'],
                'loot': self._roll_hidden_loot(d['depth']),
                'ambush': rng.random() < _dg.hidden_tier_for_depth(d['depth'])['ambush_chance'],
                'opened': False,
            }
            d['_cracked_cells'].extend(wing['cracked'])
            self.iso.generate_props(self.map)
            self._sync_weather(depth=self._delve.get('depth', 1))

        def _roll_hidden_loot(self, depth: int) -> list:
            """Depth-tiered hidden wing loot."""
            import core.delve_gen as _dg
            tier = _dg.hidden_tier_for_depth(depth)
            slots = []

            # Tarot currency fraction, scaling with depth (issue #73 phase B)
            if _rnd.random() < self._card_drop_chance(depth):
                slots.append(currency.roll_card_drop_slot(max(1, depth), _rnd))

            # Chest roll (organ drops, like delve_gen.REWARD_TABLES)
            if _rnd.random() < 0.8:
                organ = _rnd.choice(['lungs', 'liver', 'heart', 'kidney', 'intestine'])
                slots.append(itemgen.roll_for(organ, 1, depth))

            # Guaranteed equipment from depth 10 (rarity floor per tier).
            # rarity_floor is a RARITY_ORDER INDEX (int) — map to its name;
            # feeding the int straight into generate_instance used to raise
            # KeyError the moment equip_guaranteed flipped on (depth 10+).
            if tier['equip_guaranteed']:
                organ = _rnd.choice(['lungs', 'liver', 'heart', 'intestine'])
                defn = ITEMS.get(organ, {})
                slots.append({
                    'item': organ, 'count': 1,
                    'instance_data': itemgen.generate_instance(
                        organ, depth + tier.get('reward_ilvl_bonus', 0),
                        rarity=itemgen.RARITY_ORDER[tier['rarity_floor']],
                        equip_slot=defn.get('equipSlot'),
                        base_name=defn.get('name', organ)),
                })
            # ROT ETERNAL roll (§27): 2% on organ drops at depth 1-10
            for slot in slots:
                itemgen.try_rot_mythic(slot, depth)
            return slots

        @staticmethod
        def _card_drop_chance(depth: int) -> float:
            """Tarot card drop chance (§6): ~2% wings, ~8% bosses, depth-scaled."""
            return min(0.12, 0.02 + depth * 0.001)

        def _open_hidden_wing(self, wing_id):
            """Drop a hidden wing's loot when its cracked seal is broken (§4)."""
            d = self._delve
            wing = d.get('hidden_wings', {}).get(wing_id)
            if wing is None or wing.get('opened'):
                return
            wing['opened'] = True
            chart = d.get('chart') or {}
            if wing_id not in chart.get('looted', []):
                chart.setdefault('looted', []).append(wing_id)
            for slot in wing.get('loot', []):
                self.ground_items.append({
                    'x': wing['cx'] + _rnd.uniform(-0.8, 0.8),
                    'y': wing['cy'] + _rnd.uniform(-0.8, 0.8),
                    'items': [slot], 'type': 'drop',
                })
                self._loot_sparkles.append(
                    {'x': wing['cx'], 'y': wing['cy'], 'timer': 2.0})
            if wing.get('ambush'):
                self._delve_spawn_wave(d['depth'])

        def _relic_effects(self) -> dict:
            import systems.delve_relics as relics
            return relics.aggregate_relic_effects(
                self._delve.get('relics', []) if self._delve else [])

        def _open_relic_offer(self):
            """Offer 1-of-3 run boons at a checkpoint shrine."""
            import systems.delve_relics as relics
            d = self._delve
            d['_relic_offer'] = relics.roll_relic_offer(
                _rnd.Random(), d.get('relics', []))
            d['state'] = 'relic'

        def _update_relic_choice(self):
            d = self._delve
            if inp.key_pressed(self, rl.KEY_ESCAPE):
                d['_relic_offer'] = None
                d['state'] = 'ready'
                return
            if inp.mouse_pressed(self, rl.MOUSE_BUTTON_LEFT):
                mx, my = rl.get_mouse_x(), rl.get_mouse_y()
                for rect, boon in d.get('_relic_rects', []):
                    if rl.check_collision_point_rec(rl.Vector2(float(mx), float(my)), rect):
                        d.setdefault('relics', []).append(boon['id'])
                        d['_relic_offer'] = None
                        d['_relic_rects'] = []
                        d['state'] = 'ready'
                        self._apply_relic_passives()
                        self._save_delve()
                        return

        def _apply_relic_passives(self):
            """Re-apply relic multipliers to live delve state."""
            d = self._delve
            if d is None:
                return
            effects = self._relic_effects()
            base_light = d.get('_base_light_r', DELVE_LIGHT_RADIUS)
            d['light_r'] = max(1.0, base_light * effects['light_mult'])
            d['_base_darkness_dps'] = DELVE_DARKNESS_DPS * (1.0 + d['depth'] * 0.3)
            d['darkness_dps'] = d['_base_darkness_dps'] * effects['darkness_mult']

        def _delve_children(self):
            """Nodes the player may enter right now.

            Rules: cleared nodes are permanently done and never enterable;
            discovered-but-uncleared nodes you walked past stay enterable (so
            retreating to a shallower node is a legal, lower-darkness move);
            forward children of the current node stay enterable.
            """
            import core.delve_gen as _dg
            chart = self._delve.get('chart')
            if not chart:
                return []
            graph = chart['graph']
            _dg.ensure_depth_rows(graph, self._delve_chart_rng(), self._delve['depth'])
            # Depth rows are infinite (§26) — refresh an exhausted row
            _dg.ensure_row_supply(graph, self._delve_chart_rng(),
                                  chart.get('current_node_id'))
            enterable = set(_dg.enterable_node_ids(graph, chart))
            return [graph['nodes'][nid] for nid in sorted(enterable)
                    if nid in graph['nodes'] and not graph['nodes'][nid].get('dead_end')]

        def _apply_organ_rot(self):
            """End-of-wave organ rot (BLUEPRINT §22): every organ carried in
            the inventory (equipped + backpack) gains a flat rot chunk. When
            an EQUIPPED organ turns ROTTEN its affix values changed, so the
            derived-stat cache is invalidated the same way an implant does
            (see _on_gear_changed)."""
            import systems.itemgen as itemgen
            if itemgen.apply_wave_rot(self.inventory):
                self._on_gear_changed()

        def _delve_mark_cleared(self):
            """Mark the current chart node cleared (called on room-clear)."""
            chart = self._delve.get('chart')
            if not chart:
                return
            import core.delve_gen as _dg
            graph = chart['graph']
            node = graph['nodes'].get(chart['current_node_id'])
            if node is None:
                return
            node['state'] = _dg.STATE_CLEARED
            if node['id'] not in chart['visited']:
                chart['visited'].append(node['id'])
            if node['type'] == 'checkpoint' and node['id'] not in chart['checkpoints']:
                chart['checkpoints'].append(node['id'])
                node['touched'] = True
            # The depth record only ever grows.
            chart['best_depth'] = max(chart.get('best_depth', 0) or 0,
                                      node['depth'])

        def _delve_descend(self, child_id=None):
            """Move the delve to a child chart node (junction choice), carving a
            room for it."""
            import core.delve_gen as _dg
            d = self._delve
            chart = d.get('chart')
            if not chart:
                self._init_delve_chart()
                chart = d['chart']

            kids = self._delve_children()
            if not kids:
                d['state'] = 'clearing'
                return
            child = None
            if child_id is not None:
                child = next((k for k in kids if k['id'] == child_id), None)
            if child is None:
                child = kids[0]

            parent = chart['graph']['nodes'][chart['current_node_id']]
            parent['state'] = _dg.STATE_CLEARED

            # Depth follows the CURRENT node: moving to a left-behind node
            # retreats to a shallower depth (less darkness pressure), while
            # the depth record is monotonic and never rolls back.
            d['depth'] = child['depth']
            chart['best_depth'] = max(chart.get('best_depth', 0) or 0, d['depth'])

            # Choose a carve direction from the child's chart column position:
            # left → W, right → E, centre → S (downward bias like the chart).
            col_diff = child['col'] - parent['col']
            carve_dir = 'S'
            if col_diff < -0.15:
                carve_dir = 'W'
            elif col_diff > 0.15:
                carve_dir = 'E'

            d['_enemy_hp_mult'] = 1.0
            d['_enemy_count_bonus'] = 0
            effects = self._relic_effects()
            d['light_r'] = max(1.0, d.get('_base_light_r', DELVE_LIGHT_RADIUS)
                               * effects['light_mult'])
            d['pending_rewards'] = self._room_reward_slots(child, d['depth'])
            d['darkness_dps'] = (DELVE_DARKNESS_DPS * (1.0 + d['depth'] * 0.3)
                                 * effects['darkness_mult'])
            d['_pending_relic_offer'] = child['type'] == 'checkpoint'

            newly = self.char_mgr.note_depth(d['depth'])
            if newly:
                self._vessel_unlock_msg = newly[-1]
                self._vessel_unlock_timer = 3.5

            rng = _rnd.Random()
            new_node = _dg.generate_segment(self.map, d['node'], carve_dir, rng, d['depth'])
            d['node'] = new_node
            # Link the physical room onto the chart node so the chart screen can
            # show visited geometry.
            child['grid_col'] = new_node['col']
            child['grid_row'] = new_node['row']
            child['state'] = _dg.STATE_AVAILABLE
            # Any DIRECT edge counts as forward — sideways moves along a row
            # append to the golden route just like descending does (§26).
            was_forward = any({p, c} == {parent['id'], child['id']}
                              for p, c in chart['graph']['edges'])
            chart['current_node_id'] = child['id']
            # Forward moves append; retreating to a left-behind node rewrites
            # the golden route to the real path taken.
            if was_forward:
                if child['id'] in chart['route']:
                    chart['route'] = chart['route'][:chart['route'].index(child['id']) + 1]
                else:
                    chart['route'].append(child['id'])
            else:
                chart['route'] = _dg.find_route(chart['graph'],
                                                parent['id'], child['id'])

            d['_arrive_to_x'] = new_node['col']
            d['_arrive_to_y'] = new_node['row']
            d['state'] = 'arriving'
            self.iso.generate_props(self.map)
            self._sync_weather(depth=d['depth'], strength=None)
            self.ground_items = [gi for gi in self.ground_items if gi['type'] in ('drop', 'portal')]
            self._decor_items = []
            self._spawn_delve_objects()
            self._attach_hidden_wing()
            self._save_delve()

        def _delve_chart_is_open(self):
            """Return whether the transient delve-heart chart popup is open."""
            return bool(getattr(self, '_delve_chart_open', False))

        def _close_delve_anima_panel(self):
            """Close the delve-heart chart and clear all transient open state."""
            self._delve_chart_open = False

        def _open_delve_anima_panel(self):
            """Open the hub's shared Anima chart for the current wave."""
            d = self._delve
            if d is None or d.get('state') != 'ready':
                return False
            kids = self._delve_children()
            if not kids:
                return False
            if self._chart_screen is None:
                from ui.delve_chart import DelveChartScreen
                self._chart_screen = DelveChartScreen(self)
            self._chart_screen.open(
                d['chart'], selectable_ids=[kid['id'] for kid in kids],
                on_select=lambda _node_id: None, title='Anima Chart', closable=True)
            self._delve_chart_open = True
            return True

        def _trigger_wave(self):
            self._wave_num    += 1
            self._next_wave_t += 20.0

            wave_number = self._wave_num
            sk_count    = min(6 + wave_number * 2, 24)
            sl_count    = min(wave_number + 1,     10)

            entries = ['skeleton'] * sk_count + ['slime'] * sl_count
            random.shuffle(entries)
            for enemy_type in entries:
                self._spawn_queue.append(enemy_type)

        def _drain_spawn_queue(self, dt):
            if not self._spawn_queue:
                return

            spawn_interval = max(0.3, 1.2 - self._wave_num * 0.09)
            self._spawn_timer -= dt
            if self._spawn_timer > 0:
                return

            self._spawn_timer = spawn_interval
            enemy_type  = self._spawn_queue.pop(0)
            enemy_level = self._get_enemy_level()
            mit         = self._enemy_mitigation(enemy_level)

            min_r = 8
            max_r = min(14 + self._wave_num, 20)
            _map  = self.map

            for _ in range(120):
                angle = random.uniform(0, math.tau)
                dist  = random.uniform(min_r, max_r)
                spawn_x = self.px + math.cos(angle) * dist
                spawn_y = self.py + math.sin(angle) * dist
                tile_col, tile_row = int(spawn_x), int(spawn_y)
                if not (0 <= tile_col < MAP_SIZE and 0 <= tile_row < MAP_SIZE):
                    continue
                if _map[tile_col][tile_row] != 0:
                    continue

                self._enemy_id_seq += 1
                if enemy_type == 'slime':
                    slime_hp = self._enemy_hp(150.0)
                    self.zombies.append({
                        'id':               f'wsl{self._enemy_id_seq}',
                        'enemy_type':       'slime',
                        'level':            int(enemy_level),
                        'x':                spawn_x,
                        'y':                spawn_y,
                        'health':           slime_hp,
                        'max_health':       slime_hp,
                        'state':            'idle',
                        'anim_timer':       0.0,
                        'frame':            0,
                        'facing_x':         1.0,
                        'facing_y':         0.0,
                        'accuracy':         int(combat.skeleton_accuracy(int(enemy_level)) * 0.8),
                        'evasion':          enemy_evasion('slime', enemy_level),
                        'spawn_x':          spawn_x,
                        'spawn_y':          spawn_y,
                        'move_speed':       make_move_speed('slime'),
                        'speed_ramp':       0.0,
                        'dmg_type':         _pick_enemy_dmg_type(enemy_level),
                        'damage_reduction': mit['damage_reduction'],
                        'resist_pct':       dict(mit['resist_pct']),
                        **default_status_fields(),
                    })
                else:
                    skeleton_hp = self._enemy_hp(100.0)
                    self.zombies.append({
                        'id':               f'wsk{self._enemy_id_seq}',
                        'enemy_type':       'skeleton',
                        'level':            int(enemy_level),
                        'x':                spawn_x,
                        'y':                spawn_y,
                        'health':           skeleton_hp,
                        'max_health':       skeleton_hp,
                        'state':            'idle',
                        'anim_timer':       0.0,
                        'frame':            0,
                        'facing_x':         1.0,
                        'facing_y':         0.0,
                        'accuracy':         combat.skeleton_accuracy(int(enemy_level)),
                        'evasion':          enemy_evasion('skeleton', enemy_level),
                        'spawn_x':          spawn_x,
                        'spawn_y':          spawn_y,
                        'move_speed':       make_move_speed('skeleton'),
                        'speed_ramp':       0.0,
                        'dmg_type':         _pick_enemy_dmg_type(enemy_level),
                        'damage_reduction': mit['damage_reduction'],
                        'resist_pct':       dict(mit['resist_pct']),
                        **default_status_fields(),
                    })
                break

