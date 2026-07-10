"""Small spatial hash used to keep collision and target searches fast."""
from __future__ import annotations

import math
from collections import defaultdict
from typing import Callable, Generic, Iterable, TypeVar

T = TypeVar("T")


class SpatialHash(Generic[T]):
    def __init__(self, cell_size: float = 2.0) -> None:
        self.cell_size = max(0.25, float(cell_size))
        self.buckets: dict[tuple[int, int], list[T]] = defaultdict(list)

    def clear(self) -> None:
        self.buckets.clear()

    def key(self, x: float, y: float) -> tuple[int, int]:
        return (math.floor(x / self.cell_size), math.floor(y / self.cell_size))

    def insert(self, item: T, x: float, y: float) -> None:
        self.buckets[self.key(x, y)].append(item)

    def rebuild(self, items: Iterable[T], position: Callable[[T], tuple[float, float]]) -> None:
        self.clear()
        for item in items:
            x, y = position(item)
            self.insert(item, x, y)

    def nearby(self, x: float, y: float, radius: float) -> list[T]:
        cell_radius = max(1, math.ceil(radius / self.cell_size))
        cx, cy = self.key(x, y)
        result: list[T] = []
        for yy in range(cy - cell_radius, cy + cell_radius + 1):
            for xx in range(cx - cell_radius, cx + cell_radius + 1):
                result.extend(self.buckets.get((xx, yy), ()))
        return result
