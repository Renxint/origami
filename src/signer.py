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
from playwright_stealth import Stealth

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

        # Stealth: init 脚本在页面创建前注入
        context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => false });
            window.chrome = { runtime: {} };
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5]
            });
            Object.defineProperty(navigator, 'languages', {
                get: () => ['zh-CN', 'zh', 'en']
            });
        """)
        self._page = context.new_page()

        # 额外 stealth（playwright_stealth）
        try:
            stealth = Stealth(
                navigator_webdriver=True,
                navigator_languages=True,
                navigator_plugins=True,
                navigator_vendor=True,
                chrome_runtime=True,
            )
            stealth.apply_stealth_sync(self._page)
        except Exception as e:
            _debug_log(f"Stealth warning: {e}")

        # —— Step 1: 首次导航，等待 bdms SDK 加载 ——
        # （对齐 bootstrap.js：必须先做一次不带 Cookie 的 init）
        _debug_log("Step 1: first nav + SDK wait")
        try:
            self._page.goto(
                "https://www.douyin.com/?recommend=1",
                wait_until="domcontentloaded", timeout=timeout_ms)
            # 等 bdms 对象出现（可能比 init 方法先加载）
            self._page.wait_for_function(
                "() => typeof window.bdms !== 'undefined'",
                timeout=30000)
            time.sleep(2)  # 等 SDK 完全初始化
            self._page.evaluate("""
                if (window.bdms && window.bdms.init) {
                    window.bdms.init({
                        aid: 6383, pageId: 6241, boe: false, ddrt: 8.5, ic: 8.5
                    });
                }
            """)
            _debug_log("Step 1: SDK init OK")
        except Exception as e:
            _debug_log(f"Step 1: SDK warning (non-fatal): {e}")

        # —— Step 2: JS 注入 Cookie（绕过 Playwright add_cookies 兼容问题） ——
        if cookie_str:
            _debug_log("Step 2: JS inject cookies + re-nav")
            # 先访问一次建域名（cookie 只能设在当前域名下）
            self._page.goto("https://www.douyin.com/",
                            wait_until="commit", timeout=15000)
            # 通过 JS 逐条注入 document.cookie
            for part in cookie_str.split(";"):
                part = part.strip()
                if "=" not in part:
                    continue
                name, value = part.split("=", 1)
                name = name.strip()
                value = value.strip()
                if name:
                    try:
                        self._page.evaluate(
                            """([n, v]) => {
                                document.cookie = n + '=' + v +
                                    '; domain=.douyin.com; path=/; max-age=31536000';
                            }""", [name, value])
                    except Exception:
                        pass
            _debug_log(f"Step 2: cookies injected via JS")
            # 重新导航让 cookie 生效
            self._page.goto("https://www.douyin.com/?recommend=1",
                            wait_until="domcontentloaded", timeout=30000)

            try:
                self._page.wait_for_function(
                    "() => typeof window.bdms !== 'undefined'",
                    timeout=30000)
                time.sleep(1)
                self._page.evaluate("""
                    if (window.bdms && window.bdms.init) {
                        window.bdms.init({
                            aid: 6383, pageId: 6241, boe: false,
                            ddrt: 8.5, ic: 8.5,
                            paths: ['^/aweme/v1/', '^/aweme/v2/', '/douplus/',
                                    '/v1/message/', '^/live/', '^/captcha/',
                                    '^/ecom/', '^/luna/pc']
                        });
                    }
                """)
                _debug_log("Step 2: SDK re-init OK")
            except Exception as e:
                _debug_log(f"Step 2: SDK warning (non-fatal): {e}")

        # —— Step 3: 注入设备指纹 ——
        self._page.evaluate("""(fp) => {
            if (fp.webid) localStorage.setItem('webid', fp.webid);
            if (fp.verifyFp) localStorage.setItem('verifyFp', fp.verifyFp);
            if (fp.fp) localStorage.setItem('fp', fp.fp);
            if (fp.uifid) localStorage.setItem('uifid', fp.uifid);
        }""", FINGERPRINTS)
        _debug_log("Step 3: fingerprints injected")

        self._sdk_ready = True  # 即使 SDK 有 warning 也标记就绪
        _debug_log(f"StealthBrowser: Ready (page={self._page is not None})")
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
        try:
            if self._browser:
                self._browser.close()
        except Exception:
            pass
        self._browser = None
        try:
            if self._playwright:
                self._playwright.stop()
        except Exception:
            pass
        self._playwright = None
        self._page = None
        self._sdk_ready = False


# ═══════════════════════════════════════════════════════════
# SignerDaemon — 独立线程 HTTP 服务 (server.js 等价)
# ═══════════════════════════════════════════════════════════

from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs


class _SignerHandler(BaseHTTPRequestHandler):
    """HTTP handler that routes to the StealthBrowser instance"""

    browser: StealthBrowser = None  # 类变量，由 daemon 设置

    def log_message(self, format, *args):
        _debug_log(f"[daemon] {args[0]}")

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            ready = self.browser and self.browser.is_ready()
            self._json(200, {"ok": ready, "sdkReady": ready})
        else:
            self._json(404, {"_error": "not_found"})

    def do_POST(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)

        try:
            if parsed.path == "/video":
                aweme_id = params.get("aweme_id", [""])[0]
                if not aweme_id:
                    self._json(400, {"_error": "missing aweme_id"})
                    return
                if not self.browser or not self.browser.is_ready():
                    self._json(503, {"_error": "browser_not_ready"})
                    return
                result = self.browser.fetch_video(aweme_id)
                self._json(200, result)

            elif parsed.path == "/call":
                url = params.get("url", [""])[0]
                if not url:
                    self._json(400, {"_error": "missing url"})
                    return
                if not self.browser or not self.browser.is_ready():
                    self._json(503, {"_error": "browser_not_ready"})
                    return
                result = self.browser.call_api(url)
                self._json(200, result)

            else:
                self._json(404, {"_error": "not_found"})

        except Exception as e:
            _debug_log(f"[daemon] handler error: {e}")
            self._json(500, {"_error": str(e)})

    def _json(self, status: int, data: dict):
        import json as _json
        body = _json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class SignerDaemon:
    """独立线程 HTTP 服务：浏览器创建 + HTTP 服务全在 daemon 线程内"""

    def __init__(self, port: int = 18765):
        self._port = port
        self._browser: Optional[StealthBrowser] = None
        self._server: Optional[HTTPServer] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._ready = threading.Event()
        self._error: Optional[str] = None
        self._lock = threading.Lock()

    def start(self, cookie_str: str = "") -> bool:
        with self._lock:
            if self._running and self._browser and self._browser.is_ready():
                return True

            # 先找端口
            import socket
            actual_port = self._port
            for p in range(self._port, self._port + 50):
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                try:
                    s.bind(("127.0.0.1", p))
                    s.close()
                    actual_port = p
                    break
                except OSError:
                    s.close()
            else:
                _debug_log("SignerDaemon: no available port")
                return False

            self._port = actual_port
            self._ready.clear()
            self._error = None

            # 启动 daemon 线程 — 浏览器创建全在内部完成
            self._thread = threading.Thread(
                target=self._run, args=(cookie_str,),
                daemon=True, name="signer-daemon")
            self._thread.start()

            # 等就绪或报错（最多 90s）
            if not self._ready.wait(timeout=90):
                _debug_log("SignerDaemon: startup timeout")
                return False

            if self._error:
                _debug_log(f"SignerDaemon: startup error: {self._error}")
                return False

            self._running = True
            _debug_log(f"SignerDaemon: listening on http://127.0.0.1:{self._port}")
            return True

    def _run(self, cookie_str: str):
        """在 daemon 线程内：找浏览器 → 启动 playwright → HTTP serve"""
        try:
            # 1. 找浏览器
            browser_path = BrowserFinder.find()
            if not browser_path:
                self._error = "no_browser_found"
                self._ready.set()
                return

            # 2. 启动 playwright 浏览器（在 daemon 线程，greenlet 绑这里）
            _debug_log("SignerDaemon: launching browser in daemon thread...")
            self._browser = StealthBrowser(browser_path, headless=True)
            self._browser.start(cookie_str=cookie_str, timeout_ms=90000)

            # 3. 启动 HTTP server
            _SignerHandler.browser = self._browser
            self._server = HTTPServer(
                ("127.0.0.1", self._port), _SignerHandler)

            # 4. 通知主线程就绪
            self._ready.set()

            # 5. 阻塞 serve
            _debug_log(f"SignerDaemon: serving on port {self._port}")
            self._server.serve_forever(poll_interval=0.5)

        except Exception as e:
            _debug_log(f"SignerDaemon: _run error: {e}")
            self._error = str(e)
            self._ready.set()

    def is_ready(self) -> bool:
        return (self._running
                and self._browser is not None
                and self._browser.is_ready())

    @property
    def ready(self) -> bool:
        return self.is_ready()

    @property
    def port(self) -> int:
        return self._port

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self._port}"

    def stop(self):
        with self._lock:
            if self._server:
                try:
                    self._server.shutdown()
                except Exception:
                    pass
                self._server = None
            if self._browser:
                try:
                    self._browser.close()
                except Exception:
                    pass
                self._browser = None
            self._running = False
            _debug_log("SignerDaemon: stopped")


# ── 全局单例 ──
_signer_daemon = SignerDaemon()


def get_signer() -> SignerDaemon:
    return _signer_daemon


# ═══════════════════════════════════════════════════════════
# 一次性调用 (bootstrap.js 等价)
# ═══════════════════════════════════════════════════════════

def one_shot_fetch(aweme_id: str, cookie_str: str = "",
                   timeout_ms: int = 60000) -> dict:
    """一次性：启动浏览器 → 调 API → 关浏览器"""
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


def fetch_video_detail(aweme_id: str, cookie_str: str = "") -> dict:
    """获取视频详情。优先走常驻 daemon，失败则走一次性调用"""
    if _signer_daemon.is_ready():
        import requests as _r
        try:
            r = _r.post(
                f"{_signer_daemon.url}/video?aweme_id={aweme_id}",
                timeout=60)
            return r.json()
        except Exception:
            pass

    return one_shot_fetch(aweme_id, cookie_str=cookie_str)
