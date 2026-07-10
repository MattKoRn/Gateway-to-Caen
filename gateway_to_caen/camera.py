"""Smooth tactical auto-camera, viewport transforms, and manual camera controls."""
from __future__ import annotations

import math
import time
import tkinter as tk
from dataclasses import dataclass
from typing import Iterable

from .simulation import MAP_HEIGHT, MAP_WIDTH, BattleSimulation, Unit, clamp, distance
from .ui import W95


@dataclass
class CameraFocus:
    """A desired camera composition in map coordinates."""

    x: float
    y: float
    zoom: float
    label: str


class TacticalCamera:
    """Selects action targets and eases a viewport toward them."""

    MIN_ZOOM = 1.0
    MAX_ZOOM = 2.85

    def __init__(self, enabled: bool = True) -> None:
        self.enabled = bool(enabled)
        self.x = MAP_WIDTH / 2
        self.y = MAP_HEIGHT / 2
        self.zoom = 1.0
        self.target_x = self.x
        self.target_y = self.y
        self.target_zoom = self.zoom
        self.focus_label = "Operational overview"
        self._decision_elapsed = 999.0
        self._cycle_index = 0
        self._last_cycle_time = 0.0

    def reset(self, keep_enabled: bool = True) -> None:
        enabled = self.enabled if keep_enabled else True
        self.__init__(enabled=enabled)

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = bool(enabled)
        if self.enabled:
            self._decision_elapsed = 999.0
        else:
            self.focus_label = "Manual camera"

    def overview(self) -> None:
        self.x = self.target_x = MAP_WIDTH / 2
        self.y = self.target_y = MAP_HEIGHT / 2
        self.zoom = self.target_zoom = 1.0
        self.focus_label = "Operational overview"

    def manual_zoom(self, amount: float) -> None:
        self.set_enabled(False)
        self.target_zoom = clamp(self.target_zoom + amount, self.MIN_ZOOM, self.MAX_ZOOM)
        self.zoom = self.target_zoom

    def manual_pan(self, dx_world: float, dy_world: float) -> None:
        self.set_enabled(False)
        self.x += dx_world
        self.y += dy_world
        self.target_x, self.target_y = self.x, self.y
        self._clamp_position()

    def focus_units(self, units: Iterable[Unit], label: str = "Selected units") -> None:
        living = [unit for unit in units if unit.alive]
        if not living:
            return
        focus = self._fit_units(living, label, single_zoom=2.55)
        self.target_x, self.target_y, self.target_zoom = focus.x, focus.y, focus.zoom
        self.focus_label = focus.label
        self._clamp_target()

    def update(self, sim: BattleSimulation, selected_ids: set[str], dt: float) -> bool:
        """Update target selection and interpolation. Return whether the view changed."""
        old_state = (self.x, self.y, self.zoom)
        dt = clamp(dt, 0.0, 0.25)
        self._decision_elapsed += dt

        if self.enabled and self._decision_elapsed >= 0.28:
            self._decision_elapsed = 0.0
            focus = self._choose_focus(sim, selected_ids)
            self.target_x, self.target_y, self.target_zoom = focus.x, focus.y, focus.zoom
            self.focus_label = focus.label
            self._clamp_target()

        if self.enabled:
            pan_alpha = 1.0 - math.exp(-3.8 * dt)
            zoom_alpha = 1.0 - math.exp(-2.8 * dt)
            self.x += (self.target_x - self.x) * pan_alpha
            self.y += (self.target_y - self.y) * pan_alpha
            self.zoom += (self.target_zoom - self.zoom) * zoom_alpha
            self._clamp_position()

        return any(abs(a - b) > 1e-5 for a, b in zip(old_state, (self.x, self.y, self.zoom)))

    def _choose_focus(self, sim: BattleSimulation, selected_ids: set[str]) -> CameraFocus:
        if sim.battle_over:
            return CameraFocus(MAP_WIDTH / 2, MAP_HEIGHT / 2, 1.0, "After-action overview")

        selected = [sim.unit_by_id(uid) for uid in selected_ids]
        selected = [unit for unit in selected if unit and unit.alive and unit.side == sim.player_side]
        if selected:
            return self._fit_units(selected, "Selected formation", single_zoom=2.65)

        visible_enemy_ids = {unit.uid for unit in sim.visible_enemy_units(sim.player_side)}
        recent_units = [
            unit
            for unit in sim.living_units()
            if (unit.side == sim.player_side or unit.uid in visible_enemy_ids)
            and (sim.elapsed - unit.last_fire <= 2.8 or sim.elapsed - unit.last_hit <= 3.4)
        ]
        if recent_units:
            expanded = list(recent_units)
            for unit in recent_units:
                enemy = sim.nearest_enemy(unit)
                if enemy and (enemy.side == sim.player_side or enemy.uid in visible_enemy_ids):
                    if distance((unit.x, unit.y), (enemy.x, enemy.y)) <= 8.5:
                        expanded.append(enemy)
            return self._fit_units(self._unique_units(expanded), "Active firefight", single_zoom=2.5)

        visible_effects = [
            effect
            for effect in sim.effects
            if sim.is_position_visible(effect.x1, effect.y1, sim.player_side)
            or sim.is_position_visible(effect.x2, effect.y2, sim.player_side)
        ]
        if visible_effects:
            effect = max(visible_effects, key=lambda item: (item.kind in ("impact", "blast"), item.ttl))
            return CameraFocus(
                clamp((effect.x1 + effect.x2) / 2, 0, MAP_WIDTH - 1),
                clamp((effect.y1 + effect.y2) / 2, 0, MAP_HEIGHT - 1),
                2.35,
                "Incoming fire",
            )

        active_friendlies = [
            unit
            for unit in sim.living_units(sim.player_side)
            if unit.speed > 0.12 or unit.order in ("Advance", "Assault", "Flank", "Retreat")
        ]
        if active_friendlies:
            scored = sorted(
                active_friendlies,
                key=lambda unit: (
                    (3.0 if unit.order == "Assault" else 0.0)
                    + unit.speed * 2.0
                    + unit.suppression / 45.0
                    + (1.0 if unit.unit_type in ("Scout", "Armour") else 0.0)
                ),
                reverse=True,
            )
            lead = scored[: min(3, len(scored))]
            return self._fit_units(lead, "Advancing formation", single_zoom=2.25)

        contested = []
        for point in sim.control_points:
            friendly = any(distance((unit.x, unit.y), (point.x, point.y)) <= 3.0 for unit in sim.living_units(sim.player_side))
            enemy = any(
                distance((unit.x, unit.y), (point.x, point.y)) <= 3.0
                for unit in sim.visible_enemy_units(sim.player_side)
            )
            if abs(point.capture) > 8 or (friendly and enemy):
                contested.append(point)
        if contested:
            point = max(contested, key=lambda item: abs(item.capture))
            return CameraFocus(point.x + 0.5, point.y + 0.5, 1.85, f"Objective: {point.name}")

        friendlies = sim.living_units(sim.player_side)
        if friendlies:
            if sim.elapsed - self._last_cycle_time >= 5.0:
                self._cycle_index = (self._cycle_index + 1) % len(friendlies)
                self._last_cycle_time = sim.elapsed
            unit = friendlies[self._cycle_index % len(friendlies)]
            return CameraFocus(unit.x, unit.y, 1.75, f"Unit watch: {unit.name}")

        return CameraFocus(MAP_WIDTH / 2, MAP_HEIGHT / 2, 1.0, "Operational overview")

    @staticmethod
    def _unique_units(units: Iterable[Unit]) -> list[Unit]:
        unique: dict[str, Unit] = {}
        for unit in units:
            unique[unit.uid] = unit
        return list(unique.values())

    def _fit_units(self, units: list[Unit], label: str, single_zoom: float) -> CameraFocus:
        xs = [unit.x for unit in units]
        ys = [unit.y for unit in units]
        center_x = sum(xs) / len(xs)
        center_y = sum(ys) / len(ys)
        if len(units) == 1:
            zoom = single_zoom
        else:
            span_x = max(xs) - min(xs) + 2.8
            span_y = max(ys) - min(ys) + 2.4
            zoom = min(MAP_WIDTH * 0.68 / max(span_x, 0.1), MAP_HEIGHT * 0.68 / max(span_y, 0.1))
            zoom = clamp(zoom, 1.25, 2.55)
        return CameraFocus(center_x, center_y, zoom, label)

    def _clamp_target(self) -> None:
        self.target_zoom = clamp(self.target_zoom, self.MIN_ZOOM, self.MAX_ZOOM)
        half_w = MAP_WIDTH / (2 * self.target_zoom)
        half_h = MAP_HEIGHT / (2 * self.target_zoom)
        self.target_x = clamp(self.target_x, half_w, MAP_WIDTH - half_w)
        self.target_y = clamp(self.target_y, half_h, MAP_HEIGHT - half_h)

    def _clamp_position(self) -> None:
        self.zoom = clamp(self.zoom, self.MIN_ZOOM, self.MAX_ZOOM)
        half_w = MAP_WIDTH / (2 * self.zoom)
        half_h = MAP_HEIGHT / (2 * self.zoom)
        self.x = clamp(self.x, half_w, MAP_WIDTH - half_w)
        self.y = clamp(self.y, half_h, MAP_HEIGHT - half_h)


