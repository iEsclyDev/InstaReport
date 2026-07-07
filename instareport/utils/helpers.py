"""Utility helpers used across the application."""
import os, sys, json, time, threading, subprocess, random, traceback, socket, base64
import asyncio
from pathlib import Path
from datetime import datetime
from typing import Callable, Any
from requests import Response

from instareport.utils.constants import (
    DEBUG, HEADLESS, _TARGET_RE, MAX_USERNAME_LEN, OTP_TIMEOUT_SECS,
    CONFIG_FILE, SESSIONS_DIR, SCREENSHOTS_DIR, API_BASE, VERSION,
    _VALID_HTTP_METHODS,
)
from instareport.utils.logging import log, flog, dlog, init_file_logger
from instareport.core.state import S, GLOBAL_STOP

import requests


def _req(method: str, url: str, **kw: Any) -> Response:
    if method not in _VALID_HTTP_METHODS:
        raise ValueError(f"Invalid HTTP method: {method}")
    if url.startswith("http://") and not kw.pop("_allow_http", False):
        dlog(f"WARNING: Non-HTTPS request to {url[:60]}")
    kw.setdefault("timeout", 30)
    retries: int = kw.pop("_retries", 1)
    for attempt in range(retries + 1):
        try:
            resp: Response = getattr(requests, method)(url, **kw)
            return resp
        except requests.exceptions.ConnectionError:
            if attempt < retries:
                time.sleep(2 ** attempt)
                continue
            raise


def _stopped() -> bool:
    return S.stop_event.is_set() or GLOBAL_STOP.is_set()


def _safe(fn: Callable, *args: Any, default: Any = False, label: str = "", **kwargs: Any) -> Any:
    try:
        return fn(*args, **kwargs)
    except Exception as e:
        dlog(f"{label or fn.__name__}: {type(e).__name__}: {e}")
        return default


def _center_on_parent(win: Any, parent: Any, w: int, h: int) -> None:
    try:
        px = parent.winfo_rootx() + (parent.winfo_width() - w) // 2
        py = parent.winfo_rooty() + (parent.winfo_height() - h) // 2
        px = max(0, px)
        py = max(0, py)
    except Exception:
        px = (win.winfo_screenwidth() - w) // 2
        py = (win.winfo_screenheight() - h) // 2
    win.geometry(f"{w}x{h}+{px}+{py}")


def _validate_target(raw: str) -> tuple[bool, str]:
    cleaned = raw.strip().lstrip("@").strip()
    if not cleaned:
        return False, "Target username is empty."
    if len(cleaned) > MAX_USERNAME_LEN:
        return False, f"Username too long ({len(cleaned)} chars, max {MAX_USERNAME_LEN})."
    if not _TARGET_RE.match(cleaned):
        return False, f"Invalid characters in target: {cleaned!r}"
    return True, cleaned


def _validate_sched_time(raw: str) -> tuple[bool, str]:
    import re
    raw = raw.strip()
    m = re.match(r'^(\d{1,2}):(\d{2})$', raw)
    if not m:
        return False, f"Invalid time format: {raw!r} (expected HH:MM)"
    h, mi = int(m.group(1)), int(m.group(2))
    if h > 23 or mi > 59:
        return False, f"Invalid time: {h:02d}:{mi:02d}"
    return True, f"{h:02d}:{mi:02d}"


def _run_async_in_thread(coro_fn: Callable, *args: Any, daemon: bool = True) -> threading.Thread:
    def _thread_target() -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(coro_fn(*args))
        except Exception as _exc:
            try:
                dlog(f"_run_async_in_thread error in {coro_fn.__name__}: {_exc}")
                flog(f"async thread crash: {_exc}\n{traceback.format_exc()}", "error")
                if S.log_cb:
                    S.log_cb(f"[!] Async error: {_exc}", "err")
            except Exception:
                pass
        finally:
            loop.close()
    t = threading.Thread(target=_thread_target, daemon=daemon)
    t.start()
    return t


def _system_notify(title: str, msg: str) -> None:
    try:
        title_safe = str(title).replace("'", "").replace('"', '').replace('`', '')[:80]
        msg_safe = str(msg).replace("'", "").replace('"', '').replace('`', '')[:200]
        if sys.platform == "win32":
            try:
                from ctypes import windll
                windll.user32.MessageBeep(0)
            except Exception:
                pass
            try:
                import base64 as _b64
                ps_script = (
                    f"[System.Reflection.Assembly]::LoadWithPartialName('System.Windows.Forms') | Out-Null;"
                    f"$n = New-Object System.Windows.Forms.NotifyIcon;"
                    f"$n.Icon = [System.Drawing.SystemIcons]::Information;"
                    f"$n.Visible = $true;"
                    f"$n.ShowBalloonTip(4000, '{title_safe}', '{msg_safe}', "
                    f"[System.Windows.Forms.ToolTipIcon]::Info);"
                    f"Start-Sleep -Seconds 5; $n.Dispose()"
                )
                encoded = _b64.b64encode(ps_script.encode("utf-16-le")).decode("ascii")
                subprocess.Popen([
                    "powershell", "-WindowStyle", "Hidden",
                    "-EncodedCommand", encoded
                ], creationflags=0x08000000)
            except Exception:
                pass
        elif sys.platform == "darwin":
            try:
                import json as _jn
                subprocess.Popen([
                    "osascript", "-l", "JavaScript", "-e",
                    f"var a=Application.currentApplication();a.includeStandardAdditions=true;"
                    f"a.displayNotification({_jn.dumps(msg_safe)},{{withTitle:{_jn.dumps(title_safe)}}})"
                ])
            except Exception:
                pass
        else:
            subprocess.Popen(["notify-send", "-t", "5000", title_safe, msg_safe])
    except Exception:
        pass


