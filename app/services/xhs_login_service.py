from __future__ import annotations

from pathlib import Path
import base64
import uuid
import logging
from urllib.parse import parse_qs, urlparse
from logging.handlers import RotatingFileHandler
from datetime import datetime, timedelta, timezone
from playwright.async_api import async_playwright
from app.services.auth.cookie_store import CookieStore
from app.services.auth.session_manager import AuthState, SessionManager, utcnow


class LoginServiceError(RuntimeError):
    def __init__(self, code, message, detail="", retryable=True):
        super().__init__(message)
        self.code = code
        self.message = message
        self.detail = detail
        self.retryable = retryable

    def public(self):
        return {"code": self.code, "message": self.message, "detail": self.detail, "retryable": self.retryable}


class XiaohongshuLoginService:
    HOME_URL = "https://www.xiaohongshu.com/explore"

    def __init__(self, root: Path, key: str, cdp_url: str = "http://127.0.0.1:9223"):
        self.store = CookieStore(root / "data/cookies/xiaohongshu.json", key)
        self.cdp_url = cdp_url.rstrip("/")
        self.cdp_connected = False
        self.session = SessionManager()
        self._playwright = self._browser = self._context = self._page = None
        self.logger = logging.getLogger("memflow.xhs.login")
        if not self.logger.handlers:
            (root / "logs").mkdir(exist_ok=True)
            handler = RotatingFileHandler(root / "logs/login.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8")
            handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
            self.logger.addHandler(handler)
            self.logger.setLevel(logging.INFO)

    async def connect_chrome(self):
        self._require_key()
        playwright = None
        owned_page = None
        try:
            playwright = await async_playwright().start()
            browser = await playwright.chromium.connect_over_cdp(self.cdp_url, timeout=5000)
            if not browser.contexts:
                raise LoginServiceError("CDP_NO_CONTEXT", "Chrome 没有可用的浏览器上下文")
            context = browser.contexts[0]
            pages = [candidate for candidate in context.pages if "xiaohongshu.com" in candidate.url]
            page = pages[0] if pages else await context.new_page()
            if not pages:
                owned_page = page
                await page.goto(self.HOME_URL, wait_until="domcontentloaded", timeout=30000)
            cookies = await context.cookies("https://www.xiaohongshu.com")
            if not any(cookie.get("name") in {"web_session", "a1"} for cookie in cookies):
                raise LoginServiceError("CHROME_NOT_LOGGED_IN", "请先在当前 Chrome 中登录小红书", retryable=False)
            self._page = page
            self.session.storage_state = await context.storage_state()
            await self._read_account()
            self.session.state = AuthState.AUTHENTICATED
            self.session.login_time = self.session.login_time or utcnow()
            self.session.updated_at = utcnow()
            expires = [cookie["expires"] for cookie in cookies if cookie.get("expires", -1) > 0]
            self.session.expire_at = datetime.fromtimestamp(min(expires), timezone.utc) if expires else None
            self.cdp_connected = True
            self._save()
            self.logger.info("cdp_connected endpoint=localhost")
            return self.session.public() | {"mode": "chrome_cdp"}
        except LoginServiceError:
            raise
        except Exception as exc:
            raise LoginServiceError("CDP_UNAVAILABLE", "无法连接本机 Chrome，请确认远程调试已开启", str(exc)) from exc
        finally:
            self._page = None
            if owned_page:
                await owned_page.close()
            if playwright:
                await playwright.stop()

    def _require_key(self):
        if not self.store.configured:
            raise LoginServiceError("AUTH_KEY_MISSING", "MEMFLOW_AUTH_KEY is not configured", retryable=False)

    async def start_login(self):
        self._require_key()
        await self._close()
        self.session.state = AuthState.WAITING_SCAN
        self.session.qr_id = uuid.uuid4().hex
        self.logger.info("qr_created id=%s", self.session.qr_id[:8])
        try:
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(headless=True)
            self._context = await self._browser.new_context()
            self._page = await self._context.new_page()
            await self._page.goto(self.HOME_URL, wait_until="domcontentloaded", timeout=30000)
            await self._open_login_dialog()
            self._raise_for_risk_control()
            target = None
            for selector in (
                "img.qrcode-img",
                ".login-container img",
                "[class*=qrcode] img",
                "[class*=qrcode] canvas",
                "[class*=qr-code] img",
                "[class*=qr-code] canvas",
                "canvas",
            ):
                node = self._page.locator(selector).first
                if await node.count() and await node.is_visible():
                    target = node
                    break
            if target is None:
                for selector in ("[class*=login-container]", "[class*=login-modal]", "[class*=login]"):
                    node = self._page.locator(selector).first
                    if await node.count() and await node.is_visible():
                        target = node
                        break
            if target is None:
                raise LoginServiceError("QR_NOT_FOUND", "QR code was not found", f"page={self._page.url}")
            image = await target.screenshot()
            self.session.qr_image = "data:image/png;base64," + base64.b64encode(image).decode()
            self.session.qr_expires_at = utcnow() + timedelta(seconds=60)
            return {"qrImage": self.session.qr_image, "qrId": self.session.qr_id, "expireTime": self.session.qr_expires_at.isoformat()}
        except Exception as exc:
            if not isinstance(exc, LoginServiceError) and ("error_code=300012" in str(exc) or (self._page and "website-login/error" in self._page.url)):
                error = LoginServiceError("RISK_CONTROL", "当前网络 IP 被小红书风控，请切换正常网络后重试", self._risk_detail(), retryable=False)
            else:
                error = exc if isinstance(exc, LoginServiceError) else LoginServiceError("QR_REQUEST_FAILED", "二维码请求失败", str(exc))
            self.session.state, self.session.error = AuthState.FAILED, error.public()
            self.logger.warning("login_failed code=%s", error.code)
            await self._close()
            raise error

    def _risk_detail(self):
        if not self._page:
            return "Xiaohongshu website login rejected the current network"
        query = parse_qs(urlparse(self._page.url).query)
        return f"error_code={query.get('error_code', ['300012'])[0]}"

    def _raise_for_risk_control(self):
        if self._page and "website-login/error" in self._page.url:
            raise LoginServiceError("RISK_CONTROL", "当前网络 IP 被小红书风控，请切换正常网络后重试", self._risk_detail(), retryable=False)

    async def _open_login_dialog(self):
        candidates = (
            "button.login-btn",
            ".login-btn",
            "button:has-text('登录')",
            "div:has-text('登录')",
        )
        for selector in candidates:
            try:
                node = self._page.locator(selector).first
                if await node.count() and await node.is_visible():
                    await node.click()
                    await self._page.wait_for_timeout(1500)
                    return
            except Exception:
                continue
        try:
            node = self._page.get_by_text("登录", exact=True).first
            if await node.is_visible():
                await node.click()
                await self._page.wait_for_timeout(1500)
        except Exception:
            pass

    async def poll_login(self):
        if self.session.state in {AuthState.WAITING_SCAN, AuthState.SCANNED, AuthState.CONFIRMING} and self.session.qr_expires_at and utcnow() >= self.session.qr_expires_at:
            self.session.state = AuthState.EXPIRED
            await self._close()
        elif self.session.state in {AuthState.WAITING_SCAN, AuthState.SCANNED, AuthState.CONFIRMING} and self._context:
            cookies = await self._context.cookies()
            if any(c.get("name") in {"web_session", "a1"} for c in cookies):
                self.session.storage_state = await self._context.storage_state()
                await self._read_account()
                self.session.state = AuthState.AUTHENTICATED
                self.session.login_time = self.session.updated_at = utcnow()
                expires = [c["expires"] for c in cookies if c.get("expires", -1) > 0]
                self.session.expire_at = datetime.fromtimestamp(min(expires), timezone.utc) if expires else None
                self._save()
                self.logger.info("login_success id=%s", self.session.qr_id[:8])
                await self._close()
            elif self.session.state == AuthState.SCANNED:
                self.session.state = AuthState.CONFIRMING
            elif self.session.state == AuthState.WAITING_SCAN:
                try:
                    visible = await self._page.locator("img.qrcode-img, [class*=qrcode] img").first.is_visible()
                    if not visible: self.session.state = AuthState.SCANNED
                except Exception: pass
        return self.session.status()

    async def _read_account(self):
        for selector in (".user-name", "[class*=username]", "a[href^='/user/profile/']"):
            try:
                value = (await self._page.locator(selector).first.inner_text(timeout=1000)).strip()
                if value:
                    self.session.account["nickname"] = value
                    break
            except Exception: pass
        for selector in ("img.avatar", "[class*=avatar] img"):
            try:
                value = await self._page.locator(selector).first.get_attribute("src", timeout=1000)
                if value:
                    self.session.account["avatarUrl"] = value
                    break
            except Exception: pass

    def session_status(self):
        return self.session.public()

    def _save(self):
        self.store.save({"storageState": self.session.storage_state, "account": self.session.account, "createdAt": self.session.login_time.isoformat(), "updatedAt": self.session.updated_at.isoformat(), "expireAt": self.session.expire_at.isoformat() if self.session.expire_at else None})

    async def restore(self):
        if not self.store.configured or not self.store.path.exists():
            return
        self.session.state = AuthState.CHECKING
        try:
            data = self.store.load()
            self.session.storage_state = data["storageState"]
            self.session.account = data.get("account", self.session.account)
            self.session.login_time = datetime.fromisoformat(data["createdAt"])
            await self.refresh()
        except Exception as exc:
            self.session.state = AuthState.REAUTH_REQUIRED
            self.session.error = LoginServiceError("RESTORE_FAILED", "Saved session could not be restored", str(exc)).public()

    async def refresh(self):
        self._require_key()
        if self.cdp_connected:
            return await self.connect_chrome()
        if not self.session.storage_state:
            raise LoginServiceError("NOT_AUTHENTICATED", "QR login is required")
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            context = await browser.new_context(storage_state=self.session.storage_state)
            page = await context.new_page()
            await page.goto(self.HOME_URL, wait_until="domcontentloaded", timeout=30000)
            if "login" in page.url.lower():
                await browser.close()
                self.session.state = AuthState.REAUTH_REQUIRED
                raise LoginServiceError("SESSION_EXPIRED", "Session expired")
            self.session.storage_state = await context.storage_state()
            self.session.updated_at = utcnow()
            self.session.state = AuthState.AUTHENTICATED
            self._save()
            await browser.close()
        return self.session.public()

    async def logout(self):
        await self._close()
        self.store.delete()
        self.session = SessionManager()
        self.cdp_connected = False
        self.logger.info("logout")

    async def _close(self):
        for obj in (self._context, self._browser):
            if obj:
                try: await obj.close()
                except Exception: pass
        if self._playwright:
            try: await self._playwright.stop()
            except Exception: pass
        self._playwright = self._browser = self._context = self._page = None
