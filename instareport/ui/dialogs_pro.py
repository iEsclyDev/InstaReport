"""Pro tool dialogs — open_* functions (group 2/3)."""
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
    _open_shadow_check, _open_session_rebuild, _open_captcha_config,
    _open_otp_dialog, _open_profile_scan, _open_report_history,
    _open_cookie_inject, _open_rate_limit,
)

def open_proxy_rotate(parent: tk.Widget) -> None:
    from instareport.tools.proxy import ProxyHealthChecker
    proxies = PP.snapshot()
    if not proxies:
        log("No proxies to rotate", "warn")
        return
    log(f"Rotating {len(proxies)} proxies — running health check…", "sys")
    live = ProxyHealthChecker.check_all(proxies, lambda m: log(m, "proxy"))
    PP.replace(live)
    log(f"Proxy pool: {len(live)} alive", "ok")


def open_session_rebuild(parent: tk.Widget) -> None:
    _open_session_rebuild(parent)


def open_captcha_config(parent: tk.Widget) -> None:
    _open_captcha_config(parent)


def open_twofa_bypass(parent: tk.Widget) -> None:
    _open_otp_dialog(parent)


def open_profile_scan(parent: tk.Widget) -> None:
    _open_profile_scan(parent)


def open_shadow_check_lookup(parent: tk.Widget) -> None:
    _open_shadow_check(parent)


def open_engagement(parent: tk.Widget) -> None:
    win = _tool_win("Engagement Audit", 450, 350, parent)
    DS.label(win, "Profile Engagement Stats", font=H2).pack(pady=(10, 4))
    DS.label(win, "Username:", font=BODY).pack()
    u_e = DS.entry(win, width=30)
    u_e.pack(pady=2)
    DS.label(win, "Platform:", font=BODY).pack()
    plat_cb = DS.combo(win, [p[0] for p in PLATFORMS], width=20)
    plat_cb.set("Instagram")
    plat_cb.pack(pady=2)
    result_text = tk.Text(win, font=MONO, bg=BG_CARD, fg=FG_PRIMARY,
                          relief="flat", height=8, width=50)
    result_text.pack(pady=6)

    track_var = tk.BooleanVar(value=False)
    DS.checkbox(win, "Save to Follower Tracker", track_var).pack(pady=2)

    def scan() -> None:
        username = u_e.get().strip().lstrip("@")
        if not username:
            return
        platform = next((p[1] for p in PLATFORMS if p[0] == plat_cb.get()), "instagram")
        result_text.delete("1.0", "end")
        result_text.insert("1.0", "Scanning...\n")
        from instareport.utils.helpers import _run_async_in_thread
        from instareport.browser.scraper import _scrape_engagement

        async def _do() -> None:
            data = await _scrape_engagement(username, platform)
            lines = [
                f"Username:  @{username}",
                f"Platform:  {platform}",
                f"Posts:     {data.get('posts', '?')}",
                f"Followers: {data.get('followers', '?')}",
                f"Following: {data.get('following', '?')}",
            ]
            result_text.delete("1.0", "end")
            result_text.insert("1.0", "\n".join(lines))
            log(f"[ENGAGEMENT] @{username} on {platform}: {data.get('posts')} posts, {data.get('followers')} followers", "ok")
            if track_var.get():
                from instareport.core.database import save_follower_snapshot
                try:
                    f = int(str(data.get('followers', '0')).replace(',', '').replace('K', '000').replace('M', '000000'))
                    fo = int(str(data.get('following', '0')).replace(',', '').replace('K', '000').replace('M', '000000'))
                    p = int(str(data.get('posts', '0')).replace(',', '').replace('K', '000').replace('M', '000000'))
                    save_follower_snapshot(username, platform, f, fo, p)
                    log(f"[TRACKER] Snapshot saved for @{username}", "ok")
                except Exception:
                    pass

        _run_async_in_thread(_do)

    DS.primary_btn(win, "Scan", command=scan).pack(pady=4)


