"""Procedural tactical battlefield simulation and learning AI integration."""
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
TERRAIN_COVER = {"open": 0.05, "road": 0.0, "woods": 0.38, "hedge": 0.28, "village": 0.48, "mud": 0.12}
TERRAIN_SPEED = {"open": 1.0, "road": 1.35, "woods": 0.68, "hedge": 0.58, "village": 0.78, "mud": 0.52}


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def distance(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


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

    @property
    def strength(self) -> float:
        return 0.0 if not self.alive or self.max_men <= 0 else self.men / self.max_men

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


class BattleSimulation:
    SAVE_VERSION = 1

    def __init__(self, brain: TacticalBrain, seed: int | None = None) -> None:
        self.brain = brain
        self.seed = seed if seed is not None else int(time.time() * 1000) & 0xFFFFFFFF
        self.rng = random.Random(self.seed)
        self.terrain: list[list[str]] = []
        self.units: list[Unit] = []
        self.control_points: list[ControlPoint] = []
        self.events: list[Event] = []
        self.elapsed = 0.0
        self.ai_accumulator = 0.0
        self.battle_over = False
        self.winner: str | None = None
        self.operation_name = "Operation Iron Meadow"
        self.weather = "Overcast"
        self.date_label = "July 1944"
        self.allied_ai_enabled = False
        self.experiences: dict[str, Experience] = {}
        self.last_training_error = 0.0
        self.new_battle()

    def new_battle(self, seed: int | None = None) -> None:
        self.seed = seed if seed is not None else self.rng.randrange(1, 2**31 - 1)
        self.rng.seed(self.seed)
        self.elapsed = 0.0
        self.ai_accumulator = 0.0
        self.battle_over = False
        self.winner = None
        self.events = []
        self.experiences = {}
        self.terrain = self._generate_terrain()
        self.control_points = self._generate_control_points()
        self.units = self._generate_units()
        self.weather = self.rng.choice(("Overcast", "Light rain", "Clearing", "Low cloud"))
        self.operation_name = self.rng.choice(("Operation Iron Meadow", "Operation Grey Orchard", "Operation Lantern Field", "Operation Stone Causeway"))
        self.log("Command", f"{self.operation_name} commenced. Secure the objectives.")

    def _generate_terrain(self) -> list[list[str]]:
        grid = [["open" for _ in range(MAP_WIDTH)] for _ in range(MAP_HEIGHT)]
        road_y = self.rng.randint(5, MAP_HEIGHT - 6)
        for x in range(MAP_WIDTH):
            y = int(clamp(road_y + round(math.sin(x / 4.2) * 1.4), 1, MAP_HEIGHT - 2))
            grid[y][x] = "road"
            if y + 1 < MAP_HEIGHT and self.rng.random() < 0.3:
                grid[y + 1][x] = "road"
        for _ in range(11):
            cx, cy = self.rng.randrange(2, MAP_WIDTH - 2), self.rng.randrange(1, MAP_HEIGHT - 1)
            terrain = self.rng.choice(("woods", "woods", "hedge", "village", "mud"))
            radius = self.rng.randint(1, 3)
            for y in range(max(0, cy - radius), min(MAP_HEIGHT, cy + radius + 1)):
                for x in range(max(0, cx - radius), min(MAP_WIDTH, cx + radius + 1)):
                    if distance((x, y), (cx, cy)) <= radius + self.rng.random() * 0.8 and (grid[y][x] != "road" or terrain == "village"):
                        grid[y][x] = terrain
        for _ in range(5):
            y, start = self.rng.randrange(2, MAP_HEIGHT - 2), self.rng.randrange(1, MAP_WIDTH - 8)
            for x in range(start, min(MAP_WIDTH - 1, start + self.rng.randint(4, 9))):
                if grid[y][x] == "open":
                    grid[y][x] = "hedge"
        return grid

    def _generate_control_points(self) -> list[ControlPoint]:
        candidates = [(MAP_WIDTH // 2, MAP_HEIGHT // 2, "Crossroads"), (MAP_WIDTH // 2 + 5, 4, "North Farm"), (MAP_WIDTH // 2 - 4, MAP_HEIGHT - 4, "Stone Hamlet")]
        return [ControlPoint(name, x, y, 100 + index * 25) for index, (x, y, name) in enumerate(candidates)]

    def _generate_units(self) -> list[Unit]:
        allied_specs = [("Able Rifle", "Rifle", 10, 0.42), ("Baker Rifle", "Rifle", 10, 0.36), ("Charlie Bren", "Support", 7, 0.48), ("Dog Scouts", "Scout", 6, 0.52), ("Fox Mortar", "Mortar", 5, 0.44), ("Churchill Troop", "Armour", 4, 0.58)]
        axis_specs = [("Grenadier One", "Rifle", 10, 0.40), ("Grenadier Two", "Rifle", 10, 0.38), ("Machine Gun Team", "Support", 6, 0.50), ("Recon Section", "Scout", 6, 0.55), ("Mortar Group", "Mortar", 5, 0.46), ("Panzer Detachment", "Armour", 4, 0.60)]
        units: list[Unit] = []
        for index, (name, kind, men, xp) in enumerate(allied_specs):
            units.append(Unit(str(uuid.uuid4()), "Allied", name, kind, 1.5 + (index % 2) * 1.4, 2.5 + index * 2.1, men, men, experience=xp))
        for index, (name, kind, men, xp) in enumerate(axis_specs):
            units.append(Unit(str(uuid.uuid4()), "Axis", name, kind, MAP_WIDTH - 2.5 - (index % 2) * 1.4, 2.5 + index * 2.1, men, men, experience=xp, ai_controlled=True))
        return units

    def log(self, category: str, text: str) -> None:
        self.events.append(Event(self.elapsed, category, text))
        if len(self.events) > 500:
            self.events = self.events[-500:]

    def tile_at(self, x: float, y: float) -> str:
        return self.terrain[int(clamp(round(y), 0, MAP_HEIGHT - 1))][int(clamp(round(x), 0, MAP_WIDTH - 1))]

    def living_units(self, side: str | None = None) -> list[Unit]:
        return [unit for unit in self.units if unit.alive and (side is None or unit.side == side)]

    def unit_by_id(self, uid: str) -> Unit | None:
        return next((unit for unit in self.units if unit.uid == uid), None)

    def nearest_enemy(self, unit: Unit) -> Unit | None:
        enemies = self.living_units("Axis" if unit.side == "Allied" else "Allied")
        return min(enemies, key=lambda enemy: distance((unit.x, unit.y), (enemy.x, enemy.y)), default=None)

    def nearest_objective(self, unit: Unit) -> ControlPoint | None:
        source = [point for point in self.control_points if point.owner != unit.side] or self.control_points
        return min(source, key=lambda point: distance((unit.x, unit.y), (point.x, point.y)), default=None)

    def state_vector(self, unit: Unit) -> list[float]:
        enemy, objective = self.nearest_enemy(unit), self.nearest_objective(unit)
        enemy_distance = distance((unit.x, unit.y), (enemy.x, enemy.y)) if enemy else MAP_WIDTH
        objective_distance = distance((unit.x, unit.y), (objective.x, objective.y)) if objective else MAP_WIDTH
        local_friends = sum(1 for other in self.living_units(unit.side) if other.uid != unit.uid and distance((unit.x, unit.y), (other.x, other.y)) <= 4.5)
        enemy_side = "Axis" if unit.side == "Allied" else "Allied"
        local_enemies = sum(1 for other in self.living_units(enemy_side) if distance((unit.x, unit.y), (other.x, other.y)) <= 6.0)
        cover = TERRAIN_COVER[self.tile_at(unit.x, unit.y)]
        map_direction = (MAP_WIDTH - unit.x) / MAP_WIDTH if unit.side == "Allied" else unit.x / MAP_WIDTH
        return [unit.strength * 2 - 1, unit.morale / 50 - 1, unit.ammo / 50 - 1, unit.suppression / 50 - 1, clamp(enemy_distance / 10 - 1, -1, 1), clamp(objective_distance / 10 - 1, -1, 1), clamp(local_friends / 3 - 1, -1, 1), clamp(local_enemies / 3 - 1, -1, 1), cover * 2 - 1, map_direction * 2 - 1]

    def issue_order(self, unit_ids: Iterable[str], order: str, x: float | None = None, y: float | None = None) -> None:
        for uid in unit_ids:
            unit = self.unit_by_id(uid)
            if not unit or not unit.alive or unit.side != "Allied":
                continue
            unit.order = order
            unit.stance = order
            if x is not None and y is not None:
                unit.target_x, unit.target_y = clamp(x, 0, MAP_WIDTH - 1), clamp(y, 0, MAP_HEIGHT - 1)
            self.log("Orders", f"{unit.name}: {order}.")

    def tick(self, dt: float) -> None:
        if self.battle_over:
            return
        dt = clamp(dt, 0.01, 0.5)
        self.elapsed += dt
        self.ai_accumulator += dt
        while self.ai_accumulator >= 2.0:
            self.ai_accumulator -= 2.0
            self._ai_decision_cycle()
        self._move_units(dt)
        self._resolve_combat(dt)
        self._recover_units(dt)
        self._update_control_points(dt)
        self._check_victory()

    def _ai_decision_cycle(self) -> None:
        for unit in self.living_units():
            if unit.side != "Axis" and not (unit.side == "Allied" and self.allied_ai_enabled):
                continue
            state = self.state_vector(unit)
            previous = self.experiences.get(unit.uid)
            if previous:
                self.last_training_error = self.brain.train(previous.state, previous.action, self._reward_for(unit, previous), state)
            action = self.brain.choose_action(state, explore=True)
            self._apply_ai_action(unit, ACTIONS[action])
            enemy_side = "Axis" if unit.side == "Allied" else "Allied"
            enemy_men = sum(enemy.men for enemy in self.living_units(enemy_side))
            objective = self.nearest_objective(unit)
            objective_distance = distance((unit.x, unit.y), (objective.x, objective.y)) if objective else 0.0
            self.experiences[unit.uid] = Experience(state, action, unit.men, enemy_men, objective_distance)

    def _reward_for(self, unit: Unit, previous: Experience) -> float:
        enemy_side = "Axis" if unit.side == "Allied" else "Allied"
        enemy_men = sum(enemy.men for enemy in self.living_units(enemy_side))
        objective = self.nearest_objective(unit)
        objective_distance = distance((unit.x, unit.y), (objective.x, objective.y)) if objective else 0.0
        reward = (previous.enemy_men - enemy_men) * 0.45 - (previous.own_men - unit.men) * 0.65 + (previous.objective_distance - objective_distance) * 0.05
        if self.tile_at(unit.x, unit.y) in ("woods", "hedge", "village"):
            reward += 0.025
        if unit.morale < 25 and ACTIONS[previous.action] == "retreat":
            reward += 0.12
        return clamp(reward, -2.0, 2.0)

    def _apply_ai_action(self, unit: Unit, action: str) -> None:
        enemy, objective = self.nearest_enemy(unit), self.nearest_objective(unit)
        if action == "hold":
            unit.order, unit.stance, unit.target_x, unit.target_y = "Hold", "Defend", unit.x, unit.y
        elif action == "retreat":
            unit.order, unit.stance = "Retreat", "Evade"
            unit.target_x = 1.0 if unit.side == "Allied" else MAP_WIDTH - 2.0
            unit.target_y = clamp(unit.y + self.rng.uniform(-2.0, 2.0), 0, MAP_HEIGHT - 1)
        elif action == "assault" and enemy:
            unit.order, unit.stance, unit.target_x, unit.target_y = "Assault", "Aggressive", enemy.x, enemy.y
        elif action == "flank" and enemy:
            unit.order, unit.stance = "Flank", "Cautious"
            unit.target_x = enemy.x
            unit.target_y = clamp(enemy.y + (3.5 if self.rng.random() < 0.5 else -3.5), 0, MAP_HEIGHT - 1)
        else:
            unit.order, unit.stance = "Advance", "Advance"
            if objective:
                unit.target_x = objective.x + self.rng.uniform(-1.0, 1.0)
                unit.target_y = objective.y + self.rng.uniform(-1.0, 1.0)

    def _move_units(self, dt: float) -> None:
        for unit in self.living_units():
            if unit.target_x is None or unit.target_y is None or unit.order == "Hold":
                continue
            dx, dy = unit.target_x - unit.x, unit.target_y - unit.y
            dist = math.hypot(dx, dy)
            if dist < 0.15:
                if unit.order not in ("Assault", "Flank"):
                    unit.order = "Hold"
                continue
            speed = (1.02 if unit.unit_type == "Armour" else 0.82) * TERRAIN_SPEED[self.tile_at(unit.x, unit.y)] * dt
            if unit.order == "Retreat":
                speed *= 1.18
            if unit.suppression > 65:
                speed *= 0.48
            unit.x = clamp(unit.x + dx / dist * speed, 0, MAP_WIDTH - 1)
            unit.y = clamp(unit.y + dy / dist * speed, 0, MAP_HEIGHT - 1)

    def _weapon_profile(self, unit: Unit) -> tuple[float, float]:
        return {"Rifle": (5.5, 0.30), "Support": (7.0, 0.42), "Scout": (4.8, 0.22), "Mortar": (9.5, 0.34), "Armour": (8.0, 0.52)}.get(unit.unit_type, (5.0, 0.25))

    def _resolve_combat(self, dt: float) -> None:
        attackers = list(self.living_units())
        self.rng.shuffle(attackers)
        for attacker in attackers:
            target = self.nearest_enemy(attacker)
            if target is None or not target.alive or attacker.ammo <= 0:
                continue
            attack_range, lethality = self._weapon_profile(attacker)
            dist = distance((attacker.x, attacker.y), (target.x, target.y))
            if dist > attack_range:
                continue
            cover = TERRAIN_COVER[self.tile_at(target.x, target.y)]
            stance_bonus = 1.25 if attacker.order == "Assault" else 1.0
            range_factor = clamp(1.2 - dist / max(attack_range, 0.1), 0.22, 1.0)
            armour_factor = 0.45 if target.unit_type == "Armour" and attacker.unit_type not in ("Armour", "Mortar") else 1.0
            chance = lethality * stance_bonus * (1.0 - attacker.suppression / 160.0) * range_factor * (1.0 - cover) * armour_factor * dt
            attacker.ammo = max(0.0, attacker.ammo - (0.5 + lethality) * dt)
            target.suppression = clamp(target.suppression + chance * 65.0, 0.0, 100.0)
            if self.rng.random() < chance:
                losses = 1 + (1 if attacker.unit_type == "Armour" and target.unit_type != "Armour" and self.rng.random() < 0.28 else 0)
                target.men = max(0, target.men - losses)
                attacker.kills += losses
                target.morale = clamp(target.morale - 7.0 * losses - target.suppression * 0.03, 0.0, 100.0)
                self.log("Combat", f"{attacker.name} hit {target.name}; {losses} casualty{'ies' if losses > 1 else ''}.")
                if target.men <= 0:
                    target.alive, target.order = False, "Destroyed"
                    self.log("Combat", f"{target.name} has been eliminated.")

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
            if point.capture >= 100:
                point.owner = "Allied"
            elif point.capture <= -100:
                point.owner = "Axis"
            elif abs(point.capture) < 5 and allied == 0 and axis == 0:
                point.owner = "Neutral"
            if old_owner != point.owner:
                self.log("Objectives", f"{point.name} captured by {point.owner} forces.")

    def _check_victory(self) -> None:
        allied, axis = self.living_units("Allied"), self.living_units("Axis")
        winner: str | None = None
        if not allied:
            winner = "Axis"
        elif not axis:
            winner = "Allied"
        elif self.elapsed >= 20 * 60:
            winner = "Allied" if self.battle_score("Allied") >= self.battle_score("Axis") else "Axis"
        if winner:
            self.battle_over, self.winner = True, winner
            self.log("Command", f"Battle concluded. {winner} victory.")
            self.brain.mark_result(winner == "Axis")
            self._finalize_experiences(winner)

    def _finalize_experiences(self, winner: str) -> None:
        for uid, previous in list(self.experiences.items()):
            unit = self.unit_by_id(uid)
            if unit:
                next_state = self.state_vector(unit) if unit.alive else [-1.0] * self.brain.input_size
                self.last_training_error = self.brain.train(previous.state, previous.action, 1.5 if unit.side == winner else -1.5, next_state, terminal=True)
        self.experiences.clear()

    def force_result(self, winner: str) -> None:
        if winner in ("Allied", "Axis"):
            self.battle_over, self.winner = True, winner
            self.log("Command", f"Battle ended by command decision: {winner} victory.")
            self.brain.mark_result(winner == "Axis")
            self._finalize_experiences(winner)

    def battle_score(self, side: str) -> int:
        return sum(unit.men * 8 + int(unit.morale) for unit in self.living_units(side)) + sum(point.value for point in self.control_points if point.owner == side)

    def to_dict(self) -> dict[str, Any]:
        return {"version": self.SAVE_VERSION, "seed": self.seed, "terrain": self.terrain, "units": [unit.to_dict() for unit in self.units], "control_points": [point.to_dict() for point in self.control_points], "events": [event.to_dict() for event in self.events[-250:]], "elapsed": self.elapsed, "battle_over": self.battle_over, "winner": self.winner, "operation_name": self.operation_name, "weather": self.weather, "date_label": self.date_label, "allied_ai_enabled": self.allied_ai_enabled}

    def load_dict(self, data: dict[str, Any]) -> None:
        terrain, units, points = data.get("terrain"), data.get("units"), data.get("control_points")
        if not isinstance(terrain, list) or not isinstance(units, list) or not isinstance(points, list):
            raise ValueError("Invalid save data")
        self.seed = int(data.get("seed", self.seed))
        self.rng.seed(self.seed)
        self.terrain = [[str(cell) for cell in row] for row in terrain]
        self.units = [Unit.from_dict(item) for item in units]
        self.control_points = [ControlPoint(**item) for item in points]
        self.events = [Event(**item) for item in data.get("events", []) if isinstance(item, dict)]
        self.elapsed = float(data.get("elapsed", 0.0))
        self.battle_over = bool(data.get("battle_over", False))
        self.winner = data.get("winner")
        self.operation_name = str(data.get("operation_name", "Operation Iron Meadow"))
        self.weather = str(data.get("weather", "Overcast"))
        self.date_label = str(data.get("date_label", "July 1944"))
        self.allied_ai_enabled = bool(data.get("allied_ai_enabled", False))
        self.ai_accumulator = 0.0
        self.experiences = {}
