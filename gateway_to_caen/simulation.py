"""Procedural tactical battlefield simulation and persistent learning AI."""
from __future__ import annotations

import math
import random
import time
import uuid
from dataclasses import asdict, dataclass
from typing import Any, Iterable

from .neural import ACTIONS, TacticalBrain

MAP_WIDTH = 26
MAP_HEIGHT = 17
TERRAIN = ("open", "road", "woods", "hedge", "village", "mud")
TERRAIN_COVER = {
    "open": 0.05,
    "road": 0.0,
    "woods": 0.38,
    "hedge": 0.28,
    "village": 0.48,
    "mud": 0.12,
}
TERRAIN_SPEED = {
    "open": 1.0,
    "road": 1.35,
    "woods": 0.68,
    "hedge": 0.58,
    "village": 0.78,
    "mud": 0.52,
}
VISION_RADIUS = {
    "Rifle": 5.8,
    "Support": 6.4,
    "Scout": 8.2,
    "Mortar": 4.8,
    "Armour": 7.0,
}
WEAPON_PROFILES: dict[str, dict[str, float]] = {
    "Rifle": {"range": 5.6, "accuracy": 0.27, "cooldown": 1.15, "suppression": 7.5, "ammo": 0.72, "min_range": 0.0},
    "Support": {"range": 7.2, "accuracy": 0.31, "cooldown": 0.72, "suppression": 12.0, "ammo": 1.05, "min_range": 0.0},
    "Scout": {"range": 4.9, "accuracy": 0.24, "cooldown": 1.30, "suppression": 5.5, "ammo": 0.58, "min_range": 0.0},
    "Mortar": {"range": 10.0, "accuracy": 0.33, "cooldown": 2.75, "suppression": 18.0, "ammo": 1.65, "min_range": 2.2},
    "Armour": {"range": 8.4, "accuracy": 0.42, "cooldown": 1.80, "suppression": 16.0, "ammo": 1.20, "min_range": 0.0},
}


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def distance(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def opposite_side(side: str) -> str:
    return "Axis" if side == "Allied" else "Allied"


@dataclass
class Unit:
    uid: str
    side: str
    name: str
    unit_type: str
    x: float
    y: float
    men: int
    max_men: int
    morale: float = 100.0
    ammo: float = 100.0
    suppression: float = 0.0
    experience: float = 0.35
    stance: str = "Defend"
    order: str = "Hold"
    target_x: float | None = None
    target_y: float | None = None
    ai_controlled: bool = False
    selected: bool = False
    kills: int = 0
    alive: bool = True
    velocity_x: float = 0.0
    velocity_y: float = 0.0
    heading: float = 0.0
    fire_cooldown: float = 0.0
    last_fire: float = -100.0
    last_hit: float = -100.0

    @property
    def strength(self) -> float:
        if not self.alive or self.max_men <= 0:
            return 0.0
        return self.men / self.max_men

    @property
    def speed(self) -> float:
        return math.hypot(self.velocity_x, self.velocity_y)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Unit":
        valid = set(cls.__dataclass_fields__)
        return cls(**{key: value for key, value in data.items() if key in valid})


@dataclass
class ControlPoint:
    name: str
    x: int
    y: int
    value: int
    owner: str = "Neutral"
    capture: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Event:
    timestamp: float
    category: str
    text: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Experience:
    state: list[float]
    action: int
    own_men: int
    enemy_men: int
    objective_distance: float


@dataclass
class CombatEffect:
    kind: str
    x1: float
    y1: float
    x2: float
    y2: float
    ttl: float
    max_ttl: float
    side: str

    @property
    def progress(self) -> float:
        return 1.0 - clamp(self.ttl / max(self.max_ttl, 0.001), 0.0, 1.0)


class BattleSimulation:
    SAVE_VERSION = 2
    NEXT_MAP_DELAY = 10.0

    def __init__(self, brain: TacticalBrain, seed: int | None = None, player_side: str = "Allied") -> None:
        self.brain = brain
        self.seed = seed if seed is not None else int(time.time() * 1000) & 0xFFFFFFFF
        self.rng = random.Random(self.seed)
        self.player_side = player_side if player_side in ("Allied", "Axis") else "Allied"
        self.player_ai_enabled = False
        self.terrain: list[list[str]] = []
        self.units: list[Unit] = []
        self.control_points: list[ControlPoint] = []
        self.events: list[Event] = []
        self.effects: list[CombatEffect] = []
        self.elapsed = 0.0
        self.ai_accumulator = 0.0
        self.visibility_accumulator = 0.0
        self.battle_over = False
        self.winner: str | None = None
        self.post_battle_elapsed = 0.0
        self.operation_name = "Operation Iron Meadow"
        self.weather = "Overcast"
        self.date_label = "July 1944"
        self.experiences: dict[str, Experience] = {}
        self.last_training_error = 0.0
        self.explored_tiles: dict[str, set[tuple[int, int]]] = {"Allied": set(), "Axis": set()}
        self._visible_cache: dict[str, set[tuple[int, int]]] = {"Allied": set(), "Axis": set()}
        self.new_battle(seed=seed)

    @property
    def enemy_side(self) -> str:
        return opposite_side(self.player_side)

    @property
    def allied_ai_enabled(self) -> bool:
        """Compatibility alias used by older saves and older UI builds."""
        return self.player_ai_enabled if self.player_side == "Allied" else False

    @allied_ai_enabled.setter
    def allied_ai_enabled(self, value: bool) -> None:
        if self.player_side == "Allied":
            self.player_ai_enabled = bool(value)

    @property
    def seconds_until_next_battle(self) -> float:
        if not self.battle_over:
            return self.NEXT_MAP_DELAY
        return max(0.0, self.NEXT_MAP_DELAY - self.post_battle_elapsed)

    def set_player_side(self, side: str) -> None:
        if side not in ("Allied", "Axis"):
            raise ValueError("Player side must be Allied or Axis")
        self.player_side = side
        self.player_ai_enabled = False
        self.experiences.clear()
        for unit in self.units:
            unit.ai_controlled = unit.side != self.player_side
        self._recalculate_visibility(force=True)

    def new_battle(self, seed: int | None = None) -> None:
        if seed is not None:
            self.seed = seed
        else:
            self.seed = self.rng.randrange(1, 2**31 - 1)
        self.rng.seed(self.seed)
        self.elapsed = 0.0
        self.ai_accumulator = 0.0
        self.visibility_accumulator = 0.0
        self.battle_over = False
        self.winner = None
        self.post_battle_elapsed = 0.0
        self.events = []
        self.effects = []
        self.experiences = {}
        self.explored_tiles = {"Allied": set(), "Axis": set()}
        self._visible_cache = {"Allied": set(), "Axis": set()}
        self.terrain = self._generate_terrain()
        self.control_points = self._generate_control_points()
        self.units = self._generate_units()
        self.weather = self.rng.choice(("Overcast", "Light rain", "Clearing", "Low cloud"))
        self.operation_name = self.rng.choice(
            (
                "Operation Iron Meadow",
                "Operation Grey Orchard",
                "Operation Lantern Field",
                "Operation Stone Causeway",
                "Operation Copper Orchard",
                "Operation Quiet Anvil",
            )
        )
        self._recalculate_visibility(force=True)
        self.log("Command", f"{self.operation_name} commenced. {self.player_side} command is under player control.")

    def advance_post_battle(self, real_dt: float) -> bool:
        """Advance the real-time end-of-map countdown and create the next map."""
        if not self.battle_over:
            return False
        self.post_battle_elapsed += max(0.0, real_dt)
        self._update_effects(max(0.0, real_dt))
        if self.post_battle_elapsed < self.NEXT_MAP_DELAY:
            return False
        self.new_battle()
        return True

    def _generate_terrain(self) -> list[list[str]]:
        grid = [["open" for _ in range(MAP_WIDTH)] for _ in range(MAP_HEIGHT)]
        road_y = self.rng.randint(5, MAP_HEIGHT - 6)
        for x in range(MAP_WIDTH):
            offset = int(round(math.sin(x / 4.2) * 1.4))
            y = int(clamp(road_y + offset, 1, MAP_HEIGHT - 2))
            grid[y][x] = "road"
            if y + 1 < MAP_HEIGHT and self.rng.random() < 0.30:
                grid[y + 1][x] = "road"

        for _ in range(13):
            cx = self.rng.randrange(2, MAP_WIDTH - 2)
            cy = self.rng.randrange(1, MAP_HEIGHT - 1)
            terrain = self.rng.choice(("woods", "woods", "hedge", "village", "mud"))
            radius = self.rng.randint(1, 3)
            for y in range(max(0, cy - radius), min(MAP_HEIGHT, cy + radius + 1)):
                for x in range(max(0, cx - radius), min(MAP_WIDTH, cx + radius + 1)):
                    if distance((x, y), (cx, cy)) <= radius + self.rng.random() * 0.8:
                        if grid[y][x] != "road" or terrain == "village":
                            grid[y][x] = terrain

        for _ in range(6):
            y = self.rng.randrange(2, MAP_HEIGHT - 2)
            start = self.rng.randrange(1, MAP_WIDTH - 8)
            for x in range(start, min(MAP_WIDTH - 1, start + self.rng.randint(4, 10))):
                if grid[y][x] == "open":
                    grid[y][x] = "hedge"
        return grid

    def _generate_control_points(self) -> list[ControlPoint]:
        candidates = [
            (MAP_WIDTH // 2, MAP_HEIGHT // 2, "Crossroads"),
            (MAP_WIDTH // 2 + 5, 4, "North Farm"),
            (MAP_WIDTH // 2 - 4, MAP_HEIGHT - 4, "Stone Hamlet"),
        ]
        return [ControlPoint(name, x, y, 100 + index * 25) for index, (x, y, name) in enumerate(candidates)]

    def _generate_units(self) -> list[Unit]:
        allied_specs = [
            ("Able Rifle", "Rifle", 10, 0.42),
            ("Baker Rifle", "Rifle", 10, 0.36),
            ("Charlie Bren", "Support", 7, 0.48),
            ("Dog Scouts", "Scout", 6, 0.52),
            ("Fox Mortar", "Mortar", 5, 0.44),
            ("Churchill Troop", "Armour", 4, 0.58),
        ]
        axis_specs = [
            ("Grenadier One", "Rifle", 10, 0.40),
            ("Grenadier Two", "Rifle", 10, 0.38),
            ("Machine Gun Team", "Support", 6, 0.50),
            ("Recon Section", "Scout", 6, 0.55),
            ("Mortar Group", "Mortar", 5, 0.46),
            ("Panzer Detachment", "Armour", 4, 0.60),
        ]
        units: list[Unit] = []
        for index, (name, unit_type, men, xp) in enumerate(allied_specs):
            units.append(
                Unit(
                    uid=str(uuid.uuid4()),
                    side="Allied",
                    name=name,
                    unit_type=unit_type,
                    x=1.5 + (index % 2) * 1.4,
                    y=2.5 + index * 2.1,
                    men=men,
                    max_men=men,
                    experience=xp,
                    ai_controlled=self.player_side != "Allied",
                    heading=0.0,
                )
            )
        for index, (name, unit_type, men, xp) in enumerate(axis_specs):
            units.append(
                Unit(
                    uid=str(uuid.uuid4()),
                    side="Axis",
                    name=name,
                    unit_type=unit_type,
                    x=MAP_WIDTH - 2.5 - (index % 2) * 1.4,
                    y=2.5 + index * 2.1,
                    men=men,
                    max_men=men,
                    experience=xp,
                    ai_controlled=self.player_side != "Axis",
                    heading=math.pi,
                )
            )
        return units

    def log(self, category: str, text: str) -> None:
        self.events.append(Event(self.elapsed, category, text))
        if len(self.events) > 500:
            self.events = self.events[-500:]

    def tile_at(self, x: float, y: float) -> str:
        ix = int(clamp(round(x), 0, MAP_WIDTH - 1))
        iy = int(clamp(round(y), 0, MAP_HEIGHT - 1))
        return self.terrain[iy][ix]

    def living_units(self, side: str | None = None) -> list[Unit]:
        return [unit for unit in self.units if unit.alive and (side is None or unit.side == side)]

    def unit_by_id(self, uid: str) -> Unit | None:
        return next((unit for unit in self.units if unit.uid == uid), None)

    def nearest_enemy(self, unit: Unit) -> Unit | None:
        enemies = self.living_units(opposite_side(unit.side))
        return min(enemies, key=lambda enemy: distance((unit.x, unit.y), (enemy.x, enemy.y)), default=None)

    def nearest_objective(self, unit: Unit) -> ControlPoint | None:
        hostile = [point for point in self.control_points if point.owner != unit.side]
        source = hostile or self.control_points
        return min(source, key=lambda point: distance((unit.x, unit.y), (point.x, point.y)), default=None)

    def vision_radius(self, unit: Unit) -> float:
        radius = VISION_RADIUS.get(unit.unit_type, 5.5)
        if unit.order == "Hold":
            radius += 0.35
        if self.tile_at(unit.x, unit.y) == "village":
            radius += 0.45
        elif self.tile_at(unit.x, unit.y) == "woods":
            radius -= 0.65
        if self.weather in ("Light rain", "Low cloud"):
            radius *= 0.88
        return max(2.5, radius)

    def _recalculate_visibility(self, force: bool = False) -> None:
        if not force and self.visibility_accumulator < 0.18:
            return
        self.visibility_accumulator = 0.0
        visible: dict[str, set[tuple[int, int]]] = {"Allied": set(), "Axis": set()}
        for side in ("Allied", "Axis"):
            for unit in self.living_units(side):
                radius = self.vision_radius(unit)
                min_x = max(0, int(math.floor(unit.x - radius)))
                max_x = min(MAP_WIDTH - 1, int(math.ceil(unit.x + radius)))
                min_y = max(0, int(math.floor(unit.y - radius)))
                max_y = min(MAP_HEIGHT - 1, int(math.ceil(unit.y + radius)))
                for y in range(min_y, max_y + 1):
                    for x in range(min_x, max_x + 1):
                        if distance((unit.x, unit.y), (x + 0.5, y + 0.5)) <= radius:
                            visible[side].add((x, y))
            self.explored_tiles.setdefault(side, set()).update(visible[side])
        self._visible_cache = visible

    def current_visible_tiles(self, side: str) -> set[tuple[int, int]]:
        if side not in self._visible_cache or not self._visible_cache[side]:
            self._recalculate_visibility(force=True)
        return set(self._visible_cache.get(side, set()))

    def is_position_visible(self, x: float, y: float, viewer_side: str) -> bool:
        tile = (int(clamp(math.floor(x), 0, MAP_WIDTH - 1)), int(clamp(math.floor(y), 0, MAP_HEIGHT - 1)))
        return tile in self.current_visible_tiles(viewer_side)

    def is_unit_visible(self, unit: Unit, viewer_side: str) -> bool:
        return unit.side == viewer_side or self.is_position_visible(unit.x, unit.y, viewer_side)

    def visible_enemy_units(self, viewer_side: str) -> list[Unit]:
        enemy = opposite_side(viewer_side)
        return [unit for unit in self.living_units(enemy) if self.is_unit_visible(unit, viewer_side)]

    def line_of_sight(self, attacker: Unit, target: Unit) -> bool:
        if attacker.unit_type == "Mortar":
            return True
        dist = distance((attacker.x, attacker.y), (target.x, target.y))
        if dist <= 2.2:
            return True
        samples = max(2, int(dist * 2.0))
        obstruction = 0.0
        for index in range(1, samples):
            ratio = index / samples
            x = attacker.x + (target.x - attacker.x) * ratio
            y = attacker.y + (target.y - attacker.y) * ratio
            terrain = self.tile_at(x, y)
            obstruction += {"woods": 0.075, "village": 0.095, "hedge": 0.055}.get(terrain, 0.0)
        return obstruction < 0.52

    def state_vector(self, unit: Unit) -> list[float]:
        enemy = self.nearest_enemy(unit)
        objective = self.nearest_objective(unit)
        enemy_distance = distance((unit.x, unit.y), (enemy.x, enemy.y)) if enemy else MAP_WIDTH
        objective_distance = distance((unit.x, unit.y), (objective.x, objective.y)) if objective else MAP_WIDTH
        local_friends = sum(
            1
            for other in self.living_units(unit.side)
            if other.uid != unit.uid and distance((unit.x, unit.y), (other.x, other.y)) <= 4.5
        )
        local_enemies = sum(
            1
            for other in self.living_units(opposite_side(unit.side))
            if distance((unit.x, unit.y), (other.x, other.y)) <= 6.0
        )
        terrain_cover = TERRAIN_COVER[self.tile_at(unit.x, unit.y)]
        map_direction = (MAP_WIDTH - unit.x) / MAP_WIDTH if unit.side == "Allied" else unit.x / MAP_WIDTH
        return [
            unit.strength * 2 - 1,
            unit.morale / 50 - 1,
            unit.ammo / 50 - 1,
            unit.suppression / 50 - 1,
            clamp(enemy_distance / 10 - 1, -1, 1),
            clamp(objective_distance / 10 - 1, -1, 1),
            clamp(local_friends / 3 - 1, -1, 1),
            clamp(local_enemies / 3 - 1, -1, 1),
            terrain_cover * 2 - 1,
            map_direction * 2 - 1,
        ]

    def issue_order(self, unit_ids: Iterable[str], order: str, x: float | None = None, y: float | None = None) -> None:
        for uid in unit_ids:
            unit = self.unit_by_id(uid)
            if not unit or not unit.alive or unit.side != self.player_side:
                continue
            unit.order = order
            unit.stance = order
            if x is not None and y is not None:
                unit.target_x = clamp(x, 0, MAP_WIDTH - 1)
                unit.target_y = clamp(y, 0, MAP_HEIGHT - 1)
            elif order == "Hold":
                unit.target_x, unit.target_y = unit.x, unit.y
            elif order == "Retreat":
                unit.target_x = 1.0 if unit.side == "Allied" else MAP_WIDTH - 2.0
                unit.target_y = unit.y
            self.log("Orders", f"{unit.name}: {order}.")

    def tick(self, dt: float) -> None:
        dt = clamp(dt, 0.005, 0.25)
        self._update_effects(dt)
        if self.battle_over:
            return
        self.elapsed += dt
        self.ai_accumulator += dt
        self.visibility_accumulator += dt
        while self.ai_accumulator >= 2.0:
            self.ai_accumulator -= 2.0
            self._ai_decision_cycle()
        self._move_units(dt)
        self._resolve_combat(dt)
        self._recover_units(dt)
        self._update_control_points(dt)
        self._recalculate_visibility()
        self._check_victory()

    def _ai_decision_cycle(self) -> None:
        for unit in self.living_units():
            should_control = unit.ai_controlled or (unit.side == self.player_side and self.player_ai_enabled)
            if not should_control:
                continue
            current_state = self.state_vector(unit)
            previous = self.experiences.get(unit.uid)
            if previous:
                reward = self._reward_for(unit, previous)
                self.last_training_error = self.brain.train(previous.state, previous.action, reward, current_state)
            action = self.brain.choose_action(current_state, explore=True)
            self._apply_ai_action(unit, ACTIONS[action])
            enemy_men = sum(enemy.men for enemy in self.living_units(opposite_side(unit.side)))
            objective = self.nearest_objective(unit)
            objective_distance = distance((unit.x, unit.y), (objective.x, objective.y)) if objective else 0.0
            self.experiences[unit.uid] = Experience(current_state, action, unit.men, enemy_men, objective_distance)

    def _reward_for(self, unit: Unit, previous: Experience) -> float:
        enemy_men = sum(enemy.men for enemy in self.living_units(opposite_side(unit.side)))
        objective = self.nearest_objective(unit)
        objective_distance = distance((unit.x, unit.y), (objective.x, objective.y)) if objective else 0.0
        casualty_reward = (previous.enemy_men - enemy_men) * 0.45
        casualty_penalty = (previous.own_men - unit.men) * 0.65
        objective_reward = (previous.objective_distance - objective_distance) * 0.05
        cover_reward = 0.025 if self.tile_at(unit.x, unit.y) in ("woods", "hedge", "village") else 0.0
        retreat_reward = 0.12 if unit.morale < 25 and ACTIONS[previous.action] == "retreat" else 0.0
        return clamp(casualty_reward - casualty_penalty + objective_reward + cover_reward + retreat_reward, -2.0, 2.0)

    def _apply_ai_action(self, unit: Unit, action: str) -> None:
        enemy = self.nearest_enemy(unit)
        objective = self.nearest_objective(unit)
        if action == "hold":
            unit.order, unit.stance = "Hold", "Defend"
            unit.target_x, unit.target_y = unit.x, unit.y
        elif action == "retreat":
            unit.order, unit.stance = "Retreat", "Evade"
            unit.target_x = 1.0 if unit.side == "Allied" else MAP_WIDTH - 2.0
            unit.target_y = clamp(unit.y + self.rng.uniform(-2.0, 2.0), 0, MAP_HEIGHT - 1)
        elif action == "assault" and enemy:
            unit.order, unit.stance = "Assault", "Aggressive"
            unit.target_x, unit.target_y = enemy.x, enemy.y
        elif action == "flank" and enemy:
            unit.order, unit.stance = "Flank", "Cautious"
            direction = 1 if self.rng.random() < 0.5 else -1
            unit.target_x = clamp(enemy.x, 0, MAP_WIDTH - 1)
            unit.target_y = clamp(enemy.y + direction * 3.5, 0, MAP_HEIGHT - 1)
        else:
            unit.order, unit.stance = "Advance", "Advance"
            if objective:
                unit.target_x = clamp(objective.x + self.rng.uniform(-1.0, 1.0), 0, MAP_WIDTH - 1)
                unit.target_y = clamp(objective.y + self.rng.uniform(-1.0, 1.0), 0, MAP_HEIGHT - 1)

    def _move_units(self, dt: float) -> None:
        for unit in self.living_units():
            desired_vx = 0.0
            desired_vy = 0.0
            if unit.target_x is not None and unit.target_y is not None and unit.order != "Hold":
                dx = unit.target_x - unit.x
                dy = unit.target_y - unit.y
                dist = math.hypot(dx, dy)
                if dist < 0.10:
                    if unit.order not in ("Assault", "Flank"):
                        unit.order = "Hold"
                    unit.target_x, unit.target_y = unit.x, unit.y
                else:
                    terrain = self.tile_at(unit.x, unit.y)
                    base_speed = 1.02 if unit.unit_type == "Armour" else 0.82
                    if unit.unit_type == "Scout":
                        base_speed *= 1.12
                    if unit.order == "Retreat":
                        base_speed *= 1.18
                    if unit.suppression > 65:
                        base_speed *= 0.48
                    elif unit.suppression > 35:
                        base_speed *= 0.72
                    desired_speed = base_speed * TERRAIN_SPEED[terrain]
                    desired_vx = dx / dist * desired_speed
                    desired_vy = dy / dist * desired_speed

            acceleration = 5.4 if unit.unit_type != "Armour" else 3.8
            blend = 1.0 - math.exp(-acceleration * dt)
            unit.velocity_x += (desired_vx - unit.velocity_x) * blend
            unit.velocity_y += (desired_vy - unit.velocity_y) * blend
            if abs(unit.velocity_x) < 0.002:
                unit.velocity_x = 0.0
            if abs(unit.velocity_y) < 0.002:
                unit.velocity_y = 0.0
            if unit.speed > 0.02:
                unit.heading = math.atan2(unit.velocity_y, unit.velocity_x)
            unit.x = clamp(unit.x + unit.velocity_x * dt, 0, MAP_WIDTH - 1)
            unit.y = clamp(unit.y + unit.velocity_y * dt, 0, MAP_HEIGHT - 1)

        self._separate_units(dt)

    def _separate_units(self, dt: float) -> None:
        living = self.living_units()
        for index, first in enumerate(living):
            for second in living[index + 1 :]:
                if first.side != second.side:
                    continue
                dx, dy = first.x - second.x, first.y - second.y
                dist = math.hypot(dx, dy)
                if dist <= 0.001 or dist >= 0.42:
                    continue
                push = (0.42 - dist) * 0.55 * min(1.0, dt * 10.0)
                nx, ny = dx / dist, dy / dist
                first.x = clamp(first.x + nx * push, 0, MAP_WIDTH - 1)
                first.y = clamp(first.y + ny * push, 0, MAP_HEIGHT - 1)
                second.x = clamp(second.x - nx * push, 0, MAP_WIDTH - 1)
                second.y = clamp(second.y - ny * push, 0, MAP_HEIGHT - 1)

    def _select_target(self, attacker: Unit, profile: dict[str, float]) -> Unit | None:
        candidates: list[tuple[float, Unit]] = []
        for target in self.living_units(opposite_side(attacker.side)):
            dist = distance((attacker.x, attacker.y), (target.x, target.y))
            if dist < profile["min_range"] or dist > profile["range"]:
                continue
            if attacker.unit_type != "Mortar" and not self.line_of_sight(attacker, target):
                continue
            priority = dist - (0.7 if target.unit_type == "Armour" and attacker.unit_type in ("Armour", "Mortar") else 0.0)
            candidates.append((priority, target))
        return min(candidates, key=lambda item: item[0])[1] if candidates else None

    def _resolve_combat(self, dt: float) -> None:
        attackers = list(self.living_units())
        self.rng.shuffle(attackers)
        for attacker in attackers:
            attacker.fire_cooldown = max(0.0, attacker.fire_cooldown - dt)
            if attacker.fire_cooldown > 0.0 or attacker.ammo <= 0.0 or attacker.suppression >= 92.0:
                continue
            profile = WEAPON_PROFILES.get(attacker.unit_type, WEAPON_PROFILES["Rifle"])
            target = self._select_target(attacker, profile)
            if target is None:
                continue

            dist = distance((attacker.x, attacker.y), (target.x, target.y))
            attacker.fire_cooldown = profile["cooldown"] * self.rng.uniform(0.82, 1.18)
            attacker.ammo = max(0.0, attacker.ammo - profile["ammo"])
            attacker.last_fire = self.elapsed
            effect_kind = "shell" if attacker.unit_type == "Mortar" else "tracer"
            self.effects.append(
                CombatEffect(effect_kind, attacker.x, attacker.y, target.x, target.y, 0.42 if effect_kind == "shell" else 0.16, 0.42 if effect_kind == "shell" else 0.16, attacker.side)
            )

            cover = TERRAIN_COVER[self.tile_at(target.x, target.y)]
            stance_bonus = 1.18 if attacker.order == "Assault" else 1.0
            morale_factor = clamp(attacker.morale / 70.0, 0.45, 1.15)
            suppression_factor = clamp(1.0 - attacker.suppression / 125.0, 0.18, 1.0)
            range_factor = clamp(1.12 - dist / max(profile["range"], 0.1), 0.28, 1.0)
            experience_factor = 0.78 + attacker.experience * 0.55
            armour_factor = 0.34 if target.unit_type == "Armour" and attacker.unit_type not in ("Armour", "Mortar") else 1.0
            hit_chance = profile["accuracy"] * stance_bonus * morale_factor * suppression_factor * range_factor * experience_factor * (1.0 - cover) * armour_factor
            target.suppression = clamp(target.suppression + profile["suppression"] * (0.78 + self.rng.random() * 0.44), 0.0, 100.0)

            if self.rng.random() >= hit_chance:
                if attacker.unit_type == "Mortar" and self.rng.random() < 0.45:
                    self.effects.append(CombatEffect("impact", target.x + self.rng.uniform(-0.7, 0.7), target.y + self.rng.uniform(-0.7, 0.7), target.x, target.y, 0.55, 0.55, attacker.side))
                continue

            losses = 1
            if attacker.unit_type in ("Mortar", "Armour") and target.unit_type != "Armour" and self.rng.random() < 0.34:
                losses += 1
            losses = min(losses, target.men)
            target.men = max(0, target.men - losses)
            target.last_hit = self.elapsed
            attacker.kills += losses
            target.morale = clamp(target.morale - 6.5 * losses - target.suppression * 0.035, 0.0, 100.0)
            self.effects.append(CombatEffect("impact", target.x, target.y, target.x, target.y, 0.70, 0.70, attacker.side))
            self.log("Combat", f"{attacker.name} hit {target.name}; {losses} casualty{'ies' if losses != 1 else ''}.")
            if target.men <= 0:
                target.alive = False
                target.order = "Destroyed"
                target.velocity_x = target.velocity_y = 0.0
                self.effects.append(CombatEffect("destroyed", target.x, target.y, target.x, target.y, 1.45, 1.45, attacker.side))
                self.log("Combat", f"{target.name} has been eliminated.")

        if len(self.effects) > 90:
            self.effects = self.effects[-90:]

    def _update_effects(self, dt: float) -> None:
        for effect in self.effects:
            effect.ttl -= dt
        self.effects = [effect for effect in self.effects if effect.ttl > 0.0]

    def _recover_units(self, dt: float) -> None:
        for unit in self.living_units():
            recovery = 2.2 if unit.order == "Hold" else 0.8
            if self.tile_at(unit.x, unit.y) in ("woods", "hedge", "village"):
                recovery *= 1.2
            unit.suppression = max(0.0, unit.suppression - recovery * dt)
            if unit.suppression < 25:
                unit.morale = min(100.0, unit.morale + 0.22 * dt)
            if unit.morale < 14 and unit.order != "Retreat":
                unit.order, unit.stance = "Retreat", "Broken"
                unit.target_x = 1.0 if unit.side == "Allied" else MAP_WIDTH - 2.0
                unit.target_y = unit.y

    def _update_control_points(self, dt: float) -> None:
        for point in self.control_points:
            allied = sum(1 for unit in self.living_units("Allied") if distance((unit.x, unit.y), (point.x, point.y)) <= 1.8)
            axis = sum(1 for unit in self.living_units("Axis") if distance((unit.x, unit.y), (point.x, point.y)) <= 1.8)
            old_owner = point.owner
            if allied > axis:
                point.capture = clamp(point.capture + dt * (allied - axis) * 12.0, -100.0, 100.0)
            elif axis > allied:
                point.capture = clamp(point.capture - dt * (axis - allied) * 12.0, -100.0, 100.0)
            else:
                point.capture *= max(0.0, 1.0 - dt * 0.08)
            if point.capture >= 100.0:
                point.owner = "Allied"
            elif point.capture <= -100.0:
                point.owner = "Axis"
            elif abs(point.capture) < 5.0 and allied == 0 and axis == 0:
                point.owner = "Neutral"
            if old_owner != point.owner:
                self.log("Objectives", f"{point.name} captured by {point.owner} forces.")

    def _check_victory(self) -> None:
        allied = self.living_units("Allied")
        axis = self.living_units("Axis")
        winner: str | None = None
        if not allied:
            winner = "Axis"
        elif not axis:
            winner = "Allied"
        elif self.elapsed >= 20 * 60:
            winner = "Allied" if self.battle_score("Allied") >= self.battle_score("Axis") else "Axis"
        if winner:
            self._conclude_battle(winner, "Battle concluded")

    def _conclude_battle(self, winner: str, reason: str) -> None:
        if self.battle_over:
            return
        self.battle_over = True
        self.winner = winner
        self.post_battle_elapsed = 0.0
        self.log("Command", f"{reason}. {winner} victory. A new map will begin in 10 seconds.")
        self.brain.mark_result(winner == self.enemy_side)
        self._finalize_experiences(winner)

    def _finalize_experiences(self, winner: str) -> None:
        for uid, previous in list(self.experiences.items()):
            unit = self.unit_by_id(uid)
            if not unit:
                continue
            terminal_reward = 1.5 if unit.side == winner else -1.5
            next_state = self.state_vector(unit) if unit.alive else [-1.0] * self.brain.input_size
            self.last_training_error = self.brain.train(previous.state, previous.action, terminal_reward, next_state, terminal=True)
        self.experiences.clear()

    def force_result(self, winner: str) -> None:
        if winner in ("Allied", "Axis"):
            self._conclude_battle(winner, "Battle ended by command decision")

    def battle_score(self, side: str) -> int:
        unit_score = sum(unit.men * 8 + int(unit.morale) for unit in self.living_units(side))
        objective_score = sum(point.value for point in self.control_points if point.owner == side)
        return unit_score + objective_score

    def to_dict(self) -> dict[str, Any]:
        explored_payload = {
            side: [[x, y] for x, y in sorted(tiles)]
            for side, tiles in self.explored_tiles.items()
        }
        return {
            "version": self.SAVE_VERSION,
            "seed": self.seed,
            "terrain": self.terrain,
            "units": [unit.to_dict() for unit in self.units],
            "control_points": [point.to_dict() for point in self.control_points],
            "events": [event.to_dict() for event in self.events[-250:]],
            "elapsed": self.elapsed,
            "battle_over": self.battle_over,
            "winner": self.winner,
            "post_battle_elapsed": self.post_battle_elapsed,
            "operation_name": self.operation_name,
            "weather": self.weather,
            "date_label": self.date_label,
            "player_side": self.player_side,
            "player_ai_enabled": self.player_ai_enabled,
            "allied_ai_enabled": self.allied_ai_enabled,
            "explored_tiles": explored_payload,
        }

    def load_dict(self, data: dict[str, Any]) -> None:
        terrain = data.get("terrain")
        units = data.get("units")
        points = data.get("control_points")
        if not isinstance(terrain, list) or not isinstance(units, list) or not isinstance(points, list):
            raise ValueError("Invalid save data")
        if len(terrain) != MAP_HEIGHT or any(not isinstance(row, list) or len(row) != MAP_WIDTH for row in terrain):
            raise ValueError("Invalid terrain dimensions")

        self.seed = int(data.get("seed", self.seed))
        self.rng.seed(self.seed)
        side = str(data.get("player_side", "Allied"))
        self.player_side = side if side in ("Allied", "Axis") else "Allied"
        self.player_ai_enabled = bool(data.get("player_ai_enabled", data.get("allied_ai_enabled", False) if self.player_side == "Allied" else False))
        self.terrain = [[str(cell) if str(cell) in TERRAIN else "open" for cell in row] for row in terrain]
        self.units = [Unit.from_dict(item) for item in units if isinstance(item, dict)]
        for unit in self.units:
            unit.ai_controlled = unit.side != self.player_side
        self.control_points = [ControlPoint(**item) for item in points if isinstance(item, dict)]
        self.events = [Event(**item) for item in data.get("events", []) if isinstance(item, dict)]
        self.effects = []
        self.elapsed = float(data.get("elapsed", 0.0))
        self.battle_over = bool(data.get("battle_over", False))
        self.winner = data.get("winner")
        self.post_battle_elapsed = clamp(float(data.get("post_battle_elapsed", 0.0)), 0.0, self.NEXT_MAP_DELAY)
        self.operation_name = str(data.get("operation_name", "Operation Iron Meadow"))
        self.weather = str(data.get("weather", "Overcast"))
        self.date_label = str(data.get("date_label", "July 1944"))
        self.ai_accumulator = 0.0
        self.visibility_accumulator = 0.0
        self.experiences = {}

        explored_data = data.get("explored_tiles", {})
        self.explored_tiles = {"Allied": set(), "Axis": set()}
        if isinstance(explored_data, dict):
            for side_name in ("Allied", "Axis"):
                values = explored_data.get(side_name, [])
                if isinstance(values, list):
                    for item in values:
                        if isinstance(item, list) and len(item) == 2:
                            x, y = int(item[0]), int(item[1])
                            if 0 <= x < MAP_WIDTH and 0 <= y < MAP_HEIGHT:
                                self.explored_tiles[side_name].add((x, y))
        self._visible_cache = {"Allied": set(), "Axis": set()}
        self._recalculate_visibility(force=True)
