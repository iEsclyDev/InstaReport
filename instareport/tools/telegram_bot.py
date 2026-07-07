"""Telegram Bot — control reports via Telegram commands."""
import threading, time, json
from typing import Any

from instareport.utils.constants import VERSION
from instareport.utils.helpers import _req
from instareport.utils.logging import log, dlog
from instareport.core.state import S, GLOBAL_STOP
from instareport.engine import mass_report_playwright


class TelegramBot:
    """Polling Telegram bot for remote control."""

    def __init__(self, token: str, allowed_chat_ids: list[int] | None = None) -> None:
        self.token = token
        self.allowed_ids = allowed_chat_ids or []
        self._offset: int = 0
        self._running = False
        self._thread: threading.Thread | None = None

    @property
    def base_url(self) -> str:
        return f"https://api.telegram.org/bot{self.token}"

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()
        log("[TELEGRAM] Bot started polling", "ok")

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None
        log("[TELEGRAM] Bot stopped", "ok")

    def send_message(self, chat_id: int, text: str) -> None:
        try:
            _req('post', f"{self.base_url}/sendMessage",
                 json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"},
                 timeout=10)
        except Exception as e:
            dlog(f"[TELEGRAM] Send failed: {e}")

    def _poll_loop(self) -> None:
        while self._running:
            try:
                resp = _req('get', f"{self.base_url}/getUpdates",
                            params={"offset": self._offset, "timeout": 30},
                            timeout=35)
                if resp.status_code == 200:
                    data = resp.json()
                    for update in data.get("result", []):
                        self._offset = update["update_id"] + 1
                        self._handle_update(update)
            except Exception as e:
                dlog(f"[TELEGRAM] Poll error: {e}")
            time.sleep(1)

    def _handle_update(self, update: dict) -> None:
        msg = update.get("message", {})
        chat_id = msg.get("chat", {}).get("id")
        text = (msg.get("text") or "").strip()
        if not chat_id or not text:
            return
        if self.allowed_ids and chat_id not in self.allowed_ids:
            self.send_message(chat_id, "Unauthorized")
            return
        parts = text.split()
        cmd = parts[0].lower()

        if cmd == "/start":
            self.send_message(chat_id, f"*InstaReport Bot v{VERSION}*\nCommands: /report, /status, /stop, /help")
        elif cmd == "/help":
            self.send_message(chat_id,
                "*/report `<target>` `<platform>`* — start report\n"
                "*/status* — current config and queue\n"
                "*/stop* — stop all active reports\n"
                "*/accounts* — account count")
        elif cmd == "/status":
            status = (
                f"*Status:*\n"
                f"Target: `{S.target or 'none'}`\n"
                f"Platform: `{S.platform}`\n"
                f"Accounts: `{len(S.accounts)}`\n"
                f"Workers: `{S.workers}`\n"
                f"Scheduler: `{'ON' if S.sched_enabled else 'OFF'}`"
            )
            self.send_message(chat_id, status)
        elif cmd == "/stop":
            GLOBAL_STOP.set()
            S.stop_event.set()
            self.send_message(chat_id, "All reports stopped.")
        elif cmd == "/report":
            if len(parts) < 2:
                self.send_message(chat_id, "Usage: /report `<target>` [platform]")
                return
            target = parts[1].lstrip("@")
            platform = parts[2] if len(parts) > 2 else S.platform
            S.target = target
            S.platform = platform
            S.stop_event.clear()
            GLOBAL_STOP.clear()
            from instareport.utils.helpers import _run_async_in_thread
            _run_async_in_thread(
                lambda: mass_report_playwright(
                    target, platform, S.reason,
                    lambda m, tag="dim": dlog(m)
                )
            )
            self.send_message(chat_id, f"Started report on `@{target}` ({platform})")
        elif cmd == "/accounts":
            count = len(S.accounts)
            sample = ", ".join(a[0] if isinstance(a, (list, tuple)) else str(a) for a in S.accounts[:5])
            self.send_message(chat_id, f"*Accounts:* `{count}`\n`{sample}{'...' if count > 5 else ''}`")


_bot: TelegramBot | None = None


def start_bot(token: str, allowed_ids: list[int] | None = None) -> None:
    global _bot
    if _bot:
        _bot.stop()
    _bot = TelegramBot(token, allowed_ids)
    _bot.start()


def stop_bot() -> None:
    global _bot
    if _bot:
        _bot.stop()
        _bot = None
