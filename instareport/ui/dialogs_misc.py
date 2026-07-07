"""Misc tool dialogs — open_* and _open_* functions (group 3/3)."""
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from typing import Any
import os, json, time, threading, random, subprocess, webbrowser

from instareport.ui.theme import (
    BG_DARK, BG_CARD, BG_INPUT, FG_PRIMARY, FG_SECONDARY, FG_DIM,
    ACCENT_GREEN, ACCENT_PINK, ACCENT_BLUE, ACCENT_AMBER, ACCENT_PURPLE,
    BORDER, FONT, H1, H2, H3, BODY, SMALL, MONO,
    DesignSystem as DS,
)
from instareport.ui.widgets import _tool_win, ConsoleWidget, LoadingSpinner
from instareport.core.state import S, GLOBAL_STOP, ACCOUNTS_LOCK, COOLDOWN_LOCK
from instareport.core.config import (
    save_config, load_config, _clear_all_cooldowns, _cooldown_remaining,
)
from instareport.core.otp import OTP
from instareport.tools.proxy import PP
from instareport.utils.constants import (
    PLATFORMS, REPORT_REASONS, MOBILE_DEVICES, API_BASE, DEBUG,
    T_PAGE_LOAD, T_POST_CLICK, T_POST_LOGIN, T_CAPTCHA_WAIT,
    T_TELEGRAM_OTP, T_REFRESH_WAIT, T_TYPE_DELAY,
)
from instareport.utils.helpers import (
    _validate_target, _validate_sched_time, _run_async_in_thread,
    _center_on_parent, _force_reload_accounts,
)
from instareport.utils.logging import log, dlog, flog
from instareport.engine import run_mass_report, run_batch

def open_webrtc_block(parent: tk.Widget) -> None:
    log("WebRTC Block: not available in this build", "dim")


def open_tls_fp(parent: tk.Widget) -> None:
    log("TLS Fingerprint: not available in this build", "dim")


def open_export_html(parent: tk.Widget) -> None:
    path = filedialog.asksaveasfilename(defaultextension=".html",
                                        filetypes=[("HTML", "*.html")])
    if not path:
        return
    from instareport.utils.helpers import _export_report_html
    ok = _export_report_html(path)
    if ok:
        log(f"HTML report exported to {path}", "ok")
    else:
        log("No run history to export", "warn")


def open_telegram_bot(parent: tk.Widget) -> None:
    win = _tool_win("Telegram Bot Control", 420, 250, parent)
    DS.label(win, "Telegram Bot Remote Control", font=H2).pack(pady=(10, 4))
    DS.label(win, "Bot Token:", font=BODY).pack()
    token_e = DS.entry(win, width=40, show="*")
    token_e.pack(pady=2)
    DS.label(win, "Allowed Chat IDs (comma sep):", font=BODY).pack()
    ids_e = DS.entry(win, width=40)
    ids_e.pack(pady=2)
    status_lbl = tk.Label(win, text="Bot: Stopped", font=BODY, fg=FG_DIM, bg=BG_DARK)
    status_lbl.pack(pady=6)

    def toggle() -> None:
        from instareport.tools.telegram_bot import _bot, start_bot, stop_bot
        if _bot and _bot._running:
            stop_bot()
            status_lbl.config(text="Bot: Stopped", fg=FG_DIM)
            log("[TELEGRAM] Bot stopped", "ok")
        else:
            token = token_e.get().strip()
            if not token:
                log("[TELEGRAM] Token required", "err")
                return
            ids = []
            raw = ids_e.get().strip()
            if raw:
                try:
                    ids = [int(x.strip()) for x in raw.split(",") if x.strip()]
                except ValueError:
                    log("[TELEGRAM] Invalid chat ID format", "err")
                    return
            start_bot(token, ids)
            status_lbl.config(text="Bot: Running", fg=ACCENT_GREEN)
            log("[TELEGRAM] Bot started", "ok")

    DS.primary_btn(win, "Start / Stop", command=toggle, width=14).pack(pady=4)


