"""Image-backed unit rendering and enhanced battlefield effects."""
from __future__ import annotations

import math
import tkinter as tk

from .simulation import clamp
from .ui import W95


class SpriteGraphicsMixin:
    def _draw_unit(self, c: tk.Canvas, unit, w: float, h: float, cw: float, ch: float) -> None:
        x = self._mx(unit.x, w, cw)
        y = self._my(unit.y, h, ch) if hasattr(self, "_my") else (unit.y + 0.5) * ch
        selected = unit.uid in self.selected
        image = self.sprite_manager.unit(unit.side, unit.unit_type, getattr(self.camera, "zoom", 1.0)) if hasattr(self, "sprite_manager") else None
        size = self.sprite_manager.size_for_zoom(getattr(self.camera, "zoom", 1.0)) if hasattr(self, "sprite_manager") else 40
        radius = size * 0.42
        if x < -size or x > w + size or y < -size or y > h + size:
            return
        bob = math.sin(self.anim_time * 9 + hash(unit.uid) % 11) * min(1.6, unit.speed * 1.7)
        y += bob
        c.create_oval(x - radius * 0.82 + 3, y + radius * 0.25, x + radius * 0.82 + 3, y + radius * 0.62, fill="#081008", outline="", stipple="gray50", tags="frame")
        if selected:
            pulse = radius + 5 + math.sin(self.anim_time * 5.5) * 2
            c.create_oval(x - pulse, y - pulse, x + pulse, y + pulse, outline="#fff15a", width=2, dash=(5, 3), tags="frame")
            for angle in range(0, 360, 90):
                rad = math.radians(angle)
                c.create_line(x + math.cos(rad) * pulse, y + math.sin(rad) * pulse, x + math.cos(rad) * (pulse + 7), y + math.sin(rad) * (pulse + 7), fill="#fff15a", width=2, tags="frame")
        if image is not None:
            c.create_image(x, y, image=image, tags="frame")
        else:
            color = W95[unit.side.lower()]
            c.create_oval(x - radius, y - radius, x + radius, y + radius, fill=color, outline="white", width=2, tags="frame")
            c.create_text(x, y, text=unit.unit_type[:2].upper(), fill="white", font=("Arial", 8, "bold"), tags="frame")
        heading = math.pi - unit.heading if self.sim.player_side == "Axis" else unit.heading
        arrow_length = radius * 1.25
        c.create_line(x, y, x + math.cos(heading) * arrow_length, y + math.sin(heading) * arrow_length, fill="#ffe985", width=2, arrow="last", tags="frame")
        if unit.speed > 0.12:
            for index in range(2):
                phase = (self.anim_time * 4.5 + index * 0.35 + (hash(unit.uid) % 7)) % 1.0
                dx = -math.cos(heading) * radius * (0.7 + phase * 0.8); dy = -math.sin(heading) * radius * (0.7 + phase * 0.8); puff = 2.5 + phase * 2.4
                c.create_oval(x + dx - puff, y + dy - puff, x + dx + puff, y + dy + puff, fill="#9e8f6c", outline="", stipple="gray50", tags="frame")
        if selected:
            label = f"{unit.name}  •  {unit.order}"; label_y = y - radius - 12
            c.create_rectangle(x - max(55, radius * 1.45), label_y - 8, x + max(55, radius * 1.45), label_y + 8, fill="#101410", outline="#dfe9d8", tags="frame")
            c.create_text(x, label_y, text=label, fill="white", font=("MS Sans Serif", 7, "bold"), tags="frame")
        bar_width = radius * 2.0; bar_y = y + radius + 4
        bars = ((unit.strength, "#34dc51", "STR"), (unit.morale / 100.0, "#62a9ff", "MOR"), (unit.ammo / 100.0, "#f2ca4c", "AMM"))
        for index, (value, fill, _label) in enumerate(bars):
            yy = bar_y + index * 4
            c.create_rectangle(x - radius, yy, x + radius, yy + 3, fill="#211f1c", outline="#070707", tags="frame")
            c.create_rectangle(x - radius + 1, yy + 1, x - radius + 1 + (bar_width - 2) * clamp(value, 0, 1), yy + 2, fill=fill, outline="", tags="frame")
        if unit.suppression > 18:
            c.create_arc(x - radius - 4, y - radius - 4, x + radius + 4, y + radius + 4, start=90, extent=-360 * unit.suppression / 100, style="arc", outline="#ff8d22", width=3, tags="frame")
        if self.sim.elapsed - unit.last_hit < 0.25:
            c.create_oval(x - radius - 4, y - radius - 4, x + radius + 4, y + radius + 4, outline="#ff3f32", width=4, tags="frame")
        if self.sim.elapsed - unit.last_fire < 0.18:
            mx = x + math.cos(heading) * radius * 1.15; my = y + math.sin(heading) * radius * 1.15
            c.create_polygon(mx - 5, my, mx, my - 6, mx + 9, my, mx, my + 6, fill="#fff5a8", outline="#ff6a00", tags="frame")
        if selected and unit.target_x is not None and unit.target_y is not None:
            tx = self._mx(unit.target_x, w, cw); ty = self._my(unit.target_y, h, ch) if hasattr(self, "_my") else (unit.target_y + 0.5) * ch
            c.create_line(x, y, tx, ty, fill="#fff15a", dash=(6, 4), arrow="last", width=2, tags="frame")
            c.create_oval(tx - 7, ty - 7, tx + 7, ty + 7, outline="#fff15a", width=2, tags="frame")
