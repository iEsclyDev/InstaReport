"""Main application window — dashboard, tabbed module browser, controls, console."""
import tkinter as tk
from tkinter import ttk, messagebox
from typing import Any, Callable
import os, sys, json, threading, time, webbrowser
from datetime import datetime

from instareport.ui.theme import (
    BG_DARK, BG_CARD, BG_INPUT, FG_PRIMARY, FG_SECONDARY, FG_DIM,
    ACCENT_GREEN, ACCENT_PINK, ACCENT_BLUE, ACCENT_AMBER, ACCENT_PURPLE,
    BORDER, SCROLL_TROUGH, SCROLL_THUMB, TAG_COLORS,
    FONT, H1, H2, H3, BODY, SMALL, MONO,
    DesignSystem as DS,
)
from instareport.ui.widgets import (
    GradientCanvas, ModuleCard, ConsoleWidget, LoadingSpinner,
    _tool_win, LabeledSeparator,
)
from instareport.ui.dialogs import TOOL_DISPATCH
from instareport.ui.accounts_manager import AccountsManager
from instareport.ui.plugin_manager import PluginManager
from instareport.ui.license_window import LicenseWindow
from instareport.core.license import LS
from instareport.core.state import S, GLOBAL_STOP, ACCOUNTS_LOCK, RUN_LOGS_LOCK, CONFIG_LOCK
from instareport.core.config import save_config, _clear_all_cooldowns, export_backup, import_backup
from instareport.core.database import setup_persistence, get_run_logs, get_run_logs_count
from instareport.tools.proxy import PP
from instareport.utils.constants import (
    PLATFORMS, REPORT_REASONS, MODULES, TABS, VERSION, TAG_PATTERNS,
    DEBUG, init_paths, T_PAGE_LOAD, T_POST_CLICK, T_POST_LOGIN,
    T_CAPTCHA_WAIT, T_TELEGRAM_OTP, T_REFRESH_WAIT, T_TYPE_DELAY,
)
from instareport.utils.helpers import (
    _validate_target, _validate_sched_time, _force_reload_accounts,
    _run_async_in_thread, _system_notify,
)
from instareport.utils.logging import log, dlog, flog, init_file_logger
from instareport.engine import run_mass_report, start_scheduler, stop_scheduler


