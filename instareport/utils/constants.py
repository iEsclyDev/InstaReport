"""All constants, module definitions, and configuration defaults."""
import os, sys, hashlib, platform, uuid, random, re, time, subprocess
import argparse
from typing import Final
from pathlib import Path

_parser = argparse.ArgumentParser(add_help=False)
_parser.add_argument("--debug", action="store_true")
_parser.add_argument("--headless", action="store_true")
_parser.add_argument("--no-dep-check", action="store_true")
_parser.add_argument("--cli", action="store_true")
_args, _ = _parser.parse_known_args()
DEBUG: bool = _args.debug
HEADLESS: bool = _args.headless
_NO_DEP_CHECK: bool = _args.no_dep_check
CLI_MODE: bool = _args.cli

VERSION: Final[str] = "8.7.0"

MAX_LOG_ENTRIES: Final[int] = 1200
MAX_USERNAME_LEN: Final[int] = 100
OTP_TIMEOUT_SECS: Final[int] = 120
PBKDF2_ITERATIONS: Final[int] = 480_000
IMG_CACHE_MAX: Final[int] = 32
PROXY_BLACKLIST_THRESHOLD: Final[int] = 3
CONSOLE_TRIM_LINES: Final[int] = 2000
MAX_BATCH_WORKERS: Final[int] = 4

T_PAGE_LOAD: Final[float] = 3.0
T_POST_LOGIN: Final[float] = 4.0
T_POST_CLICK: Final[float] = 2.0
T_CAPTCHA_WAIT: Final[float] = 25.0
T_TELEGRAM_OTP: Final[float] = 4.0
T_REFRESH_WAIT: Final[float] = 3.0
T_FORM_SUBMIT: Final[float] = 3.0
T_CAPTCHA_POLL: Final[float] = 5.0
T_URL_POLL: Final[float] = 2.0
T_COOKIE_SETTLE: Final[float] = 2.0
T_TYPE_DELAY: Final[float] = 1.0

API_BASE: Final[str] = "https://iescly.duckdns.org"
GITHUB_REPO: Final[str] = "iescly/instareport-bot"
SESSIONS_DIR: Path | None = None
SCREENSHOTS_DIR: Path | None = None
CONFIG_FILE: Path | None = None

# Initialize dirs at import time so all consumers get Path instead of None
SESSIONS_DIR = Path("sessions")
SCREENSHOTS_DIR = Path("screenshots")
CONFIG_FILE = Path("instareport_config.json")
try:
    Path("sessions").mkdir(exist_ok=True)
    Path("screenshots").mkdir(exist_ok=True)
except OSError:
    pass

def _get_data_dir() -> Path:
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "instareport"
    return Path.home() / ".local" / "share" / "instareport"


def init_paths() -> None:
    global SESSIONS_DIR, SCREENSHOTS_DIR, CONFIG_FILE
    _data = Path(os.environ.get("INSTAREPORT_DATA", _get_data_dir()))
    SESSIONS_DIR = _data / "sessions"
    SCREENSHOTS_DIR = _data / "screenshots"
    CONFIG_FILE = _data / "instareport_config.json"
    _data.mkdir(parents=True, exist_ok=True)
    SESSIONS_DIR.mkdir(exist_ok=True)
    SCREENSHOTS_DIR.mkdir(exist_ok=True)

PlatformName = str
PlatformKey = str
ReasonLabel = str
ReasonKey = str

PLATFORMS: list[tuple[str, str]] = [
    ("Instagram", "instagram"), ("YouTube", "youtube"), ("Twitter / X", "twitter"),
    ("Telegram", "telegram"), ("Discord", "discord"), ("Reddit", "reddit"),
    ("TikTok", "tiktok"), ("Facebook", "facebook"), ("Snapchat", "snapchat"),
    ("Threads", "threads"), ("Gmail", "gmail"),
]

REPORT_REASONS: list[tuple[str, str]] = [
    ("Spam", "spam"), ("Harassment", "harassment"), ("Impersonation", "impersonation"),
    ("Hate speech", "hate"), ("Nudity", "nudity"), ("Violence", "violence"),
    ("Misinformation", "misinformation"), ("Scam / Fraud", "scam"),
]

