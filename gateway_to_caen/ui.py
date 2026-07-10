"""Windows 95 styled, side-aware Tkinter command interface."""
from __future__ import annotations

import math
import time
import tkinter as tk
from tkinter import messagebox, ttk

from .neural import ACTIONS, TacticalBrain
from .persistence import atomic_write_json, read_json, user_data_dir
from .simulation import MAP_HEIGHT, MAP_WIDTH, TERRAIN_COVER, BattleSimulation, clamp, distance

W95 = {"face":"#c0c0c0","navy":"#000080","light":"#ffffff","shadow":"#808080","dark":"#000000","allied":"#244d9b","axis":"#9a2828","neutral":"#666666"}
TERRAIN = {"open":"#80965a","road":"#b8ad8c","woods":"#365f35","hedge":"#56703c","village":"#887364","mud":"#71654a"}


class TacticalCommandApp:
    TICK_MS = DRAW_MS = 33
    REFRESH_MS = 250
    GAME_SAVE_MS = 5_000
    BRAIN_SAVE_MS = 10_000

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        root.title("Gateway to Caen: Tactical Command")
        root.geometry("1280x820")
        root.minsize(1040, 690)
        root.configure(bg=W95["face"])
        self.data_dir = user_data_dir()
        self.brain_path = self.data_dir / "tactical_brain.json"
        self.save_path = self.data_dir / "autosave.json"
        self.settings_path = self.data_dir / "settings.json"
        self.settings = read_json(self.settings_path, {})
        self.brain = TacticalBrain.load_or_create(self.brain_path)
        self._style()
        side = str(self.settings.get("player_side", "Allied"))
        side = side if side in ("Allied", "Axis") else "Allied"
        if not self.save_path.exists():
            side = self._choose_side(side)
        self.sim = BattleSimulation(self.brain, player_side=side)
        self.speed = float(self.settings.get("speed", 1.0))
        self.running, self.paused = True, False
        self.selected: set[str] = set()
        self.hover: tuple[int, int] | None = None
        self.last_tick = time.perf_counter()
        self.anim_time = 0.0
        self.event_cursor = 0
        self.last_save = "Autosave pending"
        self._menu()
        self._shell()
        self._load_startup()
        self._sync_side()
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.after(self.TICK_MS, self._game_loop)
        root.after(self.DRAW_MS, self._draw_loop)
        root.after(self.REFRESH_MS, self._refresh_loop)
        root.after(self.GAME_SAVE_MS, self._autosave_game)
        root.after(self.BRAIN_SAVE_MS, self._autosave_brain)

    def _style(self) -> None:
        style = ttk.Style(self.root)
        try: style.theme_use("clam")
        except tk.TclError: pass
        for name in ("TFrame", "TLabel", "TCheckbutton", "TRadiobutton"):
            style.configure(name, background=W95["face"], font=("MS Sans Serif", 9))
        style.configure("TButton", background=W95["face"], font=("MS Sans Serif", 9), padding=(6, 3))
        style.map("TButton", background=[("active", "#d8d8d8"), ("pressed", "#a8a8a8")])
        style.configure("TNotebook", background=W95["face"], borderwidth=2)
        style.configure("TNotebook.Tab", background=W95["face"], padding=(8, 4), font=("MS Sans Serif", 9))
        style.map("TNotebook.Tab", background=[("selected", "#e0e0e0")])
        style.configure("Treeview", background="#ffffff", fieldbackground="#ffffff", rowheight=22, font=("MS Sans Serif", 9))
        style.configure("Treeview.Heading", background=W95["face"], font=("MS Sans Serif", 9, "bold"))

    def _choose_side(self, default: str) -> str:
        result = {"side": default}
        win = tk.Toplevel(self.root)
        win.title("New Save — Choose Side")
        win.configure(bg=W95["face"])
        win.resizable(False, False)
        win.transient(self.root)
        win.grab_set()
        tk.Label(win, text="▣  SELECT PLAYER COMMAND", bg=W95["navy"], fg="white", font=("MS Sans Serif", 10, "bold"), anchor="w").pack(fill="x", padx=3, pady=3)
        ttk.Label(win, text="Choose the faction this save will focus on. The opposing side is controlled by the persistent neural commander.", wraplength=490, justify="left").pack(fill="x", padx=14, pady=10)
        choice = tk.StringVar(value=default)
        row = tk.Frame(win, bg=W95["face"]); row.pack(fill="x", padx=10)
        for side, text in (("Allied", "Advance from the west. Allied lines stay on the left."), ("Axis", "Defend from the east. The map mirrors so Axis stays on the left.")):
            card = tk.Frame(row, bg=W95["face"], bd=2, relief="raised", width=240, height=110)
            card.pack(side="left", padx=5, fill="both", expand=True); card.pack_propagate(False)
            tk.Label(card, text=f"{side.upper()} COMMAND", bg=W95[side.lower()], fg="white", font=("MS Sans Serif", 9, "bold")).pack(fill="x")
            ttk.Radiobutton(card, text=f"Control {side}", variable=choice, value=side).pack(anchor="w", padx=8, pady=(10, 4))
            ttk.Label(card, text=text, wraplength=205, justify="left").pack(anchor="w", padx=8)
        def accept() -> None:
            result["side"] = choice.get() if choice.get() in ("Allied", "Axis") else default
            win.destroy()
        ttk.Button(win, text="Deploy", command=accept, width=15).pack(anchor="e", padx=15, pady=12)
        win.protocol("WM_DELETE_WINDOW", accept)
        win.update_idletasks()
        win.geometry(f"+{self.root.winfo_rootx()+120}+{self.root.winfo_rooty()+100}")
        self.root.wait_window(win)
        return result["side"]

    def _menu(self) -> None:
        menu = tk.Menu(self.root, tearoff=False, bg=W95["face"])
        file = tk.Menu(menu, tearoff=False, bg=W95["face"])
        file.add_command(label="New Battle", command=self.new_battle)
        file.add_command(label="New Save / Choose Side", command=self.new_save)
        file.add_separator(); file.add_command(label="Save Now", command=self.save); file.add_command(label="Load Autosave", command=self.load)
        file.add_separator(); file.add_command(label="Exit", command=self.close)
        menu.add_cascade(label="File", menu=file)
        game = tk.Menu(menu, tearoff=False, bg=W95["face"])
        game.add_command(label="Pause / Resume", command=self.toggle_pause)
        game.add_command(label="Allied Victory", command=lambda: self.sim.force_result("Allied"))
        game.add_command(label="Axis Victory", command=lambda: self.sim.force_result("Axis"))
        menu.add_cascade(label="Game", menu=game)
        view = tk.Menu(menu, tearoff=False, bg=W95["face"])
        view.add_command(label="Battlefield", command=lambda: self.tabs.select(self.battle_tab))
        view.add_command(label="Neural Network", command=lambda: self.tabs.select(self.neural_tab))
        view.add_command(label="War Diary", command=lambda: self.tabs.select(self.diary_tab))
        menu.add_cascade(label="View", menu=view)
        helpm = tk.Menu(menu, tearoff=False, bg=W95["face"])
        helpm.add_command(label="Controls", command=self.controls); helpm.add_command(label="About", command=self.about)
        menu.add_cascade(label="Help", menu=helpm)
        self.root.config(menu=menu)

    def _shell(self) -> None:
        title = tk.Frame(self.root, bg=W95["navy"], bd=2, relief="raised")
        title.pack(fill="x", padx=3, pady=3)
        self.title_label = tk.Label(title, text="▣  GATEWAY TO CAEN — TACTICAL COMMAND", bg=W95["navy"], fg="white", font=("MS Sans Serif", 10, "bold"), anchor="w")
        self.title_label.pack(side="left", fill="x", expand=True, padx=5, pady=3)
        self.clock = tk.Label(title, text="T+ 00:00", bg=W95["navy"], fg="white", font=("MS Sans Serif", 9, "bold")); self.clock.pack(side="right", padx=7)
        self._toolbar()
        self.tabs = ttk.Notebook(self.root); self.tabs.pack(fill="both", expand=True, padx=5, pady=(0, 3))
        self.battle_tab, self.command_tab, self.intel_tab = ttk.Frame(self.tabs), ttk.Frame(self.tabs), ttk.Frame(self.tabs)
        self.neural_tab, self.diary_tab, self.options_tab = ttk.Frame(self.tabs), ttk.Frame(self.tabs), ttk.Frame(self.tabs)
        for frame, name in ((self.battle_tab,"Battlefield"),(self.command_tab,"Command"),(self.intel_tab,"Intelligence"),(self.neural_tab,"Neural Network"),(self.diary_tab,"War Diary"),(self.options_tab,"Options")):
            self.tabs.add(frame, text=name)
        self._battle_tabs(); self._command_tabs(); self._intel_tabs(); self._neural_tabs(); self._diary(); self._options(); self._statusbar()

    def _toolbar(self) -> None:
        bar = tk.Frame(self.root, bg=W95["face"], bd=2, relief="raised"); bar.pack(fill="x", padx=4, pady=(0,4))
        for label, command in (("New Battle",self.new_battle),("Save",self.save),("Pause",self.toggle_pause),("Hold",lambda:self.order("Hold")),("Advance",lambda:self.order("Advance")),("Assault",lambda:self.order("Assault")),("Retreat",lambda:self.order("Retreat"))):
            ttk.Button(bar, text=label, command=command).pack(side="left", padx=2, pady=2)
        ttk.Label(bar, text="Speed:").pack(side="left", padx=(10,1))
        self.speed_var = tk.StringVar(value=str(self.speed))
        box = ttk.Combobox(bar, width=6, state="readonly", textvariable=self.speed_var, values=("0.5","1.0","2.0","4.0")); box.pack(side="left"); box.bind("<<ComboboxSelected>>", self._speed)
        self.ai_var = tk.BooleanVar(value=False)
        self.ai_check = ttk.Checkbutton(bar, text="Player AI Commander", variable=self.ai_var, command=self._toggle_ai); self.ai_check.pack(side="left", padx=10)
        self.operation = ttk.Label(bar, text="Operation", font=("MS Sans Serif",9,"bold")); self.operation.pack(side="right", padx=8)

    def _battle_tabs(self) -> None:
        sub = ttk.Notebook(self.battle_tab); sub.pack(fill="both", expand=True, padx=4, pady=4)
        tactical, overview = ttk.Frame(sub), ttk.Frame(sub); sub.add(tactical,text="Tactical Map"); sub.add(overview,text="Operational Overview")
        pane = tk.PanedWindow(tactical, orient="horizontal", sashwidth=5, bg=W95["face"], bd=0); pane.pack(fill="both", expand=True)
        left = tk.Frame(pane,bg=W95["face"],bd=2,relief="sunken"); right = tk.Frame(pane,bg=W95["face"],bd=2,relief="sunken",width=280)
        pane.add(left,stretch="always"); pane.add(right,minsize=260)
        self.canvas = tk.Canvas(left,bg="#172017",highlightthickness=0,cursor="crosshair"); self.canvas.pack(fill="both",expand=True)
        self.canvas.bind("<Configure>",lambda _e:self.draw()); self.canvas.bind("<Button-1>",self._left); self.canvas.bind("<Button-3>",self._right); self.canvas.bind("<Motion>",self._motion)
        tk.Label(right,text="SELECTED UNIT",bg=W95["navy"],fg="white",font=("MS Sans Serif",9,"bold"),anchor="w").pack(fill="x")
        self.detail = tk.Text(right,height=14,bg="white",font=("Courier New",9),bd=2,relief="sunken",state="disabled",wrap="word"); self.detail.pack(fill="x",padx=5,pady=5)
        orders = tk.LabelFrame(right,text=" Orders ",bg=W95["face"],font=("MS Sans Serif",9,"bold")); orders.pack(fill="x",padx=5,pady=3)
        for i,name in enumerate(("Hold","Advance","Defend","Assault","Flank","Retreat")):
            ttk.Button(orders,text=name,command=lambda n=name:self.order(n)).grid(row=i//2,column=i%2,sticky="ew",padx=3,pady=3)
        orders.grid_columnconfigure(0,weight=1); orders.grid_columnconfigure(1,weight=1)
        self.hint = ttk.Label(right,text="Left-click a friendly unit. Right-click terrain to move.",wraplength=240,justify="left"); self.hint.pack(fill="x",padx=7,pady=6)
        self.overview = tk.Text(overview,bg="white",font=("Courier New",10),state="disabled",bd=2,relief="sunken"); self.overview.pack(fill="both",expand=True,padx=5,pady=5)

    def _command_tabs(self) -> None:
        sub=ttk.Notebook(self.command_tab); sub.pack(fill="both",expand=True,padx=4,pady=4)
        roster,orders,reserves=ttk.Frame(sub),ttk.Frame(sub),ttk.Frame(sub); sub.add(roster,text="Unit Roster"); sub.add(orders,text="Standing Orders"); sub.add(reserves,text="Reinforcements")
        cols=("type","men","morale","ammo","supp","order")
        self.roster=ttk.Treeview(roster,columns=cols,show="tree headings",selectmode="extended"); self.roster.heading("#0",text="Unit"); self.roster.column("#0",width=220)
        for key,title,width in (("type","Type",90),("men","Men",65),("morale","Morale",80),("ammo","Ammo",75),("supp","Suppression",95),("order","Order",100)):
            self.roster.heading(key,text=title); self.roster.column(key,width=width,anchor="center")
        self.roster.pack(fill="both",expand=True,padx=5,pady=5); self.roster.bind("<<TreeviewSelect>>",self._roster_select)
        panel=tk.Frame(orders,bg=W95["face"],bd=2,relief="sunken"); panel.pack(fill="both",expand=True,padx=8,pady=8)
        tk.Label(panel,text="BATTLEGROUP STANDING ORDERS",bg=W95["navy"],fg="white",font=("MS Sans Serif",10,"bold"),anchor="w").pack(fill="x")
        self.order_help=ttk.Label(panel,text="",justify="left",font=("MS Sans Serif",10)); self.order_help.pack(anchor="nw",padx=12,pady=12)
        row=tk.Frame(panel,bg=W95["face"]); row.pack(anchor="nw",padx=10)
        for name in ("Hold","Advance","Defend","Assault","Flank","Retreat"): ttk.Button(row,text=name,width=14,command=lambda n=name:self.order(n)).pack(side="left",padx=3)
        ttk.Label(reserves,text="No scheduled reinforcements. New maps preserve the selected faction and all learned neural weights.",wraplength=760,justify="left").pack(anchor="nw",padx=12,pady=12)

    def _intel_tabs(self) -> None:
        sub=ttk.Notebook(self.intel_tab); sub.pack(fill="both",expand=True,padx=4,pady=4)
        contacts,terrain,objectives=ttk.Frame(sub),ttk.Frame(sub),ttk.Frame(sub); sub.add(contacts,text="Enemy Contacts"); sub.add(terrain,text="Terrain Analysis"); sub.add(objectives,text="Objectives")
        cols=("type","strength","range","status")
        self.contacts=ttk.Treeview(contacts,columns=cols,show="tree headings"); self.contacts.heading("#0",text="Contact"); self.contacts.column("#0",width=220)
        for key,title,width in (("type","Type",100),("strength","Strength",100),("range","Nearest Friendly",130),("status","Status",120)):
            self.contacts.heading(key,text=title); self.contacts.column(key,width=width,anchor="center")
        self.contacts.pack(fill="both",expand=True,padx=5,pady=5)
        info="TERRAIN          COVER     MOVEMENT\n"+"-"*42+"\n"+"\n".join(f"{n:<16} {c:<9} {m}" for n,c,m in (("Open","5%","Normal"),("Road","0%","Fast"),("Woods","38%","Slow"),("Hedgerow","28%","Very slow"),("Village","48%","Moderate"),("Mud","12%","Very slow")))
        box=tk.Text(terrain,bg="white",font=("Courier New",10),bd=2,relief="sunken"); box.insert("1.0",info); box.configure(state="disabled"); box.pack(fill="both",expand=True,padx=8,pady=8)
        self.objectives=ttk.Treeview(objectives,columns=("owner","value","capture"),show="tree headings"); self.objectives.heading("#0",text="Objective"); self.objectives.column("#0",width=240)
        for key,title,width in (("owner","Known Owner",140),("value","Value",100),("capture","Capture",180)):
            self.objectives.heading(key,text=title); self.objectives.column(key,width=width,anchor="center")
        self.objectives.pack(fill="both",expand=True,padx=5,pady=5)

    def _neural_tabs(self) -> None:
        sub=ttk.Notebook(self.neural_tab); sub.pack(fill="both",expand=True,padx=4,pady=4)
        status,decisions,training=ttk.Frame(sub),ttk.Frame(sub),ttk.Frame(sub); sub.add(status,text="Brain Status"); sub.add(decisions,text="Decisions"); sub.add(training,text="Training")
        self.brain_status=tk.Text(status,bg="white",font=("Courier New",10),state="disabled",bd=2,relief="sunken"); self.brain_status.pack(fill="both",expand=True,padx=8,pady=8)
        self.decisions=ttk.Treeview(decisions,columns=("q","count"),show="tree headings"); self.decisions.heading("#0",text="Action"); self.decisions.heading("q",text="Q-value"); self.decisions.heading("count",text="Lifetime Selections"); self.decisions.pack(fill="both",expand=True,padx=5,pady=5)
        self.training=tk.Text(training,bg="white",font=("Courier New",10),state="disabled",bd=2,relief="sunken",wrap="word"); self.training.pack(fill="both",expand=True,padx=8,pady=8)

    def _diary(self) -> None:
        self.diary=tk.Text(self.diary_tab,bg="white",font=("Courier New",9),state="disabled",bd=2,relief="sunken",wrap="word"); self.diary.pack(fill="both",expand=True,padx=6,pady=6)
        self.diary.tag_configure("Command",foreground="#000080",font=("Courier New",9,"bold")); self.diary.tag_configure("Combat",foreground="#8b0000"); self.diary.tag_configure("Orders",foreground="#006000"); self.diary.tag_configure("Objectives",foreground="#703000",font=("Courier New",9,"bold"))

    def _options(self) -> None:
        sub=ttk.Notebook(self.options_tab); sub.pack(fill="both",expand=True,padx=4,pady=4)
        game,persist=ttk.Frame(sub),ttk.Frame(sub); sub.add(game,text="Gameplay"); sub.add(persist,text="Persistence")
        box=tk.LabelFrame(game,text=" Simulation ",bg=W95["face"],font=("MS Sans Serif",9,"bold")); box.pack(fill="x",padx=10,pady=10)
        self.ai_check2=ttk.Checkbutton(box,text="Let the neural commander control my faction",variable=self.ai_var,command=self._toggle_ai); self.ai_check2.pack(anchor="w",padx=10,pady=8)
        self.side_info=ttk.Label(box,text="",justify="left"); self.side_info.pack(anchor="w",padx=10,pady=(0,8))
        pbox=tk.LabelFrame(persist,text=" Automatic Saves ",bg=W95["face"],font=("MS Sans Serif",9,"bold")); pbox.pack(fill="x",padx=10,pady=10)
        self.persist=ttk.Label(pbox,text="",justify="left"); self.persist.pack(anchor="w",padx=10,pady=10)
        ttk.Button(pbox,text="Reset Neural Brain",command=self.reset_brain).pack(anchor="w",padx=10,pady=(0,10))

    def _statusbar(self) -> None:
        bar=tk.Frame(self.root,bg=W95["face"],bd=2,relief="sunken"); bar.pack(fill="x",padx=4,pady=(0,4))
        self.status=tk.Label(bar,text="Ready",bg=W95["face"],anchor="w",font=("MS Sans Serif",8)); self.status.pack(side="left",fill="x",expand=True,padx=4)
        self.save_status=tk.Label(bar,text="Autosave: pending",bg=W95["face"],font=("MS Sans Serif",8),bd=1,relief="sunken",width=28); self.save_status.pack(side="left",padx=2)
        self.brain_label=tk.Label(bar,text="Brain: loaded",bg=W95["face"],font=("MS Sans Serif",8),bd=1,relief="sunken",width=24); self.brain_label.pack(side="left",padx=2)

    def _sync_side(self) -> None:
        side=self.sim.player_side
        self.ai_var.set(self.sim.player_ai_enabled)
        self.title_label.configure(text=f"▣  GATEWAY TO CAEN — {side.upper()} TACTICAL COMMAND")
        self.ai_check.configure(text=f"{side} AI Commander")
        self.order_help.configure(text=f"1. Select one or more {side} formations.\n2. Choose an order.\n3. Right-click the tactical map to set a destination.\n4. Fog conceals enemy units outside friendly vision.\n5. Axis maps are mirrored so your force remains on the left.")
        self.side_info.configure(text=f"Player command: {side}\nEnemy neural command: {self.sim.enemy_side}\nEnemy decisions occur every 2 simulated seconds.")

    def _load_startup(self) -> None:
        if not self.save_path.exists(): return
        try:
            self.sim.load_dict(read_json(self.save_path, {})); self.last_save="Loaded autosave"; self.sim.log("Command","Autosave restored successfully.")
        except (ValueError,TypeError,KeyError): self.sim.log("Command","Autosave invalid; fresh battle started.")

    def _game_loop(self) -> None:
        if not self.running: return
        now=time.perf_counter(); real_dt=min(0.25,now-self.last_tick); self.last_tick=now
        if not self.paused:
            if self.sim.battle_over:
                if self.sim.advance_post_battle(real_dt): self._new_map_state("New procedural map deployed automatically.")
            else: self.sim.tick(real_dt*self.speed)
        self.root.after(self.TICK_MS,self._game_loop)

    def _draw_loop(self) -> None:
        if not self.running: return
        self.anim_time=time.perf_counter(); self.draw(); self.root.after(self.DRAW_MS,self._draw_loop)

    def _refresh_loop(self) -> None:
        if not self.running: return
        self._header(); self._detail(); self._roster(); self._contacts(); self._objective_list(); self._overview(); self._brain(); self._events(); self._persistence()
        self.root.after(self.REFRESH_MS,self._refresh_loop)

    def _mx(self,x:float,width:float,cell:float,center:bool=True)->float:
        px=(x+(0.5 if center else 0.0))*cell
        return width-px if self.sim.player_side=="Axis" else px

    def _tile_rect(self,x:int,y:int,w:float,h:float,cw:float,ch:float)->tuple[float,float,float,float]:
        x1=w-(x+1)*cw if self.sim.player_side=="Axis" else x*cw
        return x1,y*ch,x1+cw,(y+1)*ch

    def draw(self) -> None:
        c=self.canvas; w,h=max(1,c.winfo_width()),max(1,c.winfo_height()); cw,ch=w/MAP_WIDTH,h/MAP_HEIGHT; c.delete("all")
        visible=self.sim.current_visible_tiles(self.sim.player_side); explored=self.sim.explored_tiles[self.sim.player_side]
        for y,row in enumerate(self.sim.terrain):
            for x,t in enumerate(row):
                x1,y1,x2,y2=self._tile_rect(x,y,w,h,cw,ch); c.create_rectangle(x1,y1,x2+1,y2+1,fill=TERRAIN.get(t,"#777"),outline="")
                seed=(x*37+y*91+self.sim.seed)%11
                if t=="woods" and cw>18:
                    for ox,oy in ((.27,.35),(.62,.25),(.52,.68)):
                        c.create_oval(x1+cw*(ox-.09),y1+ch*(oy-.12),x1+cw*(ox+.09),y1+ch*(oy+.12),fill="#214b24",outline="#163719")
                elif t=="village" and cw>20:
                    c.create_rectangle(x1+cw*.22,y1+ch*.32,x1+cw*.68,y1+ch*.75,fill="#4a3a32",outline="#251b17"); c.create_polygon(x1+cw*.16,y1+ch*.34,x1+cw*.45,y1+ch*.12,x1+cw*.74,y1+ch*.34,fill="#743c31",outline="#2b1b18")
                elif t=="hedge": c.create_line(x1,y1+ch*.55,x2,y1+ch*.55,fill="#263f21",width=max(2,int(ch*.10)))
                elif t=="mud" and seed%3==0: c.create_oval(x1+cw*.2,y1+ch*.55,x1+cw*.65,y1+ch*.72,fill="#5a4d38",outline="")
                if (x,y) not in explored: c.create_rectangle(x1,y1,x2+1,y2+1,fill="#070907",outline="")
                elif (x,y) not in visible: c.create_rectangle(x1,y1,x2+1,y2+1,fill="#111811",stipple="gray50",outline="")
        for p in self.sim.control_points:
            if (p.x,p.y) not in explored: continue
            px,py=self._mx(p.x,w,cw), (p.y+.5)*ch
            known=(p.x,p.y) in visible; owner=p.owner if known else "Neutral"; color=W95[owner.lower()] if owner in ("Allied","Axis") else W95["neutral"]
            r=max(7,min(cw,ch)*.33); c.create_polygon(px,py-r,px+r,py,px,py+r,px-r,py,fill="#ffff4d" if known else "#8c8c4d",outline=color,width=3)
            c.create_text(px,py+r+8,text=p.name if known else "?",fill="white",font=("MS Sans Serif",7,"bold"))
        for u in self.sim.living_units():
            if u.side!=self.sim.player_side and not self.sim.is_unit_visible(u,self.sim.player_side): continue
            self._draw_unit(c,u,w,h,cw,ch)
        self._draw_effects(c,w,cw,ch)
        if self.hover:
            x,y=self.hover; c.create_rectangle(*self._tile_rect(x,y,w,h,cw,ch),outline="white",width=2)
        if self.sim.battle_over:
            remain=math.ceil(self.sim.seconds_until_next_battle); c.create_rectangle(w*.20,h*.36,w*.80,h*.64,fill=W95["face"],outline="white",width=3)
            c.create_text(w/2,h*.45,text="BATTLE CONCLUDED",font=("MS Sans Serif",18,"bold")); c.create_text(w/2,h*.53,text=f"{self.sim.winner} victory",fill=W95["navy"],font=("MS Sans Serif",14,"bold")); c.create_text(w/2,h*.59,text=f"Next map in {remain} second{'s' if remain!=1 else ''}",font=("MS Sans Serif",10,"bold"))

    def _draw_unit(self,c:tk.Canvas,u,w,h,cw,ch)->None:
        x,y=self._mx(u.x,w,cw),(u.y+.5)*ch; r=max(8,min(cw,ch)*.34); selected=u.uid in self.selected
        heading=math.pi-u.heading if self.sim.player_side=="Axis" else u.heading
        bob=math.sin(self.anim_time*10+hash(u.uid)%10)*min(1.5,u.speed*1.8); y+=bob
        color=W95[u.side.lower()]; outline="#ffff00" if selected else "white"
        if selected:
            pulse=r+4+math.sin(self.anim_time*5)*2; c.create_oval(x-pulse,y-pulse,x+pulse,y+pulse,outline="#ffff00",width=2)
        if u.unit_type=="Armour":
            c.create_rectangle(x-r,y-r*.65,x+r,y+r*.65,fill=color,outline=outline,width=2); c.create_oval(x-r*.38,y-r*.38,x+r*.38,y+r*.38,fill="#4e5c39",outline="black")
            c.create_line(x,y,x+math.cos(heading)*r*1.45,y+math.sin(heading)*r*1.45,fill="black",width=3)
        else:
            shape=(x-r,y-r,x+r,y+r)
            if u.unit_type=="Support": c.create_rectangle(*shape,fill=color,outline=outline,width=2)
            else: c.create_oval(*shape,fill=color,outline=outline,width=2)
            symbol={"Rifle":"R","Support":"MG","Scout":"S","Mortar":"M"}.get(u.unit_type,"U"); c.create_text(x,y,text=symbol,fill="white",font=("Arial",7,"bold"))
            c.create_line(x,y,x+math.cos(heading)*r*.9,y+math.sin(heading)*r*.9,fill="#ffffaa",arrow="last")
        c.create_text(x,y-r-7,text=u.name if selected else "",fill="white",font=("MS Sans Serif",7,"bold"))
        barw=r*2; by=y+r+3
        c.create_rectangle(x-r,by,x+r,by+4,fill="#380000",outline=""); c.create_rectangle(x-r,by,x-r+barw*u.strength,by+4,fill="#20c020",outline="")
        c.create_rectangle(x-r,by+5,x+r,by+8,fill="#202020",outline=""); c.create_rectangle(x-r,by+5,x-r+barw*(u.morale/100),by+8,fill="#4e9dff",outline="")
        if u.suppression>20: c.create_arc(x-r-3,y-r-3,x+r+3,y+r+3,start=90,extent=-360*(u.suppression/100),style="arc",outline="#ff8c00",width=2)
        if self.sim.elapsed-u.last_fire<.18: c.create_oval(x+math.cos(heading)*r*1.1-3,y+math.sin(heading)*r*1.1-3,x+math.cos(heading)*r*1.1+3,y+math.sin(heading)*r*1.1+3,fill="#fff200",outline="#ff7b00")
        if selected and u.target_x is not None and u.target_y is not None:
            tx,ty=self._mx(u.target_x,w,cw),(u.target_y+.5)*ch; c.create_line(x,y,tx,ty,fill="#ffff00",dash=(4,3),arrow="last")

    def _draw_effects(self,c,w,cw,ch)->None:
        for e in self.sim.effects:
            x1,y1=self._mx(e.x1,w,cw),(e.y1+.5)*ch; x2,y2=self._mx(e.x2,w,cw),(e.y2+.5)*ch; p=e.progress
            if e.kind=="tracer": c.create_line(x1,y1,x1+(x2-x1)*p,y1+(y2-y1)*p,fill="#fff36b",width=2)
            elif e.kind=="shell":
                px=x1+(x2-x1)*p; py=y1+(y2-y1)*p-math.sin(math.pi*p)*max(18,abs(x2-x1)*.12); c.create_oval(px-3,py-3,px+3,py+3,fill="#202020",outline="#ff9b32")
            else:
                radius=(8+22*math.sin(math.pi*min(1,p)))*(1 if e.kind=="impact" else 1.4); c.create_oval(x1-radius,y1-radius,x1+radius,y1+radius,fill="#ff9b24" if p<.45 else "#4b4b4b",outline="#ffe45e",stipple="gray50")

    def _from_canvas(self,e:tk.Event)->tuple[float,float]:
        raw=e.x/max(1,self.canvas.winfo_width())*MAP_WIDTH; x=MAP_WIDTH-raw if self.sim.player_side=="Axis" else raw
        return clamp(x,0,MAP_WIDTH-.001),clamp(e.y/max(1,self.canvas.winfo_height())*MAP_HEIGHT,0,MAP_HEIGHT-.001)

    def _left(self,e:tk.Event)->None:
        x,y=self._from_canvas(e); nearby=[u for u in self.sim.living_units(self.sim.player_side) if distance((u.x,u.y),(x,y))<=.8]
        if not nearby: self.selected.clear(); return
        u=min(nearby,key=lambda z:distance((z.x,z.y),(x,y)))
        if not e.state&1: self.selected.clear()
        if u.uid in self.selected and e.state&1: self.selected.remove(u.uid)
        else: self.selected.add(u.uid)

    def _right(self,e:tk.Event)->None:
        x,y=self._from_canvas(e); ids=[uid for uid in self.selected if (u:=self.sim.unit_by_id(uid)) and u.alive and u.side==self.sim.player_side]
        if not ids: self.status.configure(text=f"Select at least one {self.sim.player_side} unit first."); return
        first=self.sim.unit_by_id(ids[0]); current=first.order if first and first.order in ("Assault","Flank","Retreat") else "Advance"
        self.sim.issue_order(ids,current,x,y); self.status.configure(text=f"{current} to grid {int(x):02d},{int(y):02d} issued to {len(ids)} unit(s).")

    def _motion(self,e:tk.Event)->None:
        x,y=self._from_canvas(e); self.hover=(int(x),int(y)); t=self.sim.tile_at(x,y); visible=(int(x),int(y)) in self.sim.current_visible_tiles(self.sim.player_side)
        self.hint.configure(text=f"Grid {int(x):02d},{int(y):02d} — {t.title()} — cover {int(TERRAIN_COVER[t]*100)}%\n{'Visible' if visible else 'Fogged'} terrain; right-click destination.")

    def _roster_select(self,_e:tk.Event)->None:
        self.selected={uid for uid in self.roster.selection() if self.sim.unit_by_id(uid)}
        if self.selected: self.tabs.select(self.battle_tab)

    def order(self,name:str)->None:
        ids=[uid for uid in self.selected if (u:=self.sim.unit_by_id(uid)) and u.alive and u.side==self.sim.player_side]
        if not ids: self.status.configure(text=f"Select living {self.sim.player_side} units."); return
        self.sim.issue_order(ids,name); self.status.configure(text=f"{name} issued to {len(ids)} {self.sim.player_side} unit(s).")

    def _header(self)->None:
        m,s=divmod(int(self.sim.elapsed),60); self.clock.configure(text=f"T+ {m:02d}:{s:02d}")
        suffix=" [PAUSED]" if self.paused else ""; self.operation.configure(text=f"{self.sim.operation_name} | {self.sim.weather} | {self.sim.player_side}{suffix}")
        visible=len(self.sim.visible_enemy_units(self.sim.player_side)); self.status.configure(text=f"{self.sim.player_side} score {self.sim.battle_score(self.sim.player_side)} | Visible enemy contacts {visible} | Selected {len(self.selected)}")

    def _detail(self)->None:
        units=[u for uid in self.selected if (u:=self.sim.unit_by_id(uid))]
        if not units: text="No unit selected.\n\nSelect a friendly formation on the map or roster."
        elif len(units)>1: text=f"GROUP SELECTION\n\nUnits: {len(units)}\nPersonnel: {sum(u.men for u in units)}\nAverage morale: {sum(u.morale for u in units)/len(units):.0f}%"
        else:
            u=units[0]; text=f"{u.name}\n{'='*min(28,len(u.name))}\nSide:       {u.side}\nType:       {u.unit_type}\nPersonnel:  {u.men}/{u.max_men}\nMorale:     {u.morale:5.1f}%\nAmmo:       {u.ammo:5.1f}%\nSuppression:{u.suppression:5.1f}%\nSpeed:      {u.speed:5.2f}\nOrder:      {u.order}\nStance:     {u.stance}\nKills:      {u.kills}\nGrid:       {u.x:04.1f},{u.y:04.1f}"
        self._text(self.detail,text)

    def _roster(self)->None:
        existing=set(self.roster.get_children()); friend_ids={u.uid for u in self.sim.units if u.side==self.sim.player_side}
        for iid in existing-friend_ids: self.roster.delete(iid)
        for u in [x for x in self.sim.units if x.side==self.sim.player_side]:
            values=(u.unit_type,f"{u.men}/{u.max_men}",f"{u.morale:.0f}%",f"{u.ammo:.0f}%",f"{u.suppression:.0f}%",u.order)
            if self.roster.exists(u.uid): self.roster.item(u.uid,text=u.name,values=values)
            else: self.roster.insert("","end",iid=u.uid,text=u.name,values=values)
        self.roster.selection_set([uid for uid in self.selected if self.roster.exists(uid)])

    def _contacts(self)->None:
        self.contacts.delete(*self.contacts.get_children()); friends=self.sim.living_units(self.sim.player_side)
        for u in self.sim.visible_enemy_units(self.sim.player_side):
            near=min((distance((u.x,u.y),(f.x,f.y)) for f in friends),default=99.0); self.contacts.insert("","end",text=u.name,values=(u.unit_type,f"{u.men}/{u.max_men}",f"{near:.1f}","Engaged" if near<=7 else "Observed"))

    def _objective_list(self)->None:
        self.objectives.delete(*self.objectives.get_children()); visible=self.sim.current_visible_tiles(self.sim.player_side); explored=self.sim.explored_tiles[self.sim.player_side]
        for p in self.sim.control_points:
            if (p.x,p.y) not in explored: owner,capture="Unknown","Unknown"
            elif (p.x,p.y) not in visible: owner,capture="Last known / obscured","—"
            else: owner,capture=p.owner,f"{p.capture:+.0f}%"
            self.objectives.insert("","end",text=p.name,values=(owner,p.value,capture))

    def _overview(self)->None:
        friends=self.sim.living_units(self.sim.player_side); contacts=self.sim.visible_enemy_units(self.sim.player_side); visible=self.sim.current_visible_tiles(self.sim.player_side); explored=self.sim.explored_tiles[self.sim.player_side]
        known=[]
        for p in self.sim.control_points:
            owner=p.owner if (p.x,p.y) in visible else "Obscured" if (p.x,p.y) in explored else "Unknown"; known.append(f"  {p.name:<18} {owner:<10} {p.value:3d} pts")
        state=f"CONCLUDED — {self.sim.winner}; next map in {self.sim.seconds_until_next_battle:.1f}s" if self.sim.battle_over else "IN PROGRESS"
        text=f"OPERATIONAL OVERVIEW\n{'='*60}\nOperation: {self.sim.operation_name}\nCommand:   {self.sim.player_side}\nWeather:   {self.sim.weather}\nSeed:      {self.sim.seed}\n\nFRIENDLY FORCE\n{'-'*60}\nActive formations: {len(friends)}\nPersonnel:        {sum(u.men for u in friends)}\nScore:            {self.sim.battle_score(self.sim.player_side)}\n\nINTELLIGENCE\n{'-'*60}\nVisible enemy contacts: {len(contacts)}\nExplored terrain: {len(explored)}/{MAP_WIDTH*MAP_HEIGHT} tiles\n\nOBJECTIVES\n{'-'*60}\n"+"\n".join(known)+f"\n\nBattle status: {state}"
        self._text(self.overview,text)

    def _brain(self)->None:
        st=self.brain.stats; total=st.wins+st.losses; rate=st.wins/total*100 if total else 0
        text=f"TACTICAL NEURAL BRAIN\n{'='*48}\nArchitecture:       {self.brain.input_size}-{self.brain.hidden_size}-{self.brain.output_size}\nLearning rate:      {self.brain.learning_rate:.4f}\nExploration rate:   {self.brain.epsilon:.3f}\nEnemy command:      {self.sim.enemy_side}\nPlayer AI enabled:  {'Yes' if self.sim.player_ai_enabled else 'No'}\nDecisions:          {st.decisions:,}\nTraining steps:     {st.training_steps:,}\nLifetime reward:    {st.lifetime_reward:+.3f}\nAI wins / losses:   {st.wins} / {st.losses}\nAI win rate:        {rate:.1f}%\nLast action:        {self.brain.last_action}\nLast train error:   {self.sim.last_training_error:.5f}\nBrain file:         {self.brain_path}"
        self._text(self.brain_status,text); self.decisions.delete(*self.decisions.get_children())
        for i,a in enumerate(ACTIONS): self.decisions.insert("","end",text=a.title(),values=(f"{self.brain.last_q_values[i]:+.5f}",f"{st.action_counts.get(a,0):,}"))
        self._text(self.training,"The neural commander evaluates strength, morale, ammunition, suppression, enemy and objective distance, local force density, cover, and map progress. Every two simulated seconds it chooses Advance, Flank, Hold, Retreat, or Assault. Weights and lifetime statistics persist across maps and sessions.")
        self.brain_label.configure(text=f"Brain: {st.training_steps:,} training steps")

    def _events(self)->None:
        if self.event_cursor>len(self.sim.events): self.event_cursor=0; self._text(self.diary,"")
        if self.event_cursor==len(self.sim.events): return
        self.diary.configure(state="normal")
        for e in self.sim.events[self.event_cursor:]:
            m,s=divmod(int(e.timestamp),60); self.diary.insert("end",f"[{m:02d}:{s:02d}] {e.category.upper():<10} {e.text}\n",e.category)
        self.event_cursor=len(self.sim.events); self.diary.see("end"); self.diary.configure(state="disabled")

    def _persistence(self)->None:
        self.persist.configure(text=f"Game autosave: every 5 seconds\nBrain autosave: every 10 seconds\nMap rotation: 10 seconds after battle end\nPlayer side: {self.sim.player_side}\nLast status: {self.last_save}\n\nGame: {self.save_path}\nBrain: {self.brain_path}")

    @staticmethod
    def _text(widget:tk.Text,value:str)->None:
        widget.configure(state="normal"); widget.delete("1.0","end"); widget.insert("1.0",value); widget.configure(state="disabled")

    def _autosave_game(self)->None:
        if self.running: self.save(silent=True); self.root.after(self.GAME_SAVE_MS,self._autosave_game)

    def _autosave_brain(self)->None:
        if not self.running: return
        try: self.brain.save(self.brain_path); self.last_save=f"Brain saved at {time.strftime('%H:%M:%S')}"
        except OSError as e: self.brain_label.configure(text=f"Brain save failed: {e}")
        self.root.after(self.BRAIN_SAVE_MS,self._autosave_brain)

    def save(self,silent:bool=False)->None:
        try:
            atomic_write_json(self.save_path,self.sim.to_dict()); self.settings.update(speed=self.speed,player_side=self.sim.player_side); atomic_write_json(self.settings_path,self.settings)
            self.last_save=f"Game saved at {time.strftime('%H:%M:%S')}"; self.save_status.configure(text=self.last_save)
            if not silent: messagebox.showinfo("Save Game",f"Game saved successfully.\n\n{self.save_path}",parent=self.root)
        except OSError as e:
            self.save_status.configure(text="Autosave failed")
            if not silent: messagebox.showerror("Save Error",str(e),parent=self.root)

    def load(self)->None:
        try: self.sim.load_dict(read_json(self.save_path,{})); self.selected.clear(); self.event_cursor=0; self._sync_side(); self.status.configure(text="Autosave loaded.")
        except (ValueError,TypeError,KeyError): messagebox.showerror("Load Error","The autosave could not be loaded.",parent=self.root)

    def _new_map_state(self,message:str)->None:
        self.selected.clear(); self.hover=None; self.event_cursor=0; self.save(silent=True); self.status.configure(text=message)

    def new_battle(self)->None:
        if messagebox.askyesno("New Battle",f"Start a new procedural battle as {self.sim.player_side}?\n\nThe neural brain and side are preserved.",parent=self.root): self.sim.new_battle(); self._new_map_state("New battle started.")

    def new_save(self)->None:
        if self.save_path.exists() and not messagebox.askyesno("New Save","Replace the current autosaved battle?\n\nThe neural brain is preserved.",parent=self.root): return
        side=self._choose_side(self.sim.player_side); self.sim.set_player_side(side); self.sim.new_battle(); self.settings["player_side"]=side; self._sync_side(); self._new_map_state(f"New {side} command save created.")

    def toggle_pause(self)->None:
        self.paused=not self.paused; self.last_tick=time.perf_counter(); self.status.configure(text="Simulation paused." if self.paused else "Simulation resumed.")

    def _speed(self,_e:tk.Event|None=None)->None:
        try: self.speed=float(self.speed_var.get())
        except ValueError: self.speed=1.0
        self.settings["speed"]=self.speed; atomic_write_json(self.settings_path,self.settings)

    def _toggle_ai(self)->None:
        self.sim.player_ai_enabled=bool(self.ai_var.get()); self.status.configure(text=f"{self.sim.player_side} AI Commander {'enabled' if self.sim.player_ai_enabled else 'disabled'}.")

    def reset_brain(self)->None:
        if messagebox.askyesno("Reset Neural Brain","Erase all learned neural weights and lifetime statistics?",parent=self.root): self.brain=TacticalBrain(); self.sim.brain=self.brain; self.brain.save(self.brain_path); self.status.configure(text="Neural brain reset.")

    def controls(self)->None:
        messagebox.showinfo("Controls",f"Left-click: select a visible {self.sim.player_side} unit\nShift + left-click: multi-select\nRight-click: move selected units\n\nAxis maps are mirrored. Fog conceals enemy contacts. A new map begins automatically ten seconds after battle end.",parent=self.root)

    def about(self)->None:
        messagebox.showinfo("About","Gateway to Caen: Tactical Command\nVersion 0.2.0\n\nAn original clean-room tactical game built with Python and Tkinter. No proprietary code or assets are included.",parent=self.root)

    def close(self)->None:
        self.running=False
        try:
            atomic_write_json(self.save_path,self.sim.to_dict()); self.brain.save(self.brain_path); self.settings.update(speed=self.speed,player_side=self.sim.player_side); atomic_write_json(self.settings_path,self.settings)
        finally: self.root.destroy()


def run()->None:
    root=tk.Tk(); TacticalCommandApp(root); root.mainloop()
