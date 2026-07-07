"""Platform-specific login and report flows for all supported platforms."""
import asyncio, random, time, json, uuid
from typing import Callable, Any

from instareport.utils.constants import (
    T_PAGE_LOAD, T_POST_CLICK, T_POST_LOGIN, T_REFRESH_WAIT, T_TYPE_DELAY,
    T_TELEGRAM_OTP, SESSIONS_DIR, DEBUG, _REASON_TEXT_MAP,
)
from instareport.utils.logging import dlog, flog
from instareport.core.state import S, GLOBAL_STOP
from instareport.core.selectors import get_selectors as S_sel
from instareport.core.otp import OTP
from instareport.core.config import _mark_used
from instareport.browser.helpers import (
    _delay,
    _click, _type, _wait_url, _dismiss, _handle_2fa, _human_delay,
    _clear_site_state, _ig_logo_stall, _ig_prepare_login_page, _ig_login_form_ready,
    _screenshot, _save_cookies, _load_cookies, _warmup_sequence,
    _detect_checkpoint, handle_captcha, _click_reason, _verify_report_success,
    human_click, _stopped, _import_chrome_cookies,
)

LogFn = Callable[[str, str], None] | Callable[[str], None]


async def _google_login(page: Any, user: str, pw: str, plat: str, log_fn: LogFn) -> bool:
    if await _load_cookies(page, user, plat, "https://www.google.com"):
        log_fn(f"  [G] Cookie session OK for {user}")
        return True
    await page.goto("https://accounts.google.com/signin")
    await _delay(T_PAGE_LOAD)
    if _stopped():
        return False
    await handle_captcha(page, log_fn, f"{plat}_login_{user}")
    if not await _type(page, S_sel("youtube", "email"), user):
        path = await _screenshot(page, f"{plat}_email_{user}")
        log_fn(f"  [G] email field not found{(' -> ' + path) if path else ''}")
        return False
    await _click(page, S_sel("youtube", "id_next"))
    await _delay(T_POST_CLICK)
    await handle_captcha(page, log_fn, f"{plat}_id_{user}")
    await _handle_2fa(page, user, "Google", log_fn)
    if not await _type(page, S_sel("youtube", "password"), pw):
        path = await _screenshot(page, f"{plat}_pw_{user}")
        log_fn(f"  [G] password field not found{(' -> ' + path) if path else ''}")
        return False
    await _click(page, S_sel("youtube", "pw_next"))
    await _delay(T_POST_CLICK)
    await handle_captcha(page, log_fn, f"{plat}_postpw_{user}")
    await _handle_2fa(page, user, "Google", log_fn)
    if not await _wait_url(page, S_sel("youtube", "bad_url")):
        return False
    await _delay(T_REFRESH_WAIT)
    await _save_cookies(page, user, plat)
    return True


async def _ig_login(page: Any, user: str, pw: str, log_fn: LogFn) -> bool:
    if await _load_cookies(page, user, "instagram", "https://www.instagram.com"):
        log_fn(f"  [IG] Cookie session OK for {user}")
        return True
    if S.chrome_user_data_dir:
        log_fn("  [IG] No saved session — trying Chrome profile import...")
        imported = await _import_chrome_cookies(user, "instagram")
        if imported and await _load_cookies(page, user, "instagram", "https://www.instagram.com"):
            log_fn("  [IG] Cookie session imported from Chrome profile")
            return True
        log_fn("  [IG] Chrome profile import did not yield usable cookies")
    await _clear_site_state(page)
    _nav_urls = [
        f"https://www.instagram.com/accounts/login/?hl=en&r={int(time.time())}",
        f"https://www.instagram.com/",
        f"https://m.instagram.com/accounts/login/",
    ]
    _nav_ok = False
    for _nav_try in range(4):
        log_fn(f"  [IG] Loading login page (attempt {_nav_try+1}/4)...")
        try:
            await page.goto(_nav_urls[min(_nav_try, len(_nav_urls)-1)], wait_until="domcontentloaded", timeout=35000)
            await asyncio.sleep(2 + _nav_try)
            if _nav_try in (0, 1):
                for _login_btn in ['a[href="/accounts/login/"]', 'button:has-text("Log in")',
                                   'a:has-text("Log in")', '[role="button"]:has-text("Log in")']:
                    try:
                        loc = page.locator(_login_btn)
                        if await loc.count() > 0 and await loc.first.is_visible(timeout=2000):
                            await loc.first.click(timeout=3000)
                            log_fn("  [IG] Clicked 'Log in' on main page")
                            await asyncio.sleep(3)
                            break
                    except Exception:
                        pass
            for _cib in ["//a[contains(.,'Continue in browser')]", "//button[contains(.,'Continue in browser')]",
                         "//a[contains(.,'Continue')]", "//button[contains(.,'Continue')]",
                         "//a[contains(.,'Use website')]", "//button[contains(.,'Use website')]"]:
                try:
                    loc = page.locator(f"xpath={_cib}")
                    if await loc.count() > 0 and await loc.first.is_visible(timeout=2000):
                        await loc.first.click(timeout=3000)
                        log_fn("  [IG] Clicked 'Continue in browser' interstitial")
                        await asyncio.sleep(3)
                        break
                except Exception:
                    pass
            if await _ig_logo_stall(page):
                log_fn("  [IG] Login shell stalled — resetting browser state")
                await _clear_site_state(page)
                continue
            if await _ig_prepare_login_page(page, log_fn, user):
                if await _ig_logo_stall(page):
                    log_fn("  [IG] Login shell stalled after prepare — resetting")
                    await _clear_site_state(page)
                else:
                    _nav_ok = True
                    break
        except Exception as _nav_e:
            dlog(f"ig_login goto attempt {_nav_try + 1}: {_nav_e}")
        if _nav_try == 3:
            log_fn("  [IG] Trying CDP-based navigation bypass...")
            try:
                cdp = await page.context.new_cdp_session(page)
                await cdp.send("Page.navigate", {"url": "https://www.instagram.com/accounts/login/"})
                await asyncio.sleep(5)
                if await _ig_prepare_login_page(page, log_fn, user):
                    _nav_ok = True
                    break
            except Exception as _cdp_e:
                dlog(f"ig_login CDP navigation: {_cdp_e}")
        if _nav_try < 3:
            await asyncio.sleep(2 + _nav_try * 3)
    if not _nav_ok:
        path = await _screenshot(page, f"ig_loginform_{user}")
        log_fn(f"  [IG] Could not load a usable login form after 4 attempts{(' -> ' + path) if path else ''}")
        return False
    log_fn("  [IG] Login form loaded, typing credentials...")
    await _delay(T_PAGE_LOAD)
    if _stopped():
        return False
    await _dismiss(page)
    await handle_captcha(page, log_fn, f"ig_login_{user}")
    if not await _type(page, S_sel("instagram", "username"), user, t=15):
        await _ig_prepare_login_page(page, log_fn, user)
        if not await _type(page, S_sel("instagram", "username"), user, t=15):
            path = await _screenshot(page, f"ig_username_{user}")
            log_fn(f"  [IG] username not found{(' -> ' + path) if path else ''}")
            return False
    if not await _type(page, S_sel("instagram", "password"), pw, t=15):
        await _ig_prepare_login_page(page, log_fn, user)
        if not await _type(page, S_sel("instagram", "password"), pw, t=15):
            path = await _screenshot(page, f"ig_password_{user}")
            log_fn(f"  [IG] password not found{(' -> ' + path) if path else ''}")
            return False
    await _human_delay()
    log_fn("  [IG] Clicking login button...")
    if not await _click(page, S_sel("instagram", "login_btn"), t=15):
        path = await _screenshot(page, f"ig_loginbtn_{user}")
        log_fn(f"  [IG] login btn not found{(' -> ' + path) if path else ''}")
        return False
    log_fn("  [IG] Login submitted, waiting for post-login...")
    await _delay(T_POST_LOGIN)
    await handle_captcha(page, log_fn, f"ig_postlogin_{user}")
    await _handle_2fa(page, user, "Instagram", log_fn)
    if await _detect_checkpoint(page, log_fn, "instagram"):
        await _delay(T_POST_CLICK)
        if any(p in page.url for p in S_sel("instagram", "bad_url")):
            log_fn("  [IG] Still on login/checkpoint page after challenge")
            return False
    if not await _wait_url(page, S_sel("instagram", "bad_url")):
        return False
    await _delay(T_POST_CLICK)
    await _dismiss(page)
    await _save_cookies(page, user, "instagram")
    log_fn(f"  [IG] Login successful for {user}")
    return True


