# -*- coding: utf-8 -*-
"""
Origami — 主窗口

所有页面的容器，管理导航、托盘、快捷键、版本更新。
借鉴 clawd-on-desk 的多窗口思路：主窗口 + 设置弹窗 + 更新遮罩。
"""

import sys
import os
import time
import threading
from pathlib import Path

import requests

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QStackedWidget, QWidget,
    QSystemTrayIcon, QMenu, QMessageBox,
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QIcon, QFont, QAction, QShortcut, QKeySequence, QPalette, QColor

from src.gui.fonts import font_scale, scaled_font
from src.stylesheet import build_stylesheet
from src.config import VERSION, VERSION_URLS
from src.environ import BASE_DIR, EXE_DIR, SETTINGS_FILE
from src.utils import compare_versions
from src.settings.store import load as load_settings, save as save_settings
from src.gui.pages import (
    ModePage, SinglePage, BatchPage,
    SettingsPage, UpdatePage,
)
from src.gui.pages.douyin_page import DouyinPage

# ── 单实例 ────────────────────────────────────────────────

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
    from PyQt6.QtNetwork import QLocalServer, QLocalSocket
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
    _version_signal = pyqtSignal(dict)  # 后台线程→主线程版本信息
    _nav_signal = pyqtSignal(str, str)  # 后台线程→主线程导航 ('batch'|'single', raw_url)

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
        self.batch_page = BatchPage()
        self.settings_page = SettingsPage()
        self.update_page = UpdatePage()

        self.stack.addWidget(self.mode_page)        # 0
        self.stack.addWidget(self.douyin_page)      # 1
        self.stack.addWidget(self.single_page)      # 2
        self.stack.addWidget(self.batch_page)       # 3
        self.stack.addWidget(self.settings_page)    # 4
        self.stack.addWidget(self.update_page)      # 5

        # 导航连接
        # 首页 → 平台选择
        self.mode_page.platform_selected.connect(
            lambda pid: self.stack.setCurrentIndex(1) if pid == "douyin" else None
        )
        self.mode_page.settings_clicked.connect(lambda: self.stack.setCurrentIndex(4))

        # 抖音页 → 单视频 / 批量
        self.douyin_page.back_clicked.connect(self._go_home)
        self.douyin_page.single_clicked.connect(lambda: self.stack.setCurrentIndex(2))
        self.douyin_page.batch_clicked.connect(lambda: self.stack.setCurrentIndex(3))

        # 下载页 → 回抖音页
        self.single_page.back_clicked.connect(lambda: self.stack.setCurrentIndex(1))
        self.batch_page.back_clicked.connect(lambda: self.stack.setCurrentIndex(1))

        self.settings_page.back_clicked.connect(self._go_home)
        self.update_page.cancel_clicked.connect(lambda: self.stack.setCurrentIndex(0))

        # 字体变更
        self.settings_page.font_changed.connect(self._apply_font)

        # Cookie 更新
        self.mode_page.cookie_updated.connect(self._on_cookie_updated)
        self.douyin_page.cookie_updated.connect(self._on_cookie_updated)
        self.settings_page.cookie_updated.connect(self._on_cookie_updated)
        self.settings_page.shortcuts_changed.connect(self.reload_shortcuts)

        self.stack.setCurrentIndex(0)

        pt = QApplication.instance().font().pointSize()
        self.setStyleSheet(build_stylesheet(pt))

        # 剪贴板监听：用序列号检测，解决"同一内容复制两次"问题
        self._last_clip_seq = self._get_clipboard_seq()
        self._last_clipboard = ""
        self._download_active = False
        self._clip_timer = QTimer()
        self._clip_timer.timeout.connect(self._check_clipboard)
        self._clip_timer.start(1500)

        # 快捷键
        self._setup_shortcuts()

        # 单实例监听
        if _instance_socket:
            self._instance_srv = _instance_socket
            self._instance_srv.newConnection.connect(self._on_second_instance)

        # 后台信号 → 主线程回调
        self._version_signal.connect(self._on_version_result)
        self._nav_signal.connect(self._on_nav_signal)
        QTimer.singleShot(2000, self._check_version)

        # 延迟预暖 daemon，避开 QtWebEngine 登录初始化的 Chromium 冲突
        QTimer.singleShot(2000, self._prefetch_own)

    def _prefetch_own(self):
        """后台预加载：已登录则自动获取自己主页数据"""
        from src.cookie import load_cookie
        cookie = load_cookie()
        if not cookie or "sessionid=" not in cookie:
            return
        try:
            self.batch_page._detect_own()
        except Exception:
            pass

    # ── 剪贴板监听 ──

    def set_download_active(self, active: bool):
        """下载中暂停剪贴板检测"""
        self._download_active = active

    @staticmethod
    def _get_clipboard_seq() -> int:
        """获取 Windows 剪贴板序列号，每次 Ctrl+C 都会递增"""
        import ctypes
        try:
            return ctypes.windll.user32.GetClipboardSequenceNumber()
        except Exception:
            return 0

    def _check_clipboard(self):
        """检测剪贴板中的抖音链接（用序列号，内容不变也能检测）"""
        if self._download_active:
            return
        if not load_settings().get("auto_raise", True):
            return
        try:
            # 用 Windows 剪贴板序列号检测，内容不变但 Ctrl+C 过也能检测
            seq = self._get_clipboard_seq()
            if seq == self._last_clip_seq:
                return
            self._last_clip_seq = seq

            clip = QApplication.clipboard().text()
            if not clip:
                return

            # 过滤：含多行日志标记（[检测] [解析] 等）说明是从日志区复制的，跳过
            if clip.count('\n') >= 1 and clip.lstrip().startswith('['):
                return

            import re
            # 检测所有抖音分享链接
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

            # 窗口置顶
            if load_settings().get("auto_raise", True):
                self.showNormal()
                from src.environ import force_raise_window
                force_raise_window(self)

            is_video = "/video/" in found or "/note/" in found
            is_user = "/user/" in found or "/share/user/" in found
            is_short = "v.douyin.com" in found
            if is_video:
                self._navigate_single(clip)
            elif is_user:
                self._navigate_batch(clip)
            elif is_short:
                # 短链后台解析，不阻塞 UI
                import threading as _th
                _th.Thread(
                    target=lambda u=found, c=clip: self._resolve_short_async(u, c),
                    daemon=True,
                ).start()
            else:
                return
        except Exception:
            import traceback
            try:
                with open(EXE_DIR / "_crash.log", "a", encoding="utf-8") as f:
                    f.write(f"[{time.strftime('%H:%M:%S')}] clipboard error:\n{traceback.format_exc()}\n")
            except Exception:
                pass

    def _navigate_batch(self, clip: str):
        self.stack.setCurrentIndex(3)
        page = self.batch_page
        page._tab_other.setChecked(True); page._tab_own.setChecked(False)
        page._style_tabs(); page._content.setCurrentIndex(0)
        import re
        clean_url = clip
        for pat in [r'https?://[^\s]+']:
            m = re.search(pat, clip)
            if m:
                clean_url = m.group(0).rstrip('.,;:!?）」)】')
                break
        # URL 原样填入，短链解析交给 _trigger_fetch 后台线程
        page._other_url.setText(clean_url)
        page._trigger_fetch(clean_url)

    @staticmethod
    def _resolve_short_sync(url: str) -> str:
        """同步解析短链，仅供后台线程调用"""
        try:
            from src.environ import USER_AGENT
            from src.cookie import load_cookie
            s = __import__("requests").Session()
            s.headers.update({"User-Agent": USER_AGENT})
            cookie = load_cookie()
            if cookie:
                s.headers.update({"Cookie": cookie})
            r = s.get(url, allow_redirects=True, timeout=3, stream=True)
            r.close()
            return r.url
        except Exception:
            return url

    def _resolve_short_async(self, short_url: str, raw_clip: str):
        """后台线程解析短链 → pyqtSignal 回主线程导航"""
        try:
            resolved = self._resolve_short_sync(short_url)
            if "/user/" in resolved or "/share/user/" in resolved:
                self._nav_signal.emit('batch', raw_clip)
            else:
                self._nav_signal.emit('single', raw_clip)
        except Exception:
            pass

    def _on_nav_signal(self, page_type: str, raw_clip: str):
        """主线程接收导航信号，跳转到对应页面"""
        if page_type == 'batch':
            self._navigate_batch(raw_clip)
        else:
            self._navigate_single(raw_clip)

    def _navigate_single(self, clip: str):
        self.stack.setCurrentIndex(2)
        # 只填入提取到的干净 URL
        clean_url = clip
        import re
        m = re.search(r'https?://v\.douyin\.com/[^\s]+|https?://(?:www\.)?douyin\.com/(?:video|note)/\d+[^\s]*', clip)
        if m:
            clean_url = m.group(0).rstrip('.,;:!?）」)】')
        self.single_page.url_input.setText(clean_url)

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
        self.douyin_page.refresh_cookie_status()
        self.settings_page.refresh_cookie_status()
        self.batch_page.reset_own_cache()
        # 登录后如果正在看"自己"标签，自动刷新
        self.batch_page.refresh_own_if_active()
        # 延迟重启 sign-server 加载新 cookie（stop+启都放 QTimer，不卡 UI）
        from src.webview_api import stop_server, start_server
        QTimer.singleShot(3000, lambda: (stop_server(), start_server()))

    # ── 字体/主题 ──

    def _apply_font(self, font: QFont):
        app = QApplication.instance()
        app.setFont(font)
        self.setStyleSheet(build_stylesheet(font.pointSize()))
        for w in self.findChildren(QWidget):
            w.updateGeometry()
        self.updateGeometry()

    # ── 快捷键 ──

    def _setup_shortcuts(self):
        self._shortcuts = {}  # {name: QShortcut}
        cfg = load_settings().get("shortcuts", {})

        sc = QShortcut(QKeySequence(cfg.get("home", "Ctrl+H")), self)
        sc.activated.connect(self._go_home)
        self._shortcuts["home"] = sc

        sc = QShortcut(QKeySequence(cfg.get("quit", "Ctrl+Q")), self)
        sc.activated.connect(self._real_quit)
        self._shortcuts["quit"] = sc

        sc = QShortcut(QKeySequence(cfg.get("settings", "Ctrl+,")), self)
        sc.activated.connect(lambda: self.stack.setCurrentIndex(4))
        self._shortcuts["settings"] = sc

        sc = QShortcut(QKeySequence(cfg.get("toggle_tray", "Escape")), self)
        sc.activated.connect(lambda: self.hide() if self._tray and self._tray.isVisible() else None)
        self._shortcuts["toggle_tray"] = sc

    def reload_shortcuts(self):
        """立即生效新的快捷键绑定"""
        if not hasattr(self, '_shortcuts'):
            return
        cfg = load_settings().get("shortcuts", {})
        for name, sc in self._shortcuts.items():
            new_key = cfg.get(name, "")
            if new_key:
                sc.setKey(QKeySequence(new_key))

    # ── 版本更新 ──

    def _show_about(self):
        """关于 Origami"""
        from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton
        dlg = QDialog(self)
        dlg.setWindowTitle("关于 Origami")
        dlg.setFixedSize(font_scale(380), font_scale(420))
        dlg.setStyleSheet("QDialog { background: #0A0A14; }")
        layout = QVBoxLayout(dlg)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(10)

        # 图标
        icon_lbl = QLabel()
        for sz in (256, 128, 72, 48, 32):
            pix = self._app_icon.pixmap(sz, sz)
            if not pix.isNull():
                icon_lbl.setPixmap(pix.scaled(72, 72, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
                break
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(icon_lbl)

        # 名称 + 版本
        name = QLabel(f"Origami  v{VERSION}")
        name.setStyleSheet(f"font-size: {scaled_font(18)}px; font-weight: 800; color: #F1F5F9;")
        name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(name)

        tagline = QLabel("多功能内容下载工具")
        tagline.setStyleSheet(f"font-size: {scaled_font(12)}px; color: #64748B;")
        tagline.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(tagline)

        # 分隔线
        from PyQt6.QtWidgets import QFrame
        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("background: #252550; max-height: 1px; border: none;")
        layout.addWidget(sep)

        # 技术栈
        tech = QLabel("Python 3.12 · PyQt6 · Node.js · Puppeteer · Requests")
        tech.setStyleSheet(f"font-size: {scaled_font(10)}px; color: #94A3B8;")
        tech.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(tech)

        # 平台
        plat = QLabel("支持平台：抖音 | B站(即将) | 微博(即将)")
        plat.setStyleSheet(f"font-size: {scaled_font(10)}px; color: #475569;")
        plat.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(plat)

        layout.addSpacing(8)

        # 作者
        author = QLabel("© 2026 Renxint")
        author.setStyleSheet(f"font-size: {scaled_font(11)}px; color: #64748B;")
        author.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(author)

        link = QLabel('<a href="https://gitee.com/Renxint/origami" style="color:#E11D48;">Gitee 仓库</a>')
        link.setStyleSheet(f"font-size: {scaled_font(11)}px;")
        link.setAlignment(Qt.AlignmentFlag.AlignCenter)
        link.setOpenExternalLinks(True)
        layout.addWidget(link)

        license_lbl = QLabel("MIT License")
        license_lbl.setStyleSheet(f"font-size: {scaled_font(9)}px; color: #475569;")
        license_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(license_lbl)

        layout.addSpacing(8)
        ok = QPushButton("确定")
        ok.setCursor(Qt.CursorShape.PointingHandCursor)
        ok.clicked.connect(dlg.accept)
        layout.addWidget(ok, alignment=Qt.AlignmentFlag.AlignCenter)

        dlg.exec()

    def _check_version(self):
        """后台线程检查版本，GitHub 优先，Gitee 兜底"""
        import threading

        def _fetch():
            for url in VERSION_URLS:
                try:
                    r = requests.get(url, timeout=8, headers={"User-Agent": "Origami-Update"})
                    r.raise_for_status()
                    self._version_signal.emit(r.json())
                    return
                except Exception:
                    continue
            self._version_signal.emit({"_error": "all URLs failed"})
        threading.Thread(target=_fetch, daemon=True).start()

    def _on_version_result(self, data: dict):
        """主线程接收版本信息，弹窗提示更新"""
        try:
            if "_error" in data:
                print(f"[Update] check failed: {data['_error']}")
                return
            remote = data.get("version", "")
            if compare_versions(remote, VERSION) > 0:
                note = data.get("note", "")
                reply = QMessageBox.question(
                    self, "发现新版本",
                    f"当前版本: v{VERSION}\n最新版本: v{remote}\n\n"
                    f"{note}\n\n是否打开下载页面?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                )
                if reply == QMessageBox.StandardButton.Yes:
                    import webbrowser
                    webbrowser.open("https://github.com/Renxint/origami/releases")
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
        a_about.triggered.connect(self._show_about)
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

    # ── 关闭逻辑（所有状态存 settings.json，不依赖 QSettings） ──

    def _close_preference(self) -> str:
        """从 settings.json 读取关闭偏好: 'tray' | 'quit' | None"""
        return load_settings().get("close_preference", None)

    def closeEvent(self, event):
        # 系统不支持托盘 → 直接退出
        if not QSystemTrayIcon.isSystemTrayAvailable():
            self._real_quit()
            return

        # 托盘已开启 → 最小化
        if self._tray and self._tray.isVisible():
            self.hide()
            event.ignore()
            return

        # 已记住偏好
        pref = self._close_preference()
        if pref == "tray":
            from src.settings.store import set as store_set
            store_set("tray_enabled", True)
            self._setup_tray()
            self.hide()
            event.ignore()
            return
        if pref == "quit":
            self._real_quit()
            return

        # 首次关闭 → 弹窗询问
        event.ignore()
        QTimer.singleShot(0, self._show_close_dialog)

    def _show_close_dialog(self):
        from PyQt6.QtWidgets import QMessageBox, QCheckBox

        msg = QMessageBox(None)
        msg.setWindowTitle("关闭 Origami")
        msg.setText("是否最小化到系统托盘而不是退出？")
        msg.setIcon(QMessageBox.Icon.Question)
        msg.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        msg.setDefaultButton(QMessageBox.StandardButton.Yes)
        msg.button(QMessageBox.StandardButton.Yes).setText("是")
        msg.button(QMessageBox.StandardButton.No).setText("否")
        cb = QCheckBox("不再询问")
        msg.setCheckBox(cb)
        reply = msg.exec()

        from src.settings.store import set as store_set
        if reply == QMessageBox.StandardButton.Yes:
            if cb.isChecked():
                store_set("close_preference", "tray")
            store_set("tray_enabled", True)
            self._setup_tray()
            self.hide()
        elif cb.isChecked():
            store_set("close_preference", "quit")
            self.hide()
            QTimer.singleShot(0, self._real_quit)
        else:
            self.hide()
            QTimer.singleShot(0, self._real_quit)

    def _real_quit(self):
        from src.settings.store import set as store_set
        import src.environ
        src.environ.APP_SHUTTING_DOWN = True  # 抑制后台线程报错
        try:
            geo_hex = self.saveGeometry().toHex().data().decode()
            store_set("geometry", {"geo": geo_hex})
        except Exception:
            pass
        if self._tray:
            self._tray.hide()
        try:
            if _instance_socket:
                _instance_socket.close()
        except Exception:
            pass
        # 杀掉 sign-server，防止僵尸进程
        from src.webview_api import stop_server
        stop_server()
        # 设置已保存，直接硬退出，不依赖 Qt 事件循环
        import os as _os
        _os._exit(0)

    def tray_notify(self, title: str, msg: str,
                    icon=QSystemTrayIcon.MessageIcon.Information,
                    duration: int = 3000):
        if self._tray:
            self._tray.showMessage(title, msg, icon, duration)
