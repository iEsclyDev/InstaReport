"""Instagram Private API engine — browser-free Instagram operations via instagrapi."""
import asyncio, time, json
from pathlib import Path
from typing import Callable, Any

from instareport.utils.constants import SESSIONS_DIR, DEBUG
from instareport.utils.logging import dlog

try:
    from instagrapi import Client
    from instagrapi.exceptions import LoginRequired, ClientError, TwoFactorRequired
    _API_AVAILABLE = True
except ImportError:
    _API_AVAILABLE = False
    Client = Any

LogFn = Callable[[str], None]


def _settings_path(user: str) -> Path:
    safe = "".join(c for c in user if c.isalnum() or c in "-_.")
    return SESSIONS_DIR / f"{safe}_igapi.json"


def _login(user: str, pw: str, log_fn: LogFn) -> Client | None:
    if not _API_AVAILABLE:
        log_fn("  [IG-API] instagrapi not installed — run: pip install instagrapi")
        return None
    cl = Client()
    cl.delay_range = [2, 5]
    settings_path = _settings_path(user)
    if settings_path.exists():
        try:
            cl.load_settings(str(settings_path))
            cl.login(user, pw)
            log_fn("  [IG-API] Session loaded from saved settings")
            return cl
        except LoginRequired:
            log_fn("  [IG-API] Saved session expired, re-logging in...")
            settings_path.unlink(missing_ok=True)
        except Exception as _e:
            dlog(f"igapi load_settings: {_e}")
            settings_path.unlink(missing_ok=True)
    try:
        cl.login(user, pw)
        cl.dump_settings(str(settings_path))
        log_fn("  [IG-API] Login successful")
        return cl
    except TwoFactorRequired:
        log_fn("  [IG-API] 2FA required — manual intervention needed")
        return None
    except Exception as _e:
        log_fn(f"  [IG-API] Login failed: {_e}")
        return None


def report_user(cl: Client, target: str, reason: str = "spam", log_fn: LogFn | None = None) -> bool:
    if not _API_AVAILABLE:
        return False
    lg = log_fn or (lambda m: None)
    try:
        user_id = cl.user_id_from_username(target)
        lg(f"  [IG-API] Found target user_id: {user_id}")
        reason_map = {
            "spam": "SPAM",
            "harassment": "BULLYING_OR_HARASSMENT",
            "impersonation": "FALSE_INFORMATION",
            "hate": "HATE_SPEECH",
            "nudity": "NUDITY_OR_SEXUAL_ACTIVITY",
            "violence": "VIOLENCE_OR_THREATENING_ORGANIZATIONS",
            "misinformation": "FALSE_INFORMATION",
            "scam": "FRAUD_OR_SCAM",
        }
        ig_reason = reason_map.get(reason, "SPAM")
        result = cl.report_user(user_id, ig_reason)
        lg(f"  [IG-API] Report submitted: {result}")
        return True
    except LoginRequired:
        lg("  [IG-API] Session expired, re-login required")
        settings_path = _settings_path(user)
        settings_path.unlink(missing_ok=True)
        return False
    except Exception as _e:
        lg(f"  [IG-API] Report failed: {_e}")
        return False


async def flow_instagram_api(user: str, pw: str, target: str, reason: str, log_fn: LogFn) -> bool:
    """Run an Instagram report via the Private API (no browser)."""
    log_fn("  [IG-API] Using Instagram Private API (browserless)...")
    cl = _login(user, pw, log_fn)
    if not cl:
        return False
    ok = report_user(cl, target, reason, log_fn)
    try:
        cl.logout()
    except Exception:
        pass
    return ok
