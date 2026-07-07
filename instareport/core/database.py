"""SQLite persistence — thread-safe config/account/cooldown/run_log storage with WAL mode."""
import sqlite3, json, threading, time, os
from pathlib import Path
from typing import Any

import instareport.utils.constants as _constants

_DB_PATH: Path | None = None
_queue: list[tuple[str, list[Any]]] = []
_queue_lock: threading.Lock = threading.Lock()
_WRITER_INTERVAL: float = 1.0


def _get_db_path() -> Path:
    global _DB_PATH
    if _DB_PATH is None:
        if _constants.CONFIG_FILE:
            _DB_PATH = _constants.CONFIG_FILE.with_suffix(".db")
        else:
            _DB_PATH = Path("instareport.db")
    return _DB_PATH


def _connection() -> sqlite3.Connection:
    db = _get_db_path()
    conn = sqlite3.connect(str(db), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def init_db() -> None:
    conn = _connection()
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                password TEXT NOT NULL,
                created_at REAL NOT NULL DEFAULT (julianday('now'))
            );
            CREATE TABLE IF NOT EXISTS cooldowns (
                username TEXT PRIMARY KEY,
                cooldown_until REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS run_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                target TEXT NOT NULL,
                platform TEXT NOT NULL,
                reason TEXT NOT NULL,
                successes INTEGER DEFAULT 0,
                total INTEGER DEFAULT 0,
                elapsed_s REAL DEFAULT 0,
                timestamp TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS follower_tracking (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                platform TEXT NOT NULL,
                followers INTEGER DEFAULT 0,
                following INTEGER DEFAULT 0,
                posts INTEGER DEFAULT 0,
                snapshot_date TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS account_groups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                group_name TEXT NOT NULL,
                username TEXT NOT NULL
            );
        
            CREATE TABLE IF NOT EXISTS campaigns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                targets TEXT NOT NULL,
                completed INTEGER DEFAULT 0,
                total INTEGER DEFAULT 0,
                successes INTEGER DEFAULT 0,
                status TEXT DEFAULT 'running',
                started_at TEXT DEFAULT (datetime('now')),
                finished_at TEXT
            );

            """)
        conn.commit()
    finally:
        conn.close()


def _writer_loop() -> None:
    global _queue
    while True:
        time.sleep(_WRITER_INTERVAL)
        with _queue_lock:
            if not _queue:
                continue
            batch, _queue = _queue[:], []
        conn = _connection()
        try:
            for sql, params in batch:
                conn.execute(sql, params)
            conn.commit()
        except Exception as _e:
            from instareport.utils.logging import dlog
            dlog(f"writer thread SQL error: {_e}")
        finally:
            conn.close()


_writer_thread: threading.Thread | None = None


def _ensure_writer() -> None:
    global _writer_thread
    if _writer_thread is None or not _writer_thread.is_alive():
        _writer_thread = threading.Thread(target=_writer_loop, daemon=True)
        _writer_thread.start()


def _enqueue(sql: str, params: list[Any] = None) -> None:
    _ensure_writer()
    with _queue_lock:
        _queue.append((sql, params or []))


def save_config_sqlite() -> None:
    from instareport.core.state import S
    from instareport.core.config import _encrypt_accounts
    conn = _connection()
    try:
        conn.execute("DELETE FROM accounts")
        for u, pw in S.accounts:
            eu, epw = _encrypt_accounts([(u, pw)])[0]
            conn.execute("INSERT INTO accounts (username, password) VALUES (?, ?)", (eu, epw))
        conn.execute("DELETE FROM cooldowns")
        for user, ts in S.cooldowns.items():
            conn.execute("INSERT INTO cooldowns (username, cooldown_until) VALUES (?, ?)", (user, ts))
        from instareport.core.config import _encrypt_str
        settings: dict[str, Any] = {
            "platform": S.platform, "reason": S.reason,
            "workers": str(S.workers), "headless": str(S.headless),
            "safe_mode": str(S.safe_mode), "stealth": str(S.stealth),
            "rate_limit": str(S.rate_limit), "max_retries": str(S.max_retries),
            "captcha_svc": S.captcha_svc,
            "proxy_file": S.proxy_file, "cooldown_secs": str(S.cooldown_secs),
            "sched_enabled": str(S.sched_enabled), "sched_time": S.sched_time,
            "sched_repeat": str(S.sched_repeat), "sched_interval": str(S.sched_interval),
            "screenshot_cleanup_days": str(S.screenshot_cleanup_days),
            "favorites": json.dumps(list(S.favorites)),
            "presets": json.dumps(S.presets),
            "webhook_url": S.webhook_url,
            "mobile_emulate": str(S.mobile_emulate),
            "warmup_enabled": str(S.warmup_enabled),
            "captcha_key": _encrypt_str(S.captcha_key) if S.captcha_key else "",
        }
        conn.execute("DELETE FROM settings")
        for k, v in settings.items():
            conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (k, str(v)))
        conn.commit()
    finally:
        conn.close()


def load_config_sqlite() -> dict[str, Any]:
    from instareport.core.config import _decrypt_accounts
    conn = _connection()
    try:
        settings: dict[str, Any] = {}
        for row in conn.execute("SELECT key, value FROM settings"):
            settings[row["key"]] = row["value"]
        accounts: list[tuple[str, str]] = []
        raw_accounts = []
        for row in conn.execute("SELECT username, password FROM accounts"):
            raw_accounts.append([row["username"], row["password"]])
        if raw_accounts:
            accounts = _decrypt_accounts(raw_accounts)
        cooldowns: dict[str, float] = {}
        for row in conn.execute("SELECT username, cooldown_until FROM cooldowns"):
            cooldowns[row["username"]] = row["cooldown_until"]
        return {"settings": settings, "accounts": accounts, "cooldowns": cooldowns}
    finally:
        conn.close()


def save_run_log(entry: dict[str, Any]) -> None:
    _enqueue(
        "INSERT INTO run_logs (target, platform, reason, successes, total, elapsed_s, timestamp) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        [entry.get("target", ""), entry.get("platform", ""), entry.get("reason", ""),
         entry.get("successes", 0), entry.get("total", 0), entry.get("elapsed_s", 0),
         entry.get("timestamp", "")]
    )


def get_run_logs(limit: int = 200, offset: int = 0,
                date_from: str = "", date_to: str = "",
                search: str = "") -> list[dict[str, Any]]:
    conn = _connection()
    try:
        where = []
        params: list[Any] = []
        if date_from:
            where.append("timestamp >= ?")
            params.append(date_from)
        if date_to:
            where.append("timestamp <= ?")
            params.append(date_to + "T23:59:59")
        if search:
            where.append("(target LIKE ? OR platform LIKE ? OR reason LIKE ?)")
            s = f"%{search}%"
            params.extend([s, s, s])
        sql = "SELECT target, platform, reason, successes, total, elapsed_s, timestamp FROM run_logs"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY id DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_run_logs_count(date_from: str = "", date_to: str = "",
                       search: str = "") -> int:
    conn = _connection()
    try:
        where = []
        params: list[Any] = []
        if date_from:
            where.append("timestamp >= ?")
            params.append(date_from)
        if date_to:
            where.append("timestamp <= ?")
            params.append(date_to + "T23:59:59")
        if search:
            where.append("(target LIKE ? OR platform LIKE ? OR reason LIKE ?)")
            s = f"%{search}%"
            params.extend([s, s, s])
        sql = "SELECT COUNT(*) FROM run_logs"
        if where:
            sql += " WHERE " + " AND ".join(where)
        row = conn.execute(sql, params).fetchone()
        return row[0] if row else 0
    finally:
        conn.close()


def save_follower_snapshot(username: str, platform: str,
                            followers: int, following: int, posts: int) -> None:
    from datetime import date
    _enqueue(
        "INSERT INTO follower_tracking (username, platform, followers, following, posts, snapshot_date) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        [username, platform, followers, following, posts, date.today().isoformat()]
    )


def get_follower_history(username: str, platform: str,
                         limit: int = 30) -> list[dict]:
    conn = _connection()
    try:
        rows = conn.execute(
            "SELECT followers, following, posts, snapshot_date FROM follower_tracking "
            "WHERE username=? AND platform=? ORDER BY id DESC LIMIT ?",
            (username, platform, limit)
        ).fetchall()
        return [dict(r) for r in reversed(rows)]
    finally:
        conn.close()


def get_account_groups() -> dict[str, list[str]]:
    conn = _connection()
    try:
        groups: dict[str, list[str]] = {}
        for row in conn.execute("SELECT group_name, username FROM account_groups ORDER BY group_name"):
            g = row["group_name"]
            if g not in groups:
                groups[g] = []
            groups[g].append(row["username"])
        return groups
    finally:
        conn.close()


def set_account_group(group_name: str, usernames: list[str]) -> None:
    conn = _connection()
    try:
        conn.execute("DELETE FROM account_groups WHERE group_name=?", (group_name,))
        for u in usernames:
            conn.execute("INSERT INTO account_groups (group_name, username) VALUES (?, ?)", (group_name, u))
        conn.commit()
    finally:
        conn.close()


def delete_account_group(group_name: str) -> None:
    conn = _connection()
    try:
        conn.execute("DELETE FROM account_groups WHERE group_name=?", (group_name,))
        conn.commit()
    finally:
        conn.close()


def set_plugin_dir(path: str) -> None:
    conn = _connection()
    try:
        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('plugin_dir', ?)", (path,))
        conn.commit()
    finally:
        conn.close()


def get_plugin_dir() -> str:
    conn = _connection()
    try:
        row = conn.execute("SELECT value FROM settings WHERE key='plugin_dir'").fetchone()
        return row["value"] if row else ""
    finally:
        conn.close()


def setup_persistence() -> None:
    """First-run setup: init tables, migrate from JSON if needed, enable SQLite backend."""
    from instareport.core.state import S
    from instareport.utils.logging import dlog
    cfg = _constants.CONFIG_FILE
    needs_migrate = cfg and cfg.exists() and not _get_db_path().exists()
    init_db()
    if needs_migrate:
        dlog("[DB] JSON config found — migrating to SQLite…")
        migrate_from_json()
    # Seed default plugin_dir setting
    existing_dir = get_plugin_dir()
    if not existing_dir:
        default_dir = str(Path(_get_db_path().parent) / "plugins")
        set_plugin_dir(default_dir)
    S.use_sqlite = True
    from instareport.core.config import load_config
    load_config()
    dlog("[DB] SQLite persistence enabled")


def migrate_from_json() -> None:
    cfg = _constants.CONFIG_FILE
    if cfg and cfg.exists():
        try:
            with open(cfg, encoding="utf-8") as f:
                data = json.load(f)
            conn = _connection()
            try:
                if isinstance(data.get("cooldowns"), dict):
                    conn.execute("DELETE FROM cooldowns")
                    for user, ts in data["cooldowns"].items():
                        conn.execute("INSERT INTO cooldowns (username, cooldown_until) VALUES (?, ?)",
                                     (user, ts))
                accounts_raw = data.get("accounts", [])
                if accounts_raw:
                    conn.execute("DELETE FROM accounts")
                    for a in accounts_raw:
                        if isinstance(a, (list, tuple)) and len(a) >= 2:
                            conn.execute("INSERT INTO accounts (username, password) VALUES (?, ?)",
                                         (str(a[0]), str(a[1])))
                        elif isinstance(a, dict):
                            conn.execute("INSERT INTO accounts (username, password) VALUES (?, ?)",
                                         (str(a.get("user", "")), str(a.get("pw", ""))))
                settings_map: dict[str, Any] = {}
                for k in ("platform", "reason", "workers", "headless", "safe_mode",
                          "stealth", "rate_limit", "max_retries", "captcha_svc",
                          "proxy_file", "cooldown_secs", "sched_enabled", "sched_time",
                          "sched_repeat", "sched_interval", "screenshot_cleanup_days",
                          "webhook_url", "mobile_emulate", "warmup_enabled", "captcha_key"):
                    if k in data:
                        settings_map[k] = str(data[k])
                if "favorites" in data:
                    settings_map["favorites"] = json.dumps(data["favorites"])
                if "presets" in data:
                    settings_map["presets"] = json.dumps(data["presets"])
                conn.execute("DELETE FROM settings")
                for k, v in settings_map.items():
                    conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (k, str(v)))
                conn.commit()
            finally:
                conn.close()
            bak = Path(str(cfg) + ".migrated")
            cfg.rename(bak)
        except Exception:
            pass



def save_campaign(targets: list[str], completed: int = 0, successes: int = 0,
                  status: str = "running") -> int:
    init_db()
    conn = _conn()
    try:
        cur = conn.execute(
            "INSERT INTO campaigns (targets, completed, total, successes, status) VALUES (?, ?, ?, ?, ?)",
            (json.dumps(targets), completed, len(targets), successes, status),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()

def update_campaign(campaign_id: int, completed: int, successes: int, status: str = "running") -> None:
    init_db()
    conn = _conn()
    try:
        conn.execute(
            "UPDATE campaigns SET completed=?, successes=?, status=? WHERE id=?",
            (completed, successes, status, campaign_id),
        )
        conn.commit()
    finally:
        conn.close()

def get_last_campaign() -> dict | None:
    init_db()
    conn = _conn()
    try:
        row = conn.execute(
            "SELECT * FROM campaigns WHERE status='running' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()

def get_campaign_history(limit: int = 10) -> list[dict]:
    init_db()
    conn = _conn()
    try:
        rows = conn.execute(
            "SELECT * FROM campaigns ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
