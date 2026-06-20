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

# PyInstaller 打包后 Qt 路径修正（必须在任何 PyQt 导入之前）
if getattr(sys, "frozen", False):
    _internal = Path(sys._MEIPASS)
    _exe_dir = Path(sys.executable).parent
    _exe_dir.joinpath("qt.conf").write_text(
        "[Paths]\nPrefix = _internal/PyQt6/Qt6\n", encoding="utf-8")
    _qt_bin = _internal / "PyQt6" / "Qt6" / "bin"
    if _qt_bin.exists():
        _dll_cookie = os.add_dll_directory(str(_qt_bin))
        import src.environ
        src.environ.QT_BIN_PATH = str(_qt_bin)
    # QtWebEngine 必须找到渲染进程
    _qt_wep = _qt_bin / "QtWebEngineProcess.exe"
    if _qt_wep.exists():
        os.environ["QTWEBENGINEPROCESS_PATH"] = str(_qt_wep)
    # Qt 从 resources 目录找 qt.conf，必须写一份
    _qt_res = _internal / "PyQt6" / "Qt6" / "resources"
    if _qt_res.exists():
        (_qt_res / "qt.conf").write_text("[Paths]\nPrefix = ..\n", encoding="utf-8")
    # 把 Qt bin 加入 PATH（兜底）
    os.environ["PATH"] = str(_qt_bin) + ";" + os.environ.get("PATH", "")

# 基础 PyQt 导入（不触发 QtNetwork，避免 WebEngine 加载冲突）
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTranslator, QLocale, QLibraryInfo, Qt
from PyQt6.QtGui import QPalette, QColor, QFont

QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)

# 静默 libpng iCCP 警告（Qt 自带图标的色域警告，不影响功能）
os.environ["QT_LOGGING_RULES"] = "libpng.warning=false"

from src.environ import BASE_DIR, EXE_DIR, SETTINGS_FILE
from src.settings.store import load as load_settings

# 单实例和主窗口在 main() 内延迟导入，避免 QtNetwork 先于 WebEngine 加载
# 兜底：任何退出都清理 sign-server 防止僵尸进程
import atexit
def _cleanup_sign_server():
    try:
        from src.webview_api import stop_server
        stop_server()
    except Exception:
        pass
atexit.register(_cleanup_sign_server)

# 关闭时后台线程静默
import threading as _threading
def _thread_hook(args):
    from src.environ import APP_SHUTTING_DOWN
    exc = args.exc_value
    if APP_SHUTTING_DOWN and isinstance(exc, RuntimeError) and 'deleted' in str(exc):
        return
    __import__('traceback').print_exception(args.exc_type, exc, args.exc_traceback)
_threading.excepthook = _thread_hook

sys.excepthook = lambda t, v, tb: __import__('traceback').print_exception(t, v, tb)

# IDE 终止 / Ctrl+C 静默退出
import signal as _signal
def _sigint_handler(sig, frame):
    QApplication.quit()
_signal.signal(_signal.SIGINT, _sigint_handler)
_signal.signal(_signal.SIGTERM, _sigint_handler)


def main():
    from src.gui.main_window import (
        MainWindow, setup_single_instance,
        _startup_overwrite_if_needed,
    )
    # _instance_socket 需声明 global
    from src.gui.main_window import _instance_socket as _inst_sock
    global _instance_socket

    # 启动前：检测更新并替换
    _startup_overwrite_if_needed()

    # 清理上次强杀遗留的 sign-server 孤儿
    try:
        from src.webview_api import _kill_orphan_nodes
        _kill_orphan_nodes()
    except Exception:
        pass

    # QApplication
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    # 🔑 冻结版：先加载 WebEngine，再让其他模块（QtNetwork）进来
    if getattr(sys, "frozen", False):
        try:
            from src.gui.dialogs.webview_login import _ensure_webengine
            _ensure_webengine()
        except Exception:
            pass

    # 单实例检测（内部首次加载 QtNetwork → QLocalSocket）
    _instance_socket = setup_single_instance()
    if _instance_socket is None:
        return

    # 加载自定义字体
    from PyQt6.QtGui import QFontDatabase
    _font_dir = BASE_DIR / "src" / "gui" / "assets" / "fonts"
    if _font_dir.exists():
        for _f in _font_dir.glob("*.ttf"):
            QFontDatabase.addApplicationFont(str(_f.resolve()))

    # 加载字体设置
    settings = load_settings()
    saved_family = settings.get("font_family", "")
    saved_size = settings.get("font_size", 0)
    if saved_family and saved_size:
        font = QFont(saved_family, saved_size)
        app.setFont(font)
    else:
        default_font = app.font()
        default_font.setPointSize(17)
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
    # sign-server 懒启动：首次下载时才拉起，避开与 QtWebEngine 登录同时启动 Chromium
    from src.cookie import load_cookie
    if load_cookie():
        from PyQt6.QtCore import QTimer
        from src.webview_api import start_server
        QTimer.singleShot(3000, start_server)  # 已登录才预热，等 QtWebEngine 稳定
    app.aboutToQuit.connect(_cleanup_sign_server)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
