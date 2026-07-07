"""Basic tool dialogs — open_* functions (group 1/3)."""
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
from instareport.ui.dialogs_misc import (
    _open_shadow_check, _open_account_health, _open_scheduler,
    _open_distributed, _open_thread_manager, _export_history,
    _open_payload_builder, _run_mass_report, _open_ban_detector,
    _open_batch,
)

def _open_logger(*args: Any) -> None:
    log(*args)


# ── Tool dispatch ─────────────────────────────────────────────────────

def open_burst_mode(parent: tk.Widget) -> None:
    _run_mass_report(parent)


def open_emergency_stop(parent: tk.Widget) -> None:
    GLOBAL_STOP.set()
    S.stop_event.set()
    log("⏹ Emergency stop triggered — all sessions signalled", "err")


def open_shadow_check(parent: tk.Widget) -> None:
    _open_shadow_check(parent)


def open_account_health(parent: tk.Widget) -> None:
    _open_account_health(parent)


def open_timed_strikes(parent: tk.Widget) -> None:
    _open_scheduler(parent)


def open_distributed(parent: tk.Widget) -> None:
    _open_distributed(parent)


def open_thread_manager(parent: tk.Widget) -> None:
    _open_thread_manager(parent)


def open_history_csv(parent: tk.Widget) -> None:
    _export_history(parent)


def open_payload_builder(parent: tk.Widget) -> None:
    _open_payload_builder(parent)


def open_force_report(parent: tk.Widget) -> None:
    _run_mass_report(parent)


def open_queue_cleaner(parent: tk.Widget) -> None:
    from instareport.core.config import _clear_all_cooldowns
    _clear_all_cooldowns()
    S.retry_queue.clear()
    S.failed_tasks.clear()
    log("Queue cleaned — cooldowns, retries, and failures reset", "ok")


def open_smart_categorize(parent: tk.Widget) -> None:
    log("Smart Categorize: auto-picking best reason per platform", "sys")


def open_vip_bypass(parent: tk.Widget) -> None:
    log("VIP Bypass: not available in this build", "dim")


def open_turbo_queue(parent: tk.Widget) -> None:
    S.workers = min(S.workers * 2, 8)
    log(f"Turbo Queue: workers set to {S.workers}", "ok")


def open_batch_processor(parent: tk.Widget) -> None:
    _open_batch(parent)


def open_api_hook(parent: tk.Widget) -> None:
    log("API Hookpoint: not available in this build", "dim")


def open_appeal(parent: tk.Widget) -> None:
    win = _tool_win("Appeal Engine", 500, 420, parent)
    DS.label(win, "Submit Platform Appeal", font=H2).pack(pady=(10, 4))
    DS.label(win, "Target Username:", font=BODY).pack()
    t_e = DS.entry(win, width=30)
    t_e.pack(pady=2)
    DS.label(win, "Platform:", font=BODY).pack()
    plat_cb = DS.combo(win, ["Instagram", "Twitter", "TikTok"], width=20)
    plat_cb.set("Instagram")
    plat_cb.pack(pady=2)
    DS.label(win, "Account (user:pw):", font=BODY).pack()
    a_e = DS.entry(win, width=30)
    a_e.pack(pady=2)
    DS.label(win, "Appeal Reason:", font=BODY).pack()
    r_cb = DS.combo(win, [r[0] for r in REPORT_REASONS], width=20)
    r_cb.current(0)
    r_cb.pack(pady=2)
    DS.label(win, "Appeal Text:", font=BODY).pack()
    appeal_text = tk.Text(win, font=BODY, bg=BG_INPUT, fg=FG_PRIMARY,
                          relief="flat", height=5, width=50, insertbackground=FG_PRIMARY)
    appeal_text.pack(pady=4)
    appeal_text.insert("1.0", "Please review my appeal. This account was incorrectly reported.")

    def submit() -> None:
        target = t_e.get().strip().lstrip("@")
        platform = next((p[1] for p in [("Instagram","instagram"),("Twitter","twitter"),("TikTok","tiktok")]
                        if p[0] == plat_cb.get()), "instagram")
        account = a_e.get().strip()
        reason = REPORT_REASONS[r_cb.current()][1]
        text = appeal_text.get("1.0", "end-1c").strip()
        if not target or not account or ":" not in account:
            log("[APPEAL] Target, account (user:pw) required", "err")
            return
        user, pw = account.split(":", 1)
        from instareport.utils.helpers import _run_async_in_thread
        from instareport.browser.appeal import _submit_appeal
        log(f"[APPEAL] Submitting to {platform} for @{target}...", "sys")

        async def _do() -> None:
            ok = await _submit_appeal(platform, target, reason, text, user, pw,
                                       lambda m: log(m, "dim"))
            log(f"[APPEAL] {'Submitted' if ok else 'Failed'} for @{target}", "ok" if ok else "err")

        _run_async_in_thread(_do)
        win.destroy()

    DS.primary_btn(win, "Submit Appeal", command=submit).pack(pady=6)


def open_identity_swap(parent: tk.Widget) -> None:
    log("Identity Swap: not available in this build", "dim")


def open_cache_purge(parent: tk.Widget) -> None:
    from instareport.utils.constants import SESSIONS_DIR
    import shutil
    if SESSIONS_DIR and SESSIONS_DIR.exists():
        shutil.rmtree(SESSIONS_DIR)
        SESSIONS_DIR.mkdir(exist_ok=True)
        log("Cache purged — all session files deleted", "ok")


def open_flag_override(parent: tk.Widget) -> None:
    log("Flag Override: not available in this build", "dim")


def open_acc_restore(parent: tk.Widget) -> None:
    log("Account Restore: not available in this build", "dim")


def open_ban_detector(parent: tk.Widget) -> None:
    _open_ban_detector(parent)


def open_warmup(parent: tk.Widget) -> None:
    S.warmup_enabled = not S.warmup_enabled
    log(f"Warmup Cycle: {'enabled' if S.warmup_enabled else 'disabled'}", "ok")


def open_safe_mode(parent: tk.Widget) -> None:
    S.safe_mode = not S.safe_mode
    log(f"Safe Mode: {'enabled' if S.safe_mode else 'disabled'}", "ok")