_REASON_TEXT_MAP: dict[str, str] = {
    "spam": "It's spam",
    "harassment": "Bullying or harassment",
    "impersonation": "Pretending to be someone",
    "hate": "Hate speech or symbols",
    "nudity": "Nudity or sexual activity",
    "violence": "Violence or dangerous organizations",
    "misinformation": "False information",
    "scam": "Scam or fraud",
}

REASON_LOCALIZATIONS: dict[str, dict[str, str]] = {
    "en": {k: v for k, v in _REASON_TEXT_MAP.items()},
    "es": {
        "spam": "Es spam", "harassment": "Acoso o intimidacion",
        "impersonation": "Suplantacion de identidad", "hate": "Discurso de odio",
        "nudity": "Desnudez o actividad sexual", "violence": "Violencia",
        "misinformation": "Informacion falsa", "scam": "Estafa o fraude",
    },
    "fr": {
        "spam": "C'est un spam", "harassment": "Harcelement",
        "impersonation": "Usurpation d'identite", "hate": "Discours haineux",
        "nudity": "Nudite ou activite sexuelle", "violence": "Violence",
        "misinformation": "Fausse information", "scam": "Arnaque",
    },
    "de": {
        "spam": "Spam", "harassment": "Belastigung",
        "impersonation": "Identitatsdiebstahl", "hate": "Hassrede",
        "nudity": "Nacktheit", "violence": "Gewalt",
        "misinformation": "Falschinformation", "scam": "Betrug",
    },
    "pt": {
        "spam": "E spam", "harassment": "Assedio",
        "impersonation": "Falsificacao de identidade", "hate": "Discurso de odio",
        "nudity": "Nudez", "violence": "Violencia",
        "misinformation": "Informacao falsa", "scam": "Golpe",
    },
    "ar": {
        "spam": "بريد عشوائي", "harassment": "تحرش",
        "impersonation": "انتحال شخصية", "hate": "خطاب كراهية",
        "nudity": "عري", "violence": "عنف",
        "misinformation": "معلومات مضللة", "scam": "احتيال",
    },
}

REASON_LANGUAGES: list[tuple[str, str]] = [
    ("English", "en"), ("Spanish", "es"), ("French", "fr"),
    ("German", "de"), ("Portuguese", "pt"), ("Arabic", "ar"),
]

REASON_XPATHS: dict[str, list[str]] = {
    "spam": ["//div[contains(text(),'Spam') or contains(text(),'spam')]",
             "//span[contains(text(),'Spam')]", "//label[contains(.,'Spam')]"],
    "harassment": ["//div[contains(text(),'Harassment')]", "//span[contains(text(),'Harassment')]"],
    "impersonation": ["//div[contains(text(),'mpersonation')]", "//span[contains(text(),'Pretending')]"],
    "hate": ["//div[contains(text(),'Hate')]", "//span[contains(text(),'Hate')]"],
    "nudity": ["//div[contains(text(),'Nudity')]", "//span[contains(text(),'Nudity')]"],
    "violence": ["//div[contains(text(),'Violence')]", "//span[contains(text(),'Violence')]"],
    "misinformation": ["//div[contains(text(),'False')]", "//span[contains(text(),'False')]"],
    "scam": ["//div[contains(text(),'Scam')]", "//span[contains(text(),'Scam')]"],
}

ModuleDef = tuple[str, str, str, str, str]
CategoryDict = dict[str, list[ModuleDef]]

