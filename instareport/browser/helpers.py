"""Browser interaction helpers — human-like typing, clicking, CAPTCHA, login, cookie management."""
import asyncio, random, time, re, json
from datetime import datetime
from typing import Callable, Any

from instareport.utils.constants import (
    T_PAGE_LOAD, T_POST_CLICK, T_POST_LOGIN, T_CAPTCHA_WAIT,
    T_TELEGRAM_OTP, T_REFRESH_WAIT, T_TYPE_DELAY, T_COOKIE_SETTLE, T_URL_POLL,
    T_CAPTCHA_POLL, REASON_XPATHS, _REASON_TEXT_MAP, SESSIONS_DIR, DEBUG,
)
from instareport.utils.helpers import _req
from instareport.utils.logging import dlog, flog
from instareport.core.state import S, GLOBAL_STOP
from instareport.core.selectors import get_selectors as S_sel, _LOGIN_CHECK_XPATHS
from instareport.core.otp import OTP
from instareport.tools.proxy import PP

try:
    from playwright.async_api import TimeoutError as PWTimeout
except ImportError:
    PWTimeout = type("PWTimeout", (Exception,), {})


async def _delay(seconds: float, jitter: float = 0.3) -> None:
    if seconds <= 0:
        return
    actual = seconds * random.uniform(1 - jitter, 1 + jitter)
    await asyncio.sleep(actual)


async def _check_account_health(page: Any, username: str, platform: str = "instagram") -> bool:
    try:
        if platform == "instagram":
            await page.goto("https://www.instagram.com/accounts/edit/", wait_until="domcontentloaded", timeout=15000)
            await page.wait_for_timeout(2000)
            for xp in _LOGIN_CHECK_XPATHS:
                if await page.locator(f"xpath={xp}").count() > 0:
                    dlog(f"[HEALTH] {username} logged in OK")
                    return True
            dlog(f"[HEALTH] {username} not logged in")
            return False
        else:
            await page.goto("https://www.instagram.com/", wait_until="domcontentloaded", timeout=15000)
            await page.wait_for_timeout(2000)
            for xp in _LOGIN_CHECK_XPATHS:
                if await page.locator(f"xpath={xp}").count() > 0:
                    return True
            return False
    except Exception as e:
        dlog(f"[HEALTH] {username} check failed: {e}")
        return False


async def human_type(page: Any, selector: str, text: str, timeout: int = 15000) -> None:
    await page.wait_for_selector(selector, timeout=timeout)
    await page.focus(selector)
    for char in text:
        await page.keyboard.type(char, delay=random.uniform(50, 180))
        await asyncio.sleep(random.uniform(0.01, 0.09))


async def human_click(page: Any, selector: str, timeout: int = 15000) -> bool:
    try:
        loc = page.locator(selector).first
        box = await loc.bounding_box(timeout=timeout)
        if not box:
            return False
        x = box['x'] + box['width'] * random.uniform(0.3, 0.7)
        y = box['y'] + box['height'] * random.uniform(0.3, 0.7)
        await page.mouse.move(x, y, steps=random.randint(10, 18))
        await asyncio.sleep(random.uniform(0.15, 0.5))
        await page.mouse.click(x, y)
        return True
    except Exception as _e:
        dlog(f"human_click: {_e}")
        return False


async def _click(page: Any, xps: list[str], t: int = 10) -> bool:
    timeout_ms = t * 1000
    for xp in xps:
        try:
            loc = page.locator(f"xpath={xp}").first
            await loc.wait_for(state="visible", timeout=timeout_ms)
            if S.safe_mode:
                box = await loc.bounding_box()
                if box:
                    await page.mouse.move(
                        box["x"] + box["width"]/2 + random.uniform(-2, 2),
                        box["y"] + box["height"]/2 + random.uniform(-2, 2),
                        steps=random.randint(5, 15))
            await loc.click(timeout=timeout_ms, delay=random.uniform(50, 150) if S.safe_mode else 0)
            return True
        except Exception:
            continue
    return False


