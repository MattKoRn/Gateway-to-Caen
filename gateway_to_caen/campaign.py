"""Persistent campaign rosters, resources, adaptive difficulty, and requisition."""
from __future__ import annotations

import random
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable

from .neural import TacticalBrain
from .persistence import atomic_write_json, read_json

SIDES = ("Allied", "Axis")
UNIT_TYPES = ("Rifle", "Support", "Scout", "Mortar", "Armour")
UNIT_COSTS: dict[str, dict[str, int]] = {
    "Rifle": {"manpower": 20, "supplies": 35, "command_points": 4},
    "Support": {"manpower": 16, "supplies": 55, "command_points": 8},
    "Scout": {"manpower": 12, "supplies": 30, "command_points": 6},
    "Mortar": {"manpower": 10, "supplies": 70, "command_points": 10},
    "Armour": {"manpower": 8, "supplies": 140, "command_points": 18},
}
UNIT_MEN = {"Rifle": 10, "Support": 7, "Scout": 6, "Mortar": 5, "Armour": 4}
NAME_STEMS = {
    "Allied": {
        "Rifle": ("Able", "Baker", "Charlie", "Dog", "Easy", "Fox", "George", "How"),
        "Support": ("Bren", "Vickers", "Support", "Weapons"),
        "Scout": ("Recce", "Pathfinder", "Scout", "Forward"),
        "Mortar": ("Mortar", "Bombardment", "Fire Support"),
        "Armour": ("Churchill", "Cromwell", "Sherman", "Armoured"),
    },
    "Axis": {
        "Rifle": ("Grenadier", "Fusilier", "Jäger", "Rifle"),
        "Support": ("MG", "Heavy Weapons", "Support", "Maschinengewehr"),
        "Scout": ("Aufklärung", "Recon", "Schnell", "Vanguard"),
        "Mortar": ("Granatwerfer", "Mortar", "Fire Support"),
        "Armour": ("Panzer", "Sturmgeschütz", "Armoured", "Kampfgruppe"),
    },
}


@dataclass
class FactionResources:
    manpower: int = 180
    supplies: int = 850
    command_points: int = 110

    def can_afford(self, unit_type: str) -> bool:
        cost = UNIT_COSTS[unit_type]
        return all(getattr(self, key) >= value for key, value in cost.items())

    def spend(self, unit_type: str) -> bool:
        if not self.can_afford(unit_type):
            return False
        for key, value in UNIT_COSTS[unit_type].items():
            setattr(self, key, getattr(self, key) - value)
        return True

    def grant(self, manpower: int = 0, supplies: int = 0, command_points: int = 0) -> None:
        self.manpower = max(0, self.manpower + int(manpower))
        self.supplies = max(0, self.supplies + int(supplies))
        self.command_points = max(0, self.command_points + int(command_points))

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "FactionResources":
        data = data if isinstance(data, dict) else {}
        return cls(
            manpower=max(0, int(data.get("manpower", 180))),
            supplies=max(0, int(data.get("supplies", 850))),
            command_points=max(0, int(data.get("command_points", 110))),
        )


@dataclass
class PersistentUnit:
    uid: str
    side: str
    name: str
    unit_type: str
    men: int
    max_men: int
    morale: float = 100.0
    ammo: float = 100.0
    experience: float = 0.4
    kills: int = 0
    battles: int = 0

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PersistentUnit":
        valid = set(cls.__dataclass_fields__)
        payload = {key: data[key] for key in valid if key in data}
        unit = cls(**payload)
        unit.men = max(0, min(int(unit.men), int(unit.max_men)))
        unit.morale = max(0.0, min(100.0, float(unit.morale)))
        unit.ammo = max(0.0, min(100.0, float(unit.ammo)))
        unit.experience = max(0.0, min(1.0, float(unit.experience)))
        return unit


@dataclass
class RequisitionRecord:
    battle_index: int
    side: str
    unit_type: str
    unit_name: str
    costs: dict[str, int]
    reason: str
    timestamp: float = field(default_factory=time.time)