def open_follower_track(parent: tk.Widget) -> None:
    win = _tool_win("Follower Tracker", 550, 380, parent)
    DS.label(win, "Follower History", font=H2).pack(pady=(10, 4))
    DS.label(win, "Username:", font=BODY).pack()
    u_e = DS.entry(win, width=30)
    u_e.pack(pady=2)
    DS.label(win, "Platform:", font=BODY).pack()
    plat_cb = DS.combo(win, [p[0] for p in PLATFORMS], width=20)
    plat_cb.set("Instagram")
    plat_cb.pack(pady=2)

    frame = tk.Frame(win, bg=BG_CARD)
    frame.pack(fill="both", expand=True, padx=10, pady=6)
    cols = ("Date", "Posts", "Followers", "Following")
    tree = ttk.Treeview(frame, columns=cols, show="headings", height=10)
    for c in cols:
        tree.heading(c, text=c)
        tree.column(c, width=110)
    tree.pack(side="left", fill="both", expand=True)
    sb = DS.scrollbar(frame)
    sb.pack(side="right", fill="y")
    tree.config(yscrollcommand=sb.set)
    sb.config(command=tree.yview)

    def load() -> None:
        username = u_e.get().strip().lstrip("@")
        if not username:
            return
        platform = next((p[1] for p in PLATFORMS if p[0] == plat_cb.get()), "instagram")
        from instareport.core.database import get_follower_history
        for item in tree.get_children():
            tree.delete(item)
        for entry in get_follower_history(username, platform, limit=90):
            tree.insert("", "end", values=(
                entry.get("snapshot_date", ""),
                entry.get("posts", 0),
                entry.get("followers", 0),
                entry.get("following", 0),
            ))
        log(f"[TRACKER] Loaded history for @{username}", "ok")

    DS.primary_btn(win, "Load History", command=load).pack(pady=4)