async def flow_instagram(page: Any, user: str, pw: str, target: str, reason: str, log_fn: LogFn) -> bool:
    if not await _ig_login(page, user, pw, log_fn):
        log_fn("  [IG] login failed")
        return False
    await page.goto(f"https://www.instagram.com/{target}/")
    await _delay(T_PAGE_LOAD)
    if _stopped():
        return False
    await _detect_checkpoint(page, log_fn, "instagram")
    await handle_captcha(page, log_fn, f"ig_profile_{target}")
    if not await _wait_url(page, S_sel("instagram", "bad_url")):
        log_fn("  [IG] Profile redirected — session expired")
        return False
    await _human_delay()
    if not await _click(page, S_sel("instagram", "options"), 10):
        path = await _screenshot(page, f"ig_options_{target}")
        log_fn(f"  [IG] options btn not found{(' -> ' + path) if path else ''}")
        return False
    await _delay(T_POST_CLICK)
    if not await _click(page, S_sel("instagram", "report")):
        path = await _screenshot(page, f"ig_report_{target}")
        log_fn(f"  [IG] report btn not found{(' -> ' + path) if path else ''}")
        return False
    await _delay(T_POST_CLICK)
    if not await _click_reason(page, reason):
        log_fn("  [IG] reason selection failed")
        return False
    await _delay(T_POST_CLICK)
    await _click(page, S_sel("instagram", "submit"))
    await _delay(T_POST_CLICK)
    await asyncio.sleep(random.uniform(3.0, 6.5))
    return await _verify_report_success(page, "IG", target, reason, log_fn)


async def _twitter_login(page: Any, user: str, pw: str, log_fn: LogFn) -> bool:
    already_logged_in = await _load_cookies(page, user, "twitter", "https://x.com")
    if already_logged_in:
        log_fn(f"  [TW] Cookie session OK for {user}")
        return True
    await page.goto("https://x.com/i/flow/login")
    await _delay(T_PAGE_LOAD)
    if _stopped():
        return False
    await handle_captcha(page, log_fn, f"tw_login_{user}")
    if not await _type(page, S_sel("twitter", "username"), user):
        path = await _screenshot(page, f"tw_user_{user}")
        log_fn(f"  [TW] username not found{(' -> ' + path) if path else ''}")
        return False
    await _click(page, S_sel("twitter", "next"))
    await _delay(T_POST_CLICK)
    if await page.locator(f"xpath={S_sel('twitter', 'email_ver')[0]}").count() > 0:
        log_fn("  [TW] Email verification step")
        await _type(page, S_sel("twitter", "email_ver"), user)
        await _click(page, S_sel("twitter", "email_next"))
        await _delay(T_POST_CLICK)
    elif await page.locator('input[name="phone"], input[data-testid="ocfEnterTextTextInput"][type="tel"]').count() > 0:
        log_fn("  [TW] Phone verification requested — cannot auto-fill")
        path = await _screenshot(page, f"tw_phone_{user}")
        if path:
            log_fn(f"  [TW] Screenshot: {path}")
        return False
    await _type(page, S_sel("twitter", "password"), pw)
    await _delay(T_POST_CLICK)
    await _click(page, S_sel("twitter", "login_btn"))
    await _delay(T_POST_LOGIN)
    await handle_captcha(page, log_fn, f"tw_postlogin_{user}")
    await _handle_2fa(page, user, "Twitter", log_fn)
    if not await _wait_url(page, S_sel("twitter", "bad_url")):
        return False
    await _delay(T_REFRESH_WAIT)
    await _save_cookies(page, user, "twitter")
    return True


async def flow_twitter(page: Any, user: str, pw: str, target: str, reason: str, log_fn: LogFn) -> bool:
    if not await _twitter_login(page, user, pw, log_fn):
        log_fn("  [TW] login failed")
        return False
    await page.goto(f"https://x.com/{target}")
    await _delay(T_PAGE_LOAD)
    if _stopped():
        return False
    await handle_captcha(page, log_fn, f"tw_profile_{target}")
    if not await _wait_url(page, S_sel("twitter", "bad_url")):
        log_fn("  [TW] Profile redirected — session expired")
        return False
    await _human_delay()
    if not await _click(page, S_sel("twitter", "actions")):
        path = await _screenshot(page, f"tw_actions_{target}")
        log_fn(f"  [TW] actions not found{(' -> ' + path) if path else ''}")
        return False
    await _delay(T_POST_CLICK)
    if not await _click(page, S_sel("twitter", "report")):
        path = await _screenshot(page, f"tw_report_{target}")
        log_fn(f"  [TW] report not found{(' -> ' + path) if path else ''}")
        return False
    await _delay(T_POST_CLICK)
    if not await _click_reason(page, reason):
        log_fn("  [TW] reason selection failed")
        return False
    await _delay(T_POST_CLICK)
    await _click(page, S_sel("twitter", "submit"))
    await _delay(T_POST_CLICK)
    await asyncio.sleep(random.uniform(2.0, 5.0))
    return await _verify_report_success(page, "TW", target, reason, log_fn)


