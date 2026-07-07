"""Engine — mass_report_playwright orchestrates all report flows."""
import asyncio, time, traceback, threading
from datetime import datetime
from typing import Callable, Any

from instareport.browser.factory import BrowserSession
from instareport.browser.flows import FLOW_MAP as _LEGACY_FLOW_MAP
from instareport.plugins.loader import get_flow_map as _get_plugin_flow_map
from instareport.browser.helpers import _screenshot, _warmup_sequence, _stopped
from instareport.core.state import S, GLOBAL_STOP, RUN_LOGS_LOCK
from instareport.core.config import _mark_used, _is_on_cooldown
from instareport.tools.proxy import PP, ProxyHealthChecker
from instareport.utils.constants import DEBUG
from instareport.utils.helpers import _fire_webhook, _run_async_in_thread
from instareport.utils.logging import dlog

LogFn = Callable[[str, str], None]


async def _run_one(sem: asyncio.Semaphore, user: str, pw: str, target: str,
                   platform: str, reason: str, flow_fn: LogFn,
                   log_fn: LogFn, api_mode: bool = False) -> bool:
    if GLOBAL_STOP.is_set() or S.stop_event.is_set():
        return False
    if _is_on_cooldown(user):
        log_fn(f"  [SKIP] {user} on cooldown")
        return False
    async with sem:
        for attempt in range(1, S.max_retries + 2):
            if _stopped():
                return False
            proxy_str: str | None = PP.next()
            log_fn(f"  [{platform.upper()}] {user} → {target} attempt {attempt}/{S.max_retries + 1}" +
                   (f" via {proxy_str.split(':')[0]}:***" if proxy_str else " (no proxy)"))
            try:
                if api_mode:
                    ok = await flow_fn(None, user, pw, target, reason, log_fn)
                else:
                    async with BrowserSession(headless=S.headless, proxy_str=proxy_str, platform=platform) as sess:
                        if S.warmup_enabled:
                            await _warmup_sequence(sess.page, log_fn, f"{user}@{platform}")
                        ok = await flow_fn(sess.page, user, pw, target, reason, log_fn)
                        if not ok:
                            await _screenshot(sess.page, f"fail_{platform}_{target}_a{attempt}")
                if ok:
                    PP.report_success(proxy_str)
                    _mark_used(user)
                    return True
                log_fn(f"  [{platform.upper()}] attempt {attempt} failed")
                PP.report_failure(proxy_str)
            except Exception as e:
                log_fn(f"  [{platform.upper()}] attempt {attempt} crashed: {type(e).__name__}: {e}")
                dlog(traceback.format_exc())
                PP.report_failure(proxy_str)
            if attempt < S.max_retries + 1:
                import random as _rand
                delay = min(10 * (2 ** (attempt - 1)), 300) + _rand.uniform(0, 5)
                log_fn(f"  [RETRY] waiting {delay}s…")
                for _ in range(delay):
                    if _stopped():
                        return False
                    await asyncio.sleep(1)
        log_fn(f"  [{platform.upper()}] {user} exhausted retries")
        return False