def open_screenshot_gallery(parent: tk.Widget) -> None:
    win = _tool_win("Screenshot Gallery", 700, 450, parent)
    DS.label(win, "Screenshot Gallery", font=H2).pack(pady=(10, 4))
    from instareport.utils.constants import SCREENSHOTS_DIR
    frame = tk.Frame(win, bg=BG_CARD)
    frame.pack(fill="both", expand=True, padx=10, pady=6)
    cols = ("Filename", "Date", "Size (KB)")
    tree = ttk.Treeview(frame, columns=cols, show="headings", height=16)
    for c in cols:
        tree.heading(c, text=c)
        tree.column(c, width=180)
    tree.pack(side="left", fill="both", expand=True)
    sb = DS.scrollbar(frame)
    sb.pack(side="right", fill="y")
    tree.config(yscrollcommand=sb.set)
    sb.config(command=tree.yview)

    def refresh() -> None:
        for item in tree.get_children():
            tree.delete(item)
        if SCREENSHOTS_DIR and SCREENSHOTS_DIR.exists():
            for f in sorted(SCREENSHOTS_DIR.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
                if f.suffix.lower() in (".png", ".jpg", ".jpeg"):
                    size = f.stat().st_size // 1024
                    tree.insert("", "end", values=(
                        f.name, f.stat().st_mtime, size
                    ), tags=(str(f),))
        log(f"[GALLERY] Loaded {len(tree.get_children())} screenshots", "ok")

    def delete_selected() -> None:
        sel = tree.selection()
        if not sel:
            return
        item = sel[0]
        fpath = tree.item(item, "tags")[0] if tree.item(item, "tags") else ""
        if fpath and os.path.exists(fpath):
            os.remove(fpath)
            tree.delete(item)
            log(f"[GALLERY] Deleted {os.path.basename(fpath)}", "ok")

    def open_selected() -> None:
        sel = tree.selection()
        if not sel:
            return
        item = sel[0]
        fpath = tree.item(item, "tags")[0] if tree.item(item, "tags") else ""
        if fpath and os.path.exists(fpath):
            os.startfile(fpath)

    btn_bar = tk.Frame(win, bg=BG_DARK)
    btn_bar.pack(fill="x", padx=10, pady=2)
    DS.primary_btn(btn_bar, "Refresh", command=refresh, width=10).pack(side="left", padx=2)
    DS.ghost_btn(btn_bar, "Open", command=open_selected, width=8).pack(side="left", padx=2)
    DS.danger_btn(btn_bar, "Delete", command=delete_selected, width=8).pack(side="left", padx=2)
    refresh()


def open_report_history(parent: tk.Widget) -> None:
    _open_report_history(parent)


def open_ip_resolve(parent: tk.Widget) -> None:
    win = _tool_win("IP Resolver", 450, 280, parent)
    DS.label(win, "Resolve IP Geolocation", font=H2).pack(pady=(10, 4))
    DS.label(win, "IP Address / Domain:", font=BODY).pack()
    e = DS.entry(win, width=36)
    e.pack(pady=4)

    result_text = tk.Text(win, font=MONO, bg=BG_CARD, fg=FG_PRIMARY,
                          relief="flat", height=8, width=52)
    result_text.pack(pady=6)

    def resolve() -> None:
        target = e.get().strip()
        if not target:
            return
        from instareport.utils.helpers import _req
        try:
            r = _req('get', f"http://ip-api.com/json/{target}",
                     headers={"Origin": "https://ip-api.com"}, timeout=10)
            data = r.json()
            if data.get("status") == "success":
                lines = [
                    f"IP:      {data.get('query', '?')}",
                    f"Country: {data.get('country', '?')} ({data.get('countryCode', '?')})",
                    f"Region:  {data.get('regionName', '?')}",
                    f"City:    {data.get('city', '?')}",
                    f"ISP:     {data.get('isp', '?')}",
                    f"Org:     {data.get('org', '?')}",
                    f"AS:      {data.get('as', '?')}",
                    f"Lat/Lon: {data.get('lat', '?')}, {data.get('lon', '?')}",
                ]
                result_text.delete("1.0", "end")
                result_text.insert("1.0", "\n".join(lines))
                log(f"[IP] Resolved {target}: {data.get('city', '?')}, {data.get('country', '?')}", "ok")
            else:
                result_text.delete("1.0", "end")
                result_text.insert("1.0", f"Error: {data.get('message', 'Unknown')}")
        except Exception as ex:
            result_text.delete("1.0", "end")
            result_text.insert("1.0", f"Request failed: {ex}")

    DS.primary_btn(win, "Resolve", command=resolve).pack(pady=4)


def open_fingerprint(parent: tk.Widget) -> None:
    win = _tool_win("Device Fingerprint", 500, 340, parent)
    DS.label(win, "Browser Fingerprint Snapshot", font=H2).pack(pady=(10, 4))
    result_text = tk.Text(win, font=MONO, bg=BG_CARD, fg=FG_PRIMARY,
                          relief="flat", height=14, width=58)
    result_text.pack(pady=6)

    def scan() -> None:
        log("[FINGERPRINT] Launching browser to capture fingerprint…", "proxy")
        result_text.delete("1.0", "end")
        result_text.insert("1.0", "Capturing...\n")
        from instareport.utils.helpers import _run_async_in_thread
        from instareport.browser.factory import init_browser

        async def _do_scan() -> None:
            pw, browser, context, page = await init_browser(
                headless=True, force_desktop=True)
            try:
                fp = await page.evaluate("""() => ({
                    userAgent: navigator.userAgent,
                    platform: navigator.platform,
                    language: navigator.language,
                    languages: navigator.languages,
                    hardwareConcurrency: navigator.hardwareConcurrency,
                    deviceMemory: navigator.deviceMemory,
                    webdriver: navigator.webdriver,
                    cookieEnabled: navigator.cookieEnabled,
                    doNotTrack: navigator.doNotTrack,
                    timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
                    screen: `${screen.width}x${screen.height}`,
                    colorDepth: screen.colorDepth,
                    pixelRatio: devicePixelRatio,
                    canvas: await (() => {
                        const c = document.createElement('canvas');
                        c.width = 256; c.height = 256;
                        const ctx = c.getContext('2d');
                        ctx.fillText('FP', 100, 100);
                        return c.toDataURL().slice(0, 64);
                    })(),
                    webgl: (() => { try {
                        const gl = document.createElement('canvas').getContext('webgl');
                        return gl ? gl.getParameter(gl.RENDERER) : 'N/A';
                    } catch(e) { return 'N/A'; } })(),
                })""")
                lines = [f"{k}: {v}" for k, v in fp.items()]
                result_text.delete("1.0", "end")
                result_text.insert("1.0", "\n".join(lines))
                log("[FINGERPRINT] Captured", "ok")
            finally:
                await context.close()
                await browser.close()
                await pw.stop()

        _run_async_in_thread(_do_scan)

    DS.primary_btn(win, "Scan Fingerprint", command=scan).pack(pady=4)


def open_acc_age(parent: tk.Widget) -> None:
    win = _tool_win("Account Age Estimator", 450, 250, parent)
    DS.label(win, "Estimate Account Creation Date", font=H2).pack(pady=(10, 4))
    DS.label(win, "Username:", font=BODY).pack()
    e = DS.entry(win, width=30)
    e.pack(pady=4)
    DS.label(win, "Platform:", font=BODY).pack()
    plat_cb = DS.combo(win, [p[0] for p in PLATFORMS], width=20)
    plat_cb.set("Instagram")
    plat_cb.pack(pady=2)
    result_text = tk.Text(win, font=MONO, bg=BG_CARD, fg=FG_PRIMARY,
                          relief="flat", height=4, width=50)
    result_text.pack(pady=6)

    def check() -> None:
        username = e.get().strip().lstrip("@")
        if not username:
            return
        platform = plat_cb.get()
        log(f"[AGE] Checking @{username} on {platform}…", "sys")
        from instareport.utils.helpers import _run_async_in_thread
        from instareport.browser.scraper import _estimate_account_age

        async def _do() -> None:
            age = await _estimate_account_age(username, platform)
            result_text.delete("1.0", "end")
            if age:
                result_text.insert("1.0", f"Estimated creation: {age}")
                log(f"[AGE] @{username}: {age}", "ok")
            else:
                result_text.insert("1.0", "Could not determine account age")
                log(f"[AGE] @{username}: could not determine", "warn")

        _run_async_in_thread(_do)

    DS.primary_btn(win, "Check Age", command=check).pack(pady=4)


def open_link_trace(parent: tk.Widget) -> None:
    win = _tool_win("Link Tracer", 550, 280, parent)
    DS.label(win, "Trace URL Redirect Chain", font=H2).pack(pady=(10, 4))
    DS.label(win, "URL:", font=BODY).pack()
    e = DS.entry(win, width=60)
    e.pack(pady=4)
    result_text = tk.Text(win, font=MONO, bg=BG_CARD, fg=FG_PRIMARY,
                          relief="flat", height=8, width=65)
    result_text.pack(pady=6)

    def trace() -> None:
        url = e.get().strip()
        if not url:
            return
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        from instareport.utils.helpers import _req
        result_text.delete("1.0", "end")
        result_text.insert("1.0", f"Tracing: {url}\n")
        try:
            resp = _req('get', url, allow_redirects=True,
                        timeout=15, _retries=1)
            history = resp.history + [resp]
            lines = [f"Step {i}: {r.status_code}  {r.url}" for i, r in enumerate(history)]
            lines.append("")
            lines.append(f"Final URL: {resp.url}")
            lines.append(f"Final status: {resp.status_code}")
            lines.append(f"Redirects: {len(resp.history)}")
            result_text.insert("end", "\n".join(lines))
            log(f"[TRACE] {url} -> {resp.url} ({resp.status_code}, {len(resp.history)} redirects)", "ok")
        except Exception as ex:
            result_text.insert("end", f"Failed: {ex}")

    DS.primary_btn(win, "Trace", command=trace).pack(pady=4)


def open_hash_lookup(parent: tk.Widget) -> None:
    win = _tool_win("Hash Lookup", 500, 300, parent)
    DS.label(win, "Have I Been Pwned — Breach Check", font=H2).pack(pady=(10, 4))
    DS.label(win, "Email / Username:", font=BODY).pack()
    e = DS.entry(win, width=36)
    e.pack(pady=4)
    result_text = tk.Text(win, font=MONO, bg=BG_CARD, fg=FG_PRIMARY,
                          relief="flat", height=10, width=55)
    result_text.pack(pady=6)

    def check() -> None:
        query = e.get().strip()
        if not query:
            return
        import hashlib
        from instareport.utils.helpers import _req
        result_text.delete("1.0", "end")
        result_text.insert("1.0", f"Checking {query}...\n")
        try:
            sha1 = hashlib.sha1(query.encode()).hexdigest().upper()
            prefix, suffix = sha1[:5], sha1[5:]
            r = _req('get', f"https://api.pwnedpasswords.com/range/{prefix}",
                     timeout=10)
            if r.status_code == 200:
                hashes = [l.split(":") for l in r.text.splitlines()]
                matched = [h for h in hashes if h[0] == suffix]
                if matched:
                    count = int(matched[0][1])
                    lines = [f"Found in {count} breach(es)!"]
                    # Try full breach names via HIBP API
                    try:
                        r2 = _req('get', f"https://haveibeenpwned.com/api/v3/breachedaccount/{query}",
                                  headers={"hibp-api-key": ""}, timeout=10)
                        if r2.status_code == 200:
                            breaches = r2.json()
                            for b in breaches:
                                lines.append(f"  - {b.get('Name', '?')} ({b.get('BreachDate', '?')})")
                    except Exception:
                        lines.append("  (use hibp-api-key for breach names)")
                    result_text.delete("1.0", "end")
                    result_text.insert("1.0", "\n".join(lines))
                    log(f"[HIBP] {query}: {count} breaches", "err" if count > 0 else "ok")
                else:
                    result_text.delete("1.0", "end")
                    result_text.insert("1.0", "No breaches found — account appears clean")
                    log(f"[HIBP] {query}: no breaches", "ok")
            else:
                result_text.insert("end", f"API error: {r.status_code}")
        except Exception as ex:
            result_text.insert("end", f"Lookup failed: {ex}")

    DS.primary_btn(win, "Check Breaches", command=check).pack(pady=4)


def open_report_templates(parent: tk.Widget) -> None:
    win = _tool_win("Report Templates", 500, 350, parent)
    DS.label(win, "Save / Load Report Configurations", font=H2).pack(pady=(10, 4))
    from instareport.core.database import _connection
    conn = _connection()
    templates_raw = conn.execute("SELECT value FROM settings WHERE key='report_templates'").fetchone()
    templates: dict = {}
    if templates_raw:
        try:
            templates = json.loads(templates_raw["value"])
        except Exception:
            templates = {}
    conn.close()

    frame = tk.Frame(win, bg=BG_CARD)
    frame.pack(fill="both", expand=True, padx=10, pady=6)
    cols = ("Name", "Target", "Platform", "Reason", "Workers")
    tree = ttk.Treeview(frame, columns=cols, show="headings", height=10)
    for c in cols:
        tree.heading(c, text=c)
        tree.column(c, width=90)
    tree.pack(side="left", fill="both", expand=True)
    sb = DS.scrollbar(frame)
    sb.pack(side="right", fill="y")
    tree.config(yscrollcommand=sb.set)
    sb.config(command=tree.yview)

    def refresh_tree() -> None:
        for item in tree.get_children():
            tree.delete(item)
        for name, cfg in templates.items():
            tree.insert("", "end", values=(
                name, cfg.get("target", ""), cfg.get("platform", ""),
                cfg.get("reason", ""), str(cfg.get("workers", 0))
            ))

    def save_current() -> None:
        from tkinter.simpledialog import askstring
        name = askstring("Template Name", "Enter template name:")
        if not name:
            return
        templates[name] = {
            "target": S.target, "platform": S.platform, "reason": S.reason,
            "workers": S.workers, "accounts": list(S.accounts),
            "cooldown_secs": S.cooldown_secs,
            "headless": S.headless, "safe_mode": S.safe_mode,
            "stealth": S.stealth,
        }
        conn2 = _connection()
        conn2.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('report_templates', ?)",
                      (json.dumps(templates),))
        conn2.commit()
        conn2.close()
        refresh_tree()
        log(f"[TEMPLATE] Saved '{name}'", "ok")

    def load_selected() -> None:
        sel = tree.selection()
        if not sel:
            return
        name = tree.item(sel[0], "values")[0]
        cfg = templates.get(name)
        if not cfg:
            return
        S.target = cfg.get("target", "")
        S.platform = cfg.get("platform", "instagram")
        S.reason = cfg.get("reason", "spam")
        S.workers = int(cfg.get("workers", 2))
        if cfg.get("accounts"):
            S.accounts = list(cfg["accounts"])
        S.cooldown_secs = int(cfg.get("cooldown_secs", 300))
        S.headless = cfg.get("headless", False)
        S.stealth = cfg.get("stealth", False)
        save_config()
        log(f"[TEMPLATE] Loaded '{name}' — ready to run", "ok")
        win.destroy()

    def delete_selected() -> None:
        sel = tree.selection()
        if not sel:
            return
        name = tree.item(sel[0], "values")[0]
        if name in templates:
            del templates[name]
            conn3 = _connection()
            conn3.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('report_templates', ?)",
                          (json.dumps(templates),))
            conn3.commit()
            conn3.close()
            refresh_tree()
            log(f"[TEMPLATE] Deleted '{name}'", "ok")

    refresh_tree()
    btn_bar = tk.Frame(win, bg=BG_DARK)
    btn_bar.pack(fill="x", padx=10, pady=4)
    DS.primary_btn(btn_bar, "Save Current", command=save_current, width=12).pack(side="left", padx=2)
    DS.ghost_btn(btn_bar, "Load", command=load_selected, width=8).pack(side="left", padx=2)
    DS.danger_btn(btn_bar, "Delete", command=delete_selected, width=8).pack(side="left", padx=2)


