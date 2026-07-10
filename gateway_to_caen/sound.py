"""Low-overhead asynchronous sound playback with Windows and Tk fallbacks."""
from __future__ import annotations

import os
import time
from typing import Any

from .asset_bundle import ensure_assets

try:
    import winsound  # type: ignore
except ImportError:  # pragma: no cover - non-Windows fallback
    winsound = None


class SoundManager:
    def __init__(self, root: Any, enabled: bool = True) -> None:
        self.root = root
        self.enabled = bool(enabled)
        self.sound_dir = ensure_assets() / "sounds"
        self._last_played: dict[str, float] = {}
        self._event_cursor = 0
        self._cooldowns = {
            "gunfire": 0.16,
            "explosion": 0.28,
            "select": 0.08,
            "order": 0.12,
            "objective": 0.5,
            "requisition": 0.35,
        }

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = bool(enabled)

    def play(self, name: str, force: bool = False) -> None:
        if not self.enabled:
            return
        now = time.perf_counter()
        if not force and now - self._last_played.get(name, -999.0) < self._cooldowns.get(name, 0.05):
            return
        self._last_played[name] = now
        path = self.sound_dir / f"{name}.wav"
        if winsound is not None and path.exists():
            try:
                winsound.PlaySound(str(path), winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
                return
            except RuntimeError:
                pass
        try:
            self.root.bell()
        except Exception:
            pass

    def consume_events(self, events: list[Any]) -> None:
        if self._event_cursor > len(events):
            self._event_cursor = 0
        for event in events[self._event_cursor :]:
            category = str(getattr(event, "category", ""))
            text = str(getattr(event, "text", ""))
            lower = text.lower()
            if category == "Combat":
                self.play("explosion" if any(word in lower for word in ("eliminated", "destroyed", "armour")) else "gunfire")
            elif category == "Objectives":
                self.play("objective")
            elif category == "Requisition":
                self.play("requisition")
            elif category in ("Orders", "Movement"):
                self.play("order")
            elif category in ("Campaign", "Command") and "commenced" in lower:
                self.play("battle_start", force=True)
        self._event_cursor = len(events)