class AutoCameraMixin:
    """Adds camera transforms, action tracking, controls, and a camera HUD."""

    camera: TacticalCamera

    def _camera_init(self, enabled: bool) -> None:
        self.camera = TacticalCamera(enabled=enabled)
        self._camera_last_frame = time.perf_counter()
        self._rendered_camera_state: tuple[float, float, float, int, int, str] | None = None
        self._pan_anchor: tuple[int, int, float, float] | None = None

    def _camera_bindings(self) -> None:
        self.canvas.bind("<MouseWheel>", self._camera_mousewheel, add="+")
        self.canvas.bind("<Button-4>", lambda event: self._camera_zoom_step(0.18), add="+")
        self.canvas.bind("<Button-5>", lambda event: self._camera_zoom_step(-0.18), add="+")
        self.canvas.bind("<ButtonPress-2>", self._camera_pan_start, add="+")
        self.canvas.bind("<B2-Motion>", self._camera_pan_drag, add="+")
        self.canvas.bind("<Double-Button-1>", lambda event: self.focus_selected(), add="+")
        self.root.bind("<Key-c>", lambda _event: self.toggle_auto_camera())
        self.root.bind("<Key-f>", lambda _event: self.focus_selected())
        self.root.bind("<Key-plus>", lambda _event: self._camera_zoom_step(0.18))
        self.root.bind("<Key-minus>", lambda _event: self._camera_zoom_step(-0.18))

    def toggle_auto_camera(self) -> None:
        enabled = bool(self.auto_camera_var.get()) if hasattr(self, "auto_camera_var") else not self.camera.enabled
        self.camera.set_enabled(enabled)
        self.settings["auto_camera"] = enabled
        self._save_camera_setting()
        if hasattr(self, "camera_status"):
            self.camera_status.configure(text="Auto camera enabled" if enabled else "Manual camera enabled")

    def focus_selected(self) -> None:
        units = [self.sim.unit_by_id(uid) for uid in self.selected]
        units = [unit for unit in units if unit and unit.alive]
        if units:
            self.camera.set_enabled(True)
            if hasattr(self, "auto_camera_var"):
                self.auto_camera_var.set(True)
            self.camera.focus_units(units)
            self.settings["auto_camera"] = True
            self._save_camera_setting()
        else:
            self.camera._decision_elapsed = 999.0
            self.camera.set_enabled(True)
            if hasattr(self, "auto_camera_var"):
                self.auto_camera_var.set(True)

    def camera_overview(self) -> None:
        self.camera.set_enabled(False)
        self.camera.overview()
        if hasattr(self, "auto_camera_var"):
            self.auto_camera_var.set(False)
        self.settings["auto_camera"] = False
        self._save_camera_setting()
        self.terrain_signature = None
        self.fog_signature = None

    def _camera_zoom_step(self, amount: float) -> None:
        self.camera.manual_zoom(amount)
        if hasattr(self, "auto_camera_var"):
            self.auto_camera_var.set(False)
        self.settings["auto_camera"] = False
        self._save_camera_setting()
        self.terrain_signature = None
        self.fog_signature = None

    def _camera_mousewheel(self, event: tk.Event) -> str:
        self._camera_zoom_step(0.18 if event.delta > 0 else -0.18)
        return "break"

    def _camera_pan_start(self, event: tk.Event) -> None:
        self._pan_anchor = (event.x, event.y, self.camera.x, self.camera.y)
        self.camera.set_enabled(False)
        if hasattr(self, "auto_camera_var"):
            self.auto_camera_var.set(False)

    def _camera_pan_drag(self, event: tk.Event) -> None:
        if not self._pan_anchor:
            return
        start_x, start_y, camera_x, camera_y = self._pan_anchor
        w, h = max(1, self.canvas.winfo_width()), max(1, self.canvas.winfo_height())
        cw, ch = self._camera_cell_sizes(w, h)
        orientation = -1.0 if self.sim.player_side == "Axis" else 1.0
        self.camera.x = camera_x - orientation * (event.x - start_x) / max(cw, 0.001)
        self.camera.y = camera_y - (event.y - start_y) / max(ch, 0.001)
        self.camera.target_x, self.camera.target_y = self.camera.x, self.camera.y
        self.camera._clamp_position()
        self.camera.target_x, self.camera.target_y = self.camera.x, self.camera.y
        self.settings["auto_camera"] = False
        self._save_camera_setting()

    def _save_camera_setting(self) -> None:
        try:
            from .persistence import atomic_write_json

            atomic_write_json(self.settings_path, self.settings)
        except (OSError, AttributeError):
            pass

    def _camera_cell_sizes(self, w: float, h: float) -> tuple[float, float]:
        return w / MAP_WIDTH * self.camera.zoom, h / MAP_HEIGHT * self.camera.zoom

    def _mx(self, x: float, width: float, cell: float, center: bool = True) -> float:
        world_x = x + (0.5 if center else 0.0)
        orientation = -1.0 if self.sim.player_side == "Axis" else 1.0
        return width / 2 + orientation * (world_x - self.camera.x) * cell

    def _my(self, y: float, height: float, cell: float, center: bool = True) -> float:
        world_y = y + (0.5 if center else 0.0)
        return height / 2 + (world_y - self.camera.y) * cell

    def _tile_rect(self, x: int, y: int, w: float, h: float, cw: float, ch: float) -> tuple[float, float, float, float]:
        left = self._mx(x, w, cw, center=False)
        right = self._mx(x + 1, w, cw, center=False)
        top = self._my(y, h, ch, center=False)
        bottom = self._my(y + 1, h, ch, center=False)
        return min(left, right), min(top, bottom), max(left, right), max(top, bottom)

    def _from_canvas(self, event: tk.Event) -> tuple[float, float]:
        w, h = max(1, self.canvas.winfo_width()), max(1, self.canvas.winfo_height())
        cw, ch = self._camera_cell_sizes(w, h)
        orientation = -1.0 if self.sim.player_side == "Axis" else 1.0
        x = self.camera.x + orientation * (event.x - w / 2) / max(cw, 0.001)
        y = self.camera.y + (event.y - h / 2) / max(ch, 0.001)
        return clamp(x, 0, MAP_WIDTH - 0.001), clamp(y, 0, MAP_HEIGHT - 0.001)

    def draw(self) -> None:
        c = self.canvas
        w, h = max(1, c.winfo_width()), max(1, c.winfo_height())
        now = time.perf_counter()
        dt = min(0.25, now - self._camera_last_frame)
        self._camera_last_frame = now
        self.camera.update(self.sim, self.selected, dt)

        cw, ch = self._camera_cell_sizes(w, h)
        signature = (self.sim.seed, w, h, self.sim.player_side)
        current_state = (self.camera.x, self.camera.y, self.camera.zoom, w, h, self.sim.player_side)
        if signature != self.terrain_signature:
            c.delete("all")
            c.create_rectangle(0, 0, w, h, fill="#263326", outline="", tags="backdrop")
            self._draw_battlefield_background(c, w, h, cw, ch)
            self.terrain_signature = signature
            self.fog_signature = None
            self._rendered_camera_state = current_state
        else:
            self._transform_cached_layers(c, current_state)

        visible = self.sim.current_visible_tiles(self.sim.player_side)
        explored = self.sim.explored_tiles[self.sim.player_side]
        fog_signature = (self.sim.seed, self.sim.player_side, frozenset(visible), frozenset(explored))
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

        self._draw_camera_hud(c, w, h)
        c.create_rectangle(1, 1, w - 2, h - 2, outline="#101510", width=3, tags="frame")
        if self.sim.battle_over:
            self._draw_battle_overlay(c, w, h)

    def _transform_cached_layers(self, c: tk.Canvas, current: tuple[float, float, float, int, int, str]) -> None:
        old = self._rendered_camera_state
        if old is None or old[3:] != current[3:]:
            self.terrain_signature = None
            return
        old_x, old_y, old_zoom, w, h, _side = old
        new_x, new_y, new_zoom, *_ = current
        if max(abs(old_x - new_x), abs(old_y - new_y), abs(old_zoom - new_zoom)) < 1e-5:
            return
        ratio = new_zoom / max(old_zoom, 0.001)
        for tag in ("terrain", "fog"):
            c.scale(tag, w / 2, h / 2, ratio, ratio)
        orientation = -1.0 if self.sim.player_side == "Axis" else 1.0
        dx = orientation * (old_x - new_x) * (w / MAP_WIDTH) * new_zoom
        dy = (old_y - new_y) * (h / MAP_HEIGHT) * new_zoom
        for tag in ("terrain", "fog"):
            c.move(tag, dx, dy)
        self._rendered_camera_state = current

    def _draw_battlefield_background(self, c: tk.Canvas, w: float, h: float, cw: float, ch: float) -> None:
        for y, row in enumerate(self.sim.terrain):
            for x, terrain in enumerate(row):
                self._draw_terrain_tile(c, x, y, terrain, w, h, cw, ch)
        for x in range(MAP_WIDTH + 1):
            px = self._mx(x, w, cw, center=False)
            c.create_line(px, self._my(0, h, ch, center=False), px, self._my(MAP_HEIGHT, h, ch, center=False), fill="#192119", stipple="gray75", tags="terrain")
        for y in range(MAP_HEIGHT + 1):
            py = self._my(y, h, ch, center=False)
            c.create_line(self._mx(0, w, cw, center=False), py, self._mx(MAP_WIDTH, w, cw, center=False), py, fill="#192119", stipple="gray75", tags="terrain")
        top = self._my(0, h, ch, center=False) + 8
        for x in range(0, MAP_WIDTH, 2):
            c.create_text(self._mx(x, w, cw), top, text=f"{x:02d}", fill="#d7dfd0", font=("Courier New", 6, "bold"), tags="terrain")

    def _draw_camera_hud(self, c: tk.Canvas, w: float, h: float) -> None:
        mode = "AUTO CAMERA" if self.camera.enabled else "MANUAL CAMERA"
        label = f"{mode}  |  {self.camera.focus_label}  |  {self.camera.zoom:.2f}x"
        c.create_rectangle(8, 8, min(w - 8, 390), 31, fill="#101510", outline="#d6d6d6", tags="frame")
        c.create_rectangle(10, 10, 92, 29, fill=W95["navy"] if self.camera.enabled else "#555555", outline="", tags="frame")
        c.create_text(51, 19, text="AUTO CAM" if self.camera.enabled else "MANUAL", fill="white", font=("MS Sans Serif", 8, "bold"), tags="frame")
        c.create_text(99, 19, text=label.split("|", 1)[1].strip(), anchor="w", fill="#f0f0f0", font=("MS Sans Serif", 8, "bold"), tags="frame")

    def _draw_battle_overlay(self, c: tk.Canvas, w: float, h: float) -> None:
        remain = math.ceil(self.sim.seconds_until_next_battle)
        c.create_rectangle(w * .20 + 4, h * .36 + 4, w * .80 + 4, h * .64 + 4, fill="#202020", outline="", tags="frame")
        c.create_rectangle(w * .20, h * .36, w * .80, h * .64, fill=W95["face"], outline="white", width=3, tags="frame")
        c.create_rectangle(w * .205, h * .37, w * .795, h * .405, fill=W95["navy"], outline="", tags="frame")
        c.create_text(w / 2, h * .388, text="AFTER ACTION REPORT", fill="white", font=("MS Sans Serif", 10, "bold"), tags="frame")
        c.create_text(w / 2, h * .47, text="BATTLE CONCLUDED", font=("MS Sans Serif", 18, "bold"), tags="frame")
        c.create_text(w / 2, h * .55, text=f"{self.sim.winner} victory", fill=W95["navy"], font=("MS Sans Serif", 14, "bold"), tags="frame")
        c.create_text(w / 2, h * .60, text=f"Next map in {remain} second{'s' if remain != 1 else ''}", font=("MS Sans Serif", 10, "bold"), tags="frame")