MODULES: CategoryDict = {
    "Auto-Ban Engine": [
        ("Burst Mode", "ACTIVE", "⚡", "Fire reports from all accounts simultaneously", "burst_mode"),
        ("Emergency Stop", "ACTIVE", "⏹", "Immediately kill all active browser sessions", "emergency_stop"),
        ("Shadow Ban Trigger", "ACTIVE", "◉", "Check if target account is shadow-banned", "shadow_check"),
        ("Account Health", "ACTIVE", "🩺", "View per-account health status and ban risk", "account_health"),
        ("Timed Strikes", "ACTIVE", "⏱", "Schedule reports at custom time intervals", "timed_strikes"),
        ("Distributed Attack", "PRO", "⚙", "Spread reports across multiple IPs/proxies", "distributed"),
        ("Thread Manager", "ACTIVE", "⇄", "Control parallel worker thread count live", "thread_manager"),
        ("Export History CSV", "ACTIVE", "📊", "Export all run history to CSV file", "history_csv"),
        ("Export HTML Report", "ACTIVE", "📊", "Export run history as formatted HTML report", "export_html"),
        ("Auto-Update", "ACTIVE", "⏱", "Check GitHub for new version and download", "auto_update"),
        ("Payload Builder", "ACTIVE", "⬡", "Build custom report reason payloads", "payload_builder"),
        ("Force Report", "ACTIVE", "⚡", "Bypass normal UI flow via direct API call", "force_report"),
        ("Queue Cleaner", "READY", "⬕", "Clear pending report queue and reset counters", "queue_cleaner"),
        ("Smart Categorize", "ACTIVE", "✦", "Auto-pick best report reason per platform", "smart_categorize"),
        ("VIP Bypass", "PRO", "◈", "Use premium session tokens to bypass rate limits", "vip_bypass"),
        ("Turbo Queue", "ACTIVE", "⟳", "Enable high-speed multi-account queue mode", "turbo_queue"),
        ("Batch Processor", "ACTIVE", "⊞", "Run reports for multiple targets at once", "batch_processor"),
        ("API Hookpoint", "READY", "⚓", "Connect to external automation APIs", "api_hook"),
        ("Report Templates", "ACTIVE", "⬕", "Save and load report configurations", "report_templates"),
        ("Account Groups", "ACTIVE", "⊞", "Organize accounts into named groups", "account_groups"),
    ],
    "Unban Tools": [
        ("Appeal Engine", "ACTIVE", "⚖", "Submit account appeal to platform support", "appeal"),
        ("Identity Swap", "PRO", "⬡", "Change account display info to avoid flags", "identity_swap"),
        ("Cache Purge", "ACTIVE", "⟳", "Clear all saved cookies and session files", "cache_purge"),
        ("Flag Override", "ACTIVE", "⚑", "Attempt to remove content flag via appeal", "flag_override"),
        ("Account Restore", "READY", "◈", "Re-activate a suspended account via appeal", "acc_restore"),
        ("Ban Detector", "ACTIVE", "◉", "Check if an account is currently banned", "ban_detector"),
        ("Warmup Cycle", "ACTIVE", "⬟", "Simulate normal activity before reporting", "warmup"),
        ("Safe Mode", "ACTIVE", "⬡", "Add delays and human-like pauses between actions", "safe_mode"),
        ("Proxy Rotator", "PRO", "⇄", "Reload and re-shuffle the proxy pool", "proxy_rotate"),
        ("Session Rebuilder", "ACTIVE", "⚙", "Delete cookies and force fresh login for account", "session_rebuild"),
        ("CAPTCHA Solver", "ACTIVE", "⊞", "Configure and test 2captcha / CapMonster API key", "captcha_config"),
        ("2FA Bypass", "PRO", "⬛", "Enter 2FA codes manually for pending sessions", "twofa_bypass"),
    ],
    "Lookups": [
        ("Profile Scanner", "ACTIVE", "◉", "Fetch public profile info for a username", "profile_scan"),
        ("Shadow Check", "ACTIVE", "⬟", "Check if account is shadow-banned on Instagram", "shadow_check_lookup"),
        ("Engagement Audit", "READY", "⊡", "Show follower/following/post counts via scraping", "engagement"),
        ("Follower Tracker", "ACTIVE", "⇑", "Track follower count changes over time", "follower_track"),
        ("Report History", "ACTIVE", "⬕", "View past run logs from this session", "report_history"),
        ("IP Resolver", "PRO", "⬡", "Resolve IP and geo info for a domain/username", "ip_resolve"),
        ("Device Fingerprint", "ACTIVE", "⊞", "Show current browser fingerprint details", "fingerprint"),
        ("Account Age", "ACTIVE", "⏱", "Estimate account creation date from post history", "acc_age"),
        ("Link Tracer", "READY", "⟳", "Follow redirect chain for a URL", "link_trace"),
        ("Hash Lookup", "ACTIVE", "◈", "Look up a username/email in breach databases", "hash_lookup"),
        ("Screenshot Gallery", "ACTIVE", "⬕", "Browse and delete session screenshots", "screenshot_gallery"),
    ],
    "Advanced": [
        ("Stealth Mode", "PRO", "◉", "Enable full anti-detection: delays, fingerprint spoof", "stealth"),
        ("Dark Pattern", "PRO", "⬛", "Use aggressive report escalation sequences", "dark_pattern"),
        ("Network Spoof", "ACTIVE", "⬡", "Randomize browser timezone, language, canvas hash", "net_spoof"),
        ("Behavior Mimic", "ACTIVE", "✦", "Add random mouse movement and typing delays", "behavior"),
        ("Rate Limiter", "READY", "⏱", "Set max reports per minute to avoid throttle", "rate_limit"),
        ("Header Forge", "PRO", "⬟", "Override HTTP request headers in browser", "header_forge"),
        ("Cookie Injector", "ACTIVE", "⊞", "Manually paste and inject cookie JSON for an account", "cookie_inject"),
        ("Canvas Spoof", "ACTIVE", "◈", "Randomize canvas fingerprint hash per session", "canvas_spoof"),
        ("WebRTC Block", "ACTIVE", "⚑", "Disable WebRTC to prevent IP leak through proxy", "webrtc_block"),
        ("TLS Fingerprint", "PRO", "⬡", "Rotate TLS client hello fingerprint (via uc)", "tls_fp"),
        ("Telegram Bot", "ACTIVE", "⊞", "Control reports remotely via Telegram", "telegram_bot"),
    ],
}

