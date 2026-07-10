"""Runtime loader for packaged unit and interface sprite artwork."""
from __future__ import annotations

import tkinter as tk

from .asset_bundle import ensure_assets


class SpriteManager:
    SIZES = (40, 56, 72)

    def __init__(self, root: tk.Misc) -> None:
        self.root = root
        self.asset_dir = ensure_assets()
        self._cache: dict[tuple[str, str, int], tk.PhotoImage] = {}
        self._ui_cache: dict[str, tk.PhotoImage] = {}

    @classmethod
    def size_for_zoom(cls, zoom: float) -> int:
        if zoom >= 2.15:
            return 72
        if zoom >= 1.45:
            return 56
        return 40

    def unit(self, side: str, unit_type: str, zoom: float) -> tk.PhotoImage | None:
        size = self.size_for_zoom(zoom)
        key = (side.lower(), unit_type.lower(), size)
        if key not in self._cache:
            path = self.asset_dir / "sprites" / f"{key[0]}_{key[1]}_{size}.png"
            try:
                self._cache[key] = tk.PhotoImage(master=self.root, file=str(path))
            except tk.TclError:
                return None
        return self._cache[key]

    def ui(self, name: str) -> tk.PhotoImage | None:
        if name not in self._ui_cache:
            path = self.asset_dir / "ui" / f"{name}.png"
            try:
                self._ui_cache[name] = tk.PhotoImage(master=self.root, file=str(path))
            except tk.TclError:
                return None
        return self._ui_cache[name]