async def flow_youtube(page: Any, user: str, pw: str, target: str, reason: str, log_fn: LogFn) -> bool:
    if not await _google_login(page, user, pw, "youtube", log_fn):
        log_fn("  [YT] login failed")
        return False
    await page.goto(f"https://www.youtube.com/@{target}")
    await _delay(T_PAGE_LOAD)
    if _stopped():
        return False
    await handle_captcha(page, log_fn, f"yt_profile_{target}")
    if not await _wait_url(page, S_sel("youtube", "bad_url")):
        log_fn("  [YT] Profile redirected — session expired")
        return False
    await _human_delay()
    if not await _click(page, S_sel("youtube", "more")):
        path = await _screenshot(page, f"yt_more_{target}")
        log_fn(f"  [YT] more not found{(' -> ' + path) if path else ''}")
        return False
    await _delay(T_POST_CLICK)
    if not await _click(page, S_sel("youtube", "report")):
        path = await _screenshot(page, f"yt_report_{target}")
        log_fn(f"  [YT] report not found{(' -> ' + path) if path else ''}")
        return False
    await _delay(T_POST_CLICK)
    if not await _click_reason(page, reason):
        log_fn("  [YT] reason selection failed")
        return False
    await _delay(T_POST_CLICK)
    await _click(page, S_sel("youtube", "submit"))
    await asyncio.sleep(random.uniform(2.0, 5.0))
    return await _verify_report_success(page, "YT", target, reason, log_fn)


async def flow_facebook(page: Any, user: str, pw: str, target: str, reason: str, log_fn: LogFn) -> bool:
    if await _load_cookies(page, user, "facebook", "https://www.facebook.com"):
        log_fn(f"  [FB] Cookie session OK for {user}")
    else:
        await page.goto("https://www.facebook.com/login/")
        await _delay(T_PAGE_LOAD)
        if _stopped():
            return False
        await _dismiss(page)
        await handle_captcha(page, log_fn, f"fb_login_{user}")
        if not await _type(page, S_sel("facebook", "email"), user):
            return False
        if not await _type(page, S_sel("facebook", "password"), pw):
            return False
        await _click(page, S_sel("facebook", "login_btn"))
        await _delay(T_POST_LOGIN)
        await handle_captcha(page, log_fn, f"fb_postlogin_{user}")
        await _handle_2fa(page, user, "Facebook", log_fn)
        await _detect_checkpoint(page, log_fn, "facebook")
        if not await _wait_url(page, S_sel("facebook", "bad_url")):
            return False
        await _delay(T_REFRESH_WAIT)
        await _dismiss(page)
        await _save_cookies(page, user, "facebook")
    await page.goto(f"https://www.facebook.com/{target}")
    await _delay(T_PAGE_LOAD)
    if _stopped():
        return False
    if not await _wait_url(page, S_sel("facebook", "bad_url")):
        log_fn("  [FB] Profile redirected — session expired")
        return False
    await _human_delay()
    if not await _click(page, S_sel("facebook", "more")):
        path = await _screenshot(page, f"fb_more_{target}")
        log_fn(f"  [FB] more not found{(' -> ' + path) if path else ''}")
        return False
    await _delay(T_POST_CLICK)
    if not await _click(page, S_sel("facebook", "report")):
        path = await _screenshot(page, f"fb_report_{target}")
        log_fn(f"  [FB] report not found{(' -> ' + path) if path else ''}")
        return False
    await _delay(T_POST_CLICK)
    if not await _click_reason(page, reason):
        log_fn("  reason selection failed")
        return False
    await _delay(T_POST_CLICK)
    await _click(page, S_sel("facebook", "submit"))
    await asyncio.sleep(random.uniform(2.0, 5.0))
    return await _verify_report_success(page, "FB", target, reason, log_fn)


async def flow_tiktok(page: Any, user: str, pw: str, target: str, reason: str, log_fn: LogFn) -> bool:
    if await _load_cookies(page, user, "tiktok", "https://www.tiktok.com"):
        log_fn(f"  [TT] Cookie session OK for {user}")
    else:
        await page.goto("https://www.tiktok.com/login/phone-or-email/email")
        await _delay(T_PAGE_LOAD)
        if _stopped():
            return False
        await _dismiss(page)
        await handle_captcha(page, log_fn, f"tt_login_{user}")
        if not await _type(page, S_sel("tiktok", "username"), user):
            return False
        if not await _type(page, S_sel("tiktok", "password"), pw):
            return False
        await _click(page, S_sel("tiktok", "login_btn"))
        await _delay(T_POST_LOGIN)
        await handle_captcha(page, log_fn, f"tt_post_{user}")
        await _handle_2fa(page, user, "TikTok", log_fn)
        if not await _wait_url(page, S_sel("tiktok", "bad_url")):
            return False
        await _delay(T_REFRESH_WAIT)
        await _save_cookies(page, user, "tiktok")
    await page.goto(f"https://www.tiktok.com/@{target}")
    await _delay(T_PAGE_LOAD)
    if _stopped():
        return False
    if not await _wait_url(page, S_sel("tiktok", "bad_url")):
        log_fn("  [TT] Profile redirected — session expired")
        return False
    await _human_delay()
    if not await _click(page, S_sel("tiktok", "more")):
        path = await _screenshot(page, f"tt_more_{target}")
        log_fn(f"  [TT] more not found{(' -> ' + path) if path else ''}")
        return False
    await _delay(T_POST_CLICK)
    if not await _click(page, S_sel("tiktok", "report")):
        path = await _screenshot(page, f"tt_report_{target}")
        log_fn(f"  [TT] report not found{(' -> ' + path) if path else ''}")
        return False
    await _delay(T_POST_CLICK)
    if not await _click_reason(page, reason):
        log_fn("  reason selection failed")
        return False
    await _delay(T_POST_CLICK)
    await _click(page, S_sel("tiktok", "submit"))
    await asyncio.sleep(random.uniform(2.0, 5.0))
    return await _verify_report_success(page, "TT", target, reason, log_fn)


