"""Dependency-free adaptive neural Q-network for the visible virtual commander."""
from __future__ import annotations

import json
import math
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, List, Sequence

ACTIONS = ("advance", "flank", "hold", "retreat", "assault")


def _clip(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _tanh_derivative(output: float) -> float:
    return 1.0 - output * output


@dataclass
class BrainStats:
    decisions: int = 0
    training_steps: int = 0
    replay_steps: int = 0
    lifetime_reward: float = 0.0
    wins: int = 0
    losses: int = 0
    action_counts: dict[str, int] = field(default_factory=lambda: {action: 0 for action in ACTIONS})

    def to_dict(self) -> dict:
        return {
            "decisions": self.decisions,
            "training_steps": self.training_steps,
            "replay_steps": self.replay_steps,
            "lifetime_reward": self.lifetime_reward,
            "wins": self.wins,
            "losses": self.losses,
            "action_counts": dict(self.action_counts),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "BrainStats":
        result = cls()
        result.decisions = int(data.get("decisions", 0))
        result.training_steps = int(data.get("training_steps", 0))
        result.replay_steps = int(data.get("replay_steps", 0))
        result.lifetime_reward = float(data.get("lifetime_reward", 0.0))
        result.wins = int(data.get("wins", 0))
        result.losses = int(data.get("losses", 0))
        incoming = data.get("action_counts", {})
        result.action_counts = {action: int(incoming.get(action, 0)) for action in ACTIONS}
        return result


@dataclass
class ReplayItem:
    state: list[float]
    action: int
    reward: float
    next_state: list[float]
    terminal: bool
    priority: float


class TacticalBrain:
    """A compact Q-network with replay, epsilon decay, and legacy migration.

    The model remains list-based so the game runs on a standard Windows Python
    installation. Version 2 expands the observation space and hidden layer, adds
    replay learning, adaptive exploration, gradient clipping, and weight decay.
    """

    VERSION = 2

    def __init__(self, input_size: int = 18, hidden_size: int = 32, output_size: int = len(ACTIONS), learning_rate: float = 0.009, discount: float = 0.93, epsilon: float = 0.14, seed: int | None = None) -> None:
        self.input_size = input_size
        self.hidden_size = hidden_size
        self.output_size = output_size
        self.learning_rate = learning_rate
        self.discount = discount
        self.epsilon = epsilon
        self.min_epsilon = 0.025
        self.epsilon_decay = 0.9994
        self.weight_decay = 0.000025
        self.rng = random.Random(seed)
        scale1 = math.sqrt(2.0 / max(1, input_size + hidden_size))
        scale2 = math.sqrt(2.0 / max(1, hidden_size + output_size))
        self.w1 = [[self.rng.uniform(-scale1, scale1) for _ in range(input_size)] for _ in range(hidden_size)]
        self.b1 = [0.0 for _ in range(hidden_size)]
        self.w2 = [[self.rng.uniform(-scale2, scale2) for _ in range(hidden_size)] for _ in range(output_size)]
        self.b2 = [0.0 for _ in range(output_size)]
        self.stats = BrainStats()
        self.last_q_values = [0.0] * output_size
        self.last_action = "hold"
        self.replay_memory: list[ReplayItem] = []
        self.replay_limit = 384

    @staticmethod
    def normalize_state(values: Iterable[float], expected: int = 18) -> List[float]:
        state = [_clip(float(value), -1.0, 1.0) for value in values]
        if len(state) < expected:
            state.extend([0.0] * (expected - len(state)))
        return state[:expected]

    def forward(self, state: Sequence[float]) -> tuple[List[float], List[float]]:
        x = self.normalize_state(state, self.input_size)
        hidden = [math.tanh(sum(weight * value for weight, value in zip(row, x)) + bias) for row, bias in zip(self.w1, self.b1)]
        output = [sum(weight * value for weight, value in zip(row, hidden)) + bias for row, bias in zip(self.w2, self.b2)]
        return hidden, output

    def choose_action(self, state: Sequence[float], explore: bool = True, action_mask: Sequence[bool] | None = None) -> int:
        _, q_values = self.forward(state)
        self.last_q_values = list(q_values)
        available = [index for index in range(self.output_size) if action_mask is None or (index < len(action_mask) and action_mask[index])]
        if not available:
            available = list(range(self.output_size))
        effective_epsilon = max(self.min_epsilon, self.epsilon)
        if explore and self.rng.random() < effective_epsilon:
            action_index = self.rng.choice(available)
        else:
            action_index = max(available, key=q_values.__getitem__)
        action_name = ACTIONS[action_index]
        self.last_action = action_name
        self.stats.decisions += 1
        self.stats.action_counts[action_name] = self.stats.action_counts.get(action_name, 0) + 1
        if explore:
            self.epsilon = max(self.min_epsilon, self.epsilon * self.epsilon_decay)
        return action_index

    def train(self, state: Sequence[float], action_index: int, reward: float, next_state: Sequence[float], terminal: bool = False) -> float:
        x = self.normalize_state(state, self.input_size)
        next_x = self.normalize_state(next_state, self.input_size)
        hidden, output = self.forward(x)
        _, next_output = self.forward(next_x)
        target = reward if terminal else reward + self.discount * max(next_output)
        error = _clip(target - output[action_index], -3.5, 3.5)
        old_output_row = list(self.w2[action_index])
        rate = self.learning_rate / math.sqrt(1.0 + self.stats.training_steps / 4500.0)
        for j in range(self.hidden_size):
            gradient = _clip(error * hidden[j], -1.5, 1.5)
            self.w2[action_index][j] += rate * gradient - self.weight_decay * self.w2[action_index][j]
        self.b2[action_index] += rate * error
        for j in range(self.hidden_size):
            hidden_error = _clip(error * old_output_row[j] * _tanh_derivative(hidden[j]), -1.25, 1.25)
            for i in range(self.input_size):
                self.w1[j][i] += rate * hidden_error * x[i] - self.weight_decay * self.w1[j][i]
            self.b1[j] += rate * hidden_error
        self.stats.training_steps += 1
        self.stats.lifetime_reward += reward
        return abs(error)

    def remember(self, state: Sequence[float], action_index: int, reward: float, next_state: Sequence[float], terminal: bool = False) -> None:
        _, current = self.forward(state)
        _, future = self.forward(next_state)
        target = reward if terminal else reward + self.discount * max(future)
        priority = abs(target - current[action_index]) + 0.03
        self.replay_memory.append(ReplayItem(self.normalize_state(state, self.input_size), int(action_index), float(reward), self.normalize_state(next_state, self.input_size), bool(terminal), priority))
        if len(self.replay_memory) > self.replay_limit:
            self.replay_memory = self.replay_memory[-self.replay_limit :]

    def replay(self, batch_size: int = 8) -> float:
        if not self.replay_memory:
            return 0.0
        batch_size = min(max(1, batch_size), len(self.replay_memory))
        pool = sorted(self.replay_memory, key=lambda item: item.priority, reverse=True)[: max(batch_size * 4, batch_size)]
        batch = self.rng.sample(pool, batch_size)
        error = 0.0
        for item in batch:
            item_error = self.train(item.state, item.action, item.reward, item.next_state, item.terminal)
            item.priority = item_error + 0.03
            error += item_error
        self.stats.replay_steps += batch_size
        return error / batch_size

    def learn_transition(self, state: Sequence[float], action_index: int, reward: float, next_state: Sequence[float], terminal: bool = False) -> float:
        self.remember(state, action_index, reward, next_state, terminal)
        direct = self.train(state, action_index, reward, next_state, terminal)
        replay_error = self.replay(6 if len(self.replay_memory) >= 6 else len(self.replay_memory))
        return (direct + replay_error) / 2 if replay_error else direct

    def mark_result(self, won: bool) -> None:
        if won:
            self.stats.wins += 1
        else:
            self.stats.losses += 1

    def to_dict(self) -> dict:
        return {"version": self.VERSION, "input_size": self.input_size, "hidden_size": self.hidden_size, "output_size": self.output_size, "learning_rate": self.learning_rate, "discount": self.discount, "epsilon": self.epsilon, "min_epsilon": self.min_epsilon, "epsilon_decay": self.epsilon_decay, "w1": self.w1, "b1": self.b1, "w2": self.w2, "b2": self.b2, "stats": self.stats.to_dict()}

    @classmethod
    def from_dict(cls, data: dict) -> "TacticalBrain":
        version = int(data.get("version", 1))
        if version < 2 or int(data.get("input_size", 10)) < 18 or int(data.get("hidden_size", 18)) < 28:
            return cls._migrate_legacy(data)
        brain = cls(input_size=int(data.get("input_size", 18)), hidden_size=int(data.get("hidden_size", 32)), output_size=int(data.get("output_size", len(ACTIONS))), learning_rate=float(data.get("learning_rate", 0.009)), discount=float(data.get("discount", 0.93)), epsilon=float(data.get("epsilon", 0.14)))
        brain.min_epsilon = float(data.get("min_epsilon", 0.025))
        brain.epsilon_decay = float(data.get("epsilon_decay", 0.9994))
        brain.w1 = [[float(value) for value in row] for row in data["w1"]]
        brain.b1 = [float(value) for value in data["b1"]]
        brain.w2 = [[float(value) for value in row] for row in data["w2"]]
        brain.b2 = [float(value) for value in data["b2"]]
        brain.stats = BrainStats.from_dict(data.get("stats", {}))
        return brain

    @classmethod
    def _migrate_legacy(cls, data: dict) -> "TacticalBrain":
        brain = cls()
        try:
            old_w1, old_b1, old_w2, old_b2 = data.get("w1", []), data.get("b1", []), data.get("w2", []), data.get("b2", [])
            for j in range(min(len(old_w1), brain.hidden_size)):
                for i in range(min(len(old_w1[j]), brain.input_size)):
                    brain.w1[j][i] = float(old_w1[j][i])
                if j < len(old_b1): brain.b1[j] = float(old_b1[j])
            for action in range(min(len(old_w2), brain.output_size)):
                for j in range(min(len(old_w2[action]), brain.hidden_size)):
                    brain.w2[action][j] = float(old_w2[action][j])
                if action < len(old_b2): brain.b2[action] = float(old_b2[action])
            brain.stats = BrainStats.from_dict(data.get("stats", {}))
            brain.epsilon = max(brain.min_epsilon, float(data.get("epsilon", brain.epsilon)) * 0.8)
        except (TypeError, ValueError, IndexError):
            pass
        return brain

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps(self.to_dict(), separators=(",", ":")), encoding="utf-8")
        temporary.replace(path)

    @classmethod
    def load_or_create(cls, path: Path) -> "TacticalBrain":
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return cls.from_dict(data)
        except (OSError, ValueError, KeyError, TypeError):
            return cls()
