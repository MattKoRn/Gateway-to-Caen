"""Small dependency-free neural Q-network used by tactical AI."""
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
    lifetime_reward: float = 0.0
    wins: int = 0
    losses: int = 0
    action_counts: dict[str, int] = field(
        default_factory=lambda: {action: 0 for action in ACTIONS}
    )

    def to_dict(self) -> dict:
        return {
            "decisions": self.decisions,
            "training_steps": self.training_steps,
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
        result.lifetime_reward = float(data.get("lifetime_reward", 0.0))
        result.wins = int(data.get("wins", 0))
        result.losses = int(data.get("losses", 0))
        incoming = data.get("action_counts", {})
        result.action_counts = {a: int(incoming.get(a, 0)) for a in ACTIONS}
        return result


class TacticalBrain:
    """A compact one-hidden-layer neural Q-network.

    It is intentionally implemented with Python lists rather than NumPy so the
    game can run on a default Windows Python installation.
    """

    VERSION = 1

    def __init__(
        self,
        input_size: int = 10,
        hidden_size: int = 18,
        output_size: int = len(ACTIONS),
        learning_rate: float = 0.012,
        discount: float = 0.88,
        epsilon: float = 0.12,
        seed: int | None = None,
    ) -> None:
        self.input_size = input_size
        self.hidden_size = hidden_size
        self.output_size = output_size
        self.learning_rate = learning_rate
        self.discount = discount
        self.epsilon = epsilon
        self.rng = random.Random(seed)
        scale1 = 1.0 / math.sqrt(max(1, input_size))
        scale2 = 1.0 / math.sqrt(max(1, hidden_size))
        self.w1 = [
            [self.rng.uniform(-scale1, scale1) for _ in range(input_size)]
            for _ in range(hidden_size)
        ]
        self.b1 = [0.0 for _ in range(hidden_size)]
        self.w2 = [
            [self.rng.uniform(-scale2, scale2) for _ in range(hidden_size)]
            for _ in range(output_size)
        ]
        self.b2 = [0.0 for _ in range(output_size)]
        self.stats = BrainStats()
        self.last_q_values = [0.0] * output_size
        self.last_action = "hold"

    @staticmethod
    def normalize_state(values: Iterable[float], expected: int = 10) -> List[float]:
        state = [_clip(float(v), -1.0, 1.0) for v in values]
        if len(state) < expected:
            state.extend([0.0] * (expected - len(state)))
        return state[:expected]

    def forward(self, state: Sequence[float]) -> tuple[List[float], List[float]]:
        x = self.normalize_state(state, self.input_size)
        hidden: List[float] = []
        for row, bias in zip(self.w1, self.b1):
            hidden.append(math.tanh(sum(w * v for w, v in zip(row, x)) + bias))
        output: List[float] = []
        for row, bias in zip(self.w2, self.b2):
            output.append(sum(w * h for w, h in zip(row, hidden)) + bias)
        return hidden, output

    def choose_action(self, state: Sequence[float], explore: bool = True) -> int:
        _, q_values = self.forward(state)
        self.last_q_values = list(q_values)
        if explore and self.rng.random() < self.epsilon:
            action_index = self.rng.randrange(self.output_size)
        else:
            action_index = max(range(self.output_size), key=q_values.__getitem__)
        action_name = ACTIONS[action_index]
        self.last_action = action_name
        self.stats.decisions += 1
        self.stats.action_counts[action_name] = self.stats.action_counts.get(action_name, 0) + 1
        return action_index

    def train(
        self,
        state: Sequence[float],
        action_index: int,
        reward: float,
        next_state: Sequence[float],
        terminal: bool = False,
    ) -> float:
        x = self.normalize_state(state, self.input_size)
        hidden, output = self.forward(x)
        _, next_output = self.forward(next_state)
        target = reward if terminal else reward + self.discount * max(next_output)
        error = _clip(target - output[action_index], -4.0, 4.0)

        old_output_row = list(self.w2[action_index])
        for j in range(self.hidden_size):
            self.w2[action_index][j] += self.learning_rate * error * hidden[j]
        self.b2[action_index] += self.learning_rate * error

        for j in range(self.hidden_size):
            hidden_error = error * old_output_row[j] * _tanh_derivative(hidden[j])
            for i in range(self.input_size):
                self.w1[j][i] += self.learning_rate * hidden_error * x[i]
            self.b1[j] += self.learning_rate * hidden_error

        self.stats.training_steps += 1
        self.stats.lifetime_reward += reward
        return abs(error)

    def mark_result(self, won: bool) -> None:
        if won:
            self.stats.wins += 1
        else:
            self.stats.losses += 1

    def to_dict(self) -> dict:
        return {
            "version": self.VERSION,
            "input_size": self.input_size,
            "hidden_size": self.hidden_size,
            "output_size": self.output_size,
            "learning_rate": self.learning_rate,
            "discount": self.discount,
            "epsilon": self.epsilon,
            "w1": self.w1,
            "b1": self.b1,
            "w2": self.w2,
            "b2": self.b2,
            "stats": self.stats.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "TacticalBrain":
        brain = cls(
            input_size=int(data.get("input_size", 10)),
            hidden_size=int(data.get("hidden_size", 18)),
            output_size=int(data.get("output_size", len(ACTIONS))),
            learning_rate=float(data.get("learning_rate", 0.012)),
            discount=float(data.get("discount", 0.88)),
            epsilon=float(data.get("epsilon", 0.12)),
        )
        brain.w1 = [[float(v) for v in row] for row in data["w1"]]
        brain.b1 = [float(v) for v in data["b1"]]
        brain.w2 = [[float(v) for v in row] for row in data["w2"]]
        brain.b2 = [float(v) for v in data["b2"]]
        brain.stats = BrainStats.from_dict(data.get("stats", {}))
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
