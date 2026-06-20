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
    打开抖音 WebView 登录窗口。

    返回:
        登录成功返回 Cookie 字符串，取消返回 None
    """
    from src.gui.dialogs.webview_login import WebViewLogin
    try:
        login = WebViewLogin()
        cookie = login.run(parent)
        if cookie:
            save_cookie(cookie)
            return cookie
    except RuntimeError as e:
        QMessageBox.warning(parent, "组件缺失", str(e))
    return None