def open_auto_update(parent: tk.Widget) -> None:
    from instareport.utils.helpers import _check_for_update
    win = _tool_win("Auto-Update", 400, 200, parent)
    DS.label(win, "Check for Updates", font=H2).pack(pady=(10, 4))
    from instareport.utils.constants import VERSION
    result_text = tk.Text(win, font=MONO, bg=BG_CARD, fg=FG_PRIMARY,
                          relief="flat", height=4, width=50)
    result_text.pack(pady=6)
    result_text.insert("1.0", f"Current version: {VERSION}\nChecking...")

    def check() -> None:
        result_text.delete("1.0", "end")
        result_text.insert("1.0", "Checking GitHub...\n")
        has_update, latest, url = _check_for_update()
        if has_update:
            result_text.insert("end", f"Update available: {latest}\n")
            result_text.insert("end", f"Download: {url}")
            import webbrowser
            if messagebox.askyesno("Update Available", f"Open {url} in browser?"):
                webbrowser.open(url)
        else:
            result_text.insert("end", f"You're up to date ({VERSION})")

    DS.primary_btn(win, "Check Now", command=check).pack(pady=4)


# ── Dialog implementations ────────────────────────────────────────────

def _open_shadow_check(parent: tk.Widget) -> None:
    win = _tool_win("Shadow Ban Check", 420, 200, parent)
    DS.label(win, "Check if a target is shadow-banned", font=H3).pack(pady=(12, 4))
    DS.label(win, "Username:", font=BODY).pack()
    e = DS.entry(win, width=30)
    e.pack(pady=4)

    def check() -> None:
        raw = e.get().strip().lstrip("@")
        if not raw:
            return
        log(f"[SCAN] Checking shadow ban for @{raw}…", "proxy")
        win.destroy()

    DS.primary_btn(win, "Check", command=check).pack(pady=10)


def _open_account_health(parent: tk.Widget) -> None:
    win = _tool_win("Account Health", 500, 400, parent)
    DS.label(win, "Per-Account Health Status", font=H2).pack(pady=(10, 4))
    frame = tk.Frame(win, bg=BG_CARD)
    frame.pack(fill="both", expand=True, padx=10, pady=6)
    cols = ("Username", "Cooldown", "Sessions", "Reports", "Risk")
    tree = ttk.Treeview(frame, columns=cols, show="headings",
                        height=12, selectmode="browse")
    for c in cols:
        tree.heading(c, text=c)
        tree.column(c, width=90)
    tree.pack(side="left", fill="both", expand=True)
    sb = DS.scrollbar(frame)
    sb.pack(side="right", fill="y")
    tree.config(yscrollcommand=sb.set)
    sb.config(command=tree.yview)
    for acct in S.accounts:
        u, _ = acct if isinstance(acct, (list, tuple)) else (acct.username, "")
        cooldown = _cooldown_remaining(u)
        info = acct if isinstance(acct, tuple) else (acct.username, acct.password,
                                                      acct.cooldown_until, acct.session_count,
                                                      acct.total_reports, acct.risk_level)
        tree.insert("", "end", values=(u, f"{cooldown}s", info[3] if len(info) > 3 else 0,
                                       info[4] if len(info) > 4 else 0,
                                       info[5] if len(info) > 5 else "LOW"))


def _open_scheduler(parent: tk.Widget) -> None:
    win = _tool_win("Timed Strikes", 400, 350, parent)
    DS.label(win, "Schedule Automated Reports", font=H2).pack(pady=(10, 4))
    DS.label(win, "Time (HH:MM):", font=BODY).pack()
    t_e = DS.entry(win, width=12)
    t_e.insert(0, S.sched_time)
    t_e.pack(pady=2)
    DS.label(win, "Interval (min):", font=BODY).pack()
    i_e = DS.entry(win, width=12)
    i_e.insert(0, str(S.sched_interval))
    i_e.pack(pady=2)
    rep_var = tk.BooleanVar(value=S.sched_repeat)
    DS.checkbox(win, "Repeat", rep_var).pack(pady=2)
    DS.label(win, "Report Language:", font=BODY).pack()
    from instareport.utils.constants import REASON_LANGUAGES
    lang_cb = DS.combo(win, [l[0] for l in REASON_LANGUAGES], width=16)
    lang_cb.set("English")
    lang_cb.pack(pady=2)

    def save() -> None:
        ok, val = _validate_sched_time(t_e.get())
        if not ok:
            log(f"Scheduler: {val}", "err")
            return
        S.sched_time = val
        try:
            S.sched_interval = max(1, int(i_e.get()))
        except ValueError:
            pass
        S.sched_repeat = rep_var.get()
        S.sched_enabled = True
        lang_key = next((l[1] for l in REASON_LANGUAGES if l[0] == lang_cb.get()), "en")
        S.sched_lang = lang_key
        log(f"Scheduler set @ {S.sched_time} every {S.sched_interval}min (lang={lang_key})", "ok")
        save_config()
        win.destroy()

    DS.primary_btn(win, "Save Schedule", command=save).pack(pady=10)
    DS.ghost_btn(win, "Disable", command=lambda: [setattr(S, 'sched_enabled', False),
                                                    log("Scheduler disabled", "warn"),
                                                    save_config(), win.destroy()]).pack()