TOTAL_MODULES: int = sum(len(v) for v in MODULES.values())

TabDef = tuple[str, int]
TABS: list[TabDef] = [
    ("⭐ Favorites", 0),
    ("Auto-Ban Engine", len(MODULES.get("Auto-Ban Engine", []))),
    ("Unban Tools", len(MODULES.get("Unban Tools", []))),
    ("Plugins", 0),
    ("Lookups", len(MODULES.get("Lookups", []))),
    ("Advanced", len(MODULES.get("Advanced", []))),
    ("Run History", 0),
]

MobileDevice = dict[str, str | int | bool | dict[str, int]]
MOBILE_DEVICES: list[MobileDevice] = [
    {"name": "iPhone 14 Pro",
     "user_agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
     "viewport": {"width": 393, "height": 852}, "device_scale_factor": 3, "is_mobile": True, "has_touch": True},
    {"name": "Samsung Galaxy S23",
     "user_agent": "Mozilla/5.0 (Linux; Android 14; SM-S911B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Mobile Safari/537.36",
     "viewport": {"width": 360, "height": 780}, "device_scale_factor": 3, "is_mobile": True, "has_touch": True},
    {"name": "Pixel 8",
     "user_agent": "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Mobile Safari/537.36",
     "viewport": {"width": 412, "height": 915}, "device_scale_factor": 2.625, "is_mobile": True, "has_touch": True},
    {"name": "iPad Air",
     "user_agent": "Mozilla/5.0 (iPad; CPU OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
     "viewport": {"width": 820, "height": 1180}, "device_scale_factor": 2, "is_mobile": True, "has_touch": True},
]

PLAT_ICONS: dict[str, str] = {
    "instagram": "IG", "youtube": "YT", "twitter": "X", "telegram": "TG",
    "discord": "DC", "reddit": "RD", "tiktok": "TT", "facebook": "FB",
    "snapchat": "SC", "threads": "TH", "gmail": "GM",
}

STATUS_COL: dict[str, str] = {"PRO": "#F43F7A", "ACTIVE": "#00E5A0", "READY": "#F59E0B"}

_TARGET_RE: re.Pattern = re.compile(r'^[a-zA-Z0-9._]{1,100}$')

_VALID_HTTP_METHODS: frozenset[str] = frozenset({'get', 'post', 'put', 'patch', 'delete', 'head', 'options'})

TagPattern = tuple[re.Pattern, str]
TAG_PATTERNS: list[TagPattern] = [
    (re.compile(r'✓|\[OK\]|\[READY\]'), "ok"),
    (re.compile(r'✗|\[!\]|ERR|fail', re.IGNORECASE), "err"),
    (re.compile(r'PROXY|\[NET\]|SCAN'), "proxy"),
    (re.compile(r'SYS|RETRY|SCHED|\[ENGINE\]|\[TASK\]'), "sys"),
    (re.compile(r'2FA|CAP|WARN|SHOT'), "warn"),
]