class App(tk.Tk):
    """Main InstaReport application window."""

    def __init__(self) -> None:
        super().__init__()
        self.title(f"InstaReport v{VERSION}")
        self.after(2000, self._check_update)  # check 2s after launch
        self.geometry("1280x800")
        self.configure(bg=BG_DARK)
        self.minsize(1024, 700)
        self._target_e: tk.Entry
        self._plat_cb: ttk.Combobox
        self._reason_cb: ttk.Combobox
        self._workers_e: tk.Entry
        self._run_btn: tk.Button
        self._stop_btn: tk.Button
        self._accounts_btn: tk.Button
        self._stat_total: tk.Label
        self._stat_success: tk.Label
        self._nb: ttk.Notebook
        self._tab_frames: dict[str, tk.Frame] = {}
        self._hist_tree: ttk.Treeview
        self._console: ConsoleWidget
        init_paths()
        init_file_logger()
        setup_persistence()
        S.log_cb = self._on_log
        S.otp_cb = self._on_otp
        S.captcha_cb = self._on_captcha
        self._build_ui()
        self._init_scheduler()
        self._check_license()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── UI construction ────────────────────────────────────────────

    def _build_ui(self) -> None:
        self._header()
        self._controls()
        self._notebook()
        self._footer()

    def _header(self) -> None:
        hdr = GradientCanvas(self, height=90)
        hdr.pack(fill="x")
        hdr.create_text(20, 18, anchor="w", text="InstaReport",
                        font=("Segoe UI", 22, "bold"), fill=ACCENT_GREEN)
        hdr.create_text(20, 50, anchor="w",
                        text=f"v{VERSION}  •  {len(S.accounts)} accounts  •  {PP.count()} proxies",
                        font=SMALL, fill=FG_DIM)
        stats = tk.Frame(hdr, bg=BG_DARK)
        stats.place(relx=1.0, x=-20, y=12, anchor="ne")
        self._stat_total = tk.Label(stats, text="0", font=H1,
                                    fg=ACCENT_GREEN, bg=BG_DARK)
        self._stat_total.pack(side="left", padx=16)
        tk.Label(stats, text="Reports", font=SMALL, fg=FG_DIM,
                 bg=BG_DARK).pack(side="left", padx=(0, 16))
        self._stat_success = tk.Label(stats, text="0%", font=H1,
                                      fg=ACCENT_BLUE, bg=BG_DARK)
        self._stat_success.pack(side="left", padx=16)
        tk.Label(stats, text="Success", font=SMALL, fg=FG_DIM,
                 bg=BG_DARK).pack(side="left")

    def _controls(self) -> None:
        ctrl = tk.Frame(self, bg=BG_CARD, height=50)
        ctrl.pack(fill="x", padx=0, pady=0)
        ctrl.pack_propagate(False)
        inner = tk.Frame(ctrl, bg=BG_CARD)
        inner.pack(padx=10, pady=6, fill="x")

        tk.Label(inner, text="Target:", font=BODY, fg=FG_DIM,
                 bg=BG_CARD).pack(side="left")
        self._target_e = DS.entry(inner, width=20)
        self._target_e.pack(side="left", padx=4)
        self._target_e.bind("<Return>", lambda e: self._set_target())

        tk.Label(inner, text="Platform:", font=BODY, fg=FG_DIM,
                 bg=BG_CARD).pack(side="left", padx=(12, 2))
        self._plat_cb = DS.combo(inner, [p[0] for p in PLATFORMS], width=16)
        self._plat_cb.set(next((p[0] for p in PLATFORMS if p[1] == S.platform), "Instagram"))
        self._plat_cb.pack(side="left", padx=2)
        self._plat_cb.bind("<<ComboboxSelected>>", self._on_plat_change)

        tk.Label(inner, text="Reason:", font=BODY, fg=FG_DIM,
                 bg=BG_CARD).pack(side="left", padx=(12, 2))
        self._reason_cb = DS.combo(inner, [r[0] for r in REPORT_REASONS], width=16)
        reason_idx = next((i for i, r in enumerate(REPORT_REASONS) if r[1] == S.reason), 0)
        self._reason_cb.current(reason_idx)
        self._reason_cb.pack(side="left", padx=2)

        tk.Label(inner, text="Workers:", font=BODY, fg=FG_DIM,
                 bg=BG_CARD).pack(side="left", padx=(12, 2))
        self._workers_e = DS.entry(inner, width=4)
        self._workers_e.insert(0, str(S.workers))
        self._workers_e.pack(side="left", padx=2)
        self._workers_e.bind("<Return>", lambda e: self._set_workers())

        self._run_btn = DS.primary_btn(inner, "▶ Run", command=self._run)
        self._run_btn.pack(side="right", padx=4)
        self._stop_btn = DS.danger_btn(inner, "⏹ STOP", command=self._stop)
        self._stop_btn.pack(side="right", padx=4)
        self._accounts_btn = DS.ghost_btn(inner, "Accounts", command=self._open_accounts)
        self._accounts_btn.pack(side="right", padx=4)

    def _notebook(self) -> None:
        self._nb = ttk.Notebook(self)
        self._nb.pack(fill="both", expand=True, padx=4, pady=4)
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TNotebook", background=BG_DARK, borderwidth=0)
        style.configure("TNotebook.Tab", background=BG_CARD, foreground=FG_SECONDARY,
                        padding=[12, 4], font=FONT(9))
        style.map("TNotebook.Tab", background=[("selected", BG_DARK)],
                  foreground=[("selected", ACCENT_GREEN)])
        self._tab_frames = {}
        for name, _count in TABS:
            frame = tk.Frame(self._nb, bg=BG_DARK)
            self._nb.add(frame, text=f"  {name}  ")
            self._tab_frames[name] = frame
        self._build_tab_favorites()
        self._build_tab_modules("Auto-Ban Engine")
        self._build_tab_modules("Unban Tools")
        self._build_tab_plugins()
        self._build_tab_modules("Lookups")
        self._build_tab_modules("Advanced")
        self._build_tab_history()

    def _build_tab_favorites(self) -> None:
        parent = self._tab_frames["⭐ Favorites"]
        canvas = tk.Canvas(parent, bg=BG_DARK, highlightthickness=0, bd=0)
        scroll = tk.Scrollbar(canvas, orient="vertical", bg=SCROLL_TROUGH,
                              troughcolor=SCROLL_TROUGH, activebackground=SCROLL_THUMB,
                              highlightbackground=BORDER, bd=0, relief="flat", width=10)
        inner_frame = tk.Frame(canvas, bg=BG_DARK)
        canvas.create_window((0, 0), window=inner_frame, anchor="nw", tags="inner")
        canvas.config(yscrollcommand=scroll.set)
        scroll.config(command=canvas.yview)
        canvas.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        def _configure(event: Any) -> None:
            canvas.configure(scrollregion=canvas.bbox("all"))
            canvas.itemconfig("inner", width=event.width)
        canvas.bind("<Configure>", _configure)

        row_frame = None
        for cat, items in MODULES.items():
            for label, status, icon, desc, key in items:
                if key in S.favorites:
                    if row_frame is None or len(row_frame.grid_slaves()) >= 4:
                        row_frame = tk.Frame(inner_frame, bg=BG_DARK)
                        row_frame.pack(fill="x", pady=2, padx=6)
                    card = ModuleCard(row_frame, label, status, icon, desc, key,
                                      callback=lambda k=key: self._dispatch_tool(k),
                                      favorite=True)
                    card.grid(row=0, column=len(row_frame.grid_slaves()), padx=4)

    def _build_tab_modules(self, tab_name: str) -> None:
        parent = self._tab_frames[tab_name]
        canvas = tk.Canvas(parent, bg=BG_DARK, highlightthickness=0, bd=0)
        scroll = tk.Scrollbar(canvas, orient="vertical", bg=SCROLL_TROUGH,
                              troughcolor=SCROLL_TROUGH, activebackground=SCROLL_THUMB,
                              highlightbackground=BORDER, bd=0, relief="flat", width=10)
        inner_frame = tk.Frame(canvas, bg=BG_DARK)
        canvas.create_window((0, 0), window=inner_frame, anchor="nw", tags="inner")
        canvas.config(yscrollcommand=scroll.set)
        scroll.config(command=canvas.yview)
        canvas.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        def _configure(event: Any) -> None:
            canvas.configure(scrollregion=canvas.bbox("all"))
            canvas.itemconfig("inner", width=event.width)
        canvas.bind("<Configure>", _configure)

        items = MODULES.get(tab_name, [])
        row_frame = None
        for label, status, icon, desc, key in items:
            if row_frame is None or len(row_frame.grid_slaves()) >= 4:
                row_frame = tk.Frame(inner_frame, bg=BG_DARK)
                row_frame.pack(fill="x", pady=2, padx=6)
            card = ModuleCard(row_frame, label, status, icon, desc, key,
                              callback=lambda k=key: self._dispatch_tool(k))
            card.grid(row=0, column=len(row_frame.grid_slaves()), padx=4)

    def _build_tab_plugins(self) -> None:
        parent = self._tab_frames["Plugins"]
        DS.label(parent, "Plugin Manager", font=H2).pack(pady=(10, 4))
        from instareport.plugins.loader import get_all_plugins, get_flow_map, discover_plugins
        discover_plugins()
        frame = tk.Frame(parent, bg=BG_CARD)
        frame.pack(fill="both", expand=True, padx=10, pady=6)
        cols = ("Name", "Key", "Status", "Version", "Description")
        tree = ttk.Treeview(frame, columns=cols, show="headings", height=14)
        for c in cols:
            tree.heading(c, text=c)
        tree.column("Name", width=130)
        tree.column("Key", width=120)
        tree.column("Status", width=70)
        tree.column("Version", width=60)
        tree.column("Description", width=280)
        tree.pack(side="left", fill="both", expand=True)
        sb = DS.scrollbar(frame)
        sb.pack(side="right", fill="y")
        tree.config(yscrollcommand=sb.set)
        sb.config(command=tree.yview)
        for p in sorted(get_all_plugins(), key=lambda x: x.display_name):
            status = "● ON" if p.enabled else "○ OFF"
            tree.insert("", "end", values=(p.display_name, p.platform_key, status, p.version, p.description))
        info = tk.Frame(parent, bg=BG_DARK)
        info.pack(fill="x", padx=10, pady=4)
        DS.label(info, f"Total: {len(get_all_plugins())}  |  Active flows: {len(get_flow_map())}",
                 font=SMALL, fg=FG_DIM).pack(side="left")
        DS.ghost_btn(info, "Open Manager…", command=lambda: PluginManager(self),
                     width=14).pack(side="right")

    def _build_tab_history(self) -> None:
        parent = self._tab_frames["Run History"]
        self._hist_page = 0
        self._hist_page_size = 100
        self._hist_date_from = ""
        self._hist_date_to = ""
        self._hist_search = ""

        # Filter bar
        filter_bar = tk.Frame(parent, bg=BG_DARK)
        filter_bar.pack(fill="x", padx=10, pady=(8, 2))
        tk.Label(filter_bar, text="From:", font=SMALL, fg=FG_DIM,
                 bg=BG_DARK).pack(side="left")
        self._hist_from_e = tk.Entry(filter_bar, width=12, bg=BG_INPUT,
                                     fg=FG_PRIMARY, insertbackground=FG_PRIMARY,
                                     relief="flat", font=FONT(9))
        self._hist_from_e.pack(side="left", padx=2)
        self._hist_from_e.insert(0, "")
        tk.Label(filter_bar, text="To:", font=SMALL, fg=FG_DIM,
                 bg=BG_DARK).pack(side="left", padx=(8, 2))
        self._hist_to_e = tk.Entry(filter_bar, width=12, bg=BG_INPUT,
                                   fg=FG_PRIMARY, insertbackground=FG_PRIMARY,
                                   relief="flat", font=FONT(9))
        self._hist_to_e.pack(side="left", padx=2)
        self._hist_to_e.insert(0, "")
        tk.Label(filter_bar, text="Search:", font=SMALL, fg=FG_DIM,
                 bg=BG_DARK).pack(side="left", padx=(8, 2))
        self._hist_search_e = tk.Entry(filter_bar, width=16, bg=BG_INPUT,
                                       fg=FG_PRIMARY, insertbackground=FG_PRIMARY,
                                       relief="flat", font=FONT(9))
        self._hist_search_e.pack(side="left", padx=2)
        DS.ghost_btn(filter_bar, "Filter", command=self._apply_hist_filter,
                     width=7).pack(side="left", padx=4)
        DS.ghost_btn(filter_bar, "Clear", command=self._clear_hist_filter,
                     width=7).pack(side="left", padx=2)

        # Tree + scrollbar
        tree_frame = tk.Frame(parent, bg=BG_CARD)
        tree_frame.pack(fill="both", expand=True, padx=10, pady=2)
        cols = ("Time", "Target", "Platform", "Reason", "Succeeded", "Attempted",
                "Elapsed")
        self._hist_tree = ttk.Treeview(tree_frame, columns=cols, show="headings",
                                       height=16)
        for c in cols:
            self._hist_tree.heading(c, text=c)
            self._hist_tree.column(c, width=90)
        self._hist_tree.pack(side="left", fill="both", expand=True)
        sb = DS.scrollbar(tree_frame)
        sb.pack(side="right", fill="y")
        self._hist_tree.config(yscrollcommand=sb.set)
        sb.config(command=self._hist_tree.yview)

        # Pagination bar
        page_bar = tk.Frame(parent, bg=BG_DARK)
        page_bar.pack(fill="x", padx=10, pady=2)
        DS.ghost_btn(page_bar, "< Prev", command=self._hist_prev_page,
                     width=8).pack(side="left", padx=2)
        self._hist_page_lbl = tk.Label(page_bar, text="Page 1", font=SMALL,
                                       fg=FG_DIM, bg=BG_DARK)
        self._hist_page_lbl.pack(side="left", padx=8)
        DS.ghost_btn(page_bar, "Next >", command=self._hist_next_page,
                     width=8).pack(side="left", padx=2)

        # Action buttons
        action_bar = tk.Frame(parent, bg=BG_DARK)
        action_bar.pack(fill="x", padx=10, pady=(2, 6))
        DS.danger_btn(action_bar, "Clear History",
                      command=self._clear_history, width=14).pack(side="left", padx=2)
        DS.ghost_btn(action_bar, "Export CSV",
                     command=self._export_history_csv, width=12).pack(side="left", padx=2)

        self._refresh_history()

    def _footer(self) -> None:
        ftr = tk.Frame(self, bg=BG_CARD, height=180)
        ftr.pack(fill="x")
        ftr.pack_propagate(False)
        lbl = tk.Label(ftr, text="Console:", font=SMALL, fg=FG_DIM,
                       bg=BG_CARD)
        lbl.pack(anchor="w", padx=8, pady=(4, 0))
        self._console = ConsoleWidget(ftr)
        self._console.pack(fill="both", expand=True, padx=4, pady=(0, 4))

    # ── Handlers ───────────────────────────────────────────────────

    def _on_log(self, msg: str, tag: str = "dim") -> None:
        self._console.write(str(msg), tag)
        flog(msg, tag)

    def _on_otp(self, key: str, plat: str, user: str) -> None:
        log(f"[OTP] 2FA required for {user} @ {plat} — key={key}", "warn")
        _system_notify("2FA Required", f"{user} @ {plat}")

    def _on_captcha(self, key: str, cap_type: str, page_url: str) -> None:
        log(f"[CAP] Manual solve needed: {cap_type} @ {page_url[:60]}", "warn")

    def _set_target(self) -> None:
        raw = self._target_e.get().strip()
        ok, val = _validate_target(raw)
        if ok:
            S.target = val
            log(f"Target set: @{val}", "ok")
        else:
            log(f"Target: {val}", "err")

    def _set_workers(self) -> None:
        try:
            S.workers = max(1, min(16, int(self._workers_e.get())))
        except ValueError:
            pass

    def _on_plat_change(self, event: Any = None) -> None:
        name = self._plat_cb.get()
        for pname, pkey in PLATFORMS:
            if pname == name:
                S.platform = pkey
                break

    def _dispatch_tool(self, key: str) -> None:
        fn = TOOL_DISPATCH.get(key)
        if fn:
            fn(self)
        else:
            log(f"Tool '{key}' not implemented yet", "dim")

    def _run(self) -> None:
        if not S.accounts:
            log("No accounts loaded", "err")
            return
        if not S.target:
            log("No target set — enter a username and press Enter", "warn")
            return
        ok, cleaned = _validate_target(S.target)
        if not ok:
            log(f"Invalid target: {cleaned}", "err")
            return
        reason_key = REPORT_REASONS[self._reason_cb.current()][1]
        S.reason = reason_key
        log(f"[START] Reporting @{cleaned} on {S.platform} for {reason_key} "
            f"({len(S.accounts)} accounts, {S.workers} workers)", "sys")
        _run_async_in_thread(
            lambda: run_mass_report(cleaned, S.platform, reason_key,
                                    lambda m, tag="dim": log(m, tag))
        )

    def _stop(self) -> None:
        GLOBAL_STOP.set()
        S.stop_event.set()
        log("⏹ STOP pressed — signalling all sessions", "err")

    def _open_accounts(self) -> None:
        AccountsManager(self)

    def _refresh_history(self) -> None:
        for item in self._hist_tree.get_children():
            self._hist_tree.delete(item)
        rows = get_run_logs(
            limit=self._hist_page_size,
            offset=self._hist_page * self._hist_page_size,
            date_from=self._hist_date_from,
            date_to=self._hist_date_to,
            search=self._hist_search,
        )
        for entry in rows:
            ts = str(entry.get("timestamp", ""))
            if len(ts) > 19:
                ts = ts[11:19]
            elif len(ts) > 10:
                ts = ts[-8:]
            self._hist_tree.insert("", "end", values=(
                ts,
                entry.get("target", ""),
                entry.get("platform", ""),
                entry.get("reason", ""),
                entry.get("successes", 0),
                entry.get("total", 0),
                f"{entry.get('elapsed_s', 0)}s",
            ))
        total = get_run_logs_count(self._hist_date_from, self._hist_date_to, self._hist_search)
        max_page = max(0, (total - 1) // self._hist_page_size)
        self._hist_page_lbl.config(text=f"Page {self._hist_page + 1}/{max_page + 1}  ({total} total)")
        self._update_stats()
        self.after(10000, self._refresh_history)

    def _apply_hist_filter(self) -> None:
        self._hist_date_from = self._hist_from_e.get().strip()
        self._hist_date_to = self._hist_to_e.get().strip()
        self._hist_search = self._hist_search_e.get().strip()
        self._hist_page = 0
        self._refresh_history()

    def _clear_hist_filter(self) -> None:
        self._hist_from_e.delete(0, "end")
        self._hist_to_e.delete(0, "end")
        self._hist_search_e.delete(0, "end")
        self._hist_date_from = ""
        self._hist_date_to = ""
        self._hist_search = ""
        self._hist_page = 0
        self._refresh_history()

    def _hist_prev_page(self) -> None:
        if self._hist_page > 0:
            self._hist_page -= 1
            self._refresh_history()

    def _hist_next_page(self) -> None:
        total = get_run_logs_count(self._hist_date_from, self._hist_date_to, self._hist_search)
        max_page = max(0, (total - 1) // self._hist_page_size)
        if self._hist_page < max_page:
            self._hist_page += 1
            self._refresh_history()

    def _clear_history(self) -> None:
        if not messagebox.askyesno("Clear History", "Delete all run history entries?"):
            return
        conn = None
        try:
            from instareport.core.database import _connection
            conn = _connection()
            conn.execute("DELETE FROM run_logs")
            conn.commit()
            S.run_logs.clear()
            self._hist_page = 0
            self._refresh_history()
            log("Run history cleared", "ok")
        except Exception as e:
            log(f"Failed to clear history: {e}", "err")
        finally:
            if conn:
                conn.close()

    def _export_history_csv(self) -> None:
        from tkinter import filedialog
        path = filedialog.asksaveasfilename(
            title="Export History CSV",
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
        )
        if not path:
            return
        rows = get_run_logs(limit=99999)
        try:
            import csv
            with open(path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=["timestamp", "target", "platform",
                                                       "reason", "successes", "total", "elapsed_s"])
                writer.writeheader()
                writer.writerows(rows)
            log(f"History exported to {path}", "ok")
        except Exception as e:
            log(f"Export failed: {e}", "err")


    def _check_update(self) -> None:
        from instareport.utils.helpers import _check_for_update
        info = _check_for_update()
        if info:
            from tkinter import messagebox
            ans = messagebox.askyesno(
                "Update Available",
                f"InstaReport v{info['version']} is available!\n\n"
                f"{info['body'][:200]}\n\n"
                "Open download page now?"
            )
            if ans:
                import webbrowser
                webbrowser.open(info['url'])

    def _update_stats(self) -> None:
        total = sum(e.get("total", 0) for e in S.run_logs)
        successes = sum(e.get("successes", 0) for e in S.run_logs)
        self._stat_total.config(text=str(total))
        rate = f"{int(successes / max(total, 1) * 100)}%" if total else "0%"
        self._stat_success.config(text=rate)

    def _init_scheduler(self) -> None:
        start_scheduler(max(S.sched_interval, 60))
        log("Scheduler started (async)", "ok")

    def _check_license(self) -> None:
        ok, code, msg = LS.load()
        if not ok and code is None:
            self.after(500, lambda: LicenseWindow(self, self._on_licensed))

    def _on_licensed(self) -> None:
        log("License activated — full mode enabled", "ok")

    def _on_close(self) -> None:
        stop_scheduler()
        save_config()
        self.destroy()