async def _type(page: Any, xps: list[str], txt: str, t: int = 10) -> bool:
    timeout_ms = t * 1000
    for xp in xps:
        try:
            loc = page.locator(f"xpath={xp}").first
            await loc.wait_for(state="visible", timeout=timeout_ms)
            await loc.fill("")
            if S.safe_mode:
                await loc.focus()
                for char in txt:
                    await page.keyboard.type(char, delay=random.uniform(50, 150))
                    await asyncio.sleep(random.uniform(0.01, 0.04))
            else:
                await loc.fill(txt)
            return True
        except Exception:
            continue
    return False


async def _wait_url(page: Any, bad: list[str], t: int = 60) -> bool:
    s = time.time()
    while time.time() - s < t:
        if not any(f in page.url for f in bad):
            return True
        await asyncio.sleep(T_URL_POLL)
    return False


async def _dismiss(page: Any) -> None:
    for xp in ["//button[contains(text(),'Accept')]", "//button[contains(text(),'Allow')]",
               "//button[contains(text(),'Not now')]", "//button[@aria-label='Close']"]:
        try:
            loc = page.locator(f"xpath={xp}")
            cnt = await loc.count()
            for i in range(cnt):
                el = loc.nth(i)
                if await el.is_visible():
                    await el.click()
                    await asyncio.sleep(0.3)
        except Exception:
            pass


async def _human_delay() -> None:
    if S.safe_mode:
        await asyncio.sleep(random.uniform(1.5, 4.0))


def _stopped() -> bool:
    return S.stop_event.is_set() or GLOBAL_STOP.is_set()


async def _captcha_api_solve(task_type: str, params: dict, log_fn: Callable) -> str | None:
    key = S.captcha_key
    svc = S.captcha_svc
    if svc == "manual" or not key:
        return None
    ep = "https://api.anti-captcha.com" if svc == "anticaptcha" \
          else ("https://api.capmonster.cloud" if svc == "capmonster" else "https://2captcha.com")
    log_fn(f"  [CAP] Submitting {task_type} to {svc}...")
    try:
        loop = asyncio.get_running_loop()
        if svc == "capmonster":
            r = await loop.run_in_executor(None, lambda: _req('post', f"{ep}/createTask",
                json={"clientKey": key, "task": {"type": task_type, **params}}))
            tid = r.json().get("taskId")
            if not tid:
                log_fn(f"  [CAP] createTask failed: {r.text[:80]}")
                return None

            async def _poll() -> str | None:
                for _ in range(40):
                    await asyncio.sleep(T_CAPTCHA_POLL)
                    res = await loop.run_in_executor(None, lambda: _req('post', f"{ep}/getTaskResult",
                        json={"clientKey": key, "taskId": tid}, timeout=15).json())
                    if res.get("status") == "ready":
                        sol = res.get("solution", {})
                        token = sol.get("gRecaptchaResponse") or sol.get("token") or sol.get("text")
                        log_fn("  [CAP] Solved via CapMonster")
                        return token
                return None

            try:
                result = await asyncio.wait_for(_poll(), timeout=120)
                if result:
                    return result
            except asyncio.TimeoutError:
                log_fn("  [CAP] Polling timed out (120s)")
        else:
            method_map = {
                "RecaptchaV2TaskProxyless": "userrecaptcha",
                "FunCaptchaTaskProxyless": "funcaptcha",
                "HCaptchaTaskProxyless": "hcaptcha",
                "ImageToTextTask": "base64",
            }
            method = method_map.get(task_type, "userrecaptcha")
            r = await loop.run_in_executor(None, lambda: _req('post', f"{ep}/in.php",
                data={"key": key, "method": method, "json": 1, **params}).json())
            if r.get("status") != 1:
                log_fn(f"  [CAP] Submit failed: {r}")
                return None
            rid = r["request"]

            async def _poll2() -> str | None:
                for _ in range(40):
                    await asyncio.sleep(T_CAPTCHA_POLL)
                    res = await loop.run_in_executor(None, lambda: _req('get', f"{ep}/res.php",
                        params={"key": key, "action": "get", "id": rid, "json": 1}, timeout=15).json())
                    if res.get("status") == 1:
                        log_fn("  [CAP] Solved via 2captcha")
                        return res["request"]
                return None

            try:
                result = await asyncio.wait_for(_poll2(), timeout=120)
                if result:
                    return result
            except asyncio.TimeoutError:
                log_fn("  [CAP] 2captcha polling timed out (120s)")
    except Exception as e:
        log_fn(f"  [CAP] API error: {e}")
    log_fn("  [CAP] Timeout")
    return None


