# -*- coding: utf-8 -*-
"""
Origami — 主窗口

所有页面的容器，管理导航、托盘、快捷键、版本更新。
借鉴 clawd-on-desk 的多窗口思路：主窗口 + 设置弹窗 + 更新遮罩。
"""

import sys
import os
import time
from pathlib import Path

import requests

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QStackedWidget, QWidget,
    QSystemTrayIcon, QMenu, QMessageBox,
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QIcon, QFont, QAction, QShortcut, QKeySequence, QPalette, QColor

from src.theme import font_scale, build_stylesheet, DARK_THEME
from src.config import VERSION, VERSION_URL
from src.environ import BASE_DIR, EXE_DIR, SETTINGS_FILE
from src.utils import compare_versions
from src.settings.store import load as load_settings, save as save_settings
from src.gui.pages import (
    ModePage, SinglePage, HomepagePage,
    SettingsPage, UpdatePage,
)
from src.gui.pages.douyin_page import DouyinPage

# ── 单实例 ────────────────────────────────────────────────
from PyQt6.QtNetwork import QLocalServer, QLocalSocket

_instance_socket = None


def _slog(msg: str):
    """单实例调试日志"""
    try:
        with open(EXE_DIR / "_instance.log", "a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%H:%M:%S')}] PID={os.getpid()} {msg}\n")
    except Exception:
        pass


def setup_single_instance():
    """单实例检测"""
    global _instance_socket
    _slog("setup_single_instance START")
    sock = QLocalSocket()
    sock.connectToServer("Origami_Instance")
    if sock.waitForConnected(500):
        _slog("Connected to existing instance - sending show")
        sock.write(b"show")
        sock.waitForBytesWritten(500)
        sock.close()
        return None
    sock.close()
    _slog("No existing instance - starting new server")
    server = QLocalServer()
    server.listen("Origami_Instance")
    _slog(f"Server listening: {server.isListening()}")
    _instance_socket = server
    return server


# ── 启动时更新覆盖 ────────────────────────────────────────

def _startup_overwrite_if_needed():
    """启动时检查 _update 目录，存在则覆盖安装"""
    import shutil
    update_dir = EXE_DIR.parent / "_update"
    _slog(f"update check: EXE_DIR={EXE_DIR}, update_dir={update_dir}, exists={update_dir.exists()}")
    if not update_dir.exists():
        return
    _slog("overwrite START")
    try:
        new_exes = list(update_dir.glob("*.exe"))
        if not new_exes:
            _slog("no exe in _update, abort")
            shutil.rmtree(update_dir, ignore_errors=True)
            return
        new_exe = new_exes[0].name

        _app = EXE_DIR.as_posix()
        _upd = update_dir.as_posix()
        _old_exe = Path(sys.executable).name
        bat = EXE_DIR.parent / "_install.bat"
        bat.write_text(
            '@echo off\r\n'
            'chcp 65001 >nul\r\n'
            'timeout /t 2 /nobreak >nul\r\n'
            f'xcopy "{_upd}\\*" "{_app}\\" /E /Y /Q >nul\r\n'
            f'rmdir /s /q "{_upd}"\r\n'
            f'start "" /d "{_app}" "{_app}\\{new_exe}"\r\n'
            f'timeout /t 3 /nobreak >nul\r\n'
            f'del "{_app}\\{_old_exe}"\r\n'
            'del "%~f0"\r\n',
            encoding="utf-8",
        )
        CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0
        subprocess = __import__("subprocess")
        subprocess.run(
            f'start "" /min "{bat}"',
            shell=True, creationflags=CREATE_NO_WINDOW,
        )
        time.sleep(0.5)
        os._exit(0)
    except Exception:
        _slog("overwrite FAILED")
        import traceback
        _slog(traceback.format_exc())


# ── 全局异常钩子 ──────────────────────────────────────────

