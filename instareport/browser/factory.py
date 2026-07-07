"""Async Playwright browser factory with stealth and mobile emulation."""
import asyncio, random, threading, atexit, os, signal as _signal, subprocess
from typing import Any

from instareport.utils.constants import MOBILE_DEVICES, SESSIONS_DIR, HEADLESS, DEBUG
from instareport.utils.logging import dlog
from instareport.core.state import S

try:
    from playwright.async_api import async_playwright, Playwright, Browser, BrowserContext, Page
    _PW_AVAILABLE = True
except ImportError:
    _PW_AVAILABLE = False
    Playwright = Any
    Browser = Any
    BrowserContext = Any
    Page = Any

try:
    from playwright_stealth import stealth_async
    _STEALTH_AVAILABLE = True
except ImportError:
    _STEALTH_AVAILABLE = False

_shared_pw: Playwright | None = None
_shared_browser: Browser | None = None
_shared_lock = asyncio.Lock()


def _cleanup_orphan_browsers():
    """Kill any orphaned Chrome/Chromium processes left by a crash."""
    import sys
    if sys.platform == "win32":
        try:
            subprocess.run(
                ["taskkill", "/f", "/im", "chrome.exe"],
                capture_output=True, timeout=5)
        except Exception:
            pass
        try:
            subprocess.run(
                ["taskkill", "/f", "/im", "chromium.exe"],
                capture_output=True, timeout=5)
        except Exception:
            pass
    elif sys.platform == "linux":
        try:
            subprocess.run(
                ["pkill", "-f", "chromium"],
                capture_output=True, timeout=5)
        except Exception:
            pass
        try:
            subprocess.run(
                ["pkill", "-f", "chrome"],
                capture_output=True, timeout=5)
        except Exception:
            pass


atexit.register(_cleanup_orphan_browsers)

_BASE_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--no-sandbox",
    "--disable-setuid-sandbox",
    "--disable-infobars",
    "--disable-dev-shm-usage",
    "--disable-gpu",
    "--disable-component-update",
    "--disable-background-networking",
    "--disable-sync",
    "--disable-default-apps",
    "--no-first-run",
    "--disable-features=TranslateUI,ChromeWhatsNewUI,ChromeLabs,ChromeWhatsNewUI2,PrivacySandboxSettings4,ChromeSignin",
    "--disable-background-timer-throttling",
    "--disable-backgrounding-occluded-windows",
    "--disable-renderer-backgrounding",
]

_ANTI_DETECTION_SCRIPT = """
// Patch webdriver
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });

// Patch plugins to look like a real browser
Object.defineProperty(navigator, 'plugins', {
  get: () => [1, 2, 3, 4, 5],
});

// Languages
Object.defineProperty(navigator, 'languages', {
  get: () => ['en-US', 'en'],
});

// Chrome runtime
window.chrome = {
  runtime: {},
  loadTimes: function() {},
  csi: function() {},
  app: { isInstalled: false, InstallState: { DISABLED: 'disabled', INSTALLED: 'installed', NOT_INSTALLED: 'not_installed' }, RunningState: { CANNOT_RUN: 'cannot_run', READY_TO_RUN: 'ready_to_run', RUNNING: 'running' } },
};

// Hardware
Object.defineProperty(navigator, 'deviceMemory', { get: () => 8 });
Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });

// Connection (real Chrome exposes this)
if (navigator.connection === undefined) {
  Object.defineProperty(navigator, 'connection', {
    get: () => ({
      effectiveType: '4g',
      rtt: 50,
      downlink: 10,
      saveData: false,
    }),
  });
}

// Permissions
const originalQuery = window.navigator.permissions.query;
window.navigator.permissions.query = (params) => (
  params.name === 'window-placement' || params.name === 'local-fonts'
    ? Promise.resolve({ state: 'prompt', onchange: null })
    : originalQuery(params)
);

// PDF viewer
Object.defineProperty(navigator, 'pdfViewerEnabled', { get: () => false });

// WebGL vendor/renderer
const getParameterProxyHandler = {
  apply: function(target, thisArg, args) {
    const param = args[0];
    if (param === 37445) return 'Google Inc.';
    if (param === 37446) return 'ANGLE (Intel, Intel(R) UHD Graphics (0x00009BC4) Direct3D11 vs_5_0 ps_5_0)';
    if (param === 7936) return 'WebGL 1.0 (OpenGL ES 2.0 Chromium)';
    if (param === 7937) return 'WebGL GLSL ES 1.0 (Chromium)';
    return Reflect.apply(target, thisArg, args);
  },
};
try {
  const canvas = document.createElement('canvas');
  const gl = canvas.getContext('webgl') || canvas.getContext('experimental-webgl');
  if (gl) {
    const originalGetParameter = gl.getParameter.bind(gl);
    gl.getParameter = new Proxy(originalGetParameter, getParameterProxyHandler);
  }
} catch(e) {}

// Ensure outer dimensions match viewport
Object.defineProperty(window, 'outerWidth', { get: () => window.innerWidth });
Object.defineProperty(window, 'outerHeight', { get: () => window.innerHeight });
Object.defineProperty(window, 'screenTop', { get: () => 0 });
Object.defineProperty(window, 'screenLeft', { get: () => 0 });
"""


async def _cleanup_resources(pw=None, browser=None, context=None):
    try:
        if context:
            await context.close()
    except Exception:
        pass
    try:
        if browser:
            await browser.close()
    except Exception:
        pass
    try:
        if pw:
            await pw.stop()
    except Exception:
        pass


