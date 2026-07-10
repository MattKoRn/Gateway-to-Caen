"""Coordinated utility-based conventional enemy commander."""
from __future__ import annotations

import math
import random
from collections import defaultdict
from typing import Any

from .simulation import MAP_HEIGHT, MAP_WIDTH, Unit, clamp, distance, opposite_side


class SmartEnemyAI:
    """A deterministic, non-neural battlefield commander.

    The commander coordinates roles and objectives, preserves indirect-fire units,
    concentrates force against weak contacts, and adapts its aggression to the
    campaign difficulty. It never uses the persistent neural network.
    """

    def __init__(self, seed: int = 0) -> None:
        self.rng = random.Random(seed ^ 0xA11CE)
        self.cycle = 0
        self.last_plan = "Initial deployment"
        self.assignments: dict[str, str] = {}

    def reset(self, seed: int) -> None:
        self.rng.seed(seed ^ 0xA11CE)
        self.cycle = 0
        self.assignments.clear()
        self.last_plan = "Initial deployment"

    def command_cycle(self, sim: Any, side: str, difficulty: float) -> None:
        units = sim.living_units(side)
        if not units:
            return
        self.cycle += 1
        enemy_side = opposite_side(side)
        enemies = sim.living_units(enemy_side)
        objectives = list(sim.control_points)
        groups: dict[str, list[Unit]] = defaultdict(list)
        for unit in units:
            groups[unit.unit_type].append(unit)

        target_objectives = sorted(
            objectives,
            key=lambda point: self._objective_utility(sim, side, point, units, enemies, difficulty),
            reverse=True,
        )
        main_objective = target_objectives[0] if target_objectives else None
        secondary = target_objectives[1] if len(target_objectives) > 1 else main_objective
        weak_contact = self._weak_contact(sim, side, enemies)
        aggression = clamp(0.56 + (difficulty - 1.0) * 0.42, 0.34, 0.92)

        for unit in units:
            if unit.morale < 22 or unit.suppression > 82 or unit.ammo < 7:
                self._retreat(sim, unit)
                continue
            if unit.unit_type == "Mortar":
                self._command_mortar(sim, unit, main_objective, enemies, difficulty)
            elif unit.unit_type == "Support":
                self._command_support(sim, unit, main_objective, groups, difficulty)
            elif unit.unit_type == "Scout":
                self._command_scout(sim, unit, secondary, weak_contact, difficulty)
            elif unit.unit_type == "Armour":
                self._command_armour(sim, unit, main_objective, weak_contact, aggression)
            else:
                self._command_rifle(sim, unit, main_objective, weak_contact, aggression)

        plan_target = main_objective.name if main_objective else "the opposing line"
        self.last_plan = f"Coordinated pressure toward {plan_target} at {difficulty:.2f}x difficulty"
        if self.cycle % 3 == 1:
            sim.log("Enemy AI", self.last_plan + ".")

    def _objective_utility(self, sim: Any, side: str, point: Any, friends: list[Unit], enemies: list[Unit], difficulty: float) -> float:
        friendly_near = sum(1 for unit in friends if distance((unit.x, unit.y), (point.x, point.y)) < 4.5)
        enemy_near = sum(1 for unit in enemies if distance((unit.x, unit.y), (point.x, point.y)) < 4.5)
        average_distance = sum(distance((unit.x, unit.y), (point.x, point.y)) for unit in friends) / max(1, len(friends))
        ownership = 1.8 if point.owner != side else -0.35
        contested = 1.4 if friendly_near and enemy_near else 0.0
        superiority = (friendly_near - enemy_near) * 0.38
        return point.value / 80 + ownership + contested + superiority - average_distance * (0.045 + difficulty * 0.01)

    def _weak_contact(self, sim: Any, side: str, enemies: list[Unit]) -> Unit | None:
        visible_ids = {unit.uid for unit in sim.visible_enemy_units(side)}
        contacts = [unit for unit in enemies if unit.uid in visible_ids]
        if not contacts:
            return None
        return max(
            contacts,
            key=lambda unit: (1.0 - unit.strength) * 2.6 + unit.suppression / 60 + (1.0 - unit.morale / 100) - self._cover(sim, unit) * 0.8,
        )

    @staticmethod
    def _cover(sim: Any, unit: Unit) -> float:
        return sim.TERRAIN_COVER.get(sim.tile_at(unit.x, unit.y), 0.0) if hasattr(sim, "TERRAIN_COVER") else 0.0

    def _set_target(self, sim: Any, unit: Unit, order: str, x: float, y: float, stance: str) -> None:
        unit.order = order
        unit.stance = stance
        radius = sim.unit_collision_radius(unit)
        unit.target_x, unit.target_y = sim.nearest_clear_position(clamp(x, 0, MAP_WIDTH - 1), clamp(y, 0, MAP_HEIGHT - 1), radius)
        self.assignments[unit.uid] = order

    def _retreat(self, sim: Any, unit: Unit) -> None:
        rear_x = 1.2 if unit.side == "Allied" else MAP_WIDTH - 2.2
        self._set_target(sim, unit, "Retreat", rear_x, unit.y + self.rng.uniform(-1.4, 1.4), "Evade")

    def _command_mortar(self, sim: Any, unit: Unit, objective: Any, enemies: list[Unit], difficulty: float) -> None:
        target = min(enemies, key=lambda enemy: distance((unit.x, unit.y), (enemy.x, enemy.y)), default=None)
        if target and distance((unit.x, unit.y), (target.x, target.y)) < 4.0:
            away = -1 if target.x > unit.x else 1
            self._set_target(sim, unit, "Retreat", unit.x + away * 2.8, unit.y + self.rng.uniform(-1.0, 1.0), "Displace")
            return
        if objective:
            rear_offset = -4.8 if unit.side == "Allied" else 4.8
            self._set_target(sim, unit, "Hold", objective.x + rear_offset, objective.y + self.rng.uniform(-1.2, 1.2), "Indirect Fire")

    def _command_support(self, sim: Any, unit: Unit, objective: Any, groups: dict[str, list[Unit]], difficulty: float) -> None:
        rifles = groups.get("Rifle", [])
        lead = min(rifles, key=lambda other: distance((unit.x, unit.y), (other.x, other.y)), default=None)
        if lead:
            rear = -1.25 if unit.side == "Allied" else 1.25
            self._set_target(sim, unit, "Defend", lead.x + rear, lead.y + self.rng.uniform(-0.8, 0.8), "Support")
        elif objective:
            self._set_target(sim, unit, "Defend", objective.x, objective.y, "Defend")

    def _command_scout(self, sim: Any, unit: Unit, objective: Any, contact: Unit | None, difficulty: float) -> None:
        target_x = contact.x if contact else (objective.x if objective else MAP_WIDTH / 2)
        target_y = contact.y if contact else (objective.y if objective else MAP_HEIGHT / 2)
        flank = 3.0 + difficulty * 0.8
        direction = -1 if (hash(unit.uid) + self.cycle) % 2 else 1
        self._set_target(sim, unit, "Flank", target_x, target_y + direction * flank, "Recon")

    def _command_armour(self, sim: Any, unit: Unit, objective: Any, contact: Unit | None, aggression: float) -> None:
        if contact and self.rng.random() < aggression:
            lead = 0.8 if unit.side == "Allied" else -0.8
            self._set_target(sim, unit, "Assault", contact.x + lead, contact.y, "Breakthrough")
        elif objective:
            self._set_target(sim, unit, "Advance", objective.x, objective.y + self.rng.uniform(-1.0, 1.0), "Mobile Reserve")

    def _command_rifle(self, sim: Any, unit: Unit, objective: Any, contact: Unit | None, aggression: float) -> None:
        if contact and distance((unit.x, unit.y), (contact.x, contact.y)) < 6.3 and self.rng.random() < aggression:
            offset = self.rng.uniform(-1.0, 1.0)
            self._set_target(sim, unit, "Assault", contact.x, contact.y + offset, "Aggressive")
        elif objective:
            spread = ((hash(unit.uid) >> 3) % 5 - 2) * 0.55
            self._set_target(sim, unit, "Advance", objective.x, objective.y + spread, "Advance")
