# -*- coding: utf-8 -*-
"""
Origami — Cookie 获取与管理

三层 fallback:
  1. browser-cookie3 自动提取
  2. WebView 扫码登录
  3. 手动粘贴
"""

import base64
import time
from pathlib import Path
from typing import Optional

from src.environ import COOKIE_FILE


# ═══════════════════════════════════════════════════════════
# Base64 编解码
# ═══════════════════════════════════════════════════════════

def encode_cookie(cookie_str: str) -> str:
    return base64.b64encode(cookie_str.encode("utf-8")).decode("ascii")

def decode_cookie(encoded: str) -> str:
    try:
        return base64.b64decode(encoded.encode("ascii")).decode("utf-8")
    except Exception:
        return encoded


# ═══════════════════════════════════════════════════════════
# 持久化
# ═══════════════════════════════════════════════════════════

def save_cookie(cookie_str: str):
    COOKIE_FILE.parent.mkdir(parents=True, exist_ok=True)
    COOKIE_FILE.write_text(encode_cookie(cookie_str), encoding="utf-8")

def load_cookie() -> str:
    if not COOKIE_FILE.exists():
        return ""
    content = COOKIE_FILE.read_text(encoding="utf-8").strip()
    return decode_cookie(content) if content else ""


# ═══════════════════════════════════════════════════════════
# 校验
# ═══════════════════════════════════════════════════════════

def validate_cookie(cookie_str: str) -> bool:
    return bool(cookie_str) and "sessionid=" in cookie_str and "ttwid=" in cookie_str

def get_cookie_status() -> dict:
    if not COOKIE_FILE.exists():
        return {"ok": False, "length": 0, "mtime": None}
    try:
        cookie = load_cookie()
        mtime = COOKIE_FILE.stat().st_mtime
        return {"ok": validate_cookie(cookie), "length": len(cookie), "mtime": mtime}
    except Exception:
        return {"ok": False, "length": 0, "mtime": None}

def get_cookie_age_days() -> Optional[float]:
    status = get_cookie_status()
    if status["mtime"]:
        return (time.time() - status["mtime"]) / 86400
    return None


# ═══════════════════════════════════════════════════════════
# 浏览器自动提取
# ═══════════════════════════════════════════════════════════

_BROWSER_PATHS = {
    "Chrome":  r"%LOCALAPPDATA%\Google\Chrome\User Data\Default\Network\Cookies",
    "Edge":    r"%LOCALAPPDATA%\Microsoft\Edge\User Data\Default\Network\Cookies",
    "Firefox": r"%APPDATA%\Mozilla\Firefox\Profiles",
    "Brave":   r"%LOCALAPPDATA%\BraveSoftware\Brave-Browser\User Data\Default\Network\Cookies",
    "Opera":   r"%APPDATA%\Opera Software\Opera Stable\Network\Cookies",
}

def detect_available_browsers() -> list[str]:
    import os
    available = []
    for name, path_tmpl in _BROWSER_PATHS.items():
        path = os.path.expandvars(path_tmpl)
        if name == "Firefox":
            if os.path.isdir(path):
                available.append(name)
        elif os.path.exists(path):
            available.append(name)
    return available

def extract_from_browser(browser: str = "chrome", domain: str = ".douyin.com") -> Optional[str]:
    try:
        import browser_cookie3
        extractors = {
            "chrome": browser_cookie3.chrome, "edge": browser_cookie3.edge,
            "firefox": browser_cookie3.firefox, "brave": browser_cookie3.brave,
            "opera": browser_cookie3.opera,
        }
        fn = extractors.get(browser.lower())
        if fn is None:
            return None
        cj = fn(domain_name=domain)
        cookie_str = "; ".join(f"{c.name}={c.value}" for c in cj)
        return cookie_str if validate_cookie(cookie_str) else None
    except Exception:
        return None

def extract_from_all_browsers(domain: str = ".douyin.com") -> dict[str, Optional[str]]:
    results = {}
    for browser in detect_available_browsers():
        results[browser] = extract_from_browser(browser, domain)
    return results


# ═══════════════════════════════════════════════════════════
# WebView 扫码登录 → 已移至 src/gui/dialogs/webview_login.py
# ═══════════════════════════════════════════════════════════
