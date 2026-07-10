"""Cached terrain, fog, objective, and map-frame rendering."""
from __future__ import annotations

import math
import tkinter as tk

from .simulation import MAP_HEIGHT, MAP_WIDTH
from .ui import TERRAIN, W95


class TerrainGraphicsMixin:
    def draw(self) -> None:
        c = self.canvas
        w, h = max(1, c.winfo_width()), max(1, c.winfo_height())
        cw, ch = w / MAP_WIDTH, h / MAP_HEIGHT
        signature = (self.sim.seed, w, h, self.sim.player_side)
        if signature != self.terrain_signature:
            c.delete("all")
            self._draw_battlefield_background(c, w, h, cw, ch)
            self.terrain_signature = signature
            self.fog_signature = None

        visible = self.sim.current_visible_tiles(self.sim.player_side)
        explored = self.sim.explored_tiles[self.sim.player_side]
        fog_signature = (
            self.sim.seed,
            self.sim.player_side,
            frozenset(visible),
            frozenset(explored),
            w,
            h,
        )
        if fog_signature != self.fog_signature:
            c.delete("fog")
            self._draw_fog(c, w, h, cw, ch, visible, explored)
            self.fog_signature = fog_signature

        c.delete("frame")
        self._draw_objectives(c, w, cw, ch, visible, explored)
        for unit in self.sim.living_units():
            if unit.side != self.sim.player_side and not self.sim.is_unit_visible(unit, self.sim.player_side):
                continue
            self._draw_unit(c, unit, w, h, cw, ch)
        self._draw_effects(c, w, cw, ch)
        self._draw_weather(c, w, h)

        if self.hover:
            x, y = self.hover
            x1, y1, x2, y2 = self._tile_rect(x, y, w, h, cw, ch)
            c.create_rectangle(x1 + 1, y1 + 1, x2 - 1, y2 - 1, outline="#f8f8f8", width=2, tags="frame")
            c.create_line(x1, (y1 + y2) / 2, x2, (y1 + y2) / 2, fill="#ffffff", stipple="gray50", tags="frame")
            c.create_line((x1 + x2) / 2, y1, (x1 + x2) / 2, y2, fill="#ffffff", stipple="gray50", tags="frame")

        c.create_rectangle(1, 1, w - 2, h - 2, outline="#101510", width=3, tags="frame")
        if self.sim.battle_over:
            remain = math.ceil(self.sim.seconds_until_next_battle)
            c.create_rectangle(w * .20 + 4, h * .36 + 4, w * .80 + 4, h * .64 + 4, fill="#202020", outline="", tags="frame")
            c.create_rectangle(w * .20, h * .36, w * .80, h * .64, fill=W95["face"], outline="white", width=3, tags="frame")
            c.create_rectangle(w * .205, h * .37, w * .795, h * .405, fill=W95["navy"], outline="", tags="frame")
            c.create_text(w / 2, h * .388, text="AFTER ACTION REPORT", fill="white", font=("MS Sans Serif", 10, "bold"), tags="frame")
            c.create_text(w / 2, h * .47, text="BATTLE CONCLUDED", font=("MS Sans Serif", 18, "bold"), tags="frame")
            c.create_text(w / 2, h * .55, text=f"{self.sim.winner} victory", fill=W95["navy"], font=("MS Sans Serif", 14, "bold"), tags="frame")
            c.create_text(w / 2, h * .60, text=f"Next map in {remain} second{'s' if remain != 1 else ''}", font=("MS Sans Serif", 10, "bold"), tags="frame")

    def _draw_battlefield_background(self, c: tk.Canvas, w: float, h: float, cw: float, ch: float) -> None:
        c.create_rectangle(0, 0, w, h, fill="#263326", outline="", tags="terrain")
        for y, row in enumerate(self.sim.terrain):
            for x, terrain in enumerate(row):
                self._draw_terrain_tile(c, x, y, terrain, w, h, cw, ch)
        for x in range(MAP_WIDTH + 1):
            px = w - x * cw if self.sim.player_side == "Axis" else x * cw
            c.create_line(px, 0, px, h, fill="#192119", stipple="gray75", tags="terrain")
        for y in range(MAP_HEIGHT + 1):
            c.create_line(0, y * ch, w, y * ch, fill="#192119", stipple="gray75", tags="terrain")
        for x in range(0, MAP_WIDTH, 2):
            label_x = self._mx(x, w, cw)
            c.create_text(label_x, 8, text=f"{x:02d}", fill="#d7dfd0", font=("Courier New", 6, "bold"), tags="terrain")

    def _draw_terrain_tile(self, c: tk.Canvas, x: int, y: int, terrain: str, w: float, h: float, cw: float, ch: float) -> None:
        x1, y1, x2, y2 = self._tile_rect(x, y, w, h, cw, ch)
        seed = (x * 73 + y * 151 + self.sim.seed * 3) & 0xFFFF
        base = TERRAIN.get(terrain, "#777777")
        c.create_rectangle(x1, y1, x2 + 1, y2 + 1, fill=base, outline="", tags="terrain")

        if terrain == "open":
            shade = "#71894f" if seed % 2 else "#8aa064"
            for index in range(2):
                yy = y1 + ch * (.28 + index * .34)
                offset = ((seed >> (index + 1)) % 7) / 20 * ch
                c.create_line(x1 + 2, yy + offset, x2 - 2, yy + offset - ch * .09, fill=shade, width=1, tags="terrain")
            if seed % 5 == 0:
                c.create_oval(x1 + cw * .70, y1 + ch * .22, x1 + cw * .77, y1 + ch * .31, fill="#d1c76a", outline="", tags="terrain")
        elif terrain == "road":
            c.create_rectangle(x1, y1, x2, y2, fill="#8b8068", outline="", tags="terrain")
            c.create_line(x1, y1 + 2, x2, y1 + 2, fill="#615846", width=2, tags="terrain")
            c.create_line(x1, y2 - 2, x2, y2 - 2, fill="#d2c7a6", width=2, tags="terrain")
            c.create_line(x1 + cw * .12, y1 + ch * .42, x2 - cw * .12, y1 + ch * .42, fill="#a79c7f", width=1, tags="terrain")
            c.create_line(x1 + cw * .12, y1 + ch * .68, x2 - cw * .12, y1 + ch * .68, fill="#746a55", width=1, tags="terrain")
        elif terrain == "woods":
            c.create_rectangle(x1, y1, x2, y2, fill="#31562f", outline="", tags="terrain")
            trees = ((.22, .32), (.55, .24), (.78, .49), (.42, .68), (.70, .76))
            for index, (ox, oy) in enumerate(trees):
                scale = .10 + ((seed >> index) & 1) * .025
                c.create_oval(x1 + cw * (ox - scale) + 2, y1 + ch * (oy - scale) + 3, x1 + cw * (ox + scale) + 2, y1 + ch * (oy + scale) + 3, fill="#173217", outline="", tags="terrain")
                c.create_line(x1 + cw * ox, y1 + ch * oy, x1 + cw * ox, y1 + ch * (oy + .18), fill="#4c3824", width=max(1, int(cw * .035)), tags="terrain")
                c.create_oval(x1 + cw * (ox - scale), y1 + ch * (oy - scale), x1 + cw * (ox + scale), y1 + ch * (oy + scale), fill="#1f4722" if index % 2 else "#285529", outline="#143216", tags="terrain")
        elif terrain == "hedge":
            c.create_line(x1, y1 + ch * .61 + 2, x2, y1 + ch * .61 + 2, fill="#1c2919", width=max(3, int(ch * .15)), tags="terrain")
            c.create_line(x1, y1 + ch * .55, x2, y1 + ch * .55, fill="#294a26", width=max(3, int(ch * .16)), tags="terrain")
            for index in range(5):
                px = x1 + cw * (.08 + index * .21)
                c.create_oval(px - cw * .08, y1 + ch * .39, px + cw * .08, y1 + ch * .62, fill="#3d6634", outline="#244421", tags="terrain")
        elif terrain == "village":
            c.create_rectangle(x1, y1, x2, y2, fill="#77665a", outline="", tags="terrain")
            c.create_line(x1, y1 + ch * .76, x2, y1 + ch * .76, fill="#a0937f", width=max(2, int(ch * .12)), tags="terrain")
            houses = ((.12, .18, .42, .62), (.55, .28, .88, .72))
            for index, (ax, ay, bx, by) in enumerate(houses):
                c.create_rectangle(x1 + cw * ax + 2, y1 + ch * ay + 3, x1 + cw * bx + 2, y1 + ch * by + 3, fill="#342a25", outline="", tags="terrain")
                c.create_rectangle(x1 + cw * ax, y1 + ch * ay, x1 + cw * bx, y1 + ch * by, fill="#b39a7e" if index else "#9d846d", outline="#41342b", tags="terrain")
                c.create_polygon(x1 + cw * (ax - .04), y1 + ch * ay, x1 + cw * ((ax + bx) / 2), y1 + ch * (ay - .16), x1 + cw * (bx + .04), y1 + ch * ay, fill="#6e382f", outline="#35201d", tags="terrain")
                c.create_rectangle(x1 + cw * (ax + .10), y1 + ch * (ay + .18), x1 + cw * (ax + .17), y1 + ch * by, fill="#3f332b", outline="", tags="terrain")
        elif terrain == "mud":
            c.create_rectangle(x1, y1, x2, y2, fill="#6d6248", outline="", tags="terrain")
            for index in range(2):
                ox = .18 + ((seed >> index) % 5) * .13
                oy = .28 + ((seed >> (index + 3)) % 4) * .15
                c.create_oval(x1 + cw * ox, y1 + ch * oy, x1 + cw * min(.94, ox + .28), y1 + ch * min(.88, oy + .14), fill="#4f4a39", outline="#83765a", tags="terrain")
            c.create_line(x1 + cw * .10, y1 + ch * .18, x2 - cw * .10, y2 - ch * .12, fill="#4f4737", dash=(3, 3), tags="terrain")

    def _draw_fog(self, c: tk.Canvas, w: float, h: float, cw: float, ch: float, visible: set[tuple[int, int]], explored: set[tuple[int, int]]) -> None:
        for y in range(MAP_HEIGHT):
            for x in range(MAP_WIDTH):
                x1, y1, x2, y2 = self._tile_rect(x, y, w, h, cw, ch)
                if (x, y) not in explored:
                    c.create_rectangle(x1, y1, x2 + 1, y2 + 1, fill="#040604", outline="", tags="fog")
                    if (x * 3 + y * 5 + self.sim.seed) % 4 == 0:
                        c.create_line(x1, y2, x2, y1, fill="#0c100c", stipple="gray50", tags="fog")
                elif (x, y) not in visible:
                    c.create_rectangle(x1, y1, x2 + 1, y2 + 1, fill="#101710", stipple="gray50", outline="", tags="fog")
                elif any((x + dx, y + dy) not in visible for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))):
                    c.create_rectangle(x1 + 1, y1 + 1, x2 - 1, y2 - 1, outline="#3b4b3b", stipple="gray50", tags="fog")

    def _draw_objectives(self, c: tk.Canvas, w: float, cw: float, ch: float, visible: set[tuple[int, int]], explored: set[tuple[int, int]]) -> None:
        for point in self.sim.control_points:
            if (point.x, point.y) not in explored:
                continue
            px, py = self._mx(point.x, w, cw), (point.y + .5) * ch
            known = (point.x, point.y) in visible
            owner = point.owner if known else "Neutral"
            color = W95[owner.lower()] if owner in ("Allied", "Axis") else W95["neutral"]
            radius = max(8, min(cw, ch) * .36)
            c.create_oval(px - radius - 3, py - radius - 1, px + radius + 3, py + radius + 5, fill="#202020", outline="", stipple="gray50", tags="frame")
            c.create_polygon(px, py - radius, px + radius, py, px, py + radius, px - radius, py, fill="#fff25a" if known else "#85834b", outline=color, width=3, tags="frame")
            flag_x = px + radius * .9
            c.create_line(flag_x, py - radius * .9, flag_x, py + radius * .55, fill="#e9e9e9", width=2, tags="frame")
            c.create_polygon(flag_x, py - radius * .9, flag_x + radius * .75, py - radius * .58, flag_x, py - radius * .32, fill=color, outline="#111111", tags="frame")
            label = point.name if known else "Unknown objective"
            c.create_text(px + 1, py + radius + 10, text=label, fill="#111111", font=("MS Sans Serif", 7, "bold"), tags="frame")
            c.create_text(px, py + radius + 9, text=label, fill="#ffffff", font=("MS Sans Serif", 7, "bold"), tags="frame")
