"""License validation system."""
import os, json, time, platform, uuid, hashlib
from datetime import datetime

from instareport.utils.constants import API_BASE
from instareport.utils.helpers import _req
from instareport.utils.logging import dlog


class LicenseSystem:
    def __init__(self) -> None:
        self.f: str = "user_license.dat"

    def validate(self, code: str) -> tuple[bool, str]:
        try:
            hwid = hashlib.sha256(
                f"{platform.node()}-{platform.machine()}-{uuid.getnode()}".encode()
            ).hexdigest()[:64]
        except Exception as e:
            return False, str(e)

        try:
            _req('get', f"{API_BASE}/health/live",
                 headers={"ngrok-skip-browser-warning": "true"}, timeout=30)
        except Exception:
            pass

        last_err: str | None = None
        for attempt in range(2):
            try:
                r = _req('post', f"{API_BASE}/licenses/validate",
                         json={"code": code, "hardware_id": hwid,
                               "device_label": platform.node()},
                         headers={"ngrok-skip-browser-warning": "true"}, timeout=45)
                if r.status_code == 200:
                    d = r.json()
                    if d.get("valid"):
                        return True, f"Plan:{d.get('plan','?')} Expires:{d.get('expiresAt','?')}"
                    return False, d.get("error", "Invalid license key")
                if r.status_code == 429:
                    return False, "Too many attempts — try again later"
                if r.status_code == 404:
                    return False, "Invalid license key"
                last_err = f"Server error ({r.status_code})"
            except Exception as e:
                last_err = str(e)
            if attempt == 0:
                time.sleep(2)
        return False, last_err or "Unknown error"

    def save(self, code: str) -> None:
        try:
            with open(self.f, "w", encoding="utf-8") as fp:
                json.dump({"code": code, "ts": datetime.now().isoformat()}, fp)
        except Exception as _e:
            dlog(f"license save failed: {_e}")

    def load(self) -> tuple[bool, str | None, str | None]:
        try:
            if os.path.exists(self.f):
                with open(self.f, encoding="utf-8") as fp:
                    d = json.load(fp)
                code = d.get("code", "").strip()
                if code:
                    ok, msg = self.validate(code)
                    if ok:
                        return True, code, msg
                    os.remove(self.f)
                    return False, None, msg
        except Exception as _e:
            dlog(f"license load failed: {_e}")
        return False, None, None


LS: LicenseSystem = LicenseSystem()