def open_account_groups(parent: tk.Widget) -> None:
    win = _tool_win("Account Groups", 550, 380, parent)
    DS.label(win, "Manage Account Groups", font=H2).pack(pady=(10, 4))
    from instareport.core.database import get_account_groups, set_account_group, delete_account_group

    frame = tk.Frame(win, bg=BG_CARD)
    frame.pack(fill="both", expand=True, padx=10, pady=6)
    cols = ("Group", "Accounts")
    tree = ttk.Treeview(frame, columns=cols, show="headings", height=12)
    for c in cols:
        tree.heading(c, text=c)
        tree.column("Group", width=120)
        tree.column("Accounts", width=300)
    tree.pack(side="left", fill="both", expand=True)
    sb = DS.scrollbar(frame)
    sb.pack(side="right", fill="y")
    tree.config(yscrollcommand=sb.set)
    sb.config(command=tree.yview)

    def refresh() -> None:
        for item in tree.get_children():
            tree.delete(item)
        groups = get_account_groups()
        for g, users in groups.items():
            tree.insert("", "end", values=(g, ", ".join(users)))

    def create_group() -> None:
        from tkinter.simpledialog import askstring
        name = askstring("Group Name", "Enter group name:")
        if not name:
            return
        usernames = [a[0] if isinstance(a, (list, tuple)) else a.username for a in S.accounts]
        set_account_group(name, usernames)
        refresh()
        log(f"[GROUPS] Created '{name}' with {len(usernames)} accounts", "ok")

    def use_group() -> None:
        sel = tree.selection()
        if not sel:
            return
        group_name = tree.item(sel[0], "values")[0]
        from instareport.core.database import get_account_groups
        groups = get_account_groups()
        users = groups.get(group_name, [])
        if not users:
            return
        from instareport.core.state import ACCOUNTS_LOCK
        with ACCOUNTS_LOCK:
            S.accounts = [(u, "") for u in users]
        log(f"[GROUPS] Loaded '{group_name}' — {len(users)} accounts ready", "ok")
        save_config()
        win.destroy()

    def delete_group() -> None:
        sel = tree.selection()
        if not sel:
            return
        name = tree.item(sel[0], "values")[0]
        if messagebox.askyesno("Delete Group", f"Delete group '{name}'?"):
            delete_account_group(name)
            refresh()
            log(f"[GROUPS] Deleted '{name}'", "ok")

    refresh()
    btn_bar = tk.Frame(win, bg=BG_DARK)
    btn_bar.pack(fill="x", padx=10, pady=4)
    DS.primary_btn(btn_bar, "Create from Accounts", command=create_group, width=16).pack(side="left", padx=2)
    DS.ghost_btn(btn_bar, "Use Group", command=use_group, width=10).pack(side="left", padx=2)
    DS.danger_btn(btn_bar, "Delete", command=delete_group, width=8).pack(side="left", padx=2)


def open_stealth(parent: tk.Widget) -> None:
    S.stealth = not S.stealth
    log(f"Stealth Mode: {'enabled' if S.stealth else 'disabled'}", "ok")


def open_dark_pattern(parent: tk.Widget) -> None:
    log("Dark Pattern: not available in this build", "dim")


def open_net_spoof(parent: tk.Widget) -> None:
    log("Network Spoof: not available in this build", "dim")


def open_behavior(parent: tk.Widget) -> None:
    log("Behavior Mimic: not available in this build", "dim")


def open_rate_limit(parent: tk.Widget) -> None:
    _open_rate_limit(parent)


def open_header_forge(parent: tk.Widget) -> None:
    log("Header Forge: not available in this build", "dim")


def open_cookie_inject(parent: tk.Widget) -> None:
    _open_cookie_inject(parent)


def open_canvas_spoof(parent: tk.Widget) -> None:
    log("Canvas Spoof: not available in this build", "dim")
