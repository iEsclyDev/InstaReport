"""Application state — AppState dataclass and global singleton."""
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from instareport.utils.constants import SCREENSHOTS_DIR

LogCb = Callable[[str, str], None]
OtpCb = Callable[[str, str, str], None]
CaptchaCb = Callable[[str, str, str], None]


@dataclass
class AccountInfo:
    username: str
    password: str
    cooldown_until: float = 0.0
    session_count: int = 0
    total_reports: int = 0
    risk_level: str = "LOW"

    def as_tuple(self) -> tuple[str, str]:
        return (self.username, self.password)


class AppState:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._accounts: list[tuple[str, str]] = []
        self.proxies: list[str] = []
        self.proxy_idx: int = 0
        self._target: str = ""
        self._workers: int = 2
        self.platform: str = "instagram"
        self.reason: str = "spam"
        self.headless: bool = False
        self.safe_mode: bool = False
        self.rate_limit: int = 0
        self.stealth: bool = False
        self.captcha_svc: str = "manual"
        self.captcha_key: str = ""
        self.max_retries: int = 3
        self.stop_event: threading.Event = threading.Event()
        self.log_cb: LogCb | None = None
        self.otp_cb: OtpCb | None = None
        self.captcha_cb: CaptchaCb | None = None
        self.run_logs: list[dict] = []
        self.cooldowns: dict[str, float] = {}
        self.cooldown_secs: int = 300
        self.screenshot_dir: Path | None = SCREENSHOTS_DIR
        self.sched_enabled: bool = False
        self.sched_time: str = "03:00"
        self.sched_repeat: bool = False
        self.sched_interval: int = 360
        self.proxy_file: str = "proxies.txt"
        self.screenshot_cleanup_days: int = 7
        self.operation: str = "report"
        self.custom_headers: dict[str, str] = {}
        self.ignore_https_errors: bool = False
        self.pause_event: threading.Event = threading.Event()
        self.paused: bool = False
        self.failed_accounts: list[str] = []
        self.favorites: set[str] = set()
        self.presets: dict = {}
        self.multi_targets: list[str] = []
        self.hibp_key: str = ""
        self.custom_description: str = ""
        self.webhook_url: str = ""
        self.mobile_emulate: bool = False
        self.warmup_enabled: bool = True
        self.use_sqlite: bool = False
        self.sched_lang: str = "en"
        self.failed_tasks: list = []
        self.retry_queue: list = []
        self.chrome_user_data_dir: str = ""
        self.api_mode: str = "browser"
        self.health_map: dict[str, bool] = {}

    @property
    def target(self) -> str:
        with self._lock:
            return self._target

    @target.setter
    def target(self, val: str) -> None:
        with self._lock:
            self._target = val

    @property
    def workers(self) -> int:
        with self._lock:
            return self._workers

    @workers.setter
    def workers(self, val: int) -> None:
        with self._lock:
            self._workers = val

    @property
    def accounts(self) -> list[tuple[str, str]]:
        with self._lock:
            return self._accounts

    @accounts.setter
    def accounts(self, val: list[tuple[str, str]]) -> None:
        with self._lock:
            self._accounts = val


S: AppState = AppState()

ACCOUNTS_LOCK: threading.Lock = threading.Lock()
RUN_LOGS_LOCK: threading.Lock = threading.Lock()
FAILED_LOCK: threading.Lock = threading.Lock()
STATE_LOCK: threading.Lock = threading.Lock()
COOLDOWN_LOCK: threading.Lock = threading.Lock()
CONFIG_LOCK: threading.Lock = threading.Lock()

GLOBAL_STOP: threading.Event = threading.Event()