async def flow_reddit(page: Any, user: str, pw: str, target: str, reason: str, log_fn: LogFn) -> bool:
    if await _load_cookies(page, user, "reddit", "https://www.reddit.com"):
        log_fn(f"  [RD] Cookie session OK for {user}")
    else:
        await page.goto("https://www.reddit.com/login/")
        await _delay(T_PAGE_LOAD)
        if _stopped():
            return False
        if not await _type(page, S_sel("reddit", "username"), user):
            return False
        if not await _type(page, S_sel("reddit", "password"), pw):
            return False
        await _click(page, S_sel("reddit", "login_btn"))
        await _delay(T_POST_LOGIN)
        await _handle_2fa(page, user, "Reddit", log_fn)
        if not await _wait_url(page, S_sel("reddit", "bad_url")):
            return False
        await _delay(T_REFRESH_WAIT)
        await _save_cookies(page, user, "reddit")
    await page.goto(f"https://www.reddit.com/user/{target}")
    await _delay(T_PAGE_LOAD)
    if _stopped():
        return False
    if not await _wait_url(page, S_sel("reddit", "bad_url")):
        log_fn("  [RD] Profile redirected — session expired")
        return False
    await _human_delay()
    if not await _click(page, S_sel("reddit", "more")):
        path = await _screenshot(page, f"rd_more_{target}")
        log_fn(f"  [RD] more not found{(' -> ' + path) if path else ''}")
        return False
    await _delay(T_POST_CLICK)
    if not await _click(page, S_sel("reddit", "report")):
        path = await _screenshot(page, f"rd_report_{target}")
        log_fn(f"  [RD] report not found{(' -> ' + path) if path else ''}")
        return False
    await _delay(T_POST_CLICK)
    if not await _click_reason(page, reason):
        log_fn("  reason selection failed")
        return False
    await _delay(T_POST_CLICK)
    await _click(page, S_sel("reddit", "submit"))
    await asyncio.sleep(random.uniform(2.0, 5.0))
    return await _verify_report_success(page, "RD", target, reason, log_fn)


async def flow_discord(page: Any, user: str, pw: str, target: str, reason: str, log_fn: LogFn) -> bool:
    if await _load_cookies(page, user, "discord", "https://discord.com/channels/@me"):
        log_fn(f"  [DC] Cookie session OK for {user}")
    else:
        await page.goto("https://discord.com/login")
        await _delay(T_PAGE_LOAD)
        if _stopped():
            return False
        if not await _type(page, S_sel("discord", "email"), user):
            return False
        if not await _type(page, S_sel("discord", "password"), pw):
            return False
        await _click(page, S_sel("discord", "login_btn"))
        await _delay(T_POST_LOGIN)
        await handle_captcha(page, log_fn, f"dc_login_{user}")
        await _handle_2fa(page, user, "Discord", log_fn)
        if not await _wait_url(page, S_sel("discord", "bad_url"), t=60):
            return False
        await _delay(T_REFRESH_WAIT)
        await _save_cookies(page, user, "discord")
    await page.goto("https://dis.gd/request")
    await _delay(T_PAGE_LOAD)
    if _stopped():
        return False
    await handle_captcha(page, log_fn, f"dc_form_{target}")
    await _human_delay()
    await _type(page, S_sel("discord", "report_email"), user)
    await _delay(T_TYPE_DELAY)
    await _type(page, S_sel("discord", "report_subject"), f"Abuse report ({reason}): {target}")
    await _delay(T_TYPE_DELAY)
    await _type(page, S_sel("discord", "report_body"), f"Reporting {target} for {reason}.")
    await _delay(T_TYPE_DELAY)
    if not await _click(page, S_sel("discord", "submit")):
        path = await _screenshot(page, f"dc_submit_{target}")
        log_fn(f"  [DC] submit failed{(' -> ' + path) if path else ''}")
        return False
    await asyncio.sleep(random.uniform(2.0, 5.0))
    return await _verify_report_success(page, "DC", target, reason, log_fn)


async def flow_telegram(page: Any, user: str, pw: str, target: str, reason: str, log_fn: LogFn) -> bool:
    await page.goto("https://web.telegram.org/k/")
    await _delay(T_PAGE_LOAD + 2)
    if _stopped():
        return False
    await handle_captcha(page, log_fn, f"tg_login_{user}")
    if not await _click(page, S_sel("telegram", "login_btn")):
        path = await _screenshot(page, f"tg_loginbtn_{user}")
        log_fn(f"  [TG] login btn not found{(' -> ' + path) if path else ''}")
        return False
    await _delay(T_POST_CLICK)
    if not await _type(page, S_sel("telegram", "phone"), user):
        path = await _screenshot(page, f"tg_phone_{user}")
        log_fn(f"  [TG] phone field not found{(' -> ' + path) if path else ''}")
        return False
    await _click(page, S_sel("telegram", "next"))
    await _delay(T_POST_CLICK)
    if S.otp_cb:
        key = f"Telegram:{user}:{time.time()}"
        code = await OTP.request_async(key, lambda k: S.otp_cb(k, "Telegram", user))
        if code:
            await _type(page, S_sel("telegram", "otp"), code)
            await _delay(T_TYPE_DELAY)
            await _click(page, S_sel("telegram", "next"))
            await _delay(T_TELEGRAM_OTP)
    await handle_captcha(page, log_fn, f"tg_post_login_{user}")
    if _stopped():
        return False
    await page.goto(f"https://t.me/{target}")
    await _delay(T_PAGE_LOAD)
    if _stopped():
        return False
    await _human_delay()
    if not await _click(page, S_sel("telegram", "chat_info")):
        path = await _screenshot(page, f"tg_chat_{target}")
        log_fn(f"  [TG] chat info not found{(' -> ' + path) if path else ''}")
        return False
    await _delay(T_POST_CLICK)
    await _click(page, S_sel("telegram", "menu_toggle"))
    await _delay(T_POST_CLICK)
    if not await _click(page, S_sel("telegram", "report")):
        path = await _screenshot(page, f"tg_report_{target}")
        log_fn(f"  [TG] report btn not found{(' -> ' + path) if path else ''}")
        return False
    await _delay(T_POST_CLICK)
    if not await _click_reason(page, reason):
        log_fn("  reason selection failed")
        return False
    await _delay(T_POST_CLICK)
    await _click(page, S_sel("telegram", "report_btn"))
    await asyncio.sleep(random.uniform(2.0, 5.0))
    await _save_cookies(page, user, "telegram")
    return await _verify_report_success(page, "TG", target, reason, log_fn)