def _open_distributed(parent: tk.Widget) -> None:
    win = _tool_win("Distributed Attack", 400, 200, parent)
    DS.label(win, "Distributed Attack Settings", font=H2).pack(pady=(10, 4))
    DS.label(win, "Workers:", font=BODY).pack()
    w_e = DS.entry(win, width=8)
    w_e.insert(0, str(S.workers))
    w_e.pack(pady=2)

    def save() -> None:
        try:
            S.workers = max(1, min(16, int(w_e.get())))
            log(f"Distributed workers set to {S.workers}", "ok")
            save_config()
        except ValueError:
            pass
        win.destroy()

    DS.primary_btn(win, "Save", command=save).pack(pady=10)


def _open_thread_manager(parent: tk.Widget) -> None:
    win = _tool_win("Thread Manager", 350, 150, parent)
    DS.label(win, "Worker Threads:", font=H2).pack(pady=(10, 4))
    w_e = DS.entry(win, width=8)
    w_e.insert(0, str(S.workers))
    w_e.pack(pady=2)

    def save() -> None:
        try:
            S.workers = max(1, min(16, int(w_e.get())))
            log(f"Workers set to {S.workers}", "ok")
            save_config()
        except ValueError:
            pass
        win.destroy()

    DS.primary_btn(win, "Apply", command=save).pack(pady=10)


def _export_history(parent: tk.Widget) -> None:
    import csv
    from datetime import datetime
    if not S.run_logs:
        log("No run history to export", "warn")
        return
    path = filedialog.asksaveasfilename(defaultextension=".csv",
                                        filetypes=[("CSV", "*.csv")])
    if not path:
        return
    try:
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["target", "platform", "reason",
                                              "successes", "total", "elapsed_s",
                                              "timestamp"])
            w.writeheader()
            w.writerows(S.run_logs)
        log(f"History exported to {path}", "ok")
    except Exception as e:
        log(f"Export failed: {e}", "err")


def _open_payload_builder(parent: tk.Widget) -> None:
    win = _tool_win("Payload Builder", 400, 250, parent)
    DS.label(win, "Custom Report Payload", font=H2).pack(pady=(10, 4))
    DS.label(win, "Description:", font=BODY).pack()
    t = tk.Text(win, font=BODY, bg=BG_INPUT, fg=FG_PRIMARY, relief="flat",
                bd=0, height=4, width=40, insertbackground=FG_PRIMARY)
    t.pack(pady=4)
    if S.custom_description:
        t.insert("1.0", S.custom_description)

    def save() -> None:
        S.custom_description = t.get("1.0", "end-1c").strip()
        log(f"Payload description saved ({len(S.custom_description)} chars)", "ok")
        save_config()
        win.destroy()

    DS.primary_btn(win, "Save Payload", command=save).pack(pady=6)