async def _inject_recaptcha(page: Any, token: str) -> None:
    await page.evaluate(
        "(token) => { try{document.getElementById('g-recaptcha-response').innerHTML=token;}catch(e){} }",
        token)
    await asyncio.sleep(1)


async def _detect_captcha_type(page: Any) -> str | None:
    try:
        src = await page.content()
    except Exception:
        return None
    if any(x in src for x in ["funcaptcha", "arkoselabs", "fc-iframe-wrap", "FunCaptchaIframe"]):
        return "arkose"
    try:
        if await page.locator("xpath=//iframe[contains(@src,'recaptcha') or contains(@src,'google.com/recaptcha')]").count() > 0:
            return "recaptcha"
        if await page.locator("xpath=//*[@data-sitekey]").count() > 0:
            return "recaptcha"
    except Exception:
        pass
    if "hcaptcha" in src:
        return "hcaptcha"
    try:
        if await page.locator("xpath=//img[contains(@src,'captcha') or contains(@alt,'captcha')]").count() > 0:
            return "image"
    except Exception:
        pass
    return None


async def _extract_sitekey(page: Any, cap_type: str) -> str | None:
    try:
        if cap_type in ("recaptcha", "hcaptcha"):
            el = page.locator("xpath=//*[@data-sitekey]").first
            return await el.get_attribute("data-sitekey")
        if cap_type == "arkose":
            m = re.search(r'pk["\']?\s*:\s*["\']([0-9A-F\-]{36})',
                          await page.content(), re.IGNORECASE)
            if m:
                return m.group(1)
    except Exception:
        pass
    return None


async def handle_captcha(page: Any, log_fn: Callable, label: str = "") -> bool:
    cap_type = await _detect_captcha_type(page)
    if not cap_type:
        return False
    log_fn(f"  [CAP] Detected {cap_type} on {page.url[:50]}")
    page_url = page.url
    sitekey = await _extract_sitekey(page, cap_type)
    token = None
    if S.captcha_key and S.captcha_svc != "manual":
        if cap_type == "recaptcha" and sitekey:
            token = await _captcha_api_solve("RecaptchaV2TaskProxyless",
                {"websiteURL": page_url, "websiteKey": sitekey}, log_fn)
            if token:
                await _inject_recaptcha(page, token)
                return True
        elif cap_type == "arkose" and sitekey:
            token = await _captcha_api_solve("FunCaptchaTaskProxyless",
                {"websiteURL": page_url, "websitePublicKey": sitekey}, log_fn)
            if token:
                await page.evaluate(
                    "(token) => { try{var i=document.querySelector('input[name=\"fc-token\"]');if(i)i.value=token;}catch(e){} }",
                    token)
                await asyncio.sleep(1)
                return True
        elif cap_type == "hcaptcha" and sitekey:
            token = await _captcha_api_solve("HCaptchaTaskProxyless",
                {"websiteURL": page_url, "websiteKey": sitekey}, log_fn)
            if token:
                await page.evaluate(
                    "(token) => { try{document.querySelector('textarea[name=\"h-captcha-response\"]').value=token;}catch(e){} }",
                    token)
                await asyncio.sleep(1)
                return True
    log_fn("  [CAP] No API key or solve failed — pausing 25s for manual solve")
    if S.captcha_cb:
        key = f"cap:{label}:{time.time()}"
        result = S.captcha_cb(key, cap_type, page_url)
        if asyncio.iscoroutine(result):
            await result
    await asyncio.sleep(T_CAPTCHA_WAIT)
    return True


async def _detect_2fa(page: Any) -> bool:
    for xp in ["//input[@placeholder='Security code']", "//input[contains(@aria-label,'code')]",
               "//h1[contains(text(),'Two-factor')]", "//span[contains(text(),'verification code')]"]:
        try:
            loc = page.locator(f"xpath={xp}")
            if await loc.count() > 0 and await loc.first.is_visible():
                return True
        except Exception:
            pass
    return False


