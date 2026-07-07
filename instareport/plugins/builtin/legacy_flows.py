"""Legacy flow wrappers - adapts existing flow_* functions as PlatformPlugin instances."""
from typing import Any, Callable

from instareport.plugins.base import PlatformPlugin
from instareport.browser.flows import (
    flow_instagram, flow_twitter, flow_youtube, flow_facebook,
    flow_tiktok, flow_reddit, flow_discord, flow_telegram,
    flow_snapchat, flow_threads, flow_gmail,
    _flow_instagram_post_report, _flow_instagram_comment_report,
    _flow_instagram_story_report, _flow_instagram_reel_report,
    _flow_tiktok_video_report,
)

LogFn = Callable[[str, str], None] | Callable[[str], None]


class _LegacyPlugin(PlatformPlugin):
    def __init__(self, key: str, report_fn: Callable[..., Any],
                 login_fn: Callable[..., Any] | None = None,
                 display_name: str = "", description: str = "",
                 version: str = "1.0.0") -> None:
        super().__init__()
        self._key = key
        self._report_fn = report_fn
        self._login_fn = login_fn
        self._display_name = display_name or key.replace("_", " ").title()
        self._description = description
        self._version = version

    @property
    def platform_key(self) -> str:
        return self._key

    @property
    def display_name(self) -> str:
        return self._display_name

    @property
    def description(self) -> str:
        return self._description

    @property
    def version(self) -> str:
        return self._version

    async def login(self, page: Any, user: str, pw: str, log_fn: LogFn) -> bool:
        if self._login_fn:
            return await self._login_fn(page, user, pw, log_fn)
        return True

    async def report(self, page: Any, user: str, pw: str, target: str, reason: str,
                     log_fn: LogFn) -> bool:
        return await self._report_fn(page, user, pw, target, reason, log_fn)


instagram = _LegacyPlugin("instagram", flow_instagram,
    display_name="Instagram", description="Report Instagram profiles via the options menu", version="2.1.0")
twitter = _LegacyPlugin("twitter", flow_twitter,
    display_name="Twitter / X", description="Report X/Twitter profiles via action menu", version="2.0.0")
youtube = _LegacyPlugin("youtube", flow_youtube,
    display_name="YouTube", description="Report YouTube channels via Google login", version="2.0.0")
facebook = _LegacyPlugin("facebook", flow_facebook,
    display_name="Facebook", description="Report Facebook profiles via the options menu", version="1.2.0")
tiktok = _LegacyPlugin("tiktok", flow_tiktok,
    display_name="TikTok", description="Report TikTok profiles via share/report flow", version="1.3.0")
reddit = _LegacyPlugin("reddit", flow_reddit,
    display_name="Reddit", description="Report Reddit users via the options menu", version="1.0.0")
discord = _LegacyPlugin("discord", flow_discord,
    display_name="Discord", description="Report Discord users via dis.gd/request form", version="1.1.0")
telegram = _LegacyPlugin("telegram", flow_telegram,
    display_name="Telegram", description="Report Telegram users via web app", version="1.0.0")
snapchat = _LegacyPlugin("snapchat", flow_snapchat,
    display_name="Snapchat", description="Report Snapchat users via support form", version="1.0.0")
threads = _LegacyPlugin("threads", flow_threads,
    display_name="Threads", description="Report Threads profiles via options menu", version="1.0.0")
gmail = _LegacyPlugin("gmail", flow_gmail,
    display_name="Gmail", description="Report Gmail abuse via Google support form", version="1.0.0")

instagram_post = _LegacyPlugin("instagram_post",
    lambda page, user, pw, target, reason, log_fn: _flow_instagram_post_report(page, target, reason, log_fn),
    display_name="Instagram Post", description="Report a specific Instagram post by URL", version="1.1.0")
instagram_comment = _LegacyPlugin("instagram_comment",
    lambda page, user, pw, target, reason, log_fn: _flow_instagram_comment_report(page, target, reason, log_fn=log_fn),
    display_name="Instagram Comment", description="Report a specific Instagram comment on a post", version="1.0.0")
instagram_story = _LegacyPlugin("instagram_story",
    lambda page, user, pw, target, reason, log_fn: _flow_instagram_story_report(page, target, reason, log_fn),
    display_name="Instagram Story", description="Report an Instagram story by username", version="1.0.0")
instagram_reel = _LegacyPlugin("instagram_reel",
    lambda page, user, pw, target, reason, log_fn: _flow_instagram_reel_report(page, target, reason, log_fn),
    display_name="Instagram Reel", description="Report an Instagram reel by URL", version="1.0.0")
tiktok_video = _LegacyPlugin("tiktok_video",
    lambda page, user, pw, target, reason, log_fn: _flow_tiktok_video_report(page, target, reason, log_fn),
    display_name="TikTok Video", description="Report a specific TikTok video by URL", version="1.0.0")