async def flow_snapchat(page: Any, user: str, pw: str, target: str, reason: str, log_fn: LogFn) -> bool:
    await page.goto("https://support.snapchat.com/en-US/i-need-help?lang=en-US&category=Other&subcategory=reportabuse")
    await _delay(T_PAGE_LOAD)
    if _stopped():
        return False
    await handle_captcha(page, log_fn, f"sc_form_{target}")
    await _human_delay()
    if not await _type(page, S_sel("snapchat", "target_inp"), target):
        path = await _screenshot(page, f"sc_target_{target}")
        log_fn(f"  [SC] target field not found{(' -> ' + path) if path else ''}")
        return False
    await _delay(T_TYPE_DELAY)
    await _type(page, S_sel("snapchat", "your_user"), user)
    await _delay(T_TYPE_DELAY)
    await _type(page, S_sel("snapchat", "desc_inp"), f"Reporting @{target} for {reason}.")
    await _delay(T_TYPE_DELAY)
    if not await _click(page, S_sel("snapchat", "submit")):
        path = await _screenshot(page, f"sc_submit_{target}")
        log_fn(f"  [SC] submit failed{(' -> ' + path) if path else ''}")
        return False
    await asyncio.sleep(random.uniform(2.0, 5.0))
    return await _verify_report_success(page, "SC", target, reason, log_fn)


async def flow_threads(page: Any, user: str, pw: str, target: str, reason: str, log_fn: LogFn) -> bool:
    if await _load_cookies(page, user, "threads", "https://www.threads.net"):
        log_fn(f"  [TH] Cookie session OK for {user}")
    else:
        await page.goto("https://www.threads.net/login")
        await _delay(T_PAGE_LOAD)
        if _stopped():
            return False
        await _dismiss(page)
        await handle_captcha(page, log_fn, f"th_login_{user}")
        if not await _type(page, S_sel("threads", "username"), user):
            return False
        if not await _type(page, S_sel("threads", "password"), pw):
            return False
        await _click(page, S_sel("threads", "login_btn"))
        await _delay(T_POST_LOGIN)
        await _handle_2fa(page, user, "Threads", log_fn)
        if not await _wait_url(page, S_sel("threads", "bad_url")):
            return False
        await _delay(T_REFRESH_WAIT)
        await _save_cookies(page, user, "threads")
    await page.goto(f"https://www.threads.net/@{target}")
    await _delay(T_PAGE_LOAD)
    if _stopped():
        return False
    if not await _wait_url(page, S_sel("threads", "bad_url")):
        log_fn("  [TH] Profile redirected — session expired")
        return False
    await _human_delay()
    if not await _click(page, S_sel("threads", "more")):
        path = await _screenshot(page, f"th_more_{target}")
        log_fn(f"  [TH] more not found{(' -> ' + path) if path else ''}")
        return False
    await _delay(T_POST_CLICK)
    if not await _click(page, S_sel("threads", "report")):
        path = await _screenshot(page, f"th_report_{target}")
        log_fn(f"  [TH] report not found{(' -> ' + path) if path else ''}")
        return False
    await _delay(T_POST_CLICK)
    if not await _click_reason(page, reason):
        log_fn("  reason selection failed")
        return False
    await _delay(T_POST_CLICK)
    await _click(page, S_sel("threads", "submit"))
    await asyncio.sleep(random.uniform(2.0, 5.0))
    return await _verify_report_success(page, "TH", target, reason, log_fn)


async def flow_gmail(page: Any, user: str, pw: str, target: str, reason: str, log_fn: LogFn) -> bool:
    if not await _google_login(page, user, pw, "gmail", log_fn):
        log_fn("  [GM] login failed")
        return False
    tgt = target if "@" in target else f"{target}@gmail.com"
    await page.goto("https://support.google.com/mail/contact/abuse")
    await _delay(T_PAGE_LOAD)
    if _stopped():
        return False
    await handle_captcha(page, log_fn, f"gm_form_{tgt}")
    await _human_delay()
    if not await _type(page, S_sel("gmail", "target_inp"), tgt):
        path = await _screenshot(page, f"gm_field_{tgt}")
        log_fn(f"  [GM] email field not found{(' -> ' + path) if path else ''}")
        return False
    await _delay(T_TYPE_DELAY)
    await _type(page, S_sel("gmail", "desc_inp"), f"Reporting {tgt} for {reason}.")
    await _delay(T_TYPE_DELAY)
    if not await _click(page, S_sel("gmail", "submit")):
        path = await _screenshot(page, f"gm_submit_{tgt}")
        log_fn(f"  [GM] submit failed{(' -> ' + path) if path else ''}")
        return False
    await asyncio.sleep(random.uniform(2.0, 5.0))
    return await _verify_report_success(page, "GM", tgt, reason, log_fn)


async def _flow_instagram_post_report(page: Any, target_post_url: str, reason: str = "spam",
                                       log_fn: LogFn | None = None) -> tuple[bool, str]:
    try:
        await page.goto(target_post_url, timeout=45000)
        await asyncio.sleep(random.uniform(3.5, 7.5))
        if not await human_click(page, '[aria-label="More options"]', timeout=14000):
            if not await human_click(page, 'svg[aria-label="More options"]', timeout=5000):
                return False, "Post ⋮ button not found"
        await asyncio.sleep(random.uniform(1.2, 3.0))
        if not await human_click(page, 'text=Report', timeout=12000):
            if not await human_click(page, 'button:has-text("Report")', timeout=5000):
                return False, "Report option not found"
        await asyncio.sleep(random.uniform(1.0, 2.5))
        reason_text = _REASON_TEXT_MAP.get(reason.lower(), "It's spam")
        if not await human_click(page, f'text={reason_text}', timeout=10000):
            await human_click(page, "text=It's spam", timeout=5000)
        await asyncio.sleep(random.uniform(0.9, 2.3))
        submitted = False
        for sel in ['button:has-text("Submit report")', 'button:has-text("Report")',
                     'button:has-text("Submit")', '[role="button"]:has-text("Report")']:
            if await human_click(page, sel, timeout=5000):
                submitted = True
                break
        if not submitted:
            return False, "Submit button not found"
        await asyncio.sleep(random.uniform(3.0, 6.0))
        for sel in ['text=Thanks for reporting', 'text=Your report has been submitted',
                     '[role="alertdialog"] >> text=reported', 'div[role="status"] >> text=received',
                     'text=We\'ll review your report']:
            try:
                if await page.locator(sel).first.is_visible(timeout=6000):
                    return True, "confirmed"
            except Exception:
                continue
        content = await page.content()
        if any(w in content.lower() for w in ["thank", "report", "review", "submitted"]):
            return True, "submitted (unconfirmed)"
        return False, "no confirmation"
    except Exception as e:
        return False, str(e)