async def _handle_2fa(page: Any, user: str, plat: str, log_fn: Callable) -> None:
    if not await _detect_2fa(page):
        return
    log_fn(f"  [2FA] Challenge for {user}")
    key = f"{plat}:{user}:{time.time()}"
    code = await OTP.request_async(key, lambda k: S.otp_cb and S.otp_cb(k, plat, user))
    if code:
        await _type(page, ["//input[@placeholder='Security code']", "//input[contains(@aria-label,'code')]",
                           "//input[@type='number']", "//input[@inputmode='numeric']"], code)
        await asyncio.sleep(1)
        await _click(page, ["//button[contains(.,'Confirm')]", "//button[@type='submit']",
                            "//button[contains(.,'Verify')]"])
        await asyncio.sleep(T_PAGE_LOAD)


async def _screenshot(page_or_driver: Any, label: str) -> str | None:
    try:
        S.screenshot_dir.mkdir(exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe = "".join(c for c in label if c.isalnum() or c in "-_")[:40]
        path = str(S.screenshot_dir / f"{ts}_{safe}.png")
        await page_or_driver.screenshot(path=path)
        return path
    except Exception:
        return None


async def _ig_logo_stall(page: Any) -> bool:
    try:
        if await _ig_login_form_ready(page):
            return False
        body_text = ""
        try:
            body_text = (await page.locator("body").inner_text(timeout=2500)).strip()
        except Exception:
            pass
        html = ""
        try:
            html = await page.content()
        except Exception:
            pass
        if not html:
            try:
                url = page.url
                if url.startswith("about:") or url.startswith("chrome-error"):
                    return True
            except Exception:
                pass
            return len(body_text) < 4
        _l = body_text.lower()
        if any(w in _l for w in ["username", "password", "log in", "phone number"]):
            return False
        if any(w in _l for w in ["something went wrong", "couldn't load", "try again", "sorry", "blocked",
                                  "we've detected", "suspicious", "unusual activity", "verify it's you",
                                  "page not found", "webdriver"]):
            return True
        for sel in ["img[alt='Instagram']", "svg[aria-label='Instagram']", "svg[role='img']"]:
            try:
                loc = page.locator(sel)
                if await loc.count() > 0 and await loc.first.is_visible():
                    return True
            except Exception:
                pass
        return "Instagram" in html and "username" not in html and "password" not in html and len(body_text) < 4
    except Exception as _e:
        dlog(f"ig logo stall detect: {_e}")
        return False


async def _ig_login_form_ready(page: Any) -> bool:
    selectors = ["input[name='username']", "input[name='password']", "button[type='submit']"]
    for sel in selectors:
        try:
            loc = page.locator(sel)
            if await loc.count() > 0 and await loc.first.is_visible():
                return True
        except Exception:
            pass
    return False


async def _ig_prepare_login_page(page: Any, log_fn: Callable, user: str) -> bool:
    recovery_xps = [
        "//button[contains(.,'Continue in browser')]",
        "//a[contains(.,'Continue in browser')]",
        "//button[contains(.,'Continue using data')]",
        "//button[contains(.,'Use website')]",
        "//a[contains(.,'Use website')]",
        "//button[contains(.,'Allow all cookies')]",
        "//button[contains(.,'Only allow essential cookies')]",
        "//button[contains(.,'Not now')]",
        "//a[contains(.,'Log in')]",
        "//button[contains(.,'Log in')]",
    ]
    for step in range(2):
        try:
            await page.wait_for_load_state("domcontentloaded", timeout=5000)
        except Exception:
            pass
        await _dismiss(page)
        try:
            await page.locator("input[name='username'], input[name='password']").first.wait_for(
                state="visible", timeout=8000)
        except Exception:
            pass
        if await _ig_login_form_ready(page):
            if step > 0:
                log_fn("  [IG] Recovered login form from splash/interstitial")
            return True
        try:
            if await _click(page, recovery_xps, t=3):
                dlog(f"ig login recovery click step={step+1} user={user} url={page.url}")
                await asyncio.sleep(T_POST_CLICK)
                await _dismiss(page)
                if await _ig_login_form_ready(page):
                    log_fn("  [IG] Recovered login form from splash/interstitial")
                    return True
        except Exception:
            pass
        if step < 3:
            try:
                await page.wait_for_load_state("networkidle", timeout=4000)
            except Exception:
                pass
            try:
                await page.reload(wait_until="domcontentloaded", timeout=30000)
            except Exception:
                pass
            await asyncio.sleep(2 + step)
    dlog(f"ig login form unavailable for {user}: url={page.url}")
    return False


async def _import_chrome_cookies(user: str, plat: str) -> bool:
    """Launch a throwaway Chrome with a real user data dir, export cookies, then close."""
    data_dir = getattr(S, "chrome_user_data_dir", "")
    if not data_dir or not os.path.isdir(data_dir):
        return False
    import tempfile, zipfile
    from playwright.async_api import async_playwright as _async_pw
    dlog(f"Importing {plat} cookies from Chrome profile: {data_dir}")
    try:
        pw = await _async_pw().start()
        browser = await pw.chromium.launch(
            channel="chrome",
            headless=False,
            args=[
                f"--user-data-dir={data_dir}",
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
            ],
        )
        page = await browser.new_page()
        await page.goto(f"https://www.{plat}.com/", wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(3)
        cookies = await page.context.cookies()
        safe = "".join(c for c in user if c.isalnum() or c in "-_.")
        p = SESSIONS_DIR / f"{safe}_{plat}.json"
        storage_state = None
        try:
            storage_state = await page.context.storage_state()
        except Exception:
            pass
        with open(p, "w", encoding="utf-8") as f:
            json.dump({
                "cookies": cookies,
                "storage_state": storage_state,
                "ts": datetime.now().isoformat(),
                "version": 2,
                "imported_from_chrome": True,
            }, f)
        await browser.close()
        await pw.stop()
        dlog(f"Imported {len(cookies)} cookies for {user}@{plat}")
        return True
    except Exception as _e:
        dlog(f"Chrome cookie import failed: {_e}")
        try:
            await browser.close()
        except Exception:
            pass
        try:
            await pw.stop()
        except Exception:
            pass
        return False


async def _clear_site_state(page: Any, origin_url: str = "https://www.instagram.com/") -> None:
    try:
        if not str(page.url).startswith(origin_url):
            await page.goto(origin_url, wait_until="domcontentloaded", timeout=25000)
            await asyncio.sleep(1)
    except Exception:
        pass
    try:
        await page.context.clear_cookies()
    except Exception:
        pass
    try:
        await page.evaluate("""async () => {
            try { localStorage.clear(); } catch (e) {}
            try { sessionStorage.clear(); } catch (e) {}
            try {
                if ('caches' in window) {
                    const keys = await caches.keys();
                    await Promise.all(keys.map((k) => caches.delete(k)));
                }
            } catch (e) {}
            try {
                if ('serviceWorker' in navigator) {
                    const regs = await navigator.serviceWorker.getRegistrations();
                    await Promise.all(regs.map((r) => r.unregister()));
                }
            } catch (e) {}
        }""")
    except Exception:
        pass


async def _detect_checkpoint(page: Any, log_fn: Callable, plat: str = "instagram") -> bool:
    url = page.url.lower()
    checkpoint_patterns = [
        "challenge", "checkpoint", "/accounts/suspended",
        "/accounts/onetap", "login/two_factor",
        "suspicious-login", "identity_confirm",
    ]
    if any(p in url for p in checkpoint_patterns):
        log_fn(f"  [CHECKPOINT] Detected checkpoint at {page.url[:80]}")
        path = await _screenshot(page, f"checkpoint_{plat}")
        if path:
            log_fn(f"  [SHOT] {path}")
        await handle_captcha(page, log_fn, f"checkpoint_{plat}")
        confirm_xpaths = [
            "//button[contains(text(),'This Was Me')]",
            "//button[contains(text(),'This was me')]",
            "//button[contains(text(),'It Was Me')]",
            "//button[contains(.,'Confirm')]",
            "//button[contains(.,'Continue')]",
            "//button[contains(.,'Dismiss')]",
            "//a[contains(text(),'This Was Me')]",
        ]
        clicked = await _click(page, confirm_xpaths, t=5)
        if clicked:
            log_fn("  [CHECKPOINT] Clicked confirmation button")
            await asyncio.sleep(T_POST_CLICK)
            return True
        verify_xpaths = [
            "//input[contains(@placeholder,'code')]",
            "//input[contains(@aria-label,'Security')]",
            "//input[@name='security_code']",
        ]
        for xp in verify_xpaths:
            try:
                if await page.locator(f"xpath={xp}").count() > 0:
                    log_fn("  [CHECKPOINT] Security code required — requesting OTP")
                    key = f"{plat}_checkpoint:{time.time()}"
                    code_val = await OTP.request_async(key, lambda k: S.otp_cb and S.otp_cb(k, plat, "checkpoint"))
                    if code_val:
                        await _type(page, [xp], code_val)
                        await asyncio.sleep(T_TYPE_DELAY)
                        await _click(page, ["//button[@type='submit']", "//button[contains(.,'Submit')]",
                                            "//button[contains(.,'Confirm')]"])
                        await asyncio.sleep(T_POST_CLICK)
                    return True
            except Exception:
                pass
        log_fn("  [CHECKPOINT] Could not auto-resolve — manual intervention may be needed")
        await asyncio.sleep(T_CAPTCHA_WAIT)
        return True
    return False


async def _save_cookies(page: Any, user: str, plat: str) -> None:
    try:
        context = page.context
        cookies = await context.cookies()
        safe = "".join(c for c in user if c.isalnum() or c in "-_.")
        p = SESSIONS_DIR / f"{safe}_{plat}.json"
        storage_state = None
        try:
            storage_state = await context.storage_state()
        except Exception:
            pass
        with open(p, "w", encoding="utf-8") as f:
            json.dump({
                "cookies": cookies,
                "storage_state": storage_state,
                "ts": datetime.now().isoformat(),
                "version": 2,
            }, f)
    except Exception as _e:
        dlog(f"_save_cookies: {_e}")


async def _load_cookies(page: Any, user: str, plat: str, base_url: str) -> bool:
    safe = "".join(c for c in user if c.isalnum() or c in "-_.")
    p = SESSIONS_DIR / f"{safe}_{plat}.json"
    if not p.exists():
        return False
    try:
        with open(p, encoding="utf-8") as f:
            raw = f.read()
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            dlog(f"corrupt cookie file for {user}@{plat}, removing")
            p.unlink()
            return False
        if not isinstance(data, dict):
            dlog(f"invalid cookie format for {user}@{plat}")
            p.unlink()
            return False
        cookies = data.get("cookies", [])
        if not cookies:
            p.unlink()
            return False
        try:
            ts = datetime.fromisoformat(data.get("ts", "2000-01-01"))
            if (datetime.now() - ts).days > 7:
                dlog(f"Session expired for {user}@{plat}")
                p.unlink()
                return False
        except Exception:
            pass
        context = page.context
        await page.goto(base_url, timeout=30000)
        await asyncio.sleep(T_COOKIE_SETTLE)
        storage_state = data.get("storage_state")
        if storage_state and data.get("version", 1) >= 2:
            try:
                for origin in storage_state.get("origins", []):
                    for item in origin.get("localStorage", []):
                        try:
                            await page.evaluate(
                                "(args) => { try { localStorage.setItem(args.name, args.value); } catch(e) {} }",
                                {"name": item.get("name", ""), "value": item.get("value", "")}
                            )
                        except Exception:
                            pass
            except Exception:
                pass
        pw_cookies = []
        now = time.time()
        for c in cookies:
            pc = {
                "name": c.get("name", ""),
                "value": c.get("value", ""),
                "domain": c.get("domain", ""),
                "path": c.get("path", "/"),
            }
            if c.get("expires"):
                try:
                    exp = float(c["expires"])
                    if exp > 0 and exp < now:
                        continue
                    pc["expires"] = exp
                except (ValueError, TypeError):
                    pass
            if c.get("httpOnly"):
                pc["httpOnly"] = True
            if c.get("secure"):
                pc["secure"] = True
            if c.get("sameSite"):
                ss = c["sameSite"]
                if ss in ("Strict", "Lax", "None"):
                    pc["sameSite"] = ss
            pw_cookies.append(pc)
        try:
            await context.add_cookies(pw_cookies)
        except Exception:
            pass
        await page.reload(timeout=30000)
        await asyncio.sleep(T_REFRESH_WAIT)
        check_xpaths = _LOGIN_CHECK_XPATHS.get(plat, [])
        if not check_xpaths:
            return True
        for xp in check_xpaths:
            try:
                loc = page.locator(f"xpath={xp}")
                if await loc.count() > 0 and await loc.first.is_visible():
                    return True
            except Exception:
                pass
        p.unlink()
        return False
    except Exception as _e:
        dlog(f"cookie load error (keeping file): {_e}")
        return False


async def _warmup_sequence(page: Any, log_fn: Callable, label: str = "") -> None:
    if not (S.safe_mode or S.stealth) or not S.warmup_enabled:
        return
    log_fn(f"  [WARMUP] Running warmup sequence{(' for ' + label) if label else ''}…")
    try:
        vp = page.viewport_size or {"width": 1280, "height": 720}
        for _ in range(random.randint(2, 4)):
            scroll_y = random.randint(100, 600)
            await page.evaluate(f"window.scrollBy(0, {scroll_y})")
            await asyncio.sleep(random.uniform(0.8, 2.5))
        await page.evaluate(f"window.scrollBy(0, -{random.randint(50, 300)})")
        await asyncio.sleep(random.uniform(0.5, 1.5))
        for _ in range(random.randint(3, 5)):
            x = random.randint(50, vp["width"] - 50)
            y = random.randint(50, vp["height"] - 50)
            await page.mouse.move(x, y, steps=random.randint(8, 20))
            await asyncio.sleep(random.uniform(0.3, 1.0))
        try:
            links = page.locator("a")
            count = await links.count()
            if count > 0:
                idx = random.randint(0, min(count - 1, 5))
                await links.nth(idx).hover(timeout=3000)
                await asyncio.sleep(random.uniform(0.5, 1.5))
        except Exception:
            pass
        await asyncio.sleep(random.uniform(1.0, 3.0))
        log_fn("  [WARMUP] Complete")
    except Exception as e:
        dlog(f"warmup: {e}")


async def _click_reason(page: Any, r: str) -> bool:
    if await _click(page, REASON_XPATHS.get(r, []), t=5):
        return True
    reason_text = _REASON_TEXT_MAP.get(r)
    if reason_text:
        try:
            if await human_click(page, f'text={reason_text}', timeout=8000):
                return True
        except Exception:
            pass
    if r != "spam":
        dlog(f"Preferred reason '{r}' not found, falling back to spam")
        if await _click(page, REASON_XPATHS.get("spam", []), t=5):
            return True
        try:
            return await human_click(page, "text=It's spam", timeout=5000)
        except Exception:
            pass
    return False


async def _verify_report_success(page: Any, tag: str, target: str, reason: str,
                                 log_fn: Callable, extra_selectors: list[str] | None = None,
                                 extra_keywords: list[str] | None = None) -> bool:
    success = False
    selectors = [
        'text=Thanks for reporting', 'text=Your report has been submitted',
        "text=We'll review your report", '[role="alert"]',
        'div[role="dialog"] >> text=reported', 'text=Thank you',
        'text=Thanks', 'text=submitted', 'text=received', 'text=reported',
    ]
    if extra_selectors:
        selectors.extend(extra_selectors)
    for sel in selectors:
        try:
            if await page.locator(sel).first.is_visible(timeout=4000):
                success = True
                break
        except Exception:
            pass
    if not success:
        keywords = ["thank", "report", "review", "submitted", "received", "success"]
        if extra_keywords:
            keywords.extend(extra_keywords)
        try:
            src = (await page.content()).lower()
            if any(kw in src for kw in keywords):
                success = True
        except Exception:
            pass
    if success:
        log_fn(f"  [{tag}] ✓ Confirmed report @{target} ({reason})")
        return True
    log_fn(f"  [{tag}] ⚠ Reported @{target} ({reason}) — unconfirmed")
    return False
