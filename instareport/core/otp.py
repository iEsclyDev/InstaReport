import asyncio, threading
from instareport.utils.constants import OTP_TIMEOUT_SECS

class OTPManager:
    def __init__(self):
        self._l = threading.Lock()
        self._p: dict[str, threading.Event | asyncio.Event] = {}
        self._r: dict[str, str] = {}

    def request(self, key, cb):
        evt = threading.Event()
        with self._l:
            self._p[key] = evt
            self._r[key] = ""
        cb(key)
        evt.wait(timeout=OTP_TIMEOUT_SECS)
        with self._l:
            c = self._r.pop(key, "")
            self._p.pop(key, None)
        if not c:
            from instareport.utils.logging import dlog
            dlog(f"OTP timed out for {key}")
            from instareport.core.state import S
            if S.log_cb:
                S.log_cb("[!] OTP input timed out (120s)", "warn")
        return c

    async def request_async(self, key, cb):
        with self._l:
            evt = asyncio.Event()
            self._p[key] = evt
            self._r[key] = ""
        result = cb(key)
        if asyncio.iscoroutine(result):
            await result
        try:
            await asyncio.wait_for(evt.wait(), timeout=OTP_TIMEOUT_SECS)
        except asyncio.TimeoutError:
            pass
        with self._l:
            c = self._r.pop(key, "")
            self._p.pop(key, None)
        if not c:
            from instareport.utils.logging import dlog
            dlog(f"OTP timed out for {key}")
            from instareport.core.state import S
            if S.log_cb:
                S.log_cb("[!] OTP input timed out (120s)", "warn")
        return c

    def submit(self, key, code):
        with self._l:
            self._r[key] = code
            evt = self._p.get(key)
            if evt:
                if isinstance(evt, asyncio.Event):
                    try:
                        loop = asyncio.get_running_loop()
                        loop.call_soon_threadsafe(evt.set)
                    except RuntimeError:
                        pass
                else:
                    evt.set()

OTP = OTPManager()