async def get_shared_browser() -> Browser:
    global _shared_pw, _shared_browser
    async with _shared_lock:
        if _shared_browser is None or not _shared_browser.is_connected():
            await _cleanup_resources(_shared_pw, _shared_browser)
            _shared_pw = await async_playwright().start()
            launch_args: dict[str, Any] = {
                "headless": HEADLESS,
                "args": _BASE_ARGS.copy(),
            }
            if S.stealth:
                launch_args["args"] = launch_args["args"] + [f"--lang={random.choice(['en-US','en-GB','fr-FR','de-DE'])}"]
            if os.name != "nt" and hasattr(_signal, "SIGKILL"):
                launch_args.setdefault("env", os.environ.copy())
            try:
                _shared_browser = await _shared_pw.chromium.launch(channel="chrome", **launch_args)
            except Exception:
                _shared_browser = await _shared_pw.chromium.launch(**launch_args)
        return _shared_browser


async def close_shared_browser():
    global _shared_pw, _shared_browser
    async with _shared_lock:
        await _cleanup_resources(_shared_pw, _shared_browser)
        _shared_pw = None
        _shared_browser = None


async def _create_isolated_context(browser: Browser, platform: str | None = None,
                                    force_desktop: bool = False) -> tuple[BrowserContext, Page]:
    ctx_kwargs: dict[str, Any] = {
        "locale": "en-US",
        "timezone_id": random.choice(["America/New_York", "America/Chicago", "America/Los_Angeles",
                                       "Europe/London", "Europe/Paris"]) if S.stealth else "America/New_York",
        "java_script_enabled": True,
        "ignore_https_errors": getattr(S, 'ignore_https_errors', False),
        "color_scheme": "light",
        "reduced_motion": "no-preference",
        "forced_colors": "none",
    }

    if platform == "instagram":
        ctx_kwargs["service_workers"] = "block"

    if S.stealth and not force_desktop and (S.mobile_emulate or platform == "instagram"):
        device = random.choice(MOBILE_DEVICES)
        dlog(f"Mobile emulation: {device['name']}")
        ctx_kwargs["viewport"] = device["viewport"]
        ctx_kwargs["user_agent"] = device["user_agent"]
        ctx_kwargs["device_scale_factor"] = device["device_scale_factor"]
        ctx_kwargs["is_mobile"] = device["is_mobile"]
        ctx_kwargs["has_touch"] = device["has_touch"]
    else:
        w = random.choice([1440, 1536, 1600, 1680, 1920])
        h = random.choice([800, 864, 900, 960, 1080])
        ctx_kwargs["viewport"] = {"width": w, "height": h}
        ctx_kwargs["user_agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"

    context = await browser.new_context(**ctx_kwargs)
    await context.add_init_script(_ANTI_DETECTION_SCRIPT)
    page = await context.new_page()

    if _STEALTH_AVAILABLE:
        await stealth_async(page)

    if S.custom_headers and platform != "instagram":
        try:
            await page.set_extra_http_headers(S.custom_headers)
        except Exception as _e:
            dlog(f"custom headers: {_e}")
    elif S.custom_headers and platform == "instagram":
        dlog("Skipping custom headers for Instagram hardened login")

    return context, page


class BrowserSession:
    def __init__(self, headless: bool = False, proxy_str: str | None = None,
                 platform: str | None = None) -> None:
        self._headless = headless
        self._proxy = proxy_str
        self._platform = platform
        self._owned_pw: Playwright | None = None
        self._owned_browser: Browser | None = None
        self.context: BrowserContext | None = None
        self.page: Page | None = None

    async def __aenter__(self) -> "BrowserSession":
        if self._proxy or threading.current_thread() != threading.main_thread():
            self._owned_pw = await async_playwright().start()
            launch_args: dict[str, Any] = {
                "headless": self._headless,
                "args": _BASE_ARGS.copy(),
            }
            if S.stealth:
                launch_args["args"] = launch_args["args"] + [f"--lang={random.choice(['en-US','en-GB','fr-FR','de-DE'])}"]
            if self._proxy:
                parts = self._proxy.split(":")
                if len(parts) == 4:
                    launch_args["proxy"] = {
                        "server": f"http://{parts[0]}:{parts[1]}",
                        "username": parts[2],
                        "password": parts[3],
                    }
                elif len(parts) >= 2:
                    launch_args["proxy"] = {"server": f"http://{parts[0]}:{parts[1]}"}
            try:
                self._owned_browser = await self._owned_pw.chromium.launch(channel="chrome", **launch_args)
            except Exception:
                self._owned_browser = await self._owned_pw.chromium.launch(**launch_args)
            browser = self._owned_browser
        else:
            self._owned_pw = None
            self._owned_browser = None
            browser = await get_shared_browser()

        _use_mobile = self._platform == "instagram" and S.stealth
        self.context, self.page = await _create_isolated_context(
            browser, platform=self._platform, force_desktop=not _use_mobile)
        return self

    async def __aexit__(self, exc_type: type | None, exc_val: BaseException | None,
                        exc_tb: object) -> bool:
        try:
            if self.context:
                await self.context.close()
        except Exception:
            pass
        if self._owned_pw:
            try:
                if self._owned_browser:
                    await self._owned_browser.close()
                await self._owned_pw.stop()
            except Exception:
                pass
        return False