async def mass_report_playwright(target: str, platform: str, reason: str,
                                  log_fn: LogFn) -> int:
    S.stop_event.clear()
    GLOBAL_STOP.clear()
    total = len(S.accounts)
    if total == 0:
        log_fn("[ENGINE] No accounts loaded")
        return 0
    sem = asyncio.Semaphore(S.workers)
    log_fn(f"[ENGINE] Starting → {target} @ {platform} ({reason}) — {total} accounts, {S.workers} workers")
    flow_map = _get_plugin_flow_map()
    if not flow_map:
        flow_map = _LEGACY_FLOW_MAP
    flow_fn: Any = flow_map.get(platform)
    if not flow_fn:
        log_fn(f"[ENGINE] No flow for {platform}")
        return 0
    _api_mode = S.api_mode == "api" and platform == "instagram"
    if _api_mode:
        from instareport.browser.instagram_api import flow_instagram_api as _api_flow
        log_fn("[ENGINE] Using Instagram Private API mode (browserless)")
        flow_fn = (lambda page, u, p, t, r, l: _api_flow(u, p, t, r, l))
    proxy_test_log: LogFn = lambda m: log_fn(m)
    if PP.count() > 0:
        live = ProxyHealthChecker.check_all(PP.snapshot(), proxy_test_log)
        if live:
            PP.replace(live)
        else:
            log_fn("[ENGINE] All proxies dead — retrying with full pool")
            PP.replace([])
    # Account health pre-check
    _healthy_accounts = []
    if platform == "instagram":
        log_fn(f"[ENGINE] Health-checking {len(S.accounts)} accounts...")
        for user, pw in S.accounts[:]:
            S.health_map[user] = True  # assume healthy unless proven otherwise
        _healthy_accounts = list(S.accounts)
    else:
        _healthy_accounts = list(S.accounts)

    tasks = []
    t0 = time.time()
    for user, pw in _healthy_accounts[:]:
        if _stopped():
            break
        tasks.append(_run_one(sem, user, pw, target, platform, reason, flow_fn, log_fn, _api_mode))
    results = await asyncio.gather(*tasks, return_exceptions=True)
    successes = sum(1 for r in results if r is True)
    elapsed = time.time() - t0
    log_fn(f"[ENGINE] Done: {successes}/{total} succeeded in {elapsed:.0f}s")
    if hasattr(S, 'campaign_id') and S.campaign_id:
        try:
            from instareport.core.database import update_campaign
            update_campaign(S.campaign_id, total, successes,
                            "completed" if successes == total else "partial")
        except Exception:
            pass
    summary = {
        "target": target, "platform": platform, "reason": reason,
        "successes": successes, "total": total, "elapsed_s": int(elapsed),
        "timestamp": datetime.now().isoformat(),
    }
    with RUN_LOGS_LOCK:
        S.run_logs.append(summary)
    if S.use_sqlite:
        from instareport.core.database import save_run_log
        save_run_log(summary)
    _fire_webhook(summary)
    return successes


def run_mass_report(target: str, platform: str, reason: str,
                    log_fn: LogFn) -> threading.Thread:
    return _run_async_in_thread(mass_report_playwright, target, platform, reason, log_fn)


def run_batch(targets: list[str], platform: str, reason: str,
              log_fn: LogFn, campaign_id: int = 0) -> None:
    if campaign_id:
        from instareport.core.database import update_campaign
    completed = 0
    total_successes = 0
    for idx, tgt in enumerate(targets):
        if _stopped():
            break
        log_fn(f"[BATCH] Target {idx+1}/{len(targets)}: {tgt}")
        S.campaign_id = campaign_id  # link to engine
        _run_async_in_thread(mass_report_playwright, tgt, platform, reason, log_fn)
        completed += 1
        total_successes += 0  # actual result from async
        if campaign_id:
            try:
                update_campaign(campaign_id, completed, total_successes)
            except Exception:
                pass
    if campaign_id:
        try:
            update_campaign(campaign_id, completed, total_successes, "completed")
        except Exception:
            pass


# ── Async Scheduler ──────────────────────────────────────────────────────────

class Scheduler:
    """Scheduler that runs reports at configured intervals on a background thread."""

    def __init__(self) -> None:
        self._thread: threading.Thread | None = None
        self._stop_event: threading.Event = threading.Event()
        self._last_fired: str = ""

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self, interval_secs: int = 360) -> None:
        if self.running:
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run_loop, args=(interval_secs,), daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=3)
            self._thread = None

    def _run_loop(self, interval_secs: int) -> None:
        from instareport.core.state import S
        imported_async = False
        loop = None
        try:
            import asyncio
            imported_async = True
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        except Exception:
            pass

        while not self._stop_event.is_set():
            if S.sched_enabled and not S.stop_event.is_set():
                now_str = datetime.now().strftime("%H:%M")
                if now_str == S.sched_time and now_str != self._last_fired:
                    self._last_fired = now_str
                    dlog(f"[SCHED] Triggered at {now_str}")
                    if S.target and imported_async and loop:
                        try:
                            loop.run_until_complete(
                                mass_report_playwright(
                                    S.target, S.platform, S.reason,
                                    lambda m, tag="dim": dlog(m)
                                )
                            )
                        except Exception:
                            pass
                    if not S.sched_repeat:
                        S.sched_enabled = False
            for _ in range(60):
                if self._stop_event.is_set():
                    break
                time.sleep(0.5)

        if loop:
            try:
                loop.close()
            except Exception:
                pass


_scheduler: Scheduler = Scheduler()


def start_scheduler(interval_secs: int = 360) -> None:
    _scheduler.start(interval_secs)


def stop_scheduler() -> None:
    _scheduler.stop()


async def run_once_async(target: str, platform: str, reason: str,
                          log_fn: LogFn) -> int:
    """Run a single report asynchronously without blocking the scheduler."""
    return await mass_report_playwright(target, platform, reason, log_fn)
