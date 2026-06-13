# -*- coding: utf-8 -*-
"""
Origami — 多功能内容下载工具

用法:
    python main.py
"""

import sys
import os
import time
from pathlib import Path

# QtWebEngine 必须在 QApplication 前导入
try:
    from PyQt6.QtWebEngineWidgets import QWebEngineView  # noqa: F401
except ImportError:
    pass

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTranslator, QLocale, QLibraryInfo
from PyQt6.QtGui import QPalette, QColor, QFont

from src.environ import BASE_DIR, EXE_DIR, SETTINGS_FILE
from src.settings.store import load as load_settings
from src.gui.main_window import (
    MainWindow, setup_single_instance,
    _startup_overwrite_if_needed, _instance_socket,
    global_exception_handler,
)

sys.excepthook = global_exception_handler


def main():
    global _instance_socket

    # 启动前：检测更新并替换
    _startup_overwrite_if_needed()

    # 单实例检测
    _instance_socket = setup_single_instance()
    if _instance_socket is None:
        return

    # 启动常驻浏览器服务
    from src.webview_api import start_server as _start_srv
    _start_srv()

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    # PyInstaller 打包后首次启动浏览器 Code:0 问题绕过
    _first_lock = EXE_DIR / "_first.lock"
    if not _first_lock.exists() and getattr(sys, "frozen", False):
        _first_lock.write_text("1", encoding="ascii")
        os.startfile(sys.executable)
        time.sleep(0.5)
        os._exit(0)
    _first_lock.unlink(missing_ok=True)

    # 加载字体设置
    settings = load_settings()
    saved_family = settings.get("font_family", "")
    saved_size = settings.get("font_size", 0)
    if saved_family and saved_size:
        font = QFont(saved_family, saved_size)
        app.setFont(font)
    else:
        default_font = app.font()
        default_font.setPointSize(15)
        app.setFont(default_font)

    # 中文翻译
    trans_dir = BASE_DIR / "translations"
    sys_dir = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
    for qm in ("qtbase_zh_CN", "qt_zh_CN"):
        t = QTranslator()
        local = trans_dir / f"{qm}.qm"
        if local.exists():
            t.load(str(local))
        else:
            t.load(qm, sys_dir)
        app.installTranslator(t)

    app.setStyle("Fusion")
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(10, 10, 20))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(241, 245, 249))
    palette.setColor(QPalette.ColorRole.Base, QColor(22, 33, 62))
    palette.setColor(QPalette.ColorRole.Text, QColor(224, 224, 224))
    palette.setColor(QPalette.ColorRole.Button, QColor(233, 69, 96))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(255, 255, 255))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(233, 69, 96))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(255, 255, 255))
    app.setPalette(palette)

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
