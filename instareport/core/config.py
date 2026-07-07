"""Config persistence — save/load settings to config.json with encrypted credentials."""
import json, os, hashlib, base64, threading, time, shutil
from pathlib import Path
from datetime import datetime
from typing import Any

from cryptography.fernet import Fernet as _Fernet, InvalidToken as _InvalidToken
import cryptography.hazmat.primitives.kdf.pbkdf2 as _pbkdf2
import cryptography.hazmat.primitives.hashes as _hashes
import platform, uuid

from instareport.utils.constants import PBKDF2_ITERATIONS, DEBUG, VERSION, CONFIG_FILE
from instareport.core.state import S, ACCOUNTS_LOCK, COOLDOWN_LOCK, CONFIG_LOCK
from instareport.utils.logging import dlog, flog

_CRED_SALT: bytes = hashlib.sha256(
    f"InstaReport-{uuid.getnode()}-{platform.node()}".encode()
).digest()[:16]
_CRED_RAW: bytes = f"{uuid.getnode()}-{platform.node()}-InstaReport".encode()


def _make_cred_fernet() -> _Fernet:
    kdf = _pbkdf2.PBKDF2HMAC(
        algorithm=_hashes.SHA256(), length=32,
        salt=_CRED_SALT, iterations=PBKDF2_ITERATIONS
    )
    return _Fernet(base64.urlsafe_b64encode(kdf.derive(_CRED_RAW)))


_CRED_KEY_LEGACY: bytes = hashlib.sha256(_CRED_RAW).digest()


