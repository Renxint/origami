# -*- coding: utf-8 -*-
"""
Origami v2 — Playwright 签名引擎

替代 Node.js sign-server/（server.js + bootstrap.js）。
纯 Python，零 Node 依赖，自动发现系统浏览器。

架构:
    BrowserFinder     — 六层浏览器发现
    SignServer        — 常驻浏览器服务 (server.js 等价)
    one_shot_fetch()  — 一次性调用 (bootstrap.js 等价)
"""

import os
import re
import json
import time
import shutil
import base64
import threading
from pathlib import Path
from typing import Optional

from playwright.sync_api import sync_playwright, Browser, Page
import playwright_stealth

from src.environ import (
    BASE_DIR, EXE_DIR, COOKIE_FILE, CREATE_NO_WINDOW,
    USER_AGENT, CHROME_PATH,
)

# ── 设备指纹（与 v0.6.5 完全相同） ──
FINGERPRINTS = {
    "webid": "7385142668127356466",
    "verifyFp": "verify_moblf7od_dhWzqJO5_JDbN_44xu_86lf_8A6KqJjdqijD",
    "fp": "verify_moblf7od_dhWzqJO5_JDbN_44xu_86lf_8A6KqJjdqijD",
    "uifid": "7db62a7064f9afdec5c11ec3d692d7372ef41f2765cba0856d9e1b7b4940be6ed1b35a0f14230c327616b958a98d663b4443e89c625dc584c6b48e03ecc9c0ad",
}

# ── 抖音 API 参数模板 ──
API_PARAMS = {
    "device_platform": "webapp",
    "aid": "6383",
    "channel": "channel_pc_web",
    "pc_client_type": "1",
    "version_code": "290100",
    "version_name": "29.1.0",
    "cookie_enabled": "true",
    "screen_width": "2560",
    "screen_height": "1440",
    "browser_language": "zh-CN",
    "browser_platform": "Win32",
    "browser_name": "Smart+Lenovo+Browser",
    "browser_version": "9.0.8.5161",
    "browser_online": "true",
    "engine_name": "Blink",
    "engine_version": "141.0.0.0",
    "os_name": "Windows",
    "os_version": "10",
    "cpu_core_num": "32",
    "device_memory": "8",
    "platform": "PC",
    "downlink": "10",
    "effective_type": "4g",
    "round_trip_time": "50",
}

# ── 日志 ──
def _debug_log(msg: str):
    try:
        ts = time.strftime("%H:%M:%S")
        with open(EXE_DIR / "_sign_debug.log", "a", encoding="utf-8") as f:
            f.write(f"[{ts}] {msg}\n")
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════
# BrowserFinder — 六层浏览器发现
# ═══════════════════════════════════════════════════════════