def _open_batch(parent: tk.Widget) -> None:
    win = _tool_win("Batch Processor", 500, 400, parent)
    DS.label(win, "Batch Report — Multiple Targets", font=H2).pack(pady=(10, 4))
    DS.label(win, "Targets (one per line):", font=BODY).pack()
    t = tk.Text(win, font=MONO, bg=BG_INPUT, fg=FG_PRIMARY, relief="flat",
                bd=0, height=8, width=50, insertbackground=FG_PRIMARY)
    t.pack(pady=4)

    def run() -> None:
        lines = [l.strip().lstrip("@") for l in t.get("1.0", "end-1c").splitlines() if l.strip()]
        if not lines:
            return
        log(f"[BATCH] Running {len(lines)} targets with {len(S.accounts)} accounts", "sys")
        S.multi_targets = lines
        threading.Thread(target=_run_batch_worker, args=(lines,), daemon=True).start()
        win.destroy()

    btn_frame = tk.Frame(win, bg=BG_DARK)
    btn_frame.pack(pady=4)
    DS.primary_btn(btn_frame, "Run Batch", command=run).pack(side="left", padx=4)

    def import_file() -> None:
        path = filedialog.askopenfilename(title="Import Targets", filetypes=[("Text files", "*.txt"), ("All files", "*.*")])
        if not path:
            return
        try:
            with open(path, encoding="utf-8") as f:
                lines = [l.strip() for l in f if l.strip() and not l.startswith("#")]
            t.delete("1.0", "end")
            t.insert("1.0", "\n".join(lines))
            log(f"[BATCH] Imported {len(lines)} targets from {os.path.basename(path)}", "ok")
        except Exception as e:
            messagebox.showerror("Import Error", str(e))

    tk.Button(btn_frame, text="📂 Import .txt", command=import_file,
              bg="#2d2d2d", fg="#e0e0e0", relief="flat", cursor="hand2").pack(side="left", padx=4)

    def _run_batch_worker(targets: list[str]) -> None:
        from instareport.utils.helpers import _run_async_in_thread
        for tgt in targets:
            if S.stop_event.is_set() or GLOBAL_STOP.is_set():
                break
            log(f"[BATCH] Target: {tgt}", "sys")
            _run_async_in_thread(
                lambda t=tgt: run_mass_report(t, S.platform, S.reason, lambda m, tag="dim": log(m, tag))
            )
            time.sleep(3)


def _open_ban_detector(parent: tk.Widget) -> None:
    win = _tool_win("Ban Detector", 400, 200, parent)
    DS.label(win, "Check if an account is banned", font=H2).pack(pady=(10, 4))
    DS.label(win, "Username:", font=BODY).pack()
    e = DS.entry(win, width=30)
    e.pack(pady=4)

    def check() -> None:
        raw = e.get().strip()
        if not raw:
            return
        log(f"[BAN] Checking @{raw}…", "proxy")
        win.destroy()

    DS.primary_btn(win, "Check", command=check).pack(pady=10)


def _open_session_rebuild(parent: tk.Widget) -> None:
    win = _tool_win("Session Rebuilder", 400, 200, parent)
    DS.label(win, "Delete cookies for an account", font=H2).pack(pady=(10, 4))
    from instareport.utils.constants import SESSIONS_DIR
    accounts = [a[0] if isinstance(a, (list, tuple)) else a.username for a in S.accounts]
    cb = DS.combo(win, accounts, width=28)
    cb.pack(pady=4)

    def rebuild() -> None:
        u = cb.get().strip()
        if not u:
            return
        safe = "".join(c for c in u if c.isalnum() or c in "-_.")
        deleted = 0
        if SESSIONS_DIR:
            for f in SESSIONS_DIR.glob(f"{safe}_*.json"):
                f.unlink()
                deleted += 1
        log(f"Rebuilt session for {u} — removed {deleted} cookie files", "ok")
        win.destroy()

    DS.primary_btn(win, "Rebuild", command=rebuild).pack(pady=10)


def _open_captcha_config(parent: tk.Widget) -> None:
    win = _tool_win("CAPTCHA Solver", 400, 250, parent)
    DS.label(win, "CAPTCHA Service Config", font=H2).pack(pady=(10, 4))
    DS.label(win, "Service:", font=BODY).pack()
    svc_cb = DS.combo(win, ["manual", "2captcha", "anticaptcha", "capmonster"], width=20)
    svc_cb.set(S.captcha_svc)
    svc_cb.pack(pady=2)
    DS.label(win, "API Key:", font=BODY).pack()
    k_e = DS.entry(win, width=40, show="*")
    k_e.insert(0, S.captcha_key)
    k_e.pack(pady=2)

    def save() -> None:
        S.captcha_svc = svc_cb.get()
        S.captcha_key = k_e.get().strip()
        log(f"CAPTCHA: {S.captcha_svc} key={'set' if S.captcha_key else 'empty'}", "ok")
        save_config()
        win.destroy()

    DS.primary_btn(win, "Save", command=save).pack(pady=10)


def _open_otp_dialog(parent: tk.Widget) -> None:
    from instareport.ui.otp_dialog import open_otp_dialog
    open_otp_dialog(parent)


