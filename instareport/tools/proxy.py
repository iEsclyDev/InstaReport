"""Proxy pool and health checker."""
import threading, time, json
from concurrent.futures import ThreadPoolExecutor
from abc import ABC, abstractmethod
from typing import Callable, Any

from instareport.utils.helpers import _req
from instareport.utils.logging import dlog, log
from instareport.utils.constants import PROXY_BLACKLIST_THRESHOLD


class ProxyPool:
    def __init__(self) -> None:
        self._p: list[str] = []
        self._i: int = 0
        self._l: threading.Lock = threading.Lock()
        self._blacklist: set[str] = set()
        self._fail_counts: dict[str, int] = {}

    def load(self, path: str) -> int:
        loaded: list[str] = []
        try:
            with open(path, encoding="utf-8") as f:
                for ln in f:
                    ln = ln.strip()
                    if ln and not ln.startswith("#"):
                        loaded.append(ln)
        except FileNotFoundError:
            pass
        with self._l:
            self._p = loaded
            self._i = 0
            self._blacklist.clear()
            self._fail_counts.clear()
        return len(loaded)

    def next(self) -> str | None:
        with self._l:
            if not self._p:
                return None
            attempts = 0
            while attempts < len(self._p):
                p = self._p[self._i % len(self._p)]
                self._i += 1
                if p not in self._blacklist:
                    return p
                attempts += 1
            self._blacklist.clear()
            self._fail_counts.clear()
            p = self._p[self._i % len(self._p)]
            self._i += 1
            return p

    def report_failure(self, proxy_str: str | None) -> None:
        if not proxy_str:
            return
        with self._l:
            self._fail_counts[proxy_str] = self._fail_counts.get(proxy_str, 0) + 1
            if self._fail_counts[proxy_str] >= PROXY_BLACKLIST_THRESHOLD:
                self._blacklist.add(proxy_str)
                dlog(f"Proxy blacklisted: {proxy_str.split(':')[0]}:***")

    def report_success(self, proxy_str: str | None) -> None:
        if not proxy_str:
            return
        with self._l:
            self._fail_counts.pop(proxy_str, None)

    def replace(self, new_proxies: list[str]) -> None:
        with self._l:
            self._p = list(new_proxies)
            self._i = 0
            self._blacklist.clear()
            self._fail_counts.clear()

    def count(self) -> int:
        with self._l:
            return len(self._p)

    def alive_count(self) -> int:
        with self._l:
            return len(self._p) - len(self._blacklist)

    def snapshot(self) -> list[str]:
        with self._l:
            return self._p[:]


PP: ProxyPool = ProxyPool()


class ProxyHealthChecker:
    TEST_URL: str = "https://api.ipify.org"
    TIMEOUT_SECS: int = 8
    MAX_WORKERS: int = 20
    _latency: dict[str, int] = {}
    _latency_lock: threading.Lock = threading.Lock()

    @classmethod
    def check_all(cls, proxies: list[str], log_fn: Callable) -> list[str]:
        if not proxies:
            return []
        log_fn(f"  [PROXY] Pre-flight testing {len(proxies)} proxies…")
        live: list[str] = []
        lock = threading.Lock()

        def test(p: str) -> None:
            parts = p.split(":")
            if len(parts) == 2:
                proxy_url = f"http://{p}"
            elif len(parts) == 4:
                proxy_url = f"http://{parts[2]}:{parts[3]}@{parts[0]}:{parts[1]}"
            else:
                proxy_url = None
            if not proxy_url:
                return
            try:
                t0 = time.time()
                r = _req('get', cls.TEST_URL,
                         proxies={"http": proxy_url, "https": proxy_url},
                         timeout=(cls.TIMEOUT_SECS // 2, cls.TIMEOUT_SECS))
                latency_ms = int((time.time() - t0) * 1000)
                if r.status_code == 200:
                    with lock:
                        live.append(p)
                    with cls._latency_lock:
                        cls._latency[p] = latency_ms
                    dlog(f"Proxy {p.split(':')[0]}:*** OK ({latency_ms}ms)")
            except Exception as _e:
                dlog(f"Proxy {p.split(':')[0]}:*** DEAD: {_e}")

        with ThreadPoolExecutor(max_workers=min(cls.MAX_WORKERS, len(proxies))) as ex:
            list(ex.map(test, proxies))

        dead = len(proxies) - len(live)
        with cls._latency_lock:
            live.sort(key=lambda p: cls._latency.get(p, 9999))
        avg_latency = 0
        if live:
            with cls._latency_lock:
                avg_latency = sum(cls._latency.get(p, 0) for p in live) // len(live)
        log_fn(f"  [PROXY] {len(live)} live, {dead} dead removed (avg latency: {avg_latency}ms)")
        return live

    @classmethod
    def get_fastest(cls, n: int = 5) -> list[str]:
        with cls._latency_lock:
            return sorted(cls._latency.keys(), key=lambda p: cls._latency[p])[:n]


class ProxyProviderABC(ABC):
    @abstractmethod
    def fetch_proxy(self, country: str = "", session_id: str = "") -> str | None: ...

    @abstractmethod
    def health_check(self) -> bool: ...


class ResidentialProxyProvider(ProxyProviderABC):
    def __init__(self, api_key: str = "", endpoint: str = "") -> None:
        self.api_key = api_key
        self.endpoint = endpoint

    def fetch_proxy(self, country: str = "", session_id: str = "") -> str | None:
        if not self.api_key or not self.endpoint:
            dlog("ResidentialProxyProvider: no API key or endpoint configured")
            return None
        try:
            params = {}
            if country:
                params["country"] = country
            if session_id:
                params["session"] = session_id
            resp = _req('get', self.endpoint, params=params,
                        headers={"Authorization": f"Bearer {self.api_key}"}, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                proxy_str = data.get("proxy") or data.get("ip")
                if proxy_str:
                    dlog(f"Residential proxy fetched: {proxy_str.split(':')[0]}:***")
                    return proxy_str
            dlog(f"Residential proxy API returned {resp.status_code}")
        except Exception as e:
            dlog(f"Residential proxy fetch error: {e}")
        return None

    def health_check(self) -> bool:
        if not self.endpoint:
            return False
        try:
            resp = _req('get', self.endpoint, timeout=5,
                        headers={"Authorization": f"Bearer {self.api_key}"} if self.api_key else {})
            return resp.status_code < 500
        except Exception:
            return False


_RESIDENTIAL_PROVIDER: ResidentialProxyProvider = ResidentialProxyProvider()
