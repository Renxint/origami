# -*- coding: utf-8 -*-
"""
Origami — 单视频下载页面

独立模块，包含 SingleDownloadThread。
后续 B站/微博 单视频下载通过平台适配器切换。
"""

import os
import re
import json
import time
import subprocess
import threading
from pathlib import Path

import requests

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QLineEdit, QTextEdit, QProgressBar,
    QListWidget, QListWidgetItem, QSplitter,
    QFileDialog, QMenu, QApplication,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import QSizePolicy
from PyQt6.QtGui import QAction

from src.theme import font_scale, scaled_font, DARK_THEME as T
from src.environ import (
    OUTPUT_SINGLE, BOOTSTRAP_JS, NODE_CMD,
    USER_AGENT, CREATE_NO_WINDOW,
)
from src.utils import clean_name, pick_best_video_url
from src.cookie import load_cookie, save_cookie
from src.gui.dialogs.cookie_dialog import show_login_dialog
from src.settings.store import load as load_settings


def colored_log(msg: str) -> str:
    """给日志文本加 HTML 颜色"""
    if msg.startswith("[ERROR]") or msg.startswith("[FAIL]"):
        return f'<span style="color:#EF4444">{msg}</span>'
    elif msg.startswith("[OK]") or msg.startswith("===== DONE"):
        return f'<span style="color:#22C55E">{msg}</span>'
    elif msg.startswith("[>>]") or msg.startswith("[翻页]"):
        return f'<span style="color:#94A3B8">{msg}</span>'
    elif msg.startswith("[WARN]"):
        return f'<span style="color:#F59E0B">{msg}</span>'
    return msg


def ensure_cookie(parent_widget) -> str:
    """确保已登录，未登录则弹出登录窗口"""
    cookie_str = load_cookie()
    if cookie_str:
        return cookie_str
    show_login_dialog(parent_widget)
    return load_cookie()