class BrowserFinder:
    """自动发现系统可用的 Chromium 内核浏览器"""

    CANDIDATE_NAMES = ["chrome", "msedge", "chromium", "brave", "opera"]

    @classmethod
    def find(cls) -> Optional[str]:
        # 缓存
        if CHROME_PATH and os.path.exists(CHROME_PATH):
            return CHROME_PATH

        path = (
            cls._search_path()
            or cls._search_registry()
            or cls._search_common_paths()
            or cls._search_puppeteer_cache()
        )
        if path:
            _debug_log(f"BrowserFinder: {path}")
        else:
            _debug_log("BrowserFinder: NOT FOUND")
        return path

    @classmethod
    def _search_path(cls) -> Optional[str]:
        for name in cls.CANDIDATE_NAMES:
            exe = shutil.which(name)
            if exe and os.path.exists(exe):
                return exe
        return None

    @classmethod
    def _search_registry(cls) -> Optional[str]:
        import winreg
        keys = [
            (winreg.HKEY_LOCAL_MACHINE,
             r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe"),
            (winreg.HKEY_LOCAL_MACHINE,
             r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe"),
            (winreg.HKEY_CURRENT_USER,
             r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe"),
        ]
        for hive, key_path in keys:
            try:
                with winreg.OpenKey(hive, key_path) as key:
                    exe = winreg.QueryValue(key, None)
                    if exe and os.path.exists(exe.strip()):
                        return exe.strip()
            except OSError:
                pass
        return None

    @classmethod
    def _search_common_paths(cls) -> Optional[str]:
        local = os.environ.get("LOCALAPPDATA", "")
        candidates = [
            f"{local}\\Google\\Chrome\\Application\\chrome.exe",
            "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
            "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",
            "C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe",
            "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
            f"{local}\\Microsoft\\Edge\\Application\\msedge.exe",
            "C:\\Program Files\\BraveSoftware\\Brave-Browser\\Application\\brave.exe",
            f"{local}\\BraveSoftware\\Brave-Browser\\Application\\brave.exe",
            "C:\\Program Files\\Chromium\\Application\\chrome.exe",
            f"{local}\\Chromium\\Application\\chrome.exe",
            f"{local}\\Vivaldi\\Application\\vivaldi.exe",
            "C:\\Program Files\\Opera\\opera.exe",
            f"{local}\\Programs\\Opera\\opera.exe",
        ]
        for p in candidates:
            if os.path.exists(p):
                return p
        return None

    @classmethod
    def _search_puppeteer_cache(cls) -> Optional[str]:
        cache_dir = Path(os.environ.get("LOCALAPPDATA", "")) / "puppeteer"
        if cache_dir.exists():
            for d in cache_dir.iterdir():
                chrome = d / "chrome-win64" / "chrome.exe"
                if chrome.exists():
                    return str(chrome)
        return None


# ═══════════════════════════════════════════════════════════
# Cookie 加载（与 v0.6.5 相同逻辑）
# ═══════════════════════════════════════════════════════════

def _load_cookie_raw() -> str:
    if not COOKIE_FILE.exists():
        return ""
    raw = COOKIE_FILE.read_text(encoding="utf-8").strip()
    try:
        return base64.b64decode(raw.encode("ascii")).decode("utf-8")
    except Exception:
        return raw


def _cookie_to_list(cookie_str: str) -> list[dict]:
    """将 Cookie 字符串转为 playwright 格式"""
    result = []
    for part in cookie_str.split(";"):
        part = part.strip()
        if "=" not in part:
            continue
        name, value = part.split("=", 1)
        name, value = name.strip(), value.strip()
        if name:
            result.append({
                "name": name,
                "value": value,
                "domain": ".douyin.com",
                "path": "/",
            })
    return result


# ═══════════════════════════════════════════════════════════
# StealthBrowser — 浏览器实例 + 抖音 SDK
# ═══════════════════════════════════════════════════════════

class StealthBrowser:
    """管理一个带 stealth 的 Chromium 浏览器实例，初始化抖音 bdms SDK"""

    def __init__(self, browser_path: str, headless: bool = True):
        self._browser_path = browser_path
        self._headless = headless
        self._playwright = None
        self._browser: Optional[Browser] = None
        self._page: Optional[Page] = None
        self._sdk_ready = False

    def start(self, cookie_str: str = "", timeout_ms: int = 60000):
        """启动浏览器 → 导航抖音 → 初始化 bdms SDK → 注入 Cookie + 指纹"""
        _debug_log(f"StealthBrowser.start: {self._browser_path}")

        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(
            executable_path=self._browser_path,
            headless=self._headless,
            args=[
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-gpu",
            ],
        )

        context = self._browser.new_context(
            user_agent=USER_AGENT,
            viewport={"width": 1920, "height": 1080},
        )
        self._page = context.new_page()

        # Stealth evasions
        playwright_stealth.inject(self._page)
        self._page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => false });
            window.chrome = { runtime: {} };
        """)

        # —— Step 1: 首次导航，初始化 SDK（不带 Cookie）——
        # （对齐 bootstrap.js：必须先做一次不带 Cookie 的 init）
        _debug_log("Step 1: first nav + SDK init (no cookie)")
        self._page.goto("https://www.douyin.com/?recommend=1",
                        wait_until="domcontentloaded", timeout=timeout_ms)
        self._page.wait_for_function(
            "window.bdms && window.bdms.init", timeout=30000)
        self._page.evaluate("""
            window.bdms.init({
                aid: 6383, pageId: 6241, boe: false, ddrt: 8.5, ic: 8.5
            });
        """)
        _debug_log("Step 1: SDK init OK")

        # —— Step 2: 重新导航 → 注入 Cookie → 重新初始化 SDK ——
        if cookie_str:
            _debug_log("Step 2: re-nav + inject cookie")
            self._page.goto("https://www.douyin.com/?recommend=1",
                            wait_until="domcontentloaded", timeout=30000)

            cookies = _cookie_to_list(cookie_str)
            if cookies:
                context.add_cookies(cookies)
                _debug_log(f"Step 2: {len(cookies)} cookies injected")

            self._page.wait_for_function(
                "window.bdms && window.bdms.init", timeout=30000)
            self._page.evaluate("""
                window.bdms.init({
                    aid: 6383, pageId: 6241, boe: false, ddrt: 8.5, ic: 8.5,
                    paths: ['^/aweme/v1/', '^/aweme/v2/', '/douplus/',
                            '/v1/message/', '^/live/', '^/captcha/',
                            '^/ecom/', '^/luna/pc']
                });
            """)
            _debug_log("Step 2: SDK re-init with cookie OK")

        # —— Step 3: 注入设备指纹 ——
        self._page.evaluate("""(fp) => {
            if (fp.webid) localStorage.setItem('webid', fp.webid);
            if (fp.verifyFp) localStorage.setItem('verifyFp', fp.verifyFp);
            if (fp.fp) localStorage.setItem('fp', fp.fp);
            if (fp.uifid) localStorage.setItem('uifid', fp.uifid);
        }""", FINGERPRINTS)
        _debug_log("Step 3: fingerprints injected")

        self._sdk_ready = True
        _debug_log("StealthBrowser: Ready")
        return self._page

    def is_ready(self) -> bool:
        return self._sdk_ready and self._page is not None

    def fetch_video(self, aweme_id: str) -> dict:
        """调用抖音 aweme/detail API 获取视频详情"""
        if not self.is_ready():
            return {"_error": "browser_not_ready"}

        params = dict(API_PARAMS, aweme_id=aweme_id)
        query = "&".join(f"{k}={v}" for k, v in params.items())
        url = f"https://www.douyin.com/aweme/v1/web/aweme/detail/?{query}"

        _debug_log(f"fetch_video: {aweme_id[:12]}...")
        try:
            result = self._page.evaluate("""async (apiUrl) => {
                try {
                    const r = await fetch(apiUrl, { credentials: 'include' });
                    return await r.json();
                } catch(e) {
                    return { _error: e.message };
                }
            }""", url)
            return result
        except Exception as e:
            return {"_error": str(e)}

    def call_api(self, url: str) -> dict:
        """通用 API 代理 — 在浏览器上下文中调用任意抖音 API"""
        if not self.is_ready():
            return {"_error": "browser_not_ready"}

        _debug_log(f"call_api: {url[:80]}...")
        try:
            result = self._page.evaluate("""async (apiUrl) => {
                try {
                    const r = await fetch(apiUrl, { credentials: 'include' });
                    return await r.json();
                } catch(e) {
                    return { _error: e.message };
                }
            }""", url)
            return result
        except Exception as e:
            return {"_error": str(e)}

    def close(self):
        if self._browser:
            try:
                self._browser.close()
            except Exception:
                pass
            self._browser = None
        if self._playwright:
            try:
                self._playwright.stop()
            except Exception:
                pass
            self._playwright = None
        self._page = None
        self._sdk_ready = False


# ═══════════════════════════════════════════════════════════
# SignServer — 常驻浏览器服务 (server.js 等价)
# ═══════════════════════════════════════════════════════════

class SignServer:
    """常驻浏览器 + 线程安全接口"""

    def __init__(self):
        self._browser: Optional[StealthBrowser] = None
        self._lock = threading.Lock()
        self._port = 18765  # 保留兼容
        self._running = False

    def start(self, cookie_str: str = "") -> bool:
        with self._lock:
            if self._browser and self._browser.is_ready():
                return True

            browser_path = BrowserFinder.find()
            if not browser_path:
                _debug_log("SignServer: no browser found")
                return False

            try:
                self._browser = StealthBrowser(browser_path, headless=True)
                self._browser.start(cookie_str=cookie_str)
                self._running = True
                return True
            except Exception as e:
                _debug_log(f"SignServer.start failed: {e}")
                self._running = False
                return False

    def is_ready(self) -> bool:
        with self._lock:
            return self._browser is not None and self._browser.is_ready()

    @property
    def ready(self) -> bool:
        return self.is_ready()

    def call(self, endpoint: str, **params) -> dict:
        """统一调用接口（对齐原 call_server）"""
        with self._lock:
            if not self.is_ready():
                # 自动启动
                cookie = _load_cookie_raw()
                if not self.start(cookie_str=cookie):
                    return {"_error": "sign_server_unavailable"}

            try:
                if endpoint == "video":
                    return self._browser.fetch_video(params.get("aweme_id", ""))
                elif endpoint == "call":
                    return self._browser.call_api(params.get("url", ""))
                else:
                    return {"_error": f"unknown endpoint: {endpoint}"}
            except Exception as e:
                _debug_log(f"SignServer.call({endpoint}) error: {e}")
                # 浏览器死了，标记重连
                self._browser = None
                self._running = False
                return {"_error": str(e)}

    def stop(self):
        with self._lock:
            if self._browser:
                self._browser.close()
                self._browser = None
            self._running = False

    @property
    def port(self) -> int:
        return self._port


# 全局单例
_sign_server = SignServer()


# ═══════════════════════════════════════════════════════════
# 一次性调用 (bootstrap.js 等价)
# ═══════════════════════════════════════════════════════════

def one_shot_fetch(aweme_id: str, cookie_str: str = "",
                   timeout_ms: int = 60000) -> dict:
    """
    一次性：启动浏览器 → 调 API → 关浏览器。
    完全对齐 bootstrap.js 的流程。
    """
    _debug_log(f"one_shot_fetch: {aweme_id[:12]}...")

    browser_path = BrowserFinder.find()
    if not browser_path:
        return {"_error": "no_browser_found"}

    if not cookie_str:
        cookie_str = _load_cookie_raw()

    browser = StealthBrowser(browser_path, headless=True)
    try:
        browser.start(cookie_str=cookie_str, timeout_ms=timeout_ms)
        result = browser.fetch_video(aweme_id)
        return result
    except Exception as e:
        _debug_log(f"one_shot_fetch error: {e}")
        return {"_error": str(e)}
    finally:
        browser.close()


# ═══════════════════════════════════════════════════════════
# 公共 API（供 webview_api.py / server.py 调用）
# ═══════════════════════════════════════════════════════════

def get_signer() -> SignServer:
    return _sign_server


def fetch_video_detail(aweme_id: str, cookie_str: str = "") -> dict:
    """
    获取视频详情。优先走常驻服务，失败则走一次性调用。
    """
    if _sign_server.is_ready():
        result = _sign_server.call("video", aweme_id=aweme_id)
        if "_error" not in result:
            return result

    # 回退到 one-shot
    _debug_log(f"fallback to one_shot_fetch for {aweme_id}")
    return one_shot_fetch(aweme_id, cookie_str=cookie_str)
