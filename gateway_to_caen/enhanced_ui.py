"""Offline-progress and enhanced-graphics application entry point."""
from __future__ import annotations

import time
import tkinter as tk
from tkinter import messagebox, ttk

from .graphics import EnhancedGraphicsMixin
from .neural import TacticalBrain
from .offline import (
    OfflineRewards,
    claim_offline_progress,
    dismiss_pending_report,
    format_duration,
    touch_profile,
)
from .persistence import user_data_dir
from .ui import TacticalCommandApp as BaseTacticalCommandApp, W95


class TacticalCommandApp(EnhancedGraphicsMixin, BaseTacticalCommandApp):
    """Version 0.3 application with offline progress and richer rendering."""

    def __init__(self, root: tk.Tk) -> None:
        data_dir = user_data_dir()
        self.profile_path = data_dir / "campaign_profile.json"
        self.profile, self.offline_report = claim_offline_progress(self.profile_path)
        self.terrain_signature: tuple[int, int, int, str] | None = None
        self.fog_signature: tuple[object, ...] | None = None
        super().__init__(root)
        if self.offline_report is not None:
            root.after(180, self._show_offline_report)

    def _toolbar(self) -> None:
        super()._toolbar()
        toolbar = self.operation.master
        self.wallet_label = ttk.Label(toolbar, text="CP 0 | SUP 0", font=("MS Sans Serif", 8, "bold"))
        self.wallet_label.pack(side="right", padx=8)

    def _options(self) -> None:
        sub = ttk.Notebook(self.options_tab)
        sub.pack(fill="both", expand=True, padx=4, pady=4)
        game, persist, campaign = ttk.Frame(sub), ttk.Frame(sub), ttk.Frame(sub)
        sub.add(game, text="Gameplay")
        sub.add(persist, text="Persistence")
        sub.add(campaign, text="Campaign")

        box = tk.LabelFrame(game, text=" Simulation ", bg=W95["face"], font=("MS Sans Serif", 9, "bold"))
        box.pack(fill="x", padx=10, pady=10)
        self.ai_check2 = ttk.Checkbutton(
            box,
            text="Let the neural commander control my faction",
            variable=self.ai_var,
            command=self._toggle_ai,
        )
        self.ai_check2.pack(anchor="w", padx=10, pady=8)
        self.side_info = ttk.Label(box, text="", justify="left")
        self.side_info.pack(anchor="w", padx=10, pady=(0, 8))

        pbox = tk.LabelFrame(persist, text=" Automatic Saves ", bg=W95["face"], font=("MS Sans Serif", 9, "bold"))
        pbox.pack(fill="x", padx=10, pady=10)
        self.persist = ttk.Label(pbox, text="", justify="left")
        self.persist.pack(anchor="w", padx=10, pady=10)
        ttk.Button(pbox, text="Reset Neural Brain", command=self.reset_brain).pack(anchor="w", padx=10, pady=(0, 10))

        cbox = tk.LabelFrame(campaign, text=" Offline Command Rewards ", bg=W95["face"], font=("MS Sans Serif", 9, "bold"))
        cbox.pack(fill="x", padx=10, pady=10)
        self.campaign_info = ttk.Label(cbox, text="", justify="left", font=("Courier New", 10))
        self.campaign_info.pack(anchor="w", padx=10, pady=10)
        ttk.Button(cbox, text="Show Pending Offline Report", command=self._show_offline_report).pack(anchor="w", padx=10, pady=(0, 10))

    def _statusbar(self) -> None:
        super()._statusbar()
        bar = self.brain_label.master
        self.reward_status = tk.Label(
            bar,
            text="Offline rewards: ready",
            bg=W95["face"],
            font=("MS Sans Serif", 8),
            bd=1,
            relief="sunken",
            width=24,
        )
        self.reward_status.pack(side="left", padx=2)

    def _refresh_loop(self) -> None:
        if not self.running:
            return
        super()._refresh_loop()
        self._campaign()

    def _header(self) -> None:
        super()._header()
        self.wallet_label.configure(
            text=(
                f"CP {self.profile.command_points:,} | "
                f"SUP {self.profile.supplies:,} | "
                f"RT {self.profile.reinforcement_tokens:,}"
            )
        )

    def _persistence(self) -> None:
        self.persist.configure(
            text=(
                "Game autosave: every 5 seconds\n"
                "Brain autosave: every 10 seconds\n"
                "Offline timestamp: every game save\n"
                "Map rotation: 10 seconds after battle end\n"
                f"Player side: {self.sim.player_side}\n"
                f"Last status: {self.last_save}\n\n"
                f"Game: {self.save_path}\n"
                f"Brain: {self.brain_path}\n"
                f"Campaign: {self.profile_path}"
            )
        )

    def _campaign(self) -> None:
        pending = "Yes — open the report to dismiss it" if self.profile.pending_report else "No"
        self.campaign_info.configure(
            text=(
                f"CAMPAIGN RESERVES\n{'=' * 42}\n"
                f"Command Points:       {self.profile.command_points:,}\n"
                f"Supplies:             {self.profile.supplies:,}\n"
                f"Reinforcement Tokens: {self.profile.reinforcement_tokens:,}\n"
                f"Intelligence Reports: {self.profile.intelligence_reports:,}\n\n"
                f"Lifetime offline:     {format_duration(self.profile.lifetime_offline_seconds)}\n"
                f"Sessions started:     {self.profile.sessions:,}\n"
                f"Pending report:       {pending}\n\n"
                "Reward rates: 1 Command Point/minute, 1 Supply/10 seconds, "
                "1 Reinforcement Token/30 minutes, and 1 Intelligence Report/hour. "
                "Rewarded offline time is capped at 30 days per claim."
            )
        )
        self.reward_status.configure(text=f"Offline: {self.profile.command_points:,} CP")

    def _show_offline_report(self) -> None:
        report = self.offline_report
        if report is None and self.profile.pending_report:
            report = OfflineRewards.from_dict(self.profile.pending_report)
        if report is None or report.offline_seconds <= 0:
            messagebox.showinfo("Offline Progress", "There is no pending offline progress report.", parent=self.root)
            return

        window = tk.Toplevel(self.root)
        window.title("Offline Progress — Command Report")
        window.configure(bg=W95["face"])
        window.resizable(False, False)
        window.transient(self.root)
        window.grab_set()
        tk.Label(
            window,
            text="▣  OFFLINE COMMAND REPORT",
            bg=W95["navy"],
            fg="white",
            font=("MS Sans Serif", 11, "bold"),
            anchor="w",
        ).pack(fill="x", padx=3, pady=3)

        body = tk.Frame(window, bg=W95["face"], bd=2, relief="sunken")
        body.pack(fill="both", expand=True, padx=10, pady=8)
        tk.Label(
            body,
            text="WELCOME BACK, COMMANDER",
            bg="#ffffff",
            fg=W95["navy"],
            font=("MS Sans Serif", 13, "bold"),
        ).pack(fill="x", padx=2, pady=(2, 0))
        tk.Label(
            body,
            text=f"You were offline for\n{format_duration(report.offline_seconds)}",
            bg="#ffffff",
            fg="#000000",
            font=("MS Sans Serif", 10, "bold"),
            justify="center",
        ).pack(fill="x", padx=2, pady=(6, 10))

        rewards = tk.Frame(body, bg="#ffffff")
        rewards.pack(fill="x", padx=2, pady=2)
        rows = (
            ("Command Points", report.command_points, "CP"),
            ("Supplies", report.supplies, "SUP"),
            ("Reinforcement Tokens", report.reinforcement_tokens, "RT"),
            ("Intelligence Reports", report.intelligence_reports, "INT"),
        )
        for index, (name, amount, code) in enumerate(rows):
            shade = "#edf2ff" if index % 2 == 0 else "#ffffff"
            row = tk.Frame(rewards, bg=shade, bd=1, relief="groove")
            row.pack(fill="x", padx=8, pady=2)
            tk.Label(row, text=code, width=5, bg=W95["navy"], fg="white", font=("Courier New", 9, "bold")).pack(side="left", padx=4, pady=4)
            tk.Label(row, text=name, bg=shade, anchor="w", font=("MS Sans Serif", 9, "bold")).pack(side="left", fill="x", expand=True, padx=8)
            tk.Label(row, text=f"+{amount:,}", bg=shade, fg="#006000", font=("Courier New", 11, "bold")).pack(side="right", padx=10)

        note = "Rewards have already been added to your campaign reserves."
        if report.capped:
            note += " Reward generation was capped at 30 days for this claim."
        tk.Label(body, text=note, bg="#ffffff", fg="#404040", wraplength=500, justify="left").pack(fill="x", padx=12, pady=10)

        def dismiss() -> None:
            dismiss_pending_report(self.profile_path, self.profile)
            self.offline_report = None
            try:
                window.grab_release()
            except tk.TclError:
                pass
            window.destroy()
            self.status.configure(text="Offline rewards claimed and report dismissed.")

        buttons = tk.Frame(window, bg=W95["face"])
        buttons.pack(fill="x", padx=10, pady=(0, 10))
        ttk.Button(buttons, text="Dismiss Report", command=dismiss, width=18).pack(side="right")
        window.protocol("WM_DELETE_WINDOW", dismiss)
        window.update_idletasks()
        x = self.root.winfo_rootx() + max(40, (self.root.winfo_width() - window.winfo_reqwidth()) // 2)
        y = self.root.winfo_rooty() + max(40, (self.root.winfo_height() - window.winfo_reqheight()) // 2)
        window.geometry(f"+{x}+{y}")
        self.root.wait_window(window)

    def save(self, silent: bool = False) -> None:
        super().save(silent=silent)
        try:
            touch_profile(self.profile_path, self.profile)
        except OSError as error:
            self.reward_status.configure(text=f"Offline save failed: {error}")

    def load(self) -> None:
        super().load()
        self.terrain_signature = None
        self.fog_signature = None

    def _new_map_state(self, message: str) -> None:
        self.terrain_signature = None
        self.fog_signature = None
        super()._new_map_state(message)

    def about(self) -> None:
        messagebox.showinfo(
            "About",
            "Gateway to Caen: Tactical Command\nVersion 0.3.0\n\n"
            "An original clean-room tactical game built with Python and Tkinter. "
            "No proprietary code or assets are included.",
            parent=self.root,
        )

    def close(self) -> None:
        try:
            touch_profile(self.profile_path, self.profile)
        finally:
            super().close()


def run() -> None:
    root = tk.Tk()
    TacticalCommandApp(root)
    root.mainloop()