def _open_profile_scan(parent: tk.Widget) -> None:
    win = _tool_win("Profile Scanner", 420, 220, parent)
    DS.label(win, "Fetch public profile info", font=H2).pack(pady=(10, 4))
    DS.label(win, "Username:", font=BODY).pack()
    e = DS.entry(win, width=30)
    e.pack(pady=4)
    DS.label(win, "Platform:", font=BODY).pack()
    plat_cb = DS.combo(win, [p[0] for p in PLATFORMS], width=20)
    plat_cb.set("Instagram")
    plat_cb.pack(pady=2)

    def scan() -> None:
        raw = e.get().strip()
        if not raw:
            return
        log(f"[SCAN] Scanning @{raw}…", "proxy")
        win.destroy()

    DS.primary_btn(win, "Scan", command=scan).pack(pady=6)


def _open_report_history(parent: tk.Widget) -> None:
    win = _tool_win("Report History", 600, 350, parent)
    DS.label(win, "Run History", font=H2).pack(pady=(10, 4))
    frame = tk.Frame(win, bg=BG_CARD)
    frame.pack(fill="both", expand=True, padx=10, pady=6)
    cols = ("Time", "Target", "Platform", "Reason", "Success", "Total")
    tree = ttk.Treeview(frame, columns=cols, show="headings", height=12)
    for c in cols:
        tree.heading(c, text=c)
        tree.column(c, width=90)
    tree.pack(side="left", fill="both", expand=True)
    sb = DS.scrollbar(frame)
    sb.pack(side="right", fill="y")
    tree.config(yscrollcommand=sb.set)
    sb.config(command=tree.yview)
    for entry in reversed(S.run_logs[-100:]):
        tree.insert("", "end", values=(
            entry.get("timestamp", "")[-8:],
            entry.get("target", ""),
            entry.get("platform", ""),
            entry.get("reason", ""),
            entry.get("successes", 0),
            entry.get("total", 0),
        ))


def _open_cookie_inject(parent: tk.Widget) -> None:
    win = _tool_win("Cookie Injector", 500, 350, parent)
    DS.label(win, "Inject Cookie JSON", font=H2).pack(pady=(10, 4))
    DS.label(win, "Username:", font=BODY).pack()
    u_e = DS.entry(win, width=30)
    u_e.pack(pady=2)
    DS.label(win, "Paste cookie JSON:", font=BODY).pack()
    t = tk.Text(win, font=MONO, bg=BG_INPUT, fg=FG_PRIMARY, relief="flat",
                bd=0, height=8, width=50, insertbackground=FG_PRIMARY)
    t.pack(pady=4)

    def inject() -> None:
        user = u_e.get().strip()
        raw = t.get("1.0", "end-1c").strip()
        if not user or not raw:
            return
        try:
            cookies = json.loads(raw)
            if isinstance(cookies, dict):
                cookies = [cookies]
            from instareport.utils.constants import SESSIONS_DIR
            safe = "".join(c for c in user if c.isalnum() or c in "-_.")
            p = SESSIONS_DIR / f"{safe}_injected.json"
            with open(p, "w", encoding="utf-8") as f:
                json.dump({"cookies": cookies, "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
                           "version": 2}, f)
            log(f"Injected {len(cookies)} cookies for {user}", "ok")
        except json.JSONDecodeError:
            log("Invalid JSON", "err")
        win.destroy()

    DS.primary_btn(win, "Inject", command=inject).pack(pady=6)


def _open_rate_limit(parent: tk.Widget) -> None:
    win = _tool_win("Rate Limiter", 350, 150, parent)
    DS.label(win, "Reports per minute (0=unlimited):", font=H2).pack(pady=(10, 4))
    e = DS.entry(win, width=8)
    e.insert(0, str(S.rate_limit))
    e.pack(pady=2)

    def save() -> None:
        try:
            S.rate_limit = max(0, int(e.get()))
            log(f"Rate limit set to {S.rate_limit}/min", "ok")
            save_config()
        except ValueError:
            pass
        win.destroy()

    DS.primary_btn(win, "Save", command=save).pack(pady=10)


def _run_mass_report(parent: tk.Widget) -> None:
    if not S.accounts:
        log("No accounts loaded", "err")
        return
    if not S.target:
        log("No target set", "err")
        return
    threading.Thread(target=_report_worker, daemon=True).start()

def _report_worker() -> None:
    ok, cleaned = _validate_target(S.target)
    if not ok:
        log(f"Target invalid: {cleaned}", "err")
        return
    target = cleaned
    _run_async_in_thread(
        lambda t=target, p=S.platform, r=S.reason:
            run_mass_report(t, p, r, lambda m, tag="dim": log(m, tag))
    )
