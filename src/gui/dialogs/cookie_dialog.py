# -*- coding: utf-8 -*-
"""
Origami — 抖音登录

直接打开 WebView 让用户在抖音网页中登录，
登录成功后自动检测并保存，无需多余步骤。
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QMessageBox,
)
from PyQt6.QtCore import Qt

from src.gui.fonts import font_scale, scaled_font
from src.cookie import load_cookie, save_cookie


def show_login_dialog(parent) -> str | None:
    """
    登录流程：优先 WebView → 失败则浏览器提取
    """
    # 1. 尝试 WebView 扫码登录
    from src.gui.dialogs.webview_login import WebViewLogin
    try:
        login = WebViewLogin()
        cookie = login.run(parent)
        if cookie:
            save_cookie(cookie)
            QMessageBox.information(parent, "登录成功", "抖音登录成功，可以开始下载了！")
            return cookie
    except RuntimeError:
        pass  # WebView 不可用，继续下一步

    # 2. 尝试从浏览器自动提取 Cookie
    from src.cookie import extract_from_all_browsers
    browser_cookies = extract_from_all_browsers()
    valid_cookies = {b: c for b, c in browser_cookies.items() if c}
    if valid_cookies:
        browsers = list(valid_cookies.keys())
        msg = "WebView 组件不可用，但检测到浏览器已登录抖音：\n\n"
        for b in browsers:
            msg += f"  • {b} ✓\n"
        msg += "\n是否使用浏览器 Cookie？"
        reply = QMessageBox.question(parent, "浏览器登录", msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            cookie = valid_cookies[browsers[0]]
            save_cookie(cookie)
            QMessageBox.information(parent, "登录成功", f"已从 {browsers[0]} 提取 Cookie")
            return cookie

    QMessageBox.warning(parent, "登录失败", "WebView 不可用且浏览器未登录抖音。\n请先在 Chrome/Edge 中登录抖音后再试。")
    return None