@dataclass
class RequisitionExperience:
    side: str
    state: list[float]
    action_index: int
    unit_uid: str


@dataclass
class CampaignState:
    version: int = 2
    battle_index: int = 0
    rosters: dict[str, list[PersistentUnit]] = field(default_factory=lambda: {side: [] for side in SIDES})
    resources: dict[str, FactionResources] = field(default_factory=lambda: {side: FactionResources() for side in SIDES})
    recent_player_results: list[bool] = field(default_factory=list)
    difficulty: float = 1.0
    reward_multiplier: float = 1.0
    requisition_history: list[RequisitionRecord] = field(default_factory=list)
    pending_requisition_experiences: list[RequisitionExperience] = field(default_factory=list)
    last_rewards: dict[str, dict[str, int]] = field(default_factory=dict)
    last_objectives: list[dict[str, Any]] = field(default_factory=list)
    map_history: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def fresh(cls) -> "CampaignState":
        state = cls()
        for side in SIDES:
            state.rosters[side] = default_roster(side)
        return state

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "CampaignState":
        if not isinstance(data, dict) or not data:
            return cls.fresh()
        state = cls()
        state.version = int(data.get("version", 2))
        state.battle_index = max(0, int(data.get("battle_index", 0)))
        incoming_rosters = data.get("rosters", {})
        state.rosters = {side: [] for side in SIDES}
        for side in SIDES:
            has_side = isinstance(incoming_rosters, dict) and side in incoming_rosters
            values = incoming_rosters.get(side, []) if isinstance(incoming_rosters, dict) else []
            if isinstance(values, list):
                state.rosters[side] = [PersistentUnit.from_dict(item) for item in values if isinstance(item, dict)]
            if not has_side:
                state.rosters[side] = default_roster(side)
        incoming_resources = data.get("resources", {})
        state.resources = {
            side: FactionResources.from_dict(incoming_resources.get(side) if isinstance(incoming_resources, dict) else None)
            for side in SIDES
        }
        state.recent_player_results = [bool(value) for value in data.get("recent_player_results", [])][-8:]
        state.difficulty = max(0.65, min(1.8, float(data.get("difficulty", 1.0))))
        state.reward_multiplier = max(0.7, min(1.8, float(data.get("reward_multiplier", 1.0))))
        state.requisition_history = [RequisitionRecord(**item) for item in data.get("requisition_history", []) if isinstance(item, dict)][-80:]
        state.pending_requisition_experiences = [
            RequisitionExperience(**item) for item in data.get("pending_requisition_experiences", []) if isinstance(item, dict)
        ]
        state.last_rewards = data.get("last_rewards", {}) if isinstance(data.get("last_rewards"), dict) else {}
        state.last_objectives = data.get("last_objectives", []) if isinstance(data.get("last_objectives"), list) else []
        state.map_history = data.get("map_history", []) if isinstance(data.get("map_history"), list) else []
        return state

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "battle_index": self.battle_index,
            "rosters": {side: [asdict(unit) for unit in self.rosters[side]] for side in SIDES},
            "resources": {side: asdict(self.resources[side]) for side in SIDES},
            "recent_player_results": list(self.recent_player_results),
            "difficulty": self.difficulty,
            "reward_multiplier": self.reward_multiplier,
            "requisition_history": [asdict(item) for item in self.requisition_history[-80:]],
            "pending_requisition_experiences": [asdict(item) for item in self.pending_requisition_experiences],
            "last_rewards": self.last_rewards,
            "last_objectives": self.last_objectives,
            "map_history": self.map_history[-40:],
        }

    def capture_survivors(self, units: Iterable[Any]) -> None:
        captured = {side: [] for side in SIDES}
        for unit in units:
            if not getattr(unit, "alive", False) or int(getattr(unit, "men", 0)) <= 0 or unit.side not in SIDES:
                continue
            captured[unit.side].append(
                PersistentUnit(
                    uid=str(unit.uid),
                    side=str(unit.side),
                    name=str(unit.name),
                    unit_type=str(unit.unit_type),
                    men=int(unit.men),
                    max_men=int(unit.max_men),
                    morale=float(unit.morale),
                    ammo=float(unit.ammo),
                    experience=min(1.0, float(unit.experience) + 0.015),
                    kills=int(unit.kills),
                    battles=next((old.battles for old in self.rosters[unit.side] if old.uid == unit.uid), 0) + 1,
                )
            )
        for side in SIDES:
            self.rosters[side] = captured[side]

    def update_scaling(self, player_won: bool) -> None:
        self.recent_player_results.append(bool(player_won))
        self.recent_player_results = self.recent_player_results[-8:]
        rate = sum(self.recent_player_results) / max(1, len(self.recent_player_results))
        streak = 0
        for result in reversed(self.recent_player_results):
            if result == player_won:
                streak += 1
            else:
                break
        direction = 1.0 if player_won else -1.0
        target = 0.82 + rate * 0.72 + direction * min(0.16, streak * 0.035)
        self.difficulty = max(0.65, min(1.8, self.difficulty * 0.62 + target * 0.38))
        self.reward_multiplier = max(0.72, min(1.75, 0.72 + self.difficulty * 0.48))

    def settle_battle(self, winner: str, player_side: str, objective_value: int = 0) -> None:
        player_won = winner == player_side
        self.update_scaling(player_won)
        rewards: dict[str, dict[str, int]] = {}
        for side in SIDES:
            victory = side == winner
            scale = self.reward_multiplier if side == player_side else 0.92 + self.difficulty * 0.18
            manpower = int((22 if victory else 13) * scale)
            supplies = int((125 if victory else 78) * scale + objective_value * 0.16)
            command = int((16 if victory else 9) * scale)
            self.resources[side].grant(manpower, supplies, command)
            rewards[side] = {"manpower": manpower, "supplies": supplies, "command_points": command}
        self.last_rewards = rewards
        self._train_requisition_outcomes(winner)

    def requisition_for_battle(self, brain: TacticalBrain, seed: int, max_per_side: int = 3) -> list[RequisitionRecord]:
        rng = random.Random(seed ^ 0x51A9C3)
        records: list[RequisitionRecord] = []
        self.pending_requisition_experiences = []
        for side in SIDES:
            desired_count = min(max_per_side, max(0, 8 - len(self.rosters[side])))
            if side == "Axis" and self.difficulty > 1.18:
                desired_count = min(max_per_side, desired_count + 1)
            for _ in range(desired_count):
                affordable = [kind for kind in UNIT_TYPES if self.resources[side].can_afford(kind)]
                if not affordable:
                    break
                state = self.requisition_state(side)
                _, q_values = brain.forward(state)
                counts = {kind: sum(unit.unit_type == kind for unit in self.rosters[side]) for kind in UNIT_TYPES}
                utilities: list[tuple[float, str, int]] = []
                for index, kind in enumerate(UNIT_TYPES):
                    if kind not in affordable:
                        continue
                    balance_need = {"Rifle": 1.2, "Support": 0.72, "Scout": 0.55, "Mortar": 0.62, "Armour": 0.66}[kind]
                    shortage = balance_need - counts[kind] / max(1, len(self.rosters[side]))
                    difficulty_bias = (self.difficulty - 1.0) * (0.8 if kind in ("Armour", "Mortar", "Support") else 0.25)
                    noise = rng.uniform(-0.08, 0.08)
                    q = q_values[index % len(q_values)] if q_values else 0.0
                    utilities.append((q + shortage * 1.35 + difficulty_bias + noise, kind, index))
                if not utilities:
                    break
                _, unit_type, action_index = max(utilities, key=lambda item: item[0])
                if not self.resources[side].spend(unit_type):
                    break
                unit = make_persistent_unit(side, unit_type, len(self.rosters[side]) + 1, rng)
                self.rosters[side].append(unit)
                reason = self._requisition_reason(side, unit_type, counts)
                record = RequisitionRecord(self.battle_index, side, unit_type, unit.name, dict(UNIT_COSTS[unit_type]), reason)
                self.requisition_history.append(record)
                records.append(record)
                self.pending_requisition_experiences.append(RequisitionExperience(side, state, action_index, unit.uid))
        self.requisition_history = self.requisition_history[-80:]
        return records

    def requisition_state(self, side: str) -> list[float]:
        resources = self.resources[side]
        roster = self.rosters[side]
        counts = [sum(unit.unit_type == kind for unit in roster) for kind in UNIT_TYPES]
        strength = sum(unit.men / max(1, unit.max_men) for unit in roster)
        recent_rate = sum(self.recent_player_results) / max(1, len(self.recent_player_results)) if self.recent_player_results else 0.5
        values = [
            resources.manpower / 300 * 2 - 1,
            resources.supplies / 1500 * 2 - 1,
            resources.command_points / 220 * 2 - 1,
            len(roster) / 18 * 2 - 1,
            strength / 12 * 2 - 1,
            self.difficulty - 1.0,
            recent_rate * 2 - 1,
        ]
        values.extend(count / 6 * 2 - 1 for count in counts)
        values.extend([1.0 if side == "Allied" else -1.0, self.battle_index / 20 - 1.0])
        return values

    def _train_requisition_outcomes(self, winner: str) -> None:
        roster_ids = {side: {unit.uid for unit in self.rosters[side]} for side in SIDES}
        for experience in self.pending_requisition_experiences:
            survived = experience.unit_uid in roster_ids.get(experience.side, set())
            reward = (1.2 if experience.side == winner else -0.75) + (0.35 if survived else -0.4)
            next_state = self.requisition_state(experience.side)
            try:
                self._brain.train(experience.state, experience.action_index, reward, next_state, terminal=True)  # type: ignore[attr-defined]
            except AttributeError:
                pass
        self.pending_requisition_experiences = []

    def attach_brain(self, brain: TacticalBrain) -> None:
        self._brain = brain

    @staticmethod
    def _requisition_reason(side: str, unit_type: str, counts: dict[str, int]) -> str:
        if counts.get(unit_type, 0) == 0:
            return f"Filled a missing {unit_type.lower()} capability"
        if unit_type == "Armour":
            return "Added mobile breakthrough strength"
        if unit_type == "Mortar":
            return "Expanded indirect-fire coverage"
        if unit_type == "Support":
            return "Improved suppression and defensive fire"
        if unit_type == "Scout":
            return "Improved reconnaissance and flank security"
        return f"Reinforced the {side.lower()} infantry line"


def make_persistent_unit(side: str, unit_type: str, sequence: int, rng: random.Random) -> PersistentUnit:
    stem = rng.choice(NAME_STEMS[side][unit_type])
    suffix = rng.choice(("Section", "Team", "Troop", "Group", "Detachment", str(sequence)))
    name = f"{stem} {suffix}"
    men = UNIT_MEN[unit_type]
    return PersistentUnit(
        uid=str(uuid.uuid4()),
        side=side,
        name=name,
        unit_type=unit_type,
        men=men,
        max_men=men,
        morale=rng.uniform(82.0, 100.0),
        ammo=rng.uniform(86.0, 100.0),
        experience=rng.uniform(0.34, 0.58),
    )


def default_roster(side: str) -> list[PersistentUnit]:
    rng = random.Random(7719 if side == "Allied" else 9917)
    composition = ("Rifle", "Rifle", "Support", "Scout", "Mortar", "Armour")
    return [make_persistent_unit(side, kind, index + 1, rng) for index, kind in enumerate(composition)]


def load_campaign(path: Path) -> CampaignState:
    return CampaignState.from_dict(read_json(path, {}))


def save_campaign(path: Path, state: CampaignState) -> None:
    atomic_write_json(path, state.to_dict())