def _xor_decrypt_legacy(s: str) -> str:
    try:
        b = base64.b64decode(s.encode())
        key = (_CRED_KEY_LEGACY * (len(b) // len(_CRED_KEY_LEGACY) + 1))[:len(b)]
        return bytes(x ^ y for x, y in zip(b, key)).decode()
    except Exception:
        return s


def _encrypt_str(s: str) -> str:
    return _make_cred_fernet().encrypt(s.encode()).decode()


def _decrypt_str(s: str) -> str:
    try:
        return _make_cred_fernet().decrypt(s.encode()).decode()
    except (_InvalidToken, Exception):
        result = _xor_decrypt_legacy(s)
        dlog("migrated legacy XOR credential to Fernet on next save")
        return result


def _encrypt_accounts(accounts: list[tuple[str, str]]) -> list[list[str]]:
    return [[_encrypt_str(u), _encrypt_str(p)] for u, p in accounts]


def _decrypt_accounts(raw: list) -> list[tuple[str, str]]:
    result: list[tuple[str, str]] = []
    for a in raw:
        if isinstance(a, list) and len(a) >= 2:
            result.append((_decrypt_str(a[0]), _decrypt_str(a[1])))
        elif isinstance(a, dict):
            result.append((_decrypt_str(a.get("user", "")), _decrypt_str(a.get("pw", ""))))
    return result


def _is_on_cooldown(user: str) -> bool:
    with COOLDOWN_LOCK:
        last = S.cooldowns.get(user, 0)
    return (time.time() - last) < S.cooldown_secs


def _mark_used(user: str) -> None:
    with COOLDOWN_LOCK:
        S.cooldowns[user] = time.time()


def _clear_all_cooldowns() -> None:
    with COOLDOWN_LOCK:
        S.cooldowns.clear()


def _cooldown_remaining(user: str) -> int:
    with COOLDOWN_LOCK:
        last = S.cooldowns.get(user, 0)
    remaining = S.cooldown_secs - (time.time() - last)
    return max(0, int(remaining))


def _get_cooldowns_snapshot() -> dict[str, float]:
    with COOLDOWN_LOCK:
        return dict(S.cooldowns)


def _restore_cooldowns(data: dict[str, float]) -> None:
    cutoff = time.time() - S.cooldown_secs * 2
    with COOLDOWN_LOCK:
        S.cooldowns = {u: t for u, t in data.items() if t > cutoff}


_config_save_timer: threading.Timer | None = None


def save_config_debounced(delay: float = 2.0) -> None:
    global _config_save_timer
    if _config_save_timer is not None:
        _config_save_timer.cancel()
    _config_save_timer = threading.Timer(delay, save_config)
    _config_save_timer.daemon = True
    _config_save_timer.start()


def save_config() -> None:
    if S.use_sqlite:
        from instareport.core.database import save_config_sqlite
        save_config_sqlite()
        return
    global _config_save_timer, CONFIG_FILE
    if _config_save_timer is not None:
        _config_save_timer.cancel()
        _config_save_timer = None
    with ACCOUNTS_LOCK:
        _accts_snapshot = list(S.accounts)
        if DEBUG:
            dlog(f"[ACCT-DEBUG] save_config snapshot len={len(_accts_snapshot)}")
    with CONFIG_LOCK:
        try:
            data: dict[str, Any] = {
                "config_version": 1,
                "version": VERSION,
                "platform": S.platform,
                "reason": S.reason,
                "workers": S.workers,
                "headless": S.headless,
                "safe_mode": S.safe_mode,
                "stealth": S.stealth,
                "rate_limit": S.rate_limit,
                "max_retries": S.max_retries,
                "captcha_svc": S.captcha_svc,
                "captcha_key": _encrypt_str(S.captcha_key) if S.captcha_key else "",
                "proxy_file": S.proxy_file,
                "cooldown_secs": S.cooldown_secs,
                "sched_enabled": S.sched_enabled,
                "sched_time": S.sched_time,
                "sched_repeat": S.sched_repeat,
                "sched_interval": S.sched_interval,
                "accounts": _encrypt_accounts(_accts_snapshot),
                "cooldowns": _get_cooldowns_snapshot(),
                "screenshot_cleanup_days": S.screenshot_cleanup_days,
                "custom_headers": S.custom_headers,
                "favorites": list(S.favorites),
                "presets": S.presets,
                "webhook_url": S.webhook_url,
                "mobile_emulate": S.mobile_emulate,
                "warmup_enabled": S.warmup_enabled,
                "chrome_user_data_dir": S.chrome_user_data_dir,
                "api_mode": S.api_mode,
            }
            bak = Path(str(CONFIG_FILE) + ".bak")
            if CONFIG_FILE and CONFIG_FILE.exists():
                try:
                    import shutil
                    shutil.copy2(CONFIG_FILE, bak)
                except Exception as _bak_e:
                    dlog(f"config backup: {_bak_e}")
            if CONFIG_FILE:
                tmp = Path(str(CONFIG_FILE) + ".tmp")
                try:
                    with open(tmp, "w", encoding="utf-8") as f:
                        json.dump(data, f, indent=2)
                    tmp.replace(CONFIG_FILE)
                except Exception as _write_e:
                    try:
                        tmp.unlink(missing_ok=True)
                    except Exception:
                        pass
                    raise _write_e
        except Exception as _e:
            dlog(f"save_config failed: {_e}")


def export_backup(path: str | Path, backup_key: str | None = None) -> bool:
    """Encrypt and export all config state to a backup file."""
    from instareport.core.database import _connection
    try:
        conn = _connection()
        settings = dict(conn.execute("SELECT key, value FROM settings").fetchall())
        accounts = [dict(r) for r in conn.execute("SELECT username, password FROM accounts").fetchall()]
        cooldowns = [dict(r) for r in conn.execute("SELECT username, cooldown_until FROM cooldowns").fetchall()]
        conn.close()
        payload = {
            "backup_version": 1,
            "app_version": VERSION,
            "timestamp": datetime.now().isoformat(),
            "settings": settings,
            "accounts": accounts,
            "cooldowns": cooldowns,
        }
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        key = _make_cred_fernet() if not backup_key else _Fernet(backup_key.encode() if isinstance(backup_key, str) else backup_key)
        encrypted = key.encrypt(raw)
        Path(path).write_bytes(encrypted)
        dlog(f"Config backup written to {path}")
        return True
    except Exception as e:
        dlog(f"export_backup failed: {e}")
        return False


def import_backup(path: str | Path, backup_key: str | None = None) -> bool:
    """Decrypt and restore all config state from a backup file."""
    from instareport.core.database import _connection
    from instareport.plugins.loader import discover_plugins as _rediscover_plugins
    from instareport.core.state import S, ACCOUNTS_LOCK, COOLDOWN_LOCK
    try:
        encrypted = Path(path).read_bytes()
        key = _make_cred_fernet() if not backup_key else _Fernet(backup_key.encode() if isinstance(backup_key, str) else backup_key)
        decrypted = key.decrypt(encrypted)
        payload = json.loads(decrypted.decode("utf-8"))
        if payload.get("backup_version") != 1:
            dlog(f"Unknown backup version: {payload.get('backup_version')}")
            return False
        conn = _connection()
        conn.execute("DELETE FROM settings")
        for k, v in payload.get("settings", {}).items():
            conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (k, str(v)))
        conn.execute("DELETE FROM accounts")
        for a in payload.get("accounts", []):
            conn.execute("INSERT INTO accounts (username, password) VALUES (?, ?)",
                         (a.get("username", ""), a.get("password", "")))
        conn.execute("DELETE FROM cooldowns")
        for c in payload.get("cooldowns", []):
            conn.execute("INSERT INTO cooldowns (username, cooldown_until) VALUES (?, ?)",
                         (c.get("username", ""), c.get("cooldown_until", 0)))
        conn.commit()
        conn.close()
        # Reload config into memory
        from instareport.core.config import load_config
        load_config()
        # Re-discover plugins in case plugin_dir changed
        _rediscover_plugins()
        dlog(f"Config restored from {path}")
        return True
    except Exception as e:
        dlog(f"import_backup failed: {e}")
        return False


def load_config() -> None:
    if S.use_sqlite:
        from instareport.core.database import load_config_sqlite
        data = load_config_sqlite()
        settings = data.get("settings", {})
        S.platform = settings.get("platform", S.platform)
        S.reason = settings.get("reason", S.reason)
        S.workers = int(settings.get("workers", S.workers))
        S.headless = settings.get("headless", "False") == "True"
        S.safe_mode = settings.get("safe_mode", "False") == "True"
        S.stealth = settings.get("stealth", "False") == "True"
        S.rate_limit = int(settings.get("rate_limit", S.rate_limit))
        S.max_retries = int(settings.get("max_retries", S.max_retries))
        S.captcha_svc = settings.get("captcha_svc", S.captcha_svc)
        raw = settings.get("captcha_key", "")
        S.captcha_key = _decrypt_str(raw) if raw else ""
        S.proxy_file = settings.get("proxy_file", S.proxy_file)
        S.cooldown_secs = int(settings.get("cooldown_secs", S.cooldown_secs))
        S.sched_enabled = settings.get("sched_enabled", "False") == "True"
        S.sched_time = settings.get("sched_time", S.sched_time)
        S.sched_repeat = settings.get("sched_repeat", "False") == "True"
        S.sched_interval = int(settings.get("sched_interval", S.sched_interval))
        S.screenshot_cleanup_days = int(settings.get("screenshot_cleanup_days", S.screenshot_cleanup_days))
        S.webhook_url = settings.get("webhook_url", "")
        S.mobile_emulate = settings.get("mobile_emulate", "False") == "True"
        S.warmup_enabled = settings.get("warmup_enabled", "True") == "True"
        S.chrome_user_data_dir = settings.get("chrome_user_data_dir", "")
        S.api_mode = settings.get("api_mode", "browser")
        import json
        try: S.favorites = set(json.loads(settings.get("favorites", "[]")))
        except Exception: pass
        try: S.presets = json.loads(settings.get("presets", "{}"))
        except Exception: pass
        with ACCOUNTS_LOCK:
            S.accounts = data.get("accounts", [])
        from instareport.core.database import migrate_from_json
        _restore_cooldowns(data.get("cooldowns", {}))
        return
    if not CONFIG_FILE:
        return
    bak = Path(str(CONFIG_FILE) + ".bak")
    d: dict = {}
    for path in (CONFIG_FILE, bak):
        if not path.exists():
            continue
        try:
            with open(path, encoding="utf-8") as f:
                d = json.load(f)
            break
        except Exception as _e:
            dlog(f"load_config {path.name} bad: {_e}")
            continue
    else:
        return
    cfg_ver = d.get("config_version", 0)
    if cfg_ver < 1:
        dlog("migrating config from pre-v1 schema")
    try:
        S.platform = d.get("platform", S.platform)
        S.reason = d.get("reason", S.reason)
        S.workers = d.get("workers", S.workers)
        S.headless = d.get("headless", S.headless)
        S.safe_mode = d.get("safe_mode", S.safe_mode)
        S.stealth = d.get("stealth", S.stealth)
        S.rate_limit = d.get("rate_limit", S.rate_limit)
        S.max_retries = d.get("max_retries", S.max_retries)
        S.captcha_svc = d.get("captcha_svc", S.captcha_svc)
        raw_key = d.get("captcha_key", "")
        S.captcha_key = _decrypt_str(raw_key) if raw_key else ""
        S.proxy_file = d.get("proxy_file", S.proxy_file)
        S.cooldown_secs = d.get("cooldown_secs", S.cooldown_secs)
        S.sched_enabled = d.get("sched_enabled", S.sched_enabled)
        S.sched_time = d.get("sched_time", S.sched_time)
        S.sched_repeat = d.get("sched_repeat", S.sched_repeat)
        S.sched_interval = d.get("sched_interval", S.sched_interval)
        S.screenshot_cleanup_days = d.get("screenshot_cleanup_days", S.screenshot_cleanup_days)
        S.custom_headers = d.get("custom_headers", S.custom_headers)
        S.favorites = set(d.get("favorites", []))
        S.presets = d.get("presets", {})
        S.webhook_url = d.get("webhook_url", "")
        S.mobile_emulate = d.get("mobile_emulate", False)
        S.warmup_enabled = d.get("warmup_enabled", True)
        S.chrome_user_data_dir = d.get("chrome_user_data_dir", "")
        S.api_mode = d.get("api_mode", "browser")
        with ACCOUNTS_LOCK:
            S.accounts = _decrypt_accounts(d.get("accounts", []))
            if DEBUG:
                dlog(f"[ACCT-DEBUG] load_config: loaded {len(S.accounts)} accounts from disk")
        raw_cd = d.get("cooldowns", {})
        if isinstance(raw_cd, dict):
            _restore_cooldowns(raw_cd)
    except Exception as _e:
        dlog(f"ignored: {_e}")