# ═══════════════════════════════════════════════════════════
# 单视频下载线程
# ═══════════════════════════════════════════════════════════
class SingleDownloadThread(QThread):
    log = pyqtSignal(str)
    progress = pyqtSignal(int)
    finished = pyqtSignal(bool, str)

    def __init__(self, raw_text: str, save_dir: str):
        super().__init__()
        self.raw_text = raw_text
        self.save_dir = Path(save_dir) if save_dir else OUTPUT_SINGLE

    def run(self):
        try:
            self.log.emit("[>>] 解析链接...")
            aweme_id = self._resolve(self.raw_text)
            self.log.emit(f"[OK] 视频ID: {aweme_id}")

            cookie = load_cookie()

            self.log.emit("[>>] 获取数据 (启动浏览器 ~15s)...")
            aweme = self._fetch(aweme_id, cookie)

            desc = aweme.get("desc", "") or aweme_id
            author = aweme.get("author", {}).get("nickname", "")
            self.log.emit(f"  作者: {author}")
            self.log.emit(f"  描述: {desc[:60]}")

            self._download_aweme(aweme)
        except Exception as e:
            self.log.emit(f"[ERROR] {e}")
            self.finished.emit(False, str(e))

    def _resolve(self, raw: str) -> str:
        for pat in [
            r'https?://v\.douyin\.com/[A-Za-z0-9_\-/]+',
            r'https?://(?:www\.)?douyin\.com/(?:video|note)/(\d+)',
        ]:
            m = re.search(pat, raw)
            if m:
                url = m.group(0)
                break
        else:
            raise ValueError("未识别抖音链接")

        m = re.search(r'/(?:video|note)/(\d+)', url)
        if m:
            return m.group(1)

        if 'v.douyin.com' in url:
            s = requests.Session()
            s.headers.update({"User-Agent": USER_AGENT})
            r = s.get(url, allow_redirects=True, timeout=15, stream=True)
            r.close()
            m = re.search(r'/(?:video|note)/(\d+)', r.url)
            if m:
                return m.group(1)
        raise ValueError(f"无法解析: {url}")

    def _fetch(self, aweme_id: str, cookie: str) -> dict:
        self.save_dir.mkdir(parents=True, exist_ok=True)
        log_file = self.save_dir / "_bootstrap.json"
        err_file = self.save_dir / "_bootstrap_err.log"

        log_file.unlink(missing_ok=True)
        err_file.unlink(missing_ok=True)

        cookie_file = self.save_dir / "_cookie_tmp.txt"
        # 过滤掉空 name 的 Cookie（Puppeteer 不兼容）
        clean = "; ".join(c for c in cookie.split("; ") if "=" in c and c.split("=", 1)[0])
        cookie_file.write_text(clean, encoding="utf-8")

        last_error = None
        try:
            for attempt in (1, 2):
                try:
                    with open(log_file, "w", encoding="utf-8") as out, \
                         open(err_file, "w", encoding="utf-8") as err:
                        subprocess.run(
                            [NODE_CMD, str(BOOTSTRAP_JS), aweme_id, str(cookie_file)],
                            stdout=out, stderr=err,
                            timeout=120, cwd=str(BOOTSTRAP_JS.parent),
                            creationflags=CREATE_NO_WINDOW,
                        )
                    raw_text = log_file.read_text(encoding="utf-8").strip()
                    if not raw_text:
                        err_text = err_file.read_text(encoding="utf-8") if err_file.exists() else ""
                        last_error = RuntimeError(f"bootstrap 无输出\nstderr: {err_text[:500]}")
                        if attempt == 1:
                            self.log.emit("[>>] 重试中...")
                            time.sleep(5)
                            continue
                        raise last_error
                    data = json.loads(raw_text)
                    if "_error" in data:
                        err = data["_error"]
                        if "browser" in err.lower() and attempt == 1:
                            self.log.emit("[>>] 重试中...")
                            time.sleep(5)
                            continue
                        raise RuntimeError(err)
                    return data.get("aweme_detail", {})
                except subprocess.TimeoutExpired:
                    if attempt == 1:
                        self.log.emit("[>>] 超时，重试...")
                        time.sleep(5)
                        continue
                    raise
            raise last_error or RuntimeError("获取视频数据失败")
        finally:
            log_file.unlink(missing_ok=True)
            err_file.unlink(missing_ok=True)
            cookie_file.unlink(missing_ok=True)

    def _download_aweme(self, aweme: dict):
        desc = aweme.get("desc", "") or aweme.get("aweme_id", "untitled")
        author = aweme.get("author", {}).get("nickname", "")
        video = aweme.get("video")
        images = aweme.get("images") or []

        safe_a = clean_name(author, 20)
        safe_d = clean_name(desc, 40)
        post_dir = self.save_dir / f"{safe_a}（{safe_d}）"
        post_dir.mkdir(parents=True, exist_ok=True)

        stats = {"v": 0, "i": 0, "f": 0}

        if video:
            url = pick_best_video_url(video)
            if url:
                if self._dl(url, post_dir / "video.mp4"):
                    stats["v"] += 1
                else:
                    stats["f"] += 1

        if images:
            for j, img in enumerate(images):
                urls = img.get("url_list", [])
                img_url = next(
                    (u for u in urls if "jpeg" in u.lower() or "jpg" in u.lower()),
                    urls[0] if urls else "",
                )
                if not img_url:
                    continue
                is_live = img.get("live_photo_type", 0) == 1
                tag = "_实况" if is_live else ""
                if self._dl(img_url, post_dir / f"{j+1:02d}{tag}.jpg"):
                    stats["i"] += 1
                else:
                    stats["f"] += 1
                if is_live:
                    lv = img.get("video") or {}
                    live_url = pick_best_video_url(lv)
                    if live_url:
                        if self._dl(live_url, post_dir / f"{j+1:02d}{tag}.mp4"):
                            stats["v"] += 1
                        else:
                            stats["f"] += 1

        (post_dir / "desc.txt").write_text(desc, encoding="utf-8")
        self.log.emit(f"===== 视频:{stats['v']} 图片:{stats['i']} 失败:{stats['f']} =====")
        self.finished.emit(True, f"完成! {author}")

    def _dl(self, url: str, path: Path) -> bool:
        if path.exists():
            self.log.emit(f"  [SKIP] {path.name}")
            self.progress.emit(100)
            return True
        headers = {"User-Agent": USER_AGENT, "Referer": "https://www.douyin.com/"}
        try:
            r = requests.get(url, headers=headers, stream=True, timeout=120)
            r.raise_for_status()
            total = int(r.headers.get("content-length", 0))
            dl = 0
            with open(path, "wb") as f:
                for chunk in r.iter_content(8192):
                    f.write(chunk)
                    dl += len(chunk)
                    if total:
                        self.progress.emit(dl * 100 // total)
            self.log.emit(f"  [OK] {path.name} ({dl/1024/1024:.1f}MB)")
            self.progress.emit(100)
            return True
        except Exception as e:
            self.log.emit(f"  [FAIL] {e}")
            if path.exists():
                path.unlink()
            return False


# ═══════════════════════════════════════════════════════════
# 单视频页面
# ═══════════════════════════════════════════════════════════
class SinglePage(QWidget):
    back_clicked = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.thread = None
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(16, 16, 16, 16)

        # 顶栏
        top = QHBoxLayout()
        back = QPushButton("  < 返回")
        back.setObjectName("secondaryBtn")
        back.setCursor(Qt.CursorShape.PointingHandCursor)
        back.clicked.connect(self.back_clicked)
        back.setMinimumSize(font_scale(90), font_scale(36))
        top.addWidget(back)

        title = QLabel("单视频下载")
        title.setStyleSheet(f"font-size: {scaled_font(20)}px; font-weight: bold; color: #E11D48;")
        top.addWidget(title)
        top.addStretch()
        layout.addLayout(top)

        # URL 输入
        url_row = QHBoxLayout()
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("粘贴分享链接或口令（长按复制...）")
        self.url_input.setMinimumHeight(font_scale(42))
        self.url_input.returnPressed.connect(self._start)
        url_row.addWidget(self.url_input)
        self.dl_btn = QPushButton("开始下载")
        self.dl_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.dl_btn.clicked.connect(self._start)
        self.dl_btn.setMinimumHeight(font_scale(42))
        self.dl_btn.setMinimumWidth(font_scale(100))
        self.dl_btn.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum)
        url_row.addWidget(self.dl_btn)
        layout.addLayout(url_row)

        # 保存路径
        path_row = QHBoxLayout()
        path_row.setSpacing(10)
        path_row.addWidget(QLabel("保存到"))
        self.path_input = QLineEdit()
        settings = load_settings()
        self.path_input.setText(
            settings.get("download_paths", {}).get("single", "")
            or str(OUTPUT_SINGLE)
        )
        path_row.addWidget(self.path_input)
        browse = QPushButton("浏览...")
        browse.setObjectName("secondaryBtn")
        browse.setCursor(Qt.CursorShape.PointingHandCursor)
        browse.setMinimumHeight(font_scale(36))
        browse.clicked.connect(lambda: self._browse(self.path_input))
        path_row.addWidget(browse)
        layout.addLayout(path_row)

        # 进度条
        self.progress = QProgressBar()
        self.progress.setMinimumHeight(font_scale(6))
        self.progress.setMinimumWidth(font_scale(120))
        self.progress.setVisible(False)
        layout.addWidget(self.progress)

        # 主体：日志 + 已下载列表
        splitter = QSplitter(Qt.Orientation.Horizontal)
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.addWidget(QLabel("下载日志"))
        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        ll.addWidget(self.log_view)
        splitter.addWidget(left)

        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.addWidget(QLabel("已下载"))
        self.downloaded_list = QListWidget()
        self.downloaded_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.downloaded_list.customContextMenuRequested.connect(self._on_context_menu)
        self.downloaded_list.itemDoubleClicked.connect(self._open_folder)
        rl.addWidget(self.downloaded_list)
        open_btn = QPushButton("打开目录")
        open_btn.setObjectName("secondaryBtn")
        open_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        open_btn.clicked.connect(self._open_folder)
        rl.addWidget(open_btn)
        refresh_btn = QPushButton("刷新")
        refresh_btn.setObjectName("secondaryBtn")
        refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        refresh_btn.clicked.connect(self._refresh_downloaded)
        rl.addWidget(refresh_btn)
        splitter.addWidget(right)
        splitter.setSizes([480, 240])
        layout.addWidget(splitter, 1)

        # 状态栏
        self.status = QLabel("就绪")
        self.status.setStyleSheet(f"color: #64748B; font-size: {scaled_font(11)}px; padding: 4px 0;")
        layout.addWidget(self.status)

        self._refresh_downloaded()

    def _browse(self, input_widget: QLineEdit):
        folder = QFileDialog.getExistingDirectory(self, "选择保存目录", input_widget.text())
        if folder:
            input_widget.setText(folder)

    def _refresh_downloaded(self):
        self.downloaded_list.clear()
        out = Path(self.path_input.text().strip()) if self.path_input.text().strip() else OUTPUT_SINGLE
        if not out.exists():
            return
        for d in sorted(out.iterdir(), reverse=True):
            if not d.is_dir():
                continue
            files = sum(1 for _ in d.rglob("*") if _.is_file())
            item = QListWidgetItem(f"{d.name}  [{files}文件]")
            item.setData(Qt.ItemDataRole.UserRole, str(d))
            self.downloaded_list.addItem(item)

    def _open_folder(self):
        item = self.downloaded_list.currentItem()
        out = Path(self.path_input.text().strip()) if self.path_input.text().strip() else OUTPUT_SINGLE
        if item:
            p = item.data(Qt.ItemDataRole.UserRole)
            if p and Path(p).exists():
                os.startfile(p)
        elif out.exists():
            os.startfile(str(out))

    def _start(self):
        text = self.url_input.text().strip()
        if not text:
            return

        cookie = ensure_cookie(self)
        if not cookie:
            self.status.setText("已取消 - Cookie 未设置")
            return

        save_dir = self.path_input.text().strip() or str(OUTPUT_SINGLE)
        self.dl_btn.setEnabled(False)
        self.dl_btn.setText("下载中...")
        self.progress.setVisible(True)
        self.progress.setValue(0)
        self.log_view.clear()

        self.thread = SingleDownloadThread(text, save_dir)
        self.thread.log.connect(self._log)
        self.thread.progress.connect(self.progress.setValue)
        self.thread.finished.connect(self._done)
        self.thread.start()

    def _log(self, msg: str):
        self.log_view.append(colored_log(msg))
        sb = self.log_view.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _on_context_menu(self, pos):
        item = self.downloaded_list.itemAt(pos)
        if not item:
            return
        menu = QMenu(self)
        a1 = menu.addAction("打开文件夹")
        a2 = menu.addAction("复制路径")
        action = menu.exec(self.downloaded_list.mapToGlobal(pos))
        p = item.data(Qt.ItemDataRole.UserRole)
        if not p:
            return
        if action == a1 and Path(p).exists():
            os.startfile(p)
        elif action == a2:
            QApplication.clipboard().setText(p)

    def _done(self, ok: bool, msg: str):
        if ok:
            self.progress.setValue(100)
        self._refresh_downloaded()

        self.dl_btn.setEnabled(True)
        self.dl_btn.setText("开始下载")
        self.status.setText(msg)
        w = self.window()
        if ok and hasattr(w, "tray_notify"):
            w.tray_notify("Origami", "下载完成", duration=3000)
