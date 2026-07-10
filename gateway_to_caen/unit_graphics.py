"""Detailed unit, combat-effect, and weather rendering."""
from __future__ import annotations

import math
import tkinter as tk

from .simulation import clamp
from .ui import W95


class UnitGraphicsMixin:
    @staticmethod
    def _rotated_points(cx: float, cy: float, heading: float, points: tuple[tuple[float, float], ...]) -> list[float]:
        cosine, sine = math.cos(heading), math.sin(heading)
        result: list[float] = []
        for px, py in points:
            result.extend((cx + px * cosine - py * sine, cy + px * sine + py * cosine))
        return result

    def _draw_unit(self, c: tk.Canvas, unit, w: float, h: float, cw: float, ch: float) -> None:
        x, y = self._mx(unit.x, w, cw), (unit.y + .5) * ch
        radius = max(9, min(cw, ch) * .36)
        selected = unit.uid in self.selected
        heading = math.pi - unit.heading if self.sim.player_side == "Axis" else unit.heading
        bob = math.sin(self.anim_time * 10 + hash(unit.uid) % 10) * min(1.4, unit.speed * 1.7)
        y += bob
        color = W95[unit.side.lower()]
        outline = "#ffff55" if selected else "#e8e8e8"

        c.create_oval(x - radius * .95 + 3, y - radius * .48 + 5, x + radius * .95 + 3, y + radius * .52 + 5, fill="#111811", outline="", stipple="gray50", tags="frame")
        if selected:
            pulse = radius + 5 + math.sin(self.anim_time * 5) * 2
            for sx, sy in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
                c.create_line(x + sx * pulse, y + sy * pulse, x + sx * (pulse - 6), y + sy * pulse, fill="#ffff55", width=2, tags="frame")
                c.create_line(x + sx * pulse, y + sy * pulse, x + sx * pulse, y + sy * (pulse - 6), fill="#ffff55", width=2, tags="frame")

        if unit.unit_type == "Armour":
            hull = ((-radius * .95, -radius * .52), (radius * .78, -radius * .52), (radius, 0), (radius * .78, radius * .52), (-radius * .95, radius * .52))
            track_left = ((-radius, -radius * .66), (radius * .72, -radius * .66), (radius * .88, -radius * .48), (-radius, -radius * .48))
            track_right = ((-radius, radius * .48), (radius * .88, radius * .48), (radius * .72, radius * .66), (-radius, radius * .66))
            c.create_polygon(self._rotated_points(x, y, heading, track_left), fill="#1d221b", outline="#080808", tags="frame")
            c.create_polygon(self._rotated_points(x, y, heading, track_right), fill="#1d221b", outline="#080808", tags="frame")
            c.create_polygon(self._rotated_points(x, y, heading, hull), fill=color, outline=outline, width=2, tags="frame")
            c.create_oval(x - radius * .34, y - radius * .34, x + radius * .34, y + radius * .34, fill="#596347", outline="#141714", width=2, tags="frame")
            c.create_line(x, y, x + math.cos(heading) * radius * 1.55, y + math.sin(heading) * radius * 1.55, fill="#131613", width=4, tags="frame")
            c.create_line(x, y - 1, x + math.cos(heading) * radius * 1.55, y + math.sin(heading) * radius * 1.55 - 1, fill="#778369", width=1, tags="frame")
        else:
            c.create_oval(x - radius, y - radius, x + radius, y + radius, fill=color, outline=outline, width=2, tags="frame")
            c.create_arc(x - radius + 2, y - radius + 2, x + radius - 2, y + radius - 2, start=24, extent=150, style="arc", outline="#ffffff", width=1, tags="frame")
            if unit.unit_type == "Rifle":
                for ox, oy in ((-.30, -.10), (.16, -.26), (.28, .23)):
                    c.create_oval(x + ox * radius - 2, y + oy * radius - 2, x + ox * radius + 2, y + oy * radius + 2, fill="#f1dfbd", outline="#161616", tags="frame")
                c.create_line(x - radius * .42, y + radius * .35, x + radius * .45, y - radius * .36, fill="#2b1d12", width=2, tags="frame")
            elif unit.unit_type == "Support":
                c.create_line(x - radius * .48, y + radius * .12, x + radius * .48, y - radius * .12, fill="#101010", width=3, tags="frame")
                c.create_line(x, y, x - radius * .38, y + radius * .48, fill="#111111", width=2, tags="frame")
                c.create_line(x, y, x + radius * .38, y + radius * .48, fill="#111111", width=2, tags="frame")
            elif unit.unit_type == "Scout":
                c.create_polygon(x - radius * .55, y, x, y - radius * .42, x + radius * .55, y, x, y + radius * .42, fill="#d7ebff", outline="#111111", tags="frame")
                c.create_oval(x - 3, y - 3, x + 3, y + 3, fill="#141414", outline="", tags="frame")
            elif unit.unit_type == "Mortar":
                c.create_arc(x - radius * .48, y - radius * .18, x + radius * .48, y + radius * .58, start=20, extent=150, style="arc", outline="#161616", width=4, tags="frame")
                c.create_line(x, y + radius * .12, x - radius * .42, y + radius * .52, fill="#111111", width=2, tags="frame")
                c.create_line(x, y + radius * .12, x + radius * .42, y + radius * .52, fill="#111111", width=2, tags="frame")
            c.create_line(x, y, x + math.cos(heading) * radius * .92, y + math.sin(heading) * radius * .92, fill="#fff8a0", arrow="last", width=2, tags="frame")

        if unit.speed > .15:
            phase = int(self.anim_time * 8 + hash(unit.uid)) % 3
            for index in range(phase):
                dx = -math.cos(heading) * radius * (1.0 + index * .32)
                dy = -math.sin(heading) * radius * (1.0 + index * .32)
                dust = 2 + index * 2
                c.create_oval(x + dx - dust, y + dy - dust, x + dx + dust, y + dy + dust, fill="#9b8b68", outline="", stipple="gray50", tags="frame")

        if selected:
            label = f"{unit.name}  [{unit.order}]"
            label_y = y - radius - 13
            c.create_rectangle(x - radius * 1.45, label_y - 7, x + radius * 1.45, label_y + 7, fill="#101010", outline="#f0f0f0", tags="frame")
            c.create_text(x, label_y, text=label, fill="white", font=("MS Sans Serif", 7, "bold"), tags="frame")

        bar_width = radius * 2
        bar_y = y + radius + 4
        bars = ((unit.strength, "#28c83a"), (unit.morale / 100, "#4d9dff"), (unit.ammo / 100, "#f0c63b"))
        for index, (value, fill) in enumerate(bars):
            yy = bar_y + index * 4
            c.create_rectangle(x - radius, yy, x + radius, yy + 3, fill="#251f1f", outline="#080808", tags="frame")
            c.create_rectangle(x - radius + 1, yy + 1, x - radius + 1 + max(0, bar_width - 2) * clamp(value, 0, 1), yy + 2, fill=fill, outline="", tags="frame")

        if unit.suppression > 20:
            c.create_arc(x - radius - 4, y - radius - 4, x + radius + 4, y + radius + 4, start=90, extent=-360 * (unit.suppression / 100), style="arc", outline="#ff8c00", width=3, tags="frame")
        if self.sim.elapsed - unit.last_hit < .22:
            c.create_oval(x - radius - 3, y - radius - 3, x + radius + 3, y + radius + 3, outline="#ff382e", width=3, tags="frame")
        if self.sim.elapsed - unit.last_fire < .18:
            muzzle_x = x + math.cos(heading) * radius * 1.18
            muzzle_y = y + math.sin(heading) * radius * 1.18
            c.create_polygon(muzzle_x - 4, muzzle_y, muzzle_x, muzzle_y - 5, muzzle_x + 7, muzzle_y, muzzle_x, muzzle_y + 5, fill="#fff200", outline="#ff7b00", tags="frame")
        if selected and unit.target_x is not None and unit.target_y is not None:
            tx, ty = self._mx(unit.target_x, w, cw), (unit.target_y + .5) * ch
            c.create_line(x, y, tx, ty, fill="#ffff55", dash=(5, 4), arrow="last", width=2, tags="frame")

    def _draw_effects(self, c: tk.Canvas, w: float, cw: float, ch: float) -> None:
        for effect in self.sim.effects:
            if not self.sim.is_position_visible(effect.x1, effect.y1, self.sim.player_side) and not self.sim.is_position_visible(effect.x2, effect.y2, self.sim.player_side):
                continue
            x1, y1 = self._mx(effect.x1, w, cw), (effect.y1 + .5) * ch
            x2, y2 = self._mx(effect.x2, w, cw), (effect.y2 + .5) * ch
            progress = effect.progress
            if effect.kind == "tracer":
                end_x = x1 + (x2 - x1) * progress
                end_y = y1 + (y2 - y1) * progress
                c.create_line(x1, y1, end_x, end_y, fill="#ff7b1a", width=4, stipple="gray50", tags="frame")
                c.create_line(x1, y1, end_x, end_y, fill="#fff9a2", width=1, tags="frame")
                c.create_oval(end_x - 2, end_y - 2, end_x + 2, end_y + 2, fill="#ffffff", outline="#ff9a21", tags="frame")
            elif effect.kind == "shell":
                px = x1 + (x2 - x1) * progress
                py = y1 + (y2 - y1) * progress - math.sin(math.pi * progress) * max(18, abs(x2 - x1) * .12)
                c.create_oval(px - 2, py + 4, px + 4, py + 7, fill="#1a1a1a", outline="", stipple="gray50", tags="frame")
                c.create_oval(px - 4, py - 4, px + 4, py + 4, fill="#252525", outline="#ff9b32", tags="frame")
                c.create_line(px - 7, py - 8, px - 1, py - 2, fill="#d4d4d4", stipple="gray50", width=2, tags="frame")
            else:
                peak = math.sin(math.pi * min(1.0, progress))
                radius = (8 + 24 * peak) * (1 if effect.kind == "impact" else 1.55)
                if progress < .42:
                    c.create_oval(x1 - radius, y1 - radius, x1 + radius, y1 + radius, fill="#ff8d24", outline="#fff075", width=2, stipple="gray50", tags="frame")
                    c.create_oval(x1 - radius * .42, y1 - radius * .42, x1 + radius * .42, y1 + radius * .42, fill="#fffbd0", outline="", tags="frame")
                    for angle in range(0, 360, 45):
                        radians = math.radians(angle + int(progress * 90))
                        c.create_line(x1 + math.cos(radians) * radius * .35, y1 + math.sin(radians) * radius * .35, x1 + math.cos(radians) * radius * 1.25, y1 + math.sin(radians) * radius * 1.25, fill="#ffbd3b", width=2, tags="frame")
                else:
                    smoke = max(5, radius * .66)
                    for index, (ox, oy) in enumerate(((-.35, .1), (.15, -.25), (.45, .15), (0, .35))):
                        puff = smoke * (1 - index * .08)
                        c.create_oval(x1 + ox * smoke - puff, y1 + oy * smoke - puff, x1 + ox * smoke + puff, y1 + oy * smoke + puff, fill="#3c3c3c" if index % 2 else "#555555", outline="#252525", stipple="gray50", tags="frame")

    def _draw_weather(self, c: tk.Canvas, w: float, h: float) -> None:
        if self.sim.weather == "Light rain":
            offset = int(self.anim_time * 180) % 36
            for index in range(0, int(w), 48):
                x = (index + offset) % int(max(1, w))
                for row in range(3):
                    y = (row * h / 3 + index * .7 + offset * 2) % h
                    c.create_line(x, y, x - 7, y + 15, fill="#a7bed0", stipple="gray50", tags="frame")
        elif self.sim.weather == "Low cloud":
            c.create_rectangle(0, 0, w, h, fill="#343b38", stipple="gray75", outline="", tags="frame")
        elif self.sim.weather == "Clearing":
            glow = 12 + math.sin(self.anim_time * .4) * 3
            c.create_oval(w - 70 - glow, 12 - glow, w - 70 + glow, 12 + glow, fill="#efe3a6", outline="", stipple="gray50", tags="frame")