def _fire_webhook(payload: dict) -> None:
    url = S.webhook_url
    if not url:
        return

    def _send() -> None:
        try:
            resp = _req('post', url, json=payload, timeout=10)
            dlog(f"Webhook POST {url} -> {resp.status_code}")
            flog(f"webhook: {url} -> {resp.status_code}", "info")
        except Exception as e:
            dlog(f"Webhook failed: {e}")
            flog(f"webhook error: {url} -> {e}", "error")
    threading.Thread(target=_send, daemon=True).start()


def _random_public_ip() -> str:
    while True:
        a, b, c, d = (random.randint(1, 254) for _ in range(4))
        if a == 10: continue
        if a == 172 and 16 <= b <= 31: continue
        if a == 192 and b == 168: continue
        if a == 127 or (a == 169 and b == 254): continue
        if a >= 224: continue
        return f"{a}.{b}.{c}.{d}"


def _export_report_html(path: str) -> bool:
    """Export run history as a formatted HTML report."""
    from instareport.core.database import get_run_logs
    from datetime import datetime
    rows = get_run_logs(limit=500)
    if not rows:
        return False
    html_parts = [
        "<!DOCTYPE html><html><head><meta charset='utf-8'>",
        "<title>InstaReport - Run History</title>",
        "<style>body{font-family:sans-serif;margin:20px;color:#333}",
        "h1{color:#00E5A0}table{border-collapse:collapse;width:100%}",
        "th,td{padding:8px;text-align:left;border-bottom:1px solid #ddd}",
        "th{background:#1a1a2e;color:#fff}</style></head><body>",
        f"<h1>InstaReport Run History</h1>",
        f"<p>Generated: {datetime.now().isoformat()}</p>",
        f"<p>Total runs: {len(rows)}</p>",
        "<table><tr><th>Time</th><th>Target</th><th>Platform</th>",
        "<th>Reason</th><th>Successes</th><th>Total</th><th>Elapsed</th></tr>",
    ]
    for r in rows:
        ts = str(r.get("timestamp", ""))[:19]
        html_parts.append(
            f"<tr><td>{ts}</td><td>{r.get('target','')}</td>"
            f"<td>{r.get('platform','')}</td><td>{r.get('reason','')}</td>"
            f"<td>{r.get('successes',0)}</td><td>{r.get('total',0)}</td>"
            f"<td>{r.get('elapsed_s',0)}s</td></tr>"
        )
    html_parts.append("</table></body></html>")
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(html_parts))
        return True
    except Exception:
        return False


def _check_for_update() -> dict | None:
    """Check GitHub for newer release. Returns dict with version/url/body or None."""
    try:
        from instareport.utils.constants import GITHUB_REPO
        import urllib.request as _ur, json as _json
        url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
        req = _ur.Request(url, headers={"User-Agent": "InstaReport", "Accept": "application/vnd.github.v3+json"})
        with _ur.urlopen(req, timeout=10) as resp:
            data = _json.loads(resp.read().decode())
        latest = data.get("tag_name", "").lstrip("v")
        current = VERSION.split("-")[0]
        def _ver_tuple(v):
            parts = v.split(".")
            return tuple(int(p) if p.isdigit() else 0 for p in parts)
        if latest and _ver_tuple(latest) > _ver_tuple(current):
            return {
                "version": latest,
                "url": data.get("html_url", f"https://github.com/{GITHUB_REPO}/releases/latest"),
                "body": (data.get("body") or "")[:500],
            }
    except Exception:
        pass
    return None


def _force_reload_accounts() -> None:
    if not CONFIG_FILE or not CONFIG_FILE.exists():
        return
    try:
        with open(CONFIG_FILE, encoding="utf-8") as f:
            d = json.load(f)
        from instareport.core.config import _decrypt_accounts
        reloaded = _decrypt_accounts(d.get("accounts", []))
        from instareport.core.state import ACCOUNTS_LOCK
        with ACCOUNTS_LOCK:
            S.accounts = reloaded
            if DEBUG:
                dlog(f"[ACCT-DEBUG] _force_reload_accounts: len={len(reloaded)}")
    except Exception as _e:
        dlog(f"_force_reload_accounts failed: {_e}")
