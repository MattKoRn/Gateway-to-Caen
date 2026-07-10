"""Richer terrain and obstacle rendering for campaign maps."""
from __future__ import annotations

import math
import tkinter as tk

from .ui import TERRAIN


class MapVisualMixin:
    def _draw_terrain_tile(self, c: tk.Canvas, x: int, y: int, terrain: str, w: float, h: float, cw: float, ch: float) -> None:
        x1, y1, x2, y2 = self._tile_rect(x, y, w, h, cw, ch)
        seed = (x * 92821 + y * 68917 + self.sim.seed * 13) & 0xFFFF
        palette = {"open": ("#82975d", "#6f874e", "#a6ad6a"), "road": ("#9b9075", "#6e6450", "#c7baa0"), "woods": ("#284f2c", "#17351d", "#426b3e"), "hedge": ("#526d3b", "#263e24", "#75905c"), "village": ("#826f61", "#4c3e35", "#b49a80"), "mud": ("#6e6247", "#4c4435", "#8f805c")}
        base, dark, light = palette.get(terrain, (TERRAIN.get(terrain, "#777777"), "#333333", "#aaaaaa"))
        c.create_rectangle(x1, y1, x2 + 1, y2 + 1, fill=base, outline="", tags="terrain")
        c.create_line(x1, y1 + 1, x2, y1 + 1, fill=light, stipple="gray75", tags="terrain")
        c.create_line(x1 + 1, y1, x1 + 1, y2, fill=light, stipple="gray75", tags="terrain")
        c.create_line(x1, y2 - 1, x2, y2 - 1, fill=dark, stipple="gray75", tags="terrain")
        if terrain == "open":
            for index in range(3):
                yy = y1 + ch * (0.22 + index * 0.27) + ((seed >> index) % 5)
                c.create_line(x1 + 2, yy, x2 - 2, yy - ch * 0.07, fill=dark if index % 2 else light, stipple="gray75", tags="terrain")
            if seed % 6 == 0:
                for index in range(4):
                    px = x1 + cw * (0.18 + index * 0.18); py = y1 + ch * (0.38 + ((seed >> index) & 3) * 0.08)
                    c.create_line(px, py, px + cw * 0.04, py - ch * 0.12, fill="#d8c15f", tags="terrain")
        elif terrain == "road":
            c.create_line(x1, y1 + ch * 0.34, x2, y1 + ch * 0.34, fill=light, width=max(1, int(ch * 0.06)), tags="terrain")
            c.create_line(x1, y1 + ch * 0.70, x2, y1 + ch * 0.70, fill=dark, width=max(1, int(ch * 0.07)), tags="terrain")
            for index in range(3):
                px = x1 + cw * (0.16 + index * 0.31); c.create_line(px, y1 + ch * 0.12, px + cw * 0.18, y2 - ch * 0.12, fill="#7c725d", dash=(3, 3), tags="terrain")
        elif terrain == "woods":
            for index, (ox, oy) in enumerate(((.18,.25),(.42,.18),(.68,.29),(.80,.60),(.50,.62),(.25,.70))):
                radius = min(cw, ch) * (0.10 + ((seed >> index) & 1) * 0.025); px, py = x1 + cw * ox, y1 + ch * oy
                c.create_oval(px-radius+3,py-radius+4,px+radius+3,py+radius+4,fill="#0c1f11",outline="",stipple="gray50",tags="terrain")
                c.create_line(px, py, px, py + ch * .18, fill="#4d3823", width=max(1,int(cw*.04)), tags="terrain")
                c.create_oval(px-radius,py-radius,px+radius,py+radius,fill="#1c4324" if index%2 else "#315d32",outline="#102c17",tags="terrain")
        elif terrain == "hedge":
            c.create_line(x1, y1 + ch*.58 + 3, x2, y1 + ch*.58 + 3, fill="#152018", width=max(3,int(ch*.17)), tags="terrain")
            for index in range(7):
                px=x1+cw*(.04+index*.15); c.create_oval(px-cw*.08,y1+ch*.39,px+cw*.08,y1+ch*.66,fill="#365a32" if index%2 else "#496f3e",outline="#203d24",tags="terrain")
        elif terrain == "village":
            c.create_line(x1, y1+ch*.78, x2, y1+ch*.78, fill="#a89b87", width=max(2,int(ch*.11)), tags="terrain")
            for index,(ax,ay,bx,by) in enumerate(((.08,.20,.42,.66),(.54,.26,.90,.72))):
                c.create_rectangle(x1+cw*ax+3,y1+ch*ay+4,x1+cw*bx+3,y1+ch*by+4,fill="#332a25",outline="",tags="terrain")
                c.create_rectangle(x1+cw*ax,y1+ch*ay,x1+cw*bx,y1+ch*by,fill="#b99e80" if index else "#9e846c",outline="#4b382d",tags="terrain")
                c.create_polygon(x1+cw*(ax-.04),y1+ch*ay,x1+cw*((ax+bx)/2),y1+ch*(ay-.16),x1+cw*(bx+.04),y1+ch*ay,fill="#743e32",outline="#38231e",tags="terrain")
                c.create_rectangle(x1+cw*(ax+.08),y1+ch*(ay+.18),x1+cw*(ax+.16),y1+ch*by,fill="#3a3029",outline="",tags="terrain")
                c.create_rectangle(x1+cw*(bx-.13),y1+ch*(ay+.16),x1+cw*(bx-.06),y1+ch*(ay+.28),fill="#9fd0e4",outline="#3f4a4f",tags="terrain")
        elif terrain == "mud":
            for index in range(3):
                ox=.10+((seed>>(index*2))%6)*.12; oy=.18+((seed>>(index*3+1))%5)*.13
                c.create_oval(x1+cw*ox,y1+ch*oy,x1+cw*min(.95,ox+.27),y1+ch*min(.92,oy+.13),fill="#4d4938",outline="#94835e",tags="terrain")
            c.create_line(x1+cw*.05,y1+ch*.18,x2-cw*.05,y2-ch*.12,fill="#463f31",dash=(4,3),tags="terrain")

    def _draw_obstacle(self, c: tk.Canvas, obstacle, w: float, h: float, cw: float, ch: float) -> None:
        px = self._mx(obstacle.x, w, cw); py = self._my(obstacle.y, h, ch) if hasattr(self, "_my") else obstacle.y * ch
        scale = min(cw, ch); radius = max(3, obstacle.radius * scale); length = max(radius * 2, obstacle.length * scale)
        angle = math.pi - obstacle.angle if self.sim.player_side == "Axis" else obstacle.angle
        dx, dy = math.cos(angle) * length / 2, math.sin(angle) * length / 2; kind = obstacle.kind
        c.create_line(px-dx+3,py-dy+4,px+dx+3,py+dy+4,fill="#0b0e0b",width=max(3,int(radius*1.4)),stipple="gray50",tags="terrain")
        if kind in ("stone_wall", "roadblock"):
            color="#8e8879" if kind=="stone_wall" else "#5d4d3b"
            c.create_line(px-dx,py-dy,px+dx,py+dy,fill="#2b2925",width=max(4,int(radius*1.8)),tags="terrain"); c.create_line(px-dx,py-dy-1,px+dx,py+dy-1,fill=color,width=max(2,int(radius*1.15)),tags="terrain")
            for t in (.2,.4,.6,.8):
                bx=px-dx+2*dx*t; by=py-dy+2*dy*t; c.create_oval(bx-2,by-2,bx+2,by+2,fill="#c1b8a5",outline="",tags="terrain")
        elif kind == "anti_tank":
            for t in (.25,.5,.75):
                bx=px-dx+2*dx*t; by=py-dy+2*dy*t; rr=max(4,radius*.75)
                c.create_line(bx-rr,by-rr,bx+rr,by+rr,fill="#5c625e",width=3,tags="terrain"); c.create_line(bx-rr,by+rr,bx+rr,by-rr,fill="#9da39f",width=2,tags="terrain")
        elif kind == "bunker":
            c.create_oval(px-radius-2,py-radius*.7+4,px+radius+2,py+radius*.7+7,fill="#151a14",outline="",stipple="gray50",tags="terrain")
            c.create_rectangle(px-radius,py-radius*.58,px+radius,py+radius*.58,fill="#6b6d60",outline="#20231e",width=2,tags="terrain")
            c.create_rectangle(px-radius*.55,py-radius*.12,px+radius*.55,py+radius*.12,fill="#171a17",outline="#a2a497",tags="terrain")
            c.create_polygon(px-radius,py-radius*.58,px-radius*.65,py-radius,px+radius*.65,py-radius,px+radius,py-radius*.58,fill="#75806a",outline="#252b22",tags="terrain")
        elif kind == "tree_cluster":
            for ox,oy,rr in ((-.45,.15,.58),(.12,-.28,.67),(.50,.18,.52),(-.05,.45,.50)):
                r=radius*rr; tx=px+ox*radius; ty=py+oy*radius
                c.create_oval(tx-r+3,ty-r+4,tx+r+3,ty+r+4,fill="#101c12",outline="",tags="terrain"); c.create_oval(tx-r,ty-r,tx+r,ty+r,fill="#28512e",outline="#17351e",tags="terrain")
        elif kind in ("wreck", "burning_wreck"):
            c.create_polygon(px-dx,py-dy-radius*.45,px+dx,py+dy-radius*.45,px+dx+radius*.35,py+dy+radius*.40,px-dx-radius*.35,py-dy+radius*.40,fill="#343a30",outline="#11140f",width=2,tags="terrain")
            c.create_oval(px-radius*.35,py-radius*.35,px+radius*.35,py+radius*.35,fill="#20251f",outline="#6b6f61",tags="terrain"); c.create_line(px,py,px+math.cos(angle)*radius*1.4,py+math.sin(angle)*radius*1.4,fill="#151713",width=3,tags="terrain")
        elif kind == "crater":
            c.create_oval(px-radius,py-radius*.58,px+radius,py+radius*.58,fill="#3a352a",outline="#87785a",width=2,tags="terrain"); c.create_oval(px-radius*.58,py-radius*.30,px+radius*.58,py+radius*.30,fill="#1d1b17",outline="",tags="terrain")
        else:
            c.create_oval(px-radius,py-radius,px+radius,py+radius,fill="#554d40",outline="#211e19",tags="terrain")