def global_exception_handler(exc_type, exc_value, exc_tb):
    import traceback
    tb_str = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    try:
        from src.environ import CRASH_LOG
        CRASH_LOG.write_text(
            f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] CRASH\n{tb_str}\n",
            encoding="utf-8",
        )
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════
# 主窗口
# ═══════════════════════════════════════════════════════════
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"Origami v{VERSION}")

        # 图标
        ico = BASE_DIR / "app.ico"
        self._app_icon = QIcon(str(ico)) if ico.exists() else QIcon()
        self.setWindowIcon(self._app_icon)

        # 恢复窗口位置
        settings = load_settings()
        geo = settings.get("geometry")
        if geo:
            try:
                self.restoreGeometry(bytes.fromhex(geo.get("geo", "")))
            except Exception:
                self.resize(820, 640)
        else:
            self.resize(820, 640)
        self.setMinimumSize(font_scale(520), font_scale(380))

        # 托盘
        self._tray = None
        self._setup_tray()

        # 页面栈
        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)

        self.mode_page = ModePage()
        self.douyin_page = DouyinPage()
        self.single_page = SinglePage()
        self.homepage_page = HomepagePage()
        self.settings_page = SettingsPage()
        self.update_page = UpdatePage()

        self.stack.addWidget(self.mode_page)        # 0
        self.stack.addWidget(self.douyin_page)      # 1
        self.stack.addWidget(self.single_page)      # 2
        self.stack.addWidget(self.homepage_page)    # 3
        self.stack.addWidget(self.settings_page)    # 4
        self.stack.addWidget(self.update_page)      # 5

        # 导航连接
        # 首页 → 平台选择
        self.mode_page.platform_selected.connect(
            lambda pid: self.stack.setCurrentIndex(1) if pid == "douyin" else None
        )
        self.mode_page.settings_clicked.connect(lambda: self.stack.setCurrentIndex(4))

        # 抖音页 → 单视频 / 主页
        self.douyin_page.back_clicked.connect(self._go_home)
        self.douyin_page.single_clicked.connect(lambda: self.stack.setCurrentIndex(2))
        self.douyin_page.homepage_clicked.connect(lambda: self.stack.setCurrentIndex(3))

        # 下载页 → 回抖音页
        self.single_page.back_clicked.connect(lambda: self.stack.setCurrentIndex(1))
        self.homepage_page.back_clicked.connect(lambda: self.stack.setCurrentIndex(1))

        self.settings_page.back_clicked.connect(self._go_home)
        self.update_page.cancel_clicked.connect(lambda: self.stack.setCurrentIndex(0))

        # 字体变更
        self.settings_page.font_changed.connect(self._apply_font)

        # Cookie 更新
        self.mode_page.cookie_updated.connect(self._on_cookie_updated)
        self.douyin_page.cookie_updated.connect(self._on_cookie_updated)
        self.settings_page.cookie_updated.connect(self._on_cookie_updated)

        self.stack.setCurrentIndex(0)

        # 应用样式
        pt = QApplication.instance().font().pointSize()
        self.setStyleSheet(build_stylesheet(DARK_THEME, pt))

        # 剪贴板监听
        self._last_clipboard = ""
        self._clip_timer = QTimer()
        self._clip_timer.timeout.connect(self._check_clipboard)
        self._clip_timer.start(1500)

        # 快捷键
        self._setup_shortcuts()

        # 单实例监听
        if _instance_socket:
            self._instance_srv = _instance_socket
            self._instance_srv.newConnection.connect(self._on_second_instance)

        # 版本检查
        QTimer.singleShot(2000, self._check_version)

    # ── 剪贴板监听 ──

    def _check_clipboard(self):
        """检测剪贴板中的抖音链接"""
        try:
            clip = QApplication.clipboard().text()
            if not clip or clip == self._last_clipboard:
                return
            self._last_clipboard = clip

            import re
            patterns = [
                r'https?://v\.douyin\.com/[A-Za-z0-9_\-/]+',
                r'https?://(?:www\.)?douyin\.com/(?:video|note)/\d+',
                r'https?://(?:www\.)?douyin\.com/user/MS4wLjAB[\w\-]+',
                r'https?://(?:www\.)?iesdouyin\.com/share/user/MS4wLjAB[\w\-]+',
            ]
            found = None
            for pat in patterns:
                m = re.search(pat, clip)
                if m:
                    found = m.group(0)
                    break
            if not found:
                return

            # 短链 → 302 解析，确定类型
            resolved = found
            label = None
            if "v.douyin.com" in found:
                try:
                    from src.environ import USER_AGENT
                    s = __import__("requests").Session()
                    s.headers.update({"User-Agent": USER_AGENT})
                    r = s.get(found, allow_redirects=True, timeout=10, stream=True)
                    r.close()
                    resolved = r.url
                except Exception:
                    pass

            # 判断链接类型
            if "/user/" in resolved or "/share/user/" in resolved:
                label = "主页批量下载"
                widget_idx = 3  # homepage_page
            elif "/video/" in resolved or "/note/" in resolved:
                label = "单视频下载"
                widget_idx = 2  # single_page
            else:
                return

            reply = QMessageBox.question(
                self, "检测到抖音链接",
                f"是否{label}?\n{found[:80]}",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes:
                self.stack.setCurrentIndex(widget_idx)
                page = self.stack.widget(widget_idx)
                if hasattr(page, "url_input"):
                    # 传给输入框的是原始剪贴板内容（兼容分享口令格式）
                    page.url_input.setText(clip)
        except Exception:
            pass

    # ── 导航 ──

    def _go_home(self):
        try:
            self.douyin_page.refresh_cookie_status()
        except Exception:
            pass
        try:
            self.settings_page.refresh_cookie_status()
        except Exception:
            pass
        self.stack.setCurrentIndex(0)

    def _on_cookie_updated(self):
        self.settings_page.refresh_cookie_status()

    # ── 字体/主题 ──

    def _apply_font(self, font: QFont):
        app = QApplication.instance()
        app.setFont(font)
        self.setStyleSheet(build_stylesheet(DARK_THEME, font.pointSize()))
        for w in self.findChildren(QWidget):
            w.updateGeometry()
        self.updateGeometry()

    # ── 快捷键 ──

    def _setup_shortcuts(self):
        QShortcut(QKeySequence("Ctrl+H"), self).activated.connect(self._go_home)
        QShortcut(QKeySequence("Ctrl+Q"), self).activated.connect(self._real_quit)
        QShortcut(QKeySequence("Ctrl+,"), self).activated.connect(
            lambda: self.stack.setCurrentIndex(4)
        )
        QShortcut(QKeySequence("Ctrl+S"), self).activated.connect(
            lambda: self.stack.setCurrentIndex(4)
        )
        QShortcut(QKeySequence("Escape"), self).activated.connect(
            lambda: self.hide() if self._tray and self._tray.isVisible() else None
        )

    # ── 版本更新 ──

    def _check_version(self):
        try:
            r = requests.get(VERSION_URL, timeout=5)
            data = r.json()
            remote = data.get("version", "")
            if compare_versions(remote, VERSION) > 0:
                note = data.get("note", "")
                url = data.get("url", "")
                reply = QMessageBox.question(
                    self, "发现新版本",
                    f"当前版本: v{VERSION}\n最新版本: v{remote}\n"
                    f"更新内容: {note}\n\n是否后台下载? (下次启动时自动安装)",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                )
                if reply == QMessageBox.StandardButton.Yes and url:
                    self.stack.setCurrentIndex(4)
                    self.update_page.start_update(url)
        except Exception:
            pass

    # ── 单实例 ──

    def _on_second_instance(self):
        _slog("_on_second_instance triggered!")
        conn = self._instance_srv.nextPendingConnection()
        if conn:
            conn.waitForReadyRead(500)
            data = bytes(conn.readAll())
            _slog(f"received data: {data}")
            conn.close()
            if data == b"show":
                _slog("calling _show_from_tray")
                self._show_from_tray()

    # ── 托盘 ──

    def _setup_tray(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            self._tray = None
            return

        settings = load_settings()
        if not settings.get("tray_enabled", False):
            self._tray = None
            return

        self._tray = QSystemTrayIcon(self._app_icon, self)
        self._tray.setToolTip("Origami · 就绪")
        self._tray.activated.connect(self._on_tray_activated)

        menu = QMenu()
        a_show = menu.addAction("显示主窗口")
        a_show.triggered.connect(self._show_from_tray)
        menu.addSeparator()
        a_about = menu.addAction("关于 Origami")
        a_about.triggered.connect(
            lambda: QMessageBox.about(
                self, "关于 Origami",
                f"Origami v{VERSION}\n多功能内容下载工具\n\n(c) 2026 Renxint"
            )
        )
        a_update = menu.addAction("检查更新")
        a_update.triggered.connect(self._check_version)
        menu.addSeparator()
        a_quit = menu.addAction("退出")
        a_quit.triggered.connect(self._real_quit)
        self._tray.setContextMenu(menu)
        self._tray.show()

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._show_from_tray()

    def _show_from_tray(self):
        self.showNormal()
        self.activateWindow()
        self.raise_()

    def closeEvent(self, event):
        if self._tray and self._tray.isVisible():
            self.hide()
            self._tray.showMessage(
                "Origami", "已最小化到托盘，双击恢复",
                QSystemTrayIcon.MessageIcon.Information, 2000,
            )
            event.ignore()
        else:
            self._real_quit()

    def _real_quit(self):
        try:
            geo_hex = self.saveGeometry().toHex().data().decode()
            save_settings({"geometry": {"geo": geo_hex}})
        except Exception:
            pass
        if self._tray:
            self._tray.hide()
        try:
            if _instance_socket:
                _instance_socket.close()
        except Exception:
            pass
        QApplication.quit()

    def tray_notify(self, title: str, msg: str,
                    icon=QSystemTrayIcon.MessageIcon.Information,
                    duration: int = 3000):
        if self._tray:
            self._tray.showMessage(title, msg, icon, duration)