async def _flow_instagram_comment_report(page: Any, post_url: str, reason: str = "spam",
                                          comment_snippet: str = "",
                                          log_fn: LogFn | None = None) -> tuple[bool, str]:
    try:
        await page.goto(post_url, timeout=45000)
        await asyncio.sleep(random.uniform(4.0, 8.0))
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight * 0.7)")
        await asyncio.sleep(2.0)
        if comment_snippet:
            comment_loc = page.locator(f'span:has-text("{comment_snippet[:25]}")').first
            try:
                await comment_loc.wait_for(state="visible", timeout=15000)
            except Exception:
                return False, "Comment not found"
            parent = comment_loc.locator("xpath=ancestor::li[1]")
            more_btn = parent.locator('[aria-label="More options"], [aria-label="Comment options"]').first
            try:
                await more_btn.click(timeout=8000)
            except Exception:
                await comment_loc.hover()
                await asyncio.sleep(1.0)
                try:
                    await more_btn.click(timeout=5000)
                except Exception:
                    return False, "Comment ⋮ not found"
        else:
            first_more = page.locator('ul li [aria-label="More options"]').first
            try:
                await first_more.click(timeout=10000)
            except Exception:
                return False, "No comment ⋮ found"
        await asyncio.sleep(1.5)
        if not await human_click(page, 'text=Report', timeout=10000):
            return False, "Report missing"
        await asyncio.sleep(1.2)
        reason_text = _REASON_TEXT_MAP.get(reason.lower(), "It's spam")
        if not await human_click(page, f'text={reason_text}', timeout=10000):
            await human_click(page, "text=It's spam", timeout=5000)
        await asyncio.sleep(1.0)
        await human_click(page, 'button:has-text("Report")', timeout=10000)
        await asyncio.sleep(3.5)
        for sel in ['text=Thanks for reporting this comment', 'text=Thanks for reporting',
                     'text=Your report has been submitted']:
            try:
                if await page.locator(sel).first.is_visible(timeout=6000):
                    return True, "confirmed"
            except Exception:
                continue
        return True, "submitted (unconfirmed)"
    except Exception as e:
        return False, str(e)


