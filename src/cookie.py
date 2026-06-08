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
# WebView 扫码
# ═══════════════════════════════════════════════════════════

class WebViewLogin:
    """WebView 登录，登录后保持 WebView 存活供 API 调用"""

    DOUYIN_URL = "https://www.douyin.com/"


    def __init__(self):
        try:
            from PyQt6.QtWebEngineWidgets import QWebEngineView  # noqa: F401
        except ImportError:
            raise RuntimeError("PyQt6-WebEngine 未安装")

    def run(self, parent=None) -> Optional[str]:
        from PyQt6.QtWidgets import (
            QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
        )
        from PyQt6.QtWebEngineWidgets import QWebEngineView
        from PyQt6.QtWebEngineCore import QWebEngineProfile
        from PyQt6.QtCore import QUrl, QTimer, Qt

        dlg = QDialog(parent)
        dlg.setWindowTitle("抖音登录")
        dlg.resize(900, 560)
        dlg.setMinimumSize(720, 450)
        dlg.setStyleSheet("QDialog { background: #0A0A14; }")

        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        hint = QLabel("  登录信息仅保存在本地，不会上传至任何服务器")
        hint.setStyleSheet(
            "color: #F1F5F9; font-size: 13px; font-weight: bold; "
            "padding: 8px 16px; background: #12122A;"
        )
        layout.addWidget(hint)

        view = QWebEngineView()
        layout.addWidget(view, 1)

        status = QLabel("正在加载页面...")
        status.setStyleSheet("color: #94A3B8; font-size: 11px; padding: 6px 16px;")
        layout.addWidget(status)

        cancel_btn = QPushButton("取消")
        cancel_btn.setObjectName("secondaryBtn")
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.clicked.connect(dlg.reject)

        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(12, 6, 12, 10)
        btn_row.addStretch()
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

        # 拦截未知协议（如 bitbrowser://）防止弹窗
        from PyQt6.QtWebEngineCore import QWebEnginePage
        class _SafePage(QWebEnginePage):
            def acceptNavigationRequest(self, url, nav_type, is_main_frame):
                if url.scheme() in ('http', 'https', 'data', 'about', 'blob', 'javascript'):
                    return super().acceptNavigationRequest(url, nav_type, is_main_frame)
                return False
        view.setPage(_SafePage(view))
        view.loadFinished.connect(lambda ok: status.setText("请登录抖音..." if ok else "加载失败"))
        view.load(QUrl(self.DOUYIN_URL))

        cookie_result = None
        collected = {}

        # 用 CookieStore API 监听（能拿到 HttpOnly Cookie）
        store = view.page().profile().cookieStore()

        def on_cookie_added(cookie):
            name = bytes(cookie.name().data()).decode("utf-8", errors="replace")
            value = bytes(cookie.value().data()).decode("utf-8", errors="replace")
            if not name or not value:  # 跳过空 name/value
                return
            collected[name] = value
            if "sessionid" in collected and "ttwid" in collected:
                nonlocal cookie_result
                cookie_result = "; ".join(f"{k}={v}" for k, v in collected.items())
                status.setText("登录成功！")
                dlg.accept()
                status.setText("登录成功！")
                QTimer.singleShot(300, dlg.accept)

        store.cookieAdded.connect(on_cookie_added)

        result = dlg.exec()
        if result == QDialog.DialogCode.Accepted and cookie_result:
            # 隐藏对话框（不销毁），WebView 保持存活供后续 API 调用
            dlg.hide()
            WebViewLogin._active_view = view
            return cookie_result
        return None
