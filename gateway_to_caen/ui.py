"""Windows 95 inspired Tkinter interface for Gateway to Caen: Tactical Command."""
from __future__ import annotations

import time
import tkinter as tk
from tkinter import messagebox, ttk

from .neural import ACTIONS, TacticalBrain
from .persistence import atomic_write_json, read_json, user_data_dir
from .simulation import MAP_HEIGHT, MAP_WIDTH, TERRAIN_COVER, BattleSimulation, clamp, distance

WIN95 = {"face": "#c0c0c0", "light": "#ffffff", "shadow": "#808080", "dark": "#000000", "navy": "#000080", "allied": "#244d9b", "axis": "#9a2828", "neutral": "#666666"}
TERRAIN_COLORS = {"open": "#83965d", "road": "#b5aa85", "woods": "#3e663b", "hedge": "#58733e", "village": "#8a7667", "mud": "#74684d"}


class TacticalCommandApp:
    TICK_MS = 100
    REFRESH_MS = 350
    GAME_SAVE_MS = 5_000
    BRAIN_SAVE_MS = 10_000

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        root.title("Gateway to Caen: Tactical Command")
        root.geometry("1280x820")
        root.minsize(1040, 690)
        root.configure(bg=WIN95["face"])
        self.data_dir = user_data_dir()
        self.brain_path = self.data_dir / "tactical_brain.json"
        self.save_path = self.data_dir / "autosave.json"
        self.settings_path = self.data_dir / "settings.json"
        self.brain = TacticalBrain.load_or_create(self.brain_path)
        self.sim = BattleSimulation(self.brain)
        self.settings = read_json(self.settings_path, {})
        self.speed = float(self.settings.get("speed", 1.0))
        self.paused = False
        self.running = True
        self.selected_ids: set[str] = set()
        self.hover_tile: tuple[int, int] | None = None
        self.last_tick = time.perf_counter()
        self.last_event_count = 0
        self.last_save_text = "Not yet saved"
        self._configure_style()
        self._build_menu()
        self._build_shell()
        self._load_game_if_available()
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        root.after(self.TICK_MS, self._game_loop)
        root.after(self.REFRESH_MS, self._refresh_loop)
        root.after(self.GAME_SAVE_MS, self._autosave_game)
        root.after(self.BRAIN_SAVE_MS, self._autosave_brain)

    def _configure_style(self) -> None:
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TFrame", background=WIN95["face"])
        style.configure("TLabel", background=WIN95["face"], foreground="#000000", font=("MS Sans Serif", 9))
        style.configure("TButton", background=WIN95["face"], foreground="#000000", font=("MS Sans Serif", 9), padding=(6, 3))
        style.map("TButton", background=[("active", "#d8d8d8"), ("pressed", "#a8a8a8")])
        style.configure("TCheckbutton", background=WIN95["face"], font=("MS Sans Serif", 9))
        style.configure("TNotebook", background=WIN95["face"], borderwidth=2)
        style.configure("TNotebook.Tab", background=WIN95["face"], font=("MS Sans Serif", 9), padding=(8, 4))
        style.map("TNotebook.Tab", background=[("selected", "#e0e0e0")])
        style.configure("Treeview", background="#ffffff", fieldbackground="#ffffff", foreground="#000000", rowheight=22, font=("MS Sans Serif", 9))
        style.configure("Treeview.Heading", background=WIN95["face"], foreground="#000000", font=("MS Sans Serif", 9, "bold"))
        style.configure("TCombobox", fieldbackground="#ffffff", background=WIN95["face"])

    def _build_menu(self) -> None:
        menu = tk.Menu(self.root, tearoff=False, bg=WIN95["face"], fg="#000000")
        file_menu = tk.Menu(menu, tearoff=False, bg=WIN95["face"])
        file_menu.add_command(label="New Battle", command=self.new_battle)
        file_menu.add_command(label="Save Now", command=self.save_game)
        file_menu.add_command(label="Load Autosave", command=self.load_game)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.on_close)
        menu.add_cascade(label="File", menu=file_menu)
        game_menu = tk.Menu(menu, tearoff=False, bg=WIN95["face"])
        game_menu.add_command(label="Pause / Resume", command=self.toggle_pause)
        game_menu.add_command(label="Allied Victory", command=lambda: self.sim.force_result("Allied"))
        game_menu.add_command(label="Axis Victory", command=lambda: self.sim.force_result("Axis"))
        menu.add_cascade(label="Game", menu=game_menu)
        view_menu = tk.Menu(menu, tearoff=False, bg=WIN95["face"])
        view_menu.add_command(label="Battlefield", command=lambda: self.main_tabs.select(self.battlefield_tab))
        view_menu.add_command(label="Neural Network", command=lambda: self.main_tabs.select(self.neural_tab))
        view_menu.add_command(label="War Diary", command=lambda: self.main_tabs.select(self.diary_tab))
        menu.add_cascade(label="View", menu=view_menu)
        help_menu = tk.Menu(menu, tearoff=False, bg=WIN95["face"])
        help_menu.add_command(label="Controls", command=self.show_controls)
        help_menu.add_command(label="About", command=self.show_about)
        menu.add_cascade(label="Help", menu=help_menu)
        self.root.config(menu=menu)

    def _build_shell(self) -> None:
        title = tk.Frame(self.root, bg=WIN95["navy"], bd=2, relief="raised", height=30)
        title.pack(fill="x", padx=3, pady=3)
        tk.Label(title, text="▣  GATEWAY TO CAEN — TACTICAL COMMAND", bg=WIN95["navy"], fg="#ffffff", font=("MS Sans Serif", 10, "bold"), anchor="w").pack(side="left", fill="x", expand=True, padx=5, pady=3)
        self.clock_label = tk.Label(title, text="00:00", bg=WIN95["navy"], fg="#ffffff", font=("MS Sans Serif", 9, "bold"))
        self.clock_label.pack(side="right", padx=7)
        self._build_toolbar()
        self.main_tabs = ttk.Notebook(self.root)
        self.main_tabs.pack(fill="both", expand=True, padx=5, pady=(0, 3))
        self.battlefield_tab, self.command_tab, self.intel_tab = ttk.Frame(self.main_tabs), ttk.Frame(self.main_tabs), ttk.Frame(self.main_tabs)
        self.neural_tab, self.diary_tab, self.options_tab = ttk.Frame(self.main_tabs), ttk.Frame(self.main_tabs), ttk.Frame(self.main_tabs)
        for frame, title_text in ((self.battlefield_tab, "Battlefield"), (self.command_tab, "Command"), (self.intel_tab, "Intelligence"), (self.neural_tab, "Neural Network"), (self.diary_tab, "War Diary"), (self.options_tab, "Options")):
            self.main_tabs.add(frame, text=title_text)
        self._build_battlefield_tabs()
        self._build_command_tabs()
        self._build_intelligence_tabs()
        self._build_neural_tabs()
        self._build_diary_tab()
        self._build_options_tabs()
        self._build_status_bar()

    def _build_toolbar(self) -> None:
        toolbar = tk.Frame(self.root, bg=WIN95["face"], bd=2, relief="raised")
        toolbar.pack(fill="x", padx=4, pady=(0, 4))
        for label, command in (("New Battle", self.new_battle), ("Save", self.save_game), ("Pause", self.toggle_pause), ("Hold", lambda: self.order_selected("Hold")), ("Advance", lambda: self.order_selected("Advance")), ("Assault", lambda: self.order_selected("Assault")), ("Retreat", lambda: self.order_selected("Retreat"))):
            ttk.Button(toolbar, text=label, command=command).pack(side="left", padx=2, pady=2)
        ttk.Label(toolbar, text="Speed:").pack(side="left", padx=(10, 1))
        self.speed_var = tk.StringVar(value=str(self.speed))
        speed_box = ttk.Combobox(toolbar, width=6, state="readonly", textvariable=self.speed_var, values=("0.5", "1.0", "2.0", "4.0"))
        speed_box.pack(side="left", padx=2)
        speed_box.bind("<<ComboboxSelected>>", self._on_speed_changed)
        self.ai_var = tk.BooleanVar(value=self.sim.allied_ai_enabled)
        ttk.Checkbutton(toolbar, text="Allied AI Commander", variable=self.ai_var, command=self._toggle_allied_ai).pack(side="left", padx=10)
        self.operation_label = ttk.Label(toolbar, text="Operation", font=("MS Sans Serif", 9, "bold"))
        self.operation_label.pack(side="right", padx=8)

    def _build_battlefield_tabs(self) -> None:
        tabs = ttk.Notebook(self.battlefield_tab)
        tabs.pack(fill="both", expand=True, padx=4, pady=4)
        map_tab, overview_tab = ttk.Frame(tabs), ttk.Frame(tabs)
        tabs.add(map_tab, text="Tactical Map")
        tabs.add(overview_tab, text="Operational Overview")
        split = tk.PanedWindow(map_tab, orient="horizontal", sashwidth=5, bg=WIN95["face"], bd=0)
        split.pack(fill="both", expand=True)
        left = tk.Frame(split, bg=WIN95["face"], bd=2, relief="sunken")
        right = tk.Frame(split, bg=WIN95["face"], width=280, bd=2, relief="sunken")
        split.add(left, stretch="always")
        split.add(right, minsize=260)
        self.map_canvas = tk.Canvas(left, bg="#1f2f1f", highlightthickness=0, cursor="crosshair")
        self.map_canvas.pack(fill="both", expand=True)
        self.map_canvas.bind("<Configure>", lambda _event: self.draw_map())
        self.map_canvas.bind("<Button-1>", self._map_left_click)
        self.map_canvas.bind("<Button-3>", self._map_right_click)
        self.map_canvas.bind("<Motion>", self._map_motion)
        tk.Label(right, text="SELECTED UNIT", bg=WIN95["navy"], fg="#ffffff", font=("MS Sans Serif", 9, "bold"), anchor="w").pack(fill="x")
        self.unit_detail = tk.Text(right, height=13, bg="#ffffff", fg="#000000", relief="sunken", bd=2, font=("Courier New", 9), state="disabled", wrap="word")
        self.unit_detail.pack(fill="x", padx=5, pady=5)
        order_frame = tk.LabelFrame(right, text=" Orders ", bg=WIN95["face"], font=("MS Sans Serif", 9, "bold"), bd=2, relief="groove")
        order_frame.pack(fill="x", padx=5, pady=3)
        for index, order in enumerate(("Hold", "Advance", "Defend", "Assault", "Flank", "Retreat")):
            ttk.Button(order_frame, text=order, command=lambda name=order: self.order_selected(name)).grid(row=index // 2, column=index % 2, sticky="ew", padx=3, pady=3)
        order_frame.grid_columnconfigure(0, weight=1)
        order_frame.grid_columnconfigure(1, weight=1)
        self.map_hint = ttk.Label(right, text="Left-click a unit. Right-click terrain to move selected units.", wraplength=240, justify="left")
        self.map_hint.pack(fill="x", padx=7, pady=6)
        self.overview_text = tk.Text(overview_tab, bg="#ffffff", fg="#000000", relief="sunken", bd=2, font=("Courier New", 10), state="disabled")
        self.overview_text.pack(fill="both", expand=True, padx=5, pady=5)

    def _build_command_tabs(self) -> None:
        tabs = ttk.Notebook(self.command_tab)
        tabs.pack(fill="both", expand=True, padx=4, pady=4)
        roster_tab, orders_tab, reserve_tab = ttk.Frame(tabs), ttk.Frame(tabs), ttk.Frame(tabs)
        tabs.add(roster_tab, text="Unit Roster")
        tabs.add(orders_tab, text="Standing Orders")
        tabs.add(reserve_tab, text="Reinforcements")
        columns = ("side", "type", "men", "morale", "ammo", "supp", "order")
        self.roster = ttk.Treeview(roster_tab, columns=columns, show="tree headings", selectmode="extended")
        self.roster.heading("#0", text="Unit")
        self.roster.column("#0", width=210)
        for key, title, width in (("side", "Side", 80), ("type", "Type", 90), ("men", "Men", 65), ("morale", "Morale", 80), ("ammo", "Ammo", 75), ("supp", "Suppression", 90), ("order", "Order", 100)):
            self.roster.heading(key, text=title)
            self.roster.column(key, width=width, anchor="center")
        self.roster.pack(fill="both", expand=True, padx=5, pady=5)
        self.roster.bind("<<TreeviewSelect>>", self._roster_select)
        panel = tk.Frame(orders_tab, bg=WIN95["face"], bd=2, relief="sunken")
        panel.pack(fill="both", expand=True, padx=8, pady=8)
        tk.Label(panel, text="BATTLEGROUP STANDING ORDERS", bg=WIN95["navy"], fg="#ffffff", font=("MS Sans Serif", 10, "bold"), anchor="w").pack(fill="x")
        instructions = "1. Select one or more Allied units in the roster or map.\n2. Choose an order. Advance/Flank move toward a map target.\n3. Right-click the tactical map to set a destination.\n4. Assault increases aggression but exposes the unit.\n5. Hold improves suppression recovery and preserves ammunition."
        ttk.Label(panel, text=instructions, justify="left", font=("MS Sans Serif", 10)).pack(anchor="nw", padx=12, pady=12)
        buttons = tk.Frame(panel, bg=WIN95["face"])
        buttons.pack(anchor="nw", padx=10, pady=8)
        for order in ("Hold", "Advance", "Defend", "Assault", "Flank", "Retreat"):
            ttk.Button(buttons, text=order, width=16, command=lambda name=order: self.order_selected(name)).pack(side="left", padx=4)
        ttk.Label(reserve_tab, text="No scheduled reinforcements. New battles generate a fresh map and full order of battle while preserving all learned neural weights.", wraplength=760, justify="left", font=("MS Sans Serif", 10)).pack(anchor="nw", padx=12, pady=12)

    def _build_intelligence_tabs(self) -> None:
        tabs = ttk.Notebook(self.intel_tab)
        tabs.pack(fill="both", expand=True, padx=4, pady=4)
        contacts_tab, terrain_tab, objectives_tab = ttk.Frame(tabs), ttk.Frame(tabs), ttk.Frame(tabs)
        tabs.add(contacts_tab, text="Enemy Contacts")
        tabs.add(terrain_tab, text="Terrain Analysis")
        tabs.add(objectives_tab, text="Objectives")
        columns = ("type", "strength", "morale", "range", "status")
        self.contacts = ttk.Treeview(contacts_tab, columns=columns, show="tree headings")
        self.contacts.heading("#0", text="Contact")
        self.contacts.column("#0", width=220)
        for key, title, width in (("type", "Type", 100), ("strength", "Strength", 100), ("morale", "Morale", 100), ("range", "Nearest Allied", 120), ("status", "Status", 120)):
            self.contacts.heading(key, text=title)
            self.contacts.column(key, width=width, anchor="center")
        self.contacts.pack(fill="both", expand=True, padx=5, pady=5)
        terrain_info = "TERRAIN          COVER     MOVEMENT\n" + "-" * 42 + "\n" + "\n".join(f"{name:<16} {cover:<9} {movement}" for name, cover, movement in (("Open", "5%", "Normal"), ("Road", "0%", "Fast"), ("Woods", "38%", "Slow"), ("Hedgerow", "28%", "Very slow"), ("Village", "48%", "Moderate"), ("Mud", "12%", "Very slow")))
        terrain_box = tk.Text(terrain_tab, bg="#ffffff", fg="#000000", font=("Courier New", 10), relief="sunken", bd=2)
        terrain_box.insert("1.0", terrain_info)
        terrain_box.configure(state="disabled")
        terrain_box.pack(fill="both", expand=True, padx=8, pady=8)
        self.objective_tree = ttk.Treeview(objectives_tab, columns=("owner", "value", "capture"), show="tree headings")
        self.objective_tree.heading("#0", text="Objective")
        self.objective_tree.column("#0", width=240)
        for key, title, width in (("owner", "Owner", 120), ("value", "Value", 100), ("capture", "Capture", 180)):
            self.objective_tree.heading(key, text=title)
            self.objective_tree.column(key, width=width, anchor="center")
        self.objective_tree.pack(fill="both", expand=True, padx=5, pady=5)

    def _build_neural_tabs(self) -> None:
        tabs = ttk.Notebook(self.neural_tab)
        tabs.pack(fill="both", expand=True, padx=4, pady=4)
        status_tab, decisions_tab, training_tab = ttk.Frame(tabs), ttk.Frame(tabs), ttk.Frame(tabs)
        tabs.add(status_tab, text="Brain Status")
        tabs.add(decisions_tab, text="Decisions")
        tabs.add(training_tab, text="Training")
        top = tk.Frame(status_tab, bg=WIN95["face"])
        top.pack(fill="x", padx=8, pady=8)
        self.brain_status = tk.Text(top, height=13, bg="#ffffff", fg="#000000", font=("Courier New", 10), relief="sunken", bd=2, state="disabled")
        self.brain_status.pack(side="left", fill="both", expand=True)
        diagram = tk.Canvas(top, width=360, height=230, bg="#ffffff", relief="sunken", bd=2)
        diagram.pack(side="right", fill="y", padx=(8, 0))
        self._draw_network_diagram(diagram)
        ttk.Label(status_tab, text="The brain file is loaded at startup and silently written every 10 seconds. Learning statistics and weights continue across maps and sessions.", wraplength=900, justify="left").pack(anchor="w", padx=10, pady=5)
        self.decision_tree = ttk.Treeview(decisions_tab, columns=("q", "count"), show="tree headings")
        self.decision_tree.heading("#0", text="Action")
        self.decision_tree.column("#0", width=220)
        self.decision_tree.heading("q", text="Current Q-value")
        self.decision_tree.column("q", width=180, anchor="center")
        self.decision_tree.heading("count", text="Lifetime Selections")
        self.decision_tree.column("count", width=180, anchor="center")
        self.decision_tree.pack(fill="both", expand=True, padx=5, pady=5)
        self.training_text = tk.Text(training_tab, bg="#ffffff", fg="#000000", font=("Courier New", 10), relief="sunken", bd=2, state="disabled", wrap="word")
        self.training_text.pack(fill="both", expand=True, padx=8, pady=8)

    def _draw_network_diagram(self, canvas: tk.Canvas) -> None:
        layers = ((60, 10), (180, 8), (300, 5))
        nodes: list[list[tuple[float, float]]] = []
        for x, count in layers:
            nodes.append([(x, 20 + index * (190 / max(1, count - 1))) for index in range(count)])
        for source, target in zip(nodes, nodes[1:]):
            for sx, sy in source:
                for tx, ty in target:
                    canvas.create_line(sx, sy, tx, ty, fill="#d0d0d0")
        for layer_index, layer in enumerate(nodes):
            fill = ("#d9e5ff", "#fff2b2", "#ffd7d7")[layer_index]
            for x, y in layer:
                canvas.create_oval(x - 6, y - 6, x + 6, y + 6, fill=fill, outline="#000000")
        canvas.create_text(60, 220, text="10 inputs", font=("MS Sans Serif", 8))
        canvas.create_text(180, 220, text="18 hidden", font=("MS Sans Serif", 8))
        canvas.create_text(300, 220, text="5 actions", font=("MS Sans Serif", 8))

    def _build_diary_tab(self) -> None:
        self.diary_text = tk.Text(self.diary_tab, bg="#ffffff", fg="#000000", relief="sunken", bd=2, font=("Courier New", 9), state="disabled", wrap="word")
        scrollbar = ttk.Scrollbar(self.diary_tab, orient="vertical", command=self.diary_text.yview)
        self.diary_text.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y", pady=6, padx=(0, 6))
        self.diary_text.pack(side="left", fill="both", expand=True, padx=(6, 0), pady=6)
        self.diary_text.tag_configure("Command", foreground="#000080", font=("Courier New", 9, "bold"))
        self.diary_text.tag_configure("Combat", foreground="#8b0000")
        self.diary_text.tag_configure("Orders", foreground="#006000")
        self.diary_text.tag_configure("Objectives", foreground="#703000", font=("Courier New", 9, "bold"))

    def _build_options_tabs(self) -> None:
        tabs = ttk.Notebook(self.options_tab)
        tabs.pack(fill="both", expand=True, padx=4, pady=4)
        gameplay_tab, persistence_tab = ttk.Frame(tabs), ttk.Frame(tabs)
        tabs.add(gameplay_tab, text="Gameplay")
        tabs.add(persistence_tab, text="Persistence")
        game_box = tk.LabelFrame(gameplay_tab, text=" Simulation ", bg=WIN95["face"], font=("MS Sans Serif", 9, "bold"), bd=2, relief="groove")
        game_box.pack(fill="x", padx=10, pady=10)
        ttk.Checkbutton(game_box, text="Let the neural commander control Allied units", variable=self.ai_var, command=self._toggle_allied_ai).pack(anchor="w", padx=10, pady=8)
        ttk.Label(game_box, text="Enemy decisions occur every 2 seconds. Simulation speed can be adjusted from the toolbar.").pack(anchor="w", padx=10, pady=(0, 8))
        persist_box = tk.LabelFrame(persistence_tab, text=" Automatic Saves ", bg=WIN95["face"], font=("MS Sans Serif", 9, "bold"), bd=2, relief="groove")
        persist_box.pack(fill="x", padx=10, pady=10)
        self.persistence_label = ttk.Label(persist_box, text="", justify="left")
        self.persistence_label.pack(anchor="w", padx=10, pady=10)
        ttk.Button(persist_box, text="Open Data Folder", command=self.open_data_folder).pack(anchor="w", padx=10, pady=(0, 10))
        ttk.Button(persist_box, text="Reset Neural Brain", command=self.reset_brain).pack(anchor="w", padx=10, pady=(0, 10))

    def _build_status_bar(self) -> None:
        status = tk.Frame(self.root, bg=WIN95["face"], bd=2, relief="sunken")
        status.pack(fill="x", padx=4, pady=(0, 4))
        self.status_left = tk.Label(status, text="Ready", bg=WIN95["face"], anchor="w", font=("MS Sans Serif", 8))
        self.status_left.pack(side="left", fill="x", expand=True, padx=4)
        self.status_mid = tk.Label(status, text="Autosave: pending", bg=WIN95["face"], anchor="center", font=("MS Sans Serif", 8), bd=1, relief="sunken", width=28)
        self.status_mid.pack(side="left", padx=2)
        self.status_right = tk.Label(status, text="Brain: loaded", bg=WIN95["face"], anchor="center", font=("MS Sans Serif", 8), bd=1, relief="sunken", width=24)
        self.status_right.pack(side="left", padx=2)

    def _load_game_if_available(self) -> None:
        if not self.save_path.exists():
            return
        try:
            self.sim.load_dict(read_json(self.save_path, {}))
            self.ai_var.set(self.sim.allied_ai_enabled)
            self.last_save_text = "Loaded autosave"
            self.sim.log("Command", "Autosave restored successfully.")
        except (ValueError, TypeError, KeyError):
            self.sim.log("Command", "Autosave was invalid; a fresh battle was started.")

    def _game_loop(self) -> None:
        if not self.running:
            return
        now = time.perf_counter()
        real_dt = min(0.5, now - self.last_tick)
        self.last_tick = now
        if not self.paused and not self.sim.battle_over:
            self.sim.tick(real_dt * self.speed)
        self.root.after(self.TICK_MS, self._game_loop)

    def _refresh_loop(self) -> None:
        if not self.running:
            return
        self.draw_map()
        self._refresh_header()
        self._refresh_selected_detail()
        self._refresh_roster()
        self._refresh_contacts()
        self._refresh_objectives()
        self._refresh_overview()
        self._refresh_neural()
        self._refresh_diary()
        self._refresh_persistence()
        self.root.after(self.REFRESH_MS, self._refresh_loop)

    def draw_map(self) -> None:
        canvas = self.map_canvas
        width, height = max(1, canvas.winfo_width()), max(1, canvas.winfo_height())
        cell_w, cell_h = width / MAP_WIDTH, height / MAP_HEIGHT
        canvas.delete("all")
        for y, row in enumerate(self.sim.terrain):
            for x, terrain in enumerate(row):
                x1, y1 = x * cell_w, y * cell_h
                canvas.create_rectangle(x1, y1, x1 + cell_w + 1, y1 + cell_h + 1, fill=TERRAIN_COLORS.get(terrain, "#808080"), outline="")
                if terrain == "woods" and cell_w > 22:
                    canvas.create_text(x1 + cell_w / 2, y1 + cell_h / 2, text="♣", fill="#163f18", font=("Arial", max(8, int(cell_h * 0.55))))
                elif terrain == "village" and cell_w > 22:
                    canvas.create_text(x1 + cell_w / 2, y1 + cell_h / 2, text="▪", fill="#362c27", font=("Arial", max(10, int(cell_h * 0.7))))
        for x in range(MAP_WIDTH + 1):
            canvas.create_line(x * cell_w, 0, x * cell_w, height, fill="#000000", stipple="gray75")
        for y in range(MAP_HEIGHT + 1):
            canvas.create_line(0, y * cell_h, width, y * cell_h, fill="#000000", stipple="gray75")
        for point in self.sim.control_points:
            px, py = (point.x + 0.5) * cell_w, (point.y + 0.5) * cell_h
            color = WIN95["allied"] if point.owner == "Allied" else WIN95["axis"] if point.owner == "Axis" else WIN95["neutral"]
            radius = max(7, min(cell_w, cell_h) * 0.34)
            canvas.create_polygon(px, py - radius, px + radius, py, px, py + radius, px - radius, py, fill="#ffff00", outline=color, width=3)
            canvas.create_text(px, py + radius + 8, text=point.name, fill="#ffffff", font=("MS Sans Serif", 7, "bold"))
        for unit in self.sim.living_units():
            ux, uy = (unit.x + 0.5) * cell_w, (unit.y + 0.5) * cell_h
            radius = max(6, min(cell_w, cell_h) * 0.32)
            color = WIN95["allied"] if unit.side == "Allied" else WIN95["axis"]
            selected = unit.uid in self.selected_ids
            canvas.create_oval(ux - radius, uy - radius, ux + radius, uy + radius, fill=color, outline="#ffff00" if selected else "#ffffff", width=3 if selected else 1)
            symbol = {"Rifle": "R", "Support": "MG", "Scout": "S", "Mortar": "M", "Armour": "A"}.get(unit.unit_type, "U")
            canvas.create_text(ux, uy, text=symbol, fill="#ffffff", font=("Arial", 7, "bold"))
            canvas.create_rectangle(ux - radius, uy + radius + 2, ux + radius, uy + radius + 5, fill="#400000", outline="")
            canvas.create_rectangle(ux - radius, uy + radius + 2, ux - radius + radius * 2 * unit.strength, uy + radius + 5, fill="#00c000", outline="")
            if selected and unit.target_x is not None and unit.target_y is not None:
                tx, ty = (unit.target_x + 0.5) * cell_w, (unit.target_y + 0.5) * cell_h
                canvas.create_line(ux, uy, tx, ty, fill="#ffff00", dash=(4, 3), arrow="last")
        if self.hover_tile:
            x, y = self.hover_tile
            canvas.create_rectangle(x * cell_w, y * cell_h, (x + 1) * cell_w, (y + 1) * cell_h, outline="#ffffff", width=2)
        if self.sim.battle_over:
            canvas.create_rectangle(width * 0.22, height * 0.38, width * 0.78, height * 0.62, fill=WIN95["face"], outline="#ffffff", width=3)
            canvas.create_text(width / 2, height * 0.47, text="BATTLE CONCLUDED", fill="#000000", font=("MS Sans Serif", 18, "bold"))
            canvas.create_text(width / 2, height * 0.55, text=f"{self.sim.winner} victory", fill=WIN95["navy"], font=("MS Sans Serif", 14, "bold"))

    def _canvas_to_map(self, event: tk.Event) -> tuple[float, float]:
        return clamp(event.x / max(1, self.map_canvas.winfo_width()) * MAP_WIDTH, 0, MAP_WIDTH - 0.001), clamp(event.y / max(1, self.map_canvas.winfo_height()) * MAP_HEIGHT, 0, MAP_HEIGHT - 0.001)

    def _map_left_click(self, event: tk.Event) -> None:
        x, y = self._canvas_to_map(event)
        nearby = [unit for unit in self.sim.living_units() if distance((unit.x, unit.y), (x, y)) <= 0.75]
        if nearby:
            chosen = min(nearby, key=lambda unit: distance((unit.x, unit.y), (x, y)))
            if not (event.state & 0x0001):
                self.selected_ids.clear()
            if chosen.uid in self.selected_ids and event.state & 0x0001:
                self.selected_ids.remove(chosen.uid)
            else:
                self.selected_ids.add(chosen.uid)
        else:
            self.selected_ids.clear()

    def _map_right_click(self, event: tk.Event) -> None:
        x, y = self._canvas_to_map(event)
        allied = [uid for uid in self.selected_ids if self.sim.unit_by_id(uid) and self.sim.unit_by_id(uid).side == "Allied"]
        if not allied:
            self.status_left.configure(text="Select at least one Allied unit before issuing a movement order.")
            return
        first = self.sim.unit_by_id(allied[0])
        order = first.order if first and first.order in ("Assault", "Flank", "Retreat") else "Advance"
        self.sim.issue_order(allied, order, x, y)
        self.status_left.configure(text=f"Order issued to {len(allied)} unit(s): {order} to grid {int(x):02d},{int(y):02d}")

    def _map_motion(self, event: tk.Event) -> None:
        x, y = self._canvas_to_map(event)
        self.hover_tile = int(x), int(y)
        terrain = self.sim.tile_at(x, y)
        self.map_hint.configure(text=f"Grid {int(x):02d},{int(y):02d} — {terrain.title()} — cover {int(TERRAIN_COVER.get(terrain, 0) * 100)}%\nLeft-click unit; right-click destination.")

    def _roster_select(self, _event: tk.Event) -> None:
        self.selected_ids = {item for item in self.roster.selection() if self.sim.unit_by_id(item)}
        if self.selected_ids:
            self.main_tabs.select(self.battlefield_tab)

    def order_selected(self, order: str) -> None:
        allied_ids = [uid for uid in self.selected_ids if self.sim.unit_by_id(uid) and self.sim.unit_by_id(uid).side == "Allied" and self.sim.unit_by_id(uid).alive]
        if not allied_ids:
            self.status_left.configure(text="Select one or more living Allied units.")
            return
        self.sim.issue_order(allied_ids, order)
        self.status_left.configure(text=f"{order} order issued to {len(allied_ids)} Allied unit(s).")

    def _refresh_header(self) -> None:
        minutes, seconds = divmod(int(self.sim.elapsed), 60)
        self.clock_label.configure(text=f"T+ {minutes:02d}:{seconds:02d}")
        self.operation_label.configure(text=f"{self.sim.operation_name}  |  {self.sim.weather}{' [PAUSED]' if self.paused else ''}")
        self.status_left.configure(text=f"Allied score {self.sim.battle_score('Allied')}  |  Axis score {self.sim.battle_score('Axis')}  |  Selected {len(self.selected_ids)}")

    def _refresh_selected_detail(self) -> None:
        selected = [self.sim.unit_by_id(uid) for uid in self.selected_ids]
        selected = [unit for unit in selected if unit]
        if not selected:
            text = "No unit selected.\n\nUse the map or Unit Roster to select a formation."
        elif len(selected) > 1:
            text = f"GROUP SELECTION\n\nUnits: {len(selected)}\nAllied: {sum(1 for unit in selected if unit.side == 'Allied')}\nPersonnel: {sum(unit.men for unit in selected)}\n\nOrders apply to Allied units only."
        else:
            unit = selected[0]
            text = f"{unit.name}\n{'=' * min(28, len(unit.name))}\nSide:       {unit.side}\nType:       {unit.unit_type}\nPersonnel:  {unit.men}/{unit.max_men}\nMorale:     {unit.morale:5.1f}%\nAmmo:       {unit.ammo:5.1f}%\nSuppression:{unit.suppression:5.1f}%\nExperience: {unit.experience:5.2f}\nOrder:      {unit.order}\nStance:     {unit.stance}\nKills:      {unit.kills}\nGrid:       {unit.x:04.1f},{unit.y:04.1f}"
        self._set_text(self.unit_detail, text)

    def _refresh_roster(self) -> None:
        existing = set(self.roster.get_children())
        for unit in self.sim.units:
            values = (unit.side, unit.unit_type, f"{unit.men}/{unit.max_men}", f"{unit.morale:.0f}%", f"{unit.ammo:.0f}%", f"{unit.suppression:.0f}%", unit.order)
            if unit.uid in existing:
                self.roster.item(unit.uid, text=unit.name, values=values)
                existing.remove(unit.uid)
            else:
                self.roster.insert("", "end", iid=unit.uid, text=unit.name, values=values)
        for iid in existing:
            self.roster.delete(iid)
        self.roster.selection_set([uid for uid in self.selected_ids if self.roster.exists(uid)])

    def _refresh_contacts(self) -> None:
        self.contacts.delete(*self.contacts.get_children())
        allied = self.sim.living_units("Allied")
        for unit in self.sim.living_units("Axis"):
            nearest = min((distance((unit.x, unit.y), (friend.x, friend.y)) for friend in allied), default=99.0)
            self.contacts.insert("", "end", text=unit.name, values=(unit.unit_type, f"{unit.men}/{unit.max_men}", f"{unit.morale:.0f}%", f"{nearest:.1f}", "Engaged" if nearest <= 7 else "Observed"))

    def _refresh_objectives(self) -> None:
        self.objective_tree.delete(*self.objective_tree.get_children())
        for point in self.sim.control_points:
            self.objective_tree.insert("", "end", text=point.name, values=(point.owner, point.value, f"{point.capture:+.0f}%"))

    def _refresh_overview(self) -> None:
        allied, axis = self.sim.living_units("Allied"), self.sim.living_units("Axis")
        objectives = "\n".join(f"  {point.name:<18} {point.owner:<8} {point.capture:+6.1f}%" for point in self.sim.control_points)
        text = f"OPERATIONAL OVERVIEW\n{'=' * 60}\nOperation: {self.sim.operation_name}\nDate:      {self.sim.date_label}\nWeather:   {self.sim.weather}\nSeed:      {self.sim.seed}\n\nFORCE STATUS\n{'-' * 60}\nAllied: {len(allied):2d} active units / {sum(unit.men for unit in allied):3d} personnel / score {self.sim.battle_score('Allied')}\nAxis:   {len(axis):2d} active units / {sum(unit.men for unit in axis):3d} personnel / score {self.sim.battle_score('Axis')}\n\nOBJECTIVES\n{'-' * 60}\n{objectives}\n\nBattle status: {'CONCLUDED — ' + str(self.sim.winner) + ' victory' if self.sim.battle_over else 'IN PROGRESS'}"
        self._set_text(self.overview_text, text)

    def _refresh_neural(self) -> None:
        stats = self.brain.stats
        total = stats.wins + stats.losses
        text = f"TACTICAL NEURAL BRAIN\n{'=' * 48}\nArchitecture:       {self.brain.input_size}-{self.brain.hidden_size}-{self.brain.output_size}\nLearning rate:      {self.brain.learning_rate:.4f}\nDiscount factor:    {self.brain.discount:.3f}\nExploration rate:   {self.brain.epsilon:.3f}\nDecisions:          {stats.decisions:,}\nTraining steps:     {stats.training_steps:,}\nLifetime reward:    {stats.lifetime_reward:+.3f}\nAI wins / losses:   {stats.wins} / {stats.losses}\nAI win rate:        {(stats.wins / total * 100 if total else 0):.1f}%\nLast action:        {self.brain.last_action}\nLast train error:   {self.sim.last_training_error:.5f}\nBrain file:         {self.brain_path}"
        self._set_text(self.brain_status, text)
        self.decision_tree.delete(*self.decision_tree.get_children())
        for index, action in enumerate(ACTIONS):
            self.decision_tree.insert("", "end", text=action.title(), values=(f"{self.brain.last_q_values[index]:+.5f}", f"{stats.action_counts.get(action, 0):,}"))
        self._set_text(self.training_text, "LEARNING MODEL\n" + "=" * 70 + "\n\nThe enemy commander observes ten normalized tactical signals: unit strength, morale, ammunition, suppression, enemy distance, objective distance, nearby friendly and enemy density, terrain cover, and map progress.\n\nEvery two simulated seconds it selects one of five actions. The prior action is trained using casualties inflicted, casualties suffered, movement toward objectives, terrain use, and retreat discipline. Battle outcomes add a terminal reward.\n\nThe brain is never reset when a new battle begins. Its weights and lifetime statistics are saved independently from the game autosave, allowing learning to continue across maps and sessions.")
        self.status_right.configure(text=f"Brain: {stats.training_steps:,} training steps")

    def _refresh_diary(self) -> None:
        if self.last_event_count > len(self.sim.events):
            self.last_event_count = 0
            self._set_text(self.diary_text, "")
        if self.last_event_count == len(self.sim.events):
            return
        self.diary_text.configure(state="normal")
        for event in self.sim.events[self.last_event_count:]:
            minutes, seconds = divmod(int(event.timestamp), 60)
            self.diary_text.insert("end", f"[{minutes:02d}:{seconds:02d}] {event.category.upper():<10} {event.text}\n", event.category)
        self.last_event_count = len(self.sim.events)
        self.diary_text.see("end")
        self.diary_text.configure(state="disabled")

    def _refresh_persistence(self) -> None:
        self.persistence_label.configure(text=f"Game autosave interval:   5 seconds\nBrain autosave interval: 10 seconds\nLast status: {self.last_save_text}\n\nGame file:\n  {self.save_path}\n\nBrain file:\n  {self.brain_path}\n\nWrites use a temporary file followed by an atomic replace to reduce corruption risk.")

    @staticmethod
    def _set_text(widget: tk.Text, value: str) -> None:
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", value)
        widget.configure(state="disabled")

    def _autosave_game(self) -> None:
        if self.running:
            self.save_game(silent=True)
            self.root.after(self.GAME_SAVE_MS, self._autosave_game)

    def _autosave_brain(self) -> None:
        if not self.running:
            return
        try:
            self.brain.save(self.brain_path)
            self.last_save_text = f"Brain saved at {time.strftime('%H:%M:%S')}"
        except OSError as exc:
            self.status_right.configure(text=f"Brain save failed: {exc}")
        self.root.after(self.BRAIN_SAVE_MS, self._autosave_brain)

    def save_game(self, silent: bool = False) -> None:
        try:
            atomic_write_json(self.save_path, self.sim.to_dict())
            self.last_save_text = f"Game saved at {time.strftime('%H:%M:%S')}"
            self.status_mid.configure(text=self.last_save_text)
            if not silent:
                messagebox.showinfo("Save Game", f"Game saved successfully.\n\n{self.save_path}", parent=self.root)
        except OSError as exc:
            self.status_mid.configure(text="Autosave failed")
            if not silent:
                messagebox.showerror("Save Error", str(exc), parent=self.root)

    def load_game(self) -> None:
        try:
            self.sim.load_dict(read_json(self.save_path, {}))
            self.selected_ids.clear()
            self.last_event_count = 0
            self.ai_var.set(self.sim.allied_ai_enabled)
        except (ValueError, TypeError, KeyError):
            messagebox.showerror("Load Error", "The autosave could not be loaded.", parent=self.root)

    def new_battle(self) -> None:
        if messagebox.askyesno("New Battle", "Start a new procedurally generated battle?\n\nThe neural brain will be preserved.", parent=self.root):
            self.sim.new_battle()
            self.selected_ids.clear()
            self.last_event_count = 0
            self.save_game(silent=True)

    def toggle_pause(self) -> None:
        self.paused = not self.paused
        self.last_tick = time.perf_counter()

    def _on_speed_changed(self, _event: tk.Event | None = None) -> None:
        try:
            self.speed = float(self.speed_var.get())
        except ValueError:
            self.speed = 1.0
        self.settings["speed"] = self.speed
        atomic_write_json(self.settings_path, self.settings)

    def _toggle_allied_ai(self) -> None:
        self.sim.allied_ai_enabled = bool(self.ai_var.get())

    def reset_brain(self) -> None:
        if messagebox.askyesno("Reset Neural Brain", "Erase all learned neural weights and lifetime statistics?\n\nThis cannot be undone.", parent=self.root):
            self.brain = TacticalBrain()
            self.sim.brain = self.brain
            self.brain.save(self.brain_path)

    def open_data_folder(self) -> None:
        try:
            import os
            import subprocess
            import sys
            if sys.platform.startswith("win"):
                os.startfile(self.data_dir)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(self.data_dir)])
            else:
                subprocess.Popen(["xdg-open", str(self.data_dir)])
        except OSError:
            messagebox.showinfo("Data Folder", str(self.data_dir), parent=self.root)

    def show_controls(self) -> None:
        messagebox.showinfo("Controls", "Left-click: select a unit\nShift + left-click: multi-select\nRight-click: move selected Allied units\n\nUse the toolbar or Command tab to set orders. Enemy AI decides and learns every two simulated seconds.", parent=self.root)

    def show_about(self) -> None:
        messagebox.showinfo("About", "Gateway to Caen: Tactical Command\nVersion 0.1.0\n\nAn original clean-room tactical command game built with Python and Tkinter. It uses no proprietary game code or assets.", parent=self.root)

    def on_close(self) -> None:
        self.running = False
        try:
            atomic_write_json(self.save_path, self.sim.to_dict())
            self.brain.save(self.brain_path)
            self.settings["speed"] = self.speed
            atomic_write_json(self.settings_path, self.settings)
        finally:
            self.root.destroy()


def run() -> None:
    root = tk.Tk()
    TacticalCommandApp(root)
    root.mainloop()