async def _flow_instagram_story_report(page: Any, username: str, reason: str = "spam",
                                        log_fn: LogFn | None = None) -> tuple[bool, str]:
    try:
        clean = username.lstrip("@")
        await page.goto(f"https://www.instagram.com/stories/{clean}/", timeout=45000)
        await asyncio.sleep(random.uniform(4.0, 7.0))
        vp = page.viewport_size or {"width": 1280, "height": 720}
        await page.mouse.click(vp["width"] // 2, vp["height"] // 2)
        await asyncio.sleep(2.0)
        for sel in ['[aria-label="More"]', 'button[aria-label="More options"]',
                     'svg[aria-label="More"]']:
            if await human_click(page, sel, timeout=5000):
                break
        else:
            return False, "Story ⋯ not found"
        await asyncio.sleep(1.3)
        if not await human_click(page, 'text=Report', timeout=10000):
            return False, "Report missing"
        await asyncio.sleep(1.2)
        reason_text = _REASON_TEXT_MAP.get(reason.lower(), "It's spam")
        if not await human_click(page, f'text={reason_text}', timeout=8000):
            await human_click(page, "text=It's spam", timeout=5000)
        await asyncio.sleep(1.0)
        await human_click(page, 'button:has-text("Report")', timeout=8000)
        await asyncio.sleep(3.5)
        for sel in ['text=Thanks for reporting this story', 'text=Thanks for reporting',
                     'text=Your report has been submitted']:
            try:
                if await page.locator(sel).first.is_visible(timeout=6000):
                    return True, "confirmed"
            except Exception:
                continue
        content = await page.content()
        if any(w in content.lower() for w in ["thank", "report", "submitted"]):
            return True, "submitted (unconfirmed)"
        return False, "no confirmation"
    except Exception as e:
        return False, str(e)


async def _flow_instagram_reel_report(page: Any, reel_url: str, reason: str = "spam",
                                       log_fn: LogFn | None = None) -> tuple[bool, str]:
    return await _flow_instagram_post_report(page, reel_url, reason, log_fn)


async def _flow_tiktok_video_report(page: Any, video_url: str, reason: str = "spam",
                                     log_fn: LogFn | None = None) -> tuple[bool, str]:
    try:
        await page.goto(video_url, timeout=45000)
        await asyncio.sleep(random.uniform(4.0, 8.0))
        shared = False
        for sel in ['[data-e2e="share-icon"]', 'button[aria-label="Share"]',
                     '[aria-label="Share video"]']:
            if await human_click(page, sel, timeout=5000):
                shared = True
                break
        if shared:
            await asyncio.sleep(1.5)
            if not await human_click(page, 'text=Report', timeout=10000):
                for sel2 in ['[data-e2e="more-icon"]', 'button[aria-label="More"]']:
                    if await human_click(page, sel2, timeout=5000):
                        await asyncio.sleep(1.0)
                        if await human_click(page, 'text=Report', timeout=8000):
                            break
                else:
                    return False, "Report option not found"
        else:
            for sel in ['[data-e2e="more-icon"]', 'button[aria-label="More"]']:
                if await human_click(page, sel, timeout=8000):
                    await asyncio.sleep(1.0)
                    if await human_click(page, 'text=Report', timeout=8000):
                        break
            else:
                return False, "Neither Share nor More button found"
        await asyncio.sleep(1.2)
        reason_text = {
            "spam": "Spam or scam", "nudity": "Nudity or sexual content",
            "violence": "Violence or gore", "harassment": "Harassment or bullying",
            "hate": "Hateful behavior", "misinformation": "Misleading information",
        }.get(reason.lower(), "Spam or scam")
        if not await human_click(page, f'text={reason_text}', timeout=10000):
            await human_click(page, 'text=Spam or scam', timeout=5000)
        await asyncio.sleep(1.0)
        for sel in ['button:has-text("Submit report")', 'button:has-text("Submit")',
                     'button:has-text("Report")']:
            if await human_click(page, sel, timeout=5000):
                break
        await asyncio.sleep(3.5)
        for sel in ['text=Thanks for reporting', 'text=Report submitted',
                     '[role="status"] >> text=received', 'text=We received your report']:
            try:
                if await page.locator(sel).first.is_visible(timeout=6000):
                    return True, "confirmed"
            except Exception:
                continue
        content = await page.content()
        if "report" in content.lower() and "thank" in content.lower():
            return True, "submitted (unconfirmed)"
        return False, "no confirmation"
    except Exception as e:
        return False, str(e)


FlowFunc = Callable[[Any, str, str, str, str, LogFn], Any]

FLOW_MAP: dict[str, FlowFunc] = {
    "instagram": flow_instagram,
    "twitter": flow_twitter,
    "youtube": flow_youtube,
    "facebook": flow_facebook,
    "tiktok": flow_tiktok,
    "reddit": flow_reddit,
    "discord": flow_discord,
    "telegram": flow_telegram,
    "snapchat": flow_snapchat,
    "threads": flow_threads,
    "gmail": flow_gmail,
    "instagram_post": lambda page, user, pw, target, reason, log_fn:
        _flow_instagram_post_report(page, target, reason, log_fn),
    "instagram_comment": lambda page, user, pw, target, reason, log_fn:
        _flow_instagram_comment_report(page, target, reason, log_fn=log_fn),
    "instagram_story": lambda page, user, pw, target, reason, log_fn:
        _flow_instagram_story_report(page, target, reason, log_fn),
    "instagram_reel": lambda page, user, pw, target, reason, log_fn:
        _flow_instagram_reel_report(page, target, reason, log_fn),
    "tiktok_video": lambda page, user, pw, target, reason, log_fn:
        _flow_tiktok_video_report(page, target, reason, log_fn),
}


async def _scrape_engagement(username: str, platform: str) -> dict:
    """Scrape follower/following/post counts from a public profile."""
    from instareport.browser.factory import get_shared_browser, _create_isolated_context
    from instareport.utils.constants import T_PAGE_LOAD
    result: dict = {"followers": "?", "following": "?", "posts": "?"}
    context = page = None
    try:
        browser = await get_shared_browser()
        context, page = await _create_isolated_context(browser)
        urls = {
            "instagram": f"https://www.instagram.com/{username}/",
            "twitter": f"https://x.com/{username}",
            "tiktok": f"https://www.tiktok.com/@{username}",
            "youtube": f"https://www.youtube.com/@{username}",
            "reddit": f"https://www.reddit.com/user/{username}",
        }
        url = urls.get(platform)
        if not url:
            return result
        await page.goto(url, wait_until="domcontentloaded", timeout=25000)
        await _delay(T_PAGE_LOAD + 2)
        if platform == "instagram":
            meta = await page.evaluate("""() => {
                const el = document.querySelector('meta[property="og:description"]');
                return el ? el.content : null;
            }""")
            if meta:
                parts = meta.replace(',', '').split()
                for p in parts:
                    if 'follower' in p.lower():
                        result["followers"] = parts[parts.index(p)-1]
                    elif 'following' in p.lower():
                        result["following"] = parts[parts.index(p)-1]
                    elif 'post' in p.lower():
                        result["posts"] = parts[parts.index(p)-1]
                if any(v == "?" for v in result.values()):
                    ini = await page.evaluate("""() => {
                        try {
                            const el = document.getElementById('__NEXT_DATA_FAILED__');
                            if (!el) return null;
                            const d = JSON.parse(el.textContent);
                            const u = d?.props?.pageProps?.user || d?.entryData?.ProfilePage[0]?.graphql?.user;
                            if (!u) return null;
                            return {posts: u.edge_owner_to_timeline_media?.count + '',
                                    followers: u.edge_followed_by?.count + '',
                                    following: u.edge_follow?.count + ''};
                        } catch(e) { return null; }
                    }""")
                    if ini:
                        result.update(ini)

        elif platform == "twitter":
            aria_stats = await page.evaluate("""() => {
                const aria = document.querySelectorAll('[class*="r-"] a[href*="/"]');
                const out = [];
                for (const a of aria) {
                    const label = a.getAttribute('aria-label') || a.getAttribute('title') || '';
                    if (label.match(/\\d+.*(?:Follower|Following|Post|Tweet)/i)) out.push(label);
                }
                return out;
            }""")
            for s in aria_stats:
                if 'follower' in s.lower() and result["followers"] == "?":
                    result["followers"] = s.split()[0]
                elif 'following' in s.lower() and result["following"] == "?":
                    result["following"] = s.split()[0]
                elif any(w in s.lower() for w in ['post','tweet']) and result["posts"] == "?":
                    result["posts"] = s.split()[0]
            if result["followers"] == "?":
                text_stats = await page.evaluate("""() => {
                    const all = document.querySelectorAll('a');
                    const out = {};
                    for (const a of all) {
                        const aria = a.getAttribute('aria-label') || a.getAttribute('title') || '';
                        const m = aria.match(/([\\d,.KMB]+)\\s*(Follower|Following|Post|Tweet)/i);
                        if (m) {
                            const key = m[2].toLowerCase();
                            if (!(key in out)) out[key] = m[1];
                        }
                    }
                    return out;
                }""")
                if text_stats:
                    if 'follower' in text_stats and result["followers"] == "?":
                        result["followers"] = text_stats['follower']
                    if 'following' in text_stats and result["following"] == "?":
                        result["following"] = text_stats['following']
                    if any(k in text_stats for k in ['post','tweet']) and result["posts"] == "?":
                        result["posts"] = text_stats.get('post') or text_stats.get('tweet', '?')
            fallback = await page.evaluate("""() => {
                const article = document.querySelector('article');
                if (!article) return null;
                const links = article.querySelectorAll('a[href*="/"]');
                const nums = [];
                for (const a of links) {
                    const t = a.textContent.trim();
                    if (/^\\d+[.,]?\\d*[KMB]?$/i.test(t)) nums.push(t);
                    if (nums.length === 3) break;
                }
                return nums.length === 3 ? {posts: nums[0], followers: nums[1], following: nums[2]} : null;
            }""")
            if fallback:
                result.update(fallback)
        elif platform == "tiktok":
            selectors = [
                '[data-e2e="user-post-count"], [data-e2e="followers-count"], [data-e2e="following-count"]',
                '[class*="count"], [class*="stat"]',
                'strong[title*="Follower"], strong[title*="Following"]',
            ]
            for sel in selectors:
                stats = await page.evaluate("""() => {
                    const sel = arguments[0];
                    const els = document.querySelectorAll(sel);
                    return Array.from(els).map(e => e.textContent.trim()).filter(Boolean);
                }""", sel)
                if len(stats) >= 3:
                    result["posts"] = stats[0]
                    result["followers"] = stats[1]
                    result["following"] = stats[2]
                    break
        elif platform == "youtube":
            yt = await page.evaluate("""() => {
                const meta = document.querySelector('meta[itemprop="interactionStatistic"]');
                if (meta) return {posts: meta.content};
                return null;
            }""")
            if yt:
                result.update(yt)
            subs = await page.evaluate("""() => {
                const el = document.querySelector('#subscriber-count');
                return el ? el.textContent.trim() : null;
            }""")
            if subs:
                result["followers"] = subs
        return result
    except Exception:
        return result
    finally:
        if context:
            try:
                await context.close()
            except Exception:
                pass


async def _submit_appeal(platform: str, target: str, reason: str,
                          appeal_text: str, account_user: str,
                          account_pw: str, log_fn: Callable) -> bool:
    """Submit an appeal to a platform for a reported account."""
    from instareport.browser.factory import get_shared_browser, _create_isolated_context
    from instareport.utils.constants import T_PAGE_LOAD, T_POST_CLICK
    context = page = None
    try:
        browser = await get_shared_browser()
        context, page = await _create_isolated_context(browser)
        appeal_urls = {
            "instagram": "https://help.instagram.com/contact/606967052475008",
            "twitter": "https://help.twitter.com/forms/appeal",
            "tiktok": "https://www.tiktok.com/legal/report/feedback",
        }
        url = appeal_urls.get(platform)
        if not url:
            log_fn(f"[APPEAL] No appeal form for {platform}")
            return False

        # Login first using existing login flows
        log_fn(f"[APPEAL] Logging in as {account_user} on {platform}...")
        if platform == "instagram":
            ok = await _ig_login(page, account_user, account_pw, log_fn)
        elif platform == "twitter":
            ok = await _twitter_login(page, account_user, account_pw, log_fn)
        else:
            ok = True
        if not ok:
            log_fn(f"[APPEAL] Login failed for {account_user}")
            return False
        log_fn(f"[APPEAL] Login OK, navigating to appeal form...")

        # Navigate to the appeal form
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await _delay(T_PAGE_LOAD + 1)

        # Dismiss any cookie / popup banners
        for dismiss_sel in ['button:has-text("Accept")', 'button:has-text("Allow")',
                            'button:has-text("OK")', '[aria-label="Close"]',
                            'button:has-text("Got it")']:
            try:
                btn = page.locator(dismiss_sel)
                if await btn.count() and await btn.first.is_visible(timeout=2000):
                    await btn.first.click(timeout=3000)
                    await asyncio.sleep(0.5)
            except Exception:
                pass

        # Find and fill text fields
        field_selectors = [
            "textarea",
            'input[type="text"]',
            'div[contenteditable="true"]',
            '[role="textbox"]',
        ]
        filled = False
        for sel in field_selectors:
            fields = await page.query_selector_all(sel)
            for f in fields:
                try:
                    if await f.is_visible():
                        await f.fill(appeal_text)
                        await asyncio.sleep(1)
                        filled = True
                        log_fn(f"[APPEAL] Filled {sel} field")
                        break
                except Exception:
                    continue
            if filled:
                break
        if not filled:
            log_fn("[APPEAL] Could not find any fillable text field — trying page.evaluate")
            try:
                await page.evaluate(f"document.body.innerText = '{appeal_text[:200]}'")
            except Exception:
                pass

        # Try clicking the submit button
        submit_selectors = [
            "button[type='submit']",
            "input[type='submit']",
            "button:has-text('Send')",
            "button:has-text('Submit')",
            "button:has-text('Continue')",
            "button:has-text('Report')",
            '[role="button"]:has-text("Submit")',
            '[role="button"]:has-text("Send")',
        ]
        submitted = False
        for sel in submit_selectors:
            try:
                btns = await page.query_selector_all(sel)
                for btn in btns:
                    if await btn.is_visible():
                        await btn.click()
                        await _delay(T_POST_CLICK)
                        submitted = True
                        log_fn(f"[APPEAL] Clicked submit: {sel}")
                        break
                if submitted:
                    break
            except Exception:
                continue

        if not submitted:
            log_fn("[APPEAL] Could not find submit button — attempting Enter key")
            try:
                await page.keyboard.press("Enter")
                await asyncio.sleep(2)
                submitted = True
            except Exception:
                pass

        if submitted:
            log_fn(f"[APPEAL] Submitted to {platform} for {target}")
            return True
        log_fn("[APPEAL] Failed to submit form")
        return False
    except Exception as e:
        log_fn(f"[APPEAL] Failed: {e}")
        return False
    finally:
        if context:
            try:
                await context.close()
            except Exception:
                pass


async def _estimate_account_age(username: str, platform: str) -> str | None:
    """Estimate account creation date by scraping oldest post timestamp."""
    from instareport.browser.factory import get_shared_browser, _create_isolated_context
    from instareport.utils.constants import T_PAGE_LOAD
    context = page = None
    try:
        browser = await get_shared_browser()
        context, page = await _create_isolated_context(browser)
        urls = {
            "instagram": f"https://www.instagram.com/{username}/",
            "twitter": f"https://twitter.com/{username}",
            "tiktok": f"https://www.tiktok.com/@{username}",
            "reddit": f"https://www.reddit.com/user/{username}",
            "youtube": f"https://www.youtube.com/@{username}",
        }
        url = urls.get(platform)
        if not url:
            return None
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await _delay(T_PAGE_LOAD)
        if platform == "instagram":
            selector = "article img[alt*='photo']"
            first_img = await page.query_selector(selector)
            if first_img:
                await first_img.click()
                await asyncio.sleep(2)
                ts = await page.evaluate("""() => {
                    const el = document.querySelector('time');
                    return el ? el.getAttribute('datetime') : null;
                }""")
                if ts:
                    return ts[:10]
        elif platform == "twitter":
            ts = await page.evaluate("""() => {
                const el = document.querySelector('time');
                return el ? el.getAttribute('datetime') : null;
            }""")
            if ts:
                return ts[:10]
        elif platform == "youtube":
            ts = await page.evaluate("""() => {
                const el = document.querySelector('#date yt-formatted-string');
                return el ? el.textContent : null;
            }""")
            if ts:
                return ts.strip()
        return None
    except Exception:
        return None
    finally:
        if context:
            try:
                await context.close()
            except Exception:
                pass
