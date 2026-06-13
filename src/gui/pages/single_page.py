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
    QCheckBox,
    QListWidget, QListWidgetItem, QSplitter,
    QFileDialog, QMenu, QApplication, QMessageBox,
    QFrame,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt6.QtWidgets import QSizePolicy
from PyQt6.QtGui import QAction

from src.gui.fonts import font_scale, scaled_font
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
    progress = pyqtSignal(int, int)  # (current, total)
    finished = pyqtSignal(bool, str)
    author_signal = pyqtSignal(dict)
    gallery_signal = pyqtSignal(list, object)

    def __init__(self, raw_text: str, save_dir: str, music: bool = False):
        super().__init__()
        self.raw_text = raw_text
        self.save_dir = Path(save_dir) if save_dir else OUTPUT_SINGLE
        self.download_music = music

    def run(self):
        import time as _t; _start = _t.time()
        try:
            self.log.emit("[>>] 解析链接...")
            aweme_id = self._resolve(self.raw_text)
            self.log.emit(f"[OK] 视频ID: {aweme_id}")

            cookie = load_cookie()

            self.log.emit("[>>] 获取数据...")
            aweme = self._fetch(aweme_id, cookie)

            desc = aweme.get("desc", "") or aweme_id
            author_info = aweme.get("author", {})
            author = author_info.get("nickname", "")
            avatar = (author_info.get("avatar_thumb", {}) or {}).get("url_list", [""])[0] or ""
            uid = author_info.get("unique_id", "")
            follower = author_info.get("follower_count", 0)

            # 统计信息
            st = aweme.get("statistics", {})
            likes = st.get("digg_count", 0)
            comments_count = st.get("comment_count", 0)
            shares = st.get("share_count", 0)
            collects = st.get("collect_count", 0)

            def _fmt(n: int) -> str:
                if n >= 10000:
                    return f"{n/10000:.1f}w"
                return str(n)

            stats_line = f"点赞{_fmt(likes)}  评论{_fmt(comments_count)}  分享{_fmt(shares)}  收藏{_fmt(collects)}"
            detail = f"抖音号：{uid}" if uid else ""
            if follower:
                detail += f"  粉丝: {_fmt(follower)}"

            self.author_signal.emit({
                "aweme_id": aweme_id,
                "nickname": author,
                "avatar": avatar,
                "desc": desc,
                "stats": stats_line,
                "detail": detail,
                "bio": "",
            })
            self.log.emit(f"  作者: {author}  粉丝: {_fmt(follower)}")
            self.log.emit(f"  统计: {stats_line}")
            self.log.emit(f"  描述: {desc[:60]}")

            # 图集/note：只要有图片就弹选择框
            images = aweme.get("images") or []
            selected_indices = None
            if images:
                evt = threading.Event()
                img_list = []
                for j, img in enumerate(images):
                    urls = img.get("url_list", [])
                    img_url = next((u for u in urls if "jpeg" in u.lower() or "jpg" in u.lower()), urls[0] if urls else "")
                    img_list.append({
                        "index": j, "url": img_url or "",
                        "live": img.get("live_photo_type", 0) == 1,
                        "thumb": None,  # 缩略图由 UI 异步加载
                    })
                self.gallery_signal.emit(img_list, evt)
                evt.wait(120)
                selected_indices = getattr(self, '_selected_img_indices', None)

            self._download_aweme(aweme, selected_indices)
            e = int(_t.time() - _start); h, r = divmod(e, 3600); m, s = divmod(r, 60)
            ts = f"{h}时{m}分{s}秒" if h else f"{m}分{s}秒"
            self.finished.emit(True, f"完成 | 耗时 {ts}")
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
        """通过常驻浏览器服务获取视频详情"""
        from src.webview_api import call_server
        for attempt in (1, 2):
            data = call_server('video', aweme_id=aweme_id)
            if "_error" not in data:
                return data.get("aweme_detail", {})
            err = data.get("_error", "")
            if "browser" in err.lower() and attempt == 1:
                self.log.emit("[>>] 重试中...")
                time.sleep(3)
                continue
            raise RuntimeError(err)
        raise RuntimeError("获取视频数据失败")
    def _download_aweme(self, aweme: dict, selected_indices: set = None):
        desc = aweme.get("desc", "") or aweme.get("aweme_id", "untitled")
        author = aweme.get("author", {}).get("nickname", "")
        video = aweme.get("video")
        images = aweme.get("images") or []

        safe_a = clean_name(author, 20)
        safe_d = clean_name(desc, 40)
        post_dir = self.save_dir / f"{safe_a}（{safe_d}）"
        _dir_created = False
        def _ensure_dir():
            nonlocal _dir_created
            if not _dir_created:
                post_dir.mkdir(parents=True, exist_ok=True)
                _dir_created = True

        # 计算总任务数
        total = 0
        if video and pick_best_video_url(video): total += 1
        if images and not (selected_indices is not None and len(selected_indices) == 0):
            for j, img in enumerate(images):
                if selected_indices is not None and j not in selected_indices: continue
                total += 1
                if img.get("live_photo_type", 0) == 1: total += 1
        if self.download_music:
            music = aweme.get("music", {})
            if music and ((music.get("play_url") or {}).get("url_list") or (music.get("play_url_h265") or {}).get("url_list")):
                total += 1
        if total == 0: total = 1

        # 高速模式：收集所有任务并发下载
        from src.settings.store import load as _ls
        if _ls().get("high_speed", False):
            _tasks = []
            is_live = aweme.get("is_live_photo", False) or aweme.get("media_type") == 42
            is_pure_video = bool(video) and not images and not is_live
            if is_pure_video:
                vurl = pick_best_video_url(video)
                if vurl:
                    _ensure_dir(); _tasks.append((vurl, post_dir / f"{safe_d}.mp4"))
            if images and not (selected_indices is not None and len(selected_indices) == 0):
                for j, img in enumerate(images):
                    if selected_indices is not None and j not in selected_indices: continue
                    _ensure_dir()
                    urls = img.get("url_list", [])
                    img_url = next((u for u in urls if "jpeg" in u.lower() or "jpg" in u.lower()), urls[0] if urls else "")
                    if img_url:
                        _tasks.append((img_url, post_dir / f"{j+1:02d}.jpg"))
                    if img.get("live_photo_type", 0) == 1:
                        lv = img.get("video") or {}
                        live_url = pick_best_video_url(lv)
                        if live_url:
                            _tasks.append((live_url, post_dir / f"{j+1:02d}_实况.mp4"))
            if self.download_music:
                music = aweme.get("music", {})
                if music:
                    mu = ((music.get("play_url") or {}).get("url_list") or
                          (music.get("play_url_h265") or {}).get("url_list") or [])
                    if mu:
                        _ensure_dir()
                        _tasks.append((mu[0], post_dir / f"{safe_d}_bgm.mp3"))
            self._dl_batch(_tasks, total)
            return

        cur = 0
        def _tick():
            nonlocal cur
            cur += 1
            self.progress.emit(cur, total)

        # 纯视频才下载，图集/note 跳过 video.mp4
        if video and not images:
            url = pick_best_video_url(video)
            if url:
                _ensure_dir()
                self._dl(url, post_dir / "video.mp4")
                _tick()

        if images:
            skip_all = selected_indices is not None and len(selected_indices) == 0
            if skip_all:
                self.log.emit("[SKIP] 已取消图片下载")
                images = []
            for j, img in enumerate(images):
                if selected_indices is not None and j not in selected_indices:
                    continue
                _ensure_dir()
                urls = img.get("url_list", [])
                img_url = next(
                    (u for u in urls if "jpeg" in u.lower() or "jpg" in u.lower()),
                    urls[0] if urls else "",
                )
                if not img_url:
                    _tick(); continue
                is_live = img.get("live_photo_type", 0) == 1
                tag = "_实况" if is_live else ""
                ok = self._dl(img_url, post_dir / f"{j+1:02d}{tag}.jpg")
                _tick()
                if is_live:
                    lv = img.get("video") or {}
                    live_url = pick_best_video_url(lv)
                    if live_url:
                        self._dl(live_url, post_dir / f"{j+1:02d}{tag}.mp4")
                    _tick()

        if self.download_music:
            music = aweme.get("music", {})
            if music:
                title = music.get("title", "") or music.get("author", "") or "bgm"
                play = music.get("play_url") or {}
                music_url = (play.get("url_list") or [""])[0]
                if not music_url:
                    music_url = (music.get("play_url_h265") or {}).get("url_list", [""])[0]
                if music_url:
                    _ensure_dir()
                    self._dl(music_url, post_dir / f"BGM_{clean_name(title,30)}.mp3")
                    self.log.emit(f"[BGM] {title}")
                _tick()

        if _dir_created:
            (post_dir / "desc.txt").write_text(desc, encoding="utf-8")
        self.finished.emit(True, f"完成! {author}")

    def _dl(self, url: str, path: Path) -> bool:
        if path.exists():
            self.log.emit(f"  [SKIP] {path.name}")
            return True
        headers = {"User-Agent": USER_AGENT, "Referer": "https://www.douyin.com/"}
        try:
            r = requests.get(url, headers=headers, stream=True, timeout=120)
            r.raise_for_status()
            dl = 0
            with open(path, "wb") as f:
                for chunk in r.iter_content(8192):
                    f.write(chunk)
                    dl += len(chunk)
            self.log.emit(f"  [OK] {path.name} ({dl/1024/1024:.1f}MB)")
            return True
        except Exception as e:
            self.log.emit(f"  [FAIL] {e}")
            if path.exists():
                path.unlink()
            return False

    def _dl_batch(self, tasks: list, total: int):
        """并发下载一组文件（高速模式，逐条日志+进度）"""
        from concurrent.futures import ThreadPoolExecutor, as_completed
        from src.settings.store import load as _ls
        workers = 20 if _ls().get("high_speed", False) else 6

        # 拆分：已存在 vs 待下载
        skip_tasks = [(u, p) for u, p in tasks if p.exists()]
        pending = [(u, p) for u, p in tasks if not p.exists()]
        for url, path in skip_tasks:
            self.log.emit(f"  [SKIP] {path.name}")
        self.progress.emit(len(skip_tasks), total)

        if not pending:
            return

        def _dl_one(url, path):
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                r = requests.get(url, stream=True, timeout=120,
                                 headers={"User-Agent": USER_AGENT, "Referer": "https://www.douyin.com/"})
                r.raise_for_status()
                with open(path, "wb") as f:
                    for chunk in r.iter_content(8192):
                        f.write(chunk)
                return True, path
            except Exception:
                if path.exists():
                    path.unlink()
                return False, path

        # 并发下载，结果收集后按文件名排序输出
        results = {}
        done = len(skip_tasks)
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(_dl_one, u, p): p for u, p in pending}
            for f in as_completed(futures):
                path = futures[f]
                ok, p = f.result()
                results[str(path)] = ok
                done += 1
                self.progress.emit(done, total)
        # 按文件名排序输出日志
        for path_str in sorted(results.keys()):
            p = Path(path_str)
            ok = results[path_str]
            if ok:
                sz = p.stat().st_size / 1024 / 1024
                self.log.emit(f"  [OK] {p.name} ({sz:.1f}MB)")
            else:
                self.log.emit(f"  [FAIL] {p.name}")


# ═══════════════════════════════════════════════════════════
# 单视频页面
# ═══════════════════════════════════════════════════════════
class SinglePage(QWidget):
    back_clicked = pyqtSignal()
    _comments_ready = pyqtSignal(object)
    _dl_log_signal = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self._comments_ready.connect(self._apply_comments)
        self._dl_log_signal.connect(lambda msg: self.log_view.append(msg))
        self.thread = None
        self._auto_timer = QTimer()
        self._auto_timer.setSingleShot(True)
        self._auto_timer.timeout.connect(self._start)
        self._refresh_timer = QTimer()
        self._refresh_timer.setInterval(3000)
        self._refresh_timer.timeout.connect(self._refresh_downloaded)
        self._refresh_timer.start()
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

        # 作者信息（右上角紧凑显示：头像 + 昵称）
        self._author_avatar = QLabel()
        av_sz = font_scale(30)
        self._author_avatar.setFixedSize(av_sz, av_sz)
        self._author_avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._author_avatar.setStyleSheet(
            f"border: 1px solid #334155; border-radius: {av_sz//2}px;"
        )
        self._author_avatar.hide()
        top.addWidget(self._author_avatar)
        self._author_name = QLabel("")
        self._author_name.setStyleSheet(
            f"color: #94A3B8; font-size: {scaled_font(11)}px; "
            "border: none; background: transparent;"
        )
        top.addWidget(self._author_name)
        self._author_stats = QLabel("")
        self._author_stats.setStyleSheet(
            f"color: #E2E8F0; font-size: {scaled_font(11)}px; "
            "border: none; background: transparent;"
        )
        top.addWidget(self._author_stats)
        layout.addLayout(top)

        # 作品简介
        self._aweme_desc = QLineEdit()
        self._aweme_desc.setReadOnly(True)
        self._aweme_desc.setStyleSheet(
            f"color: #64748B; font-size: {scaled_font(11)}px; "
            "background: transparent; border: none; padding: 0px 4px;"
        )
        self._aweme_desc.hide()
        layout.addWidget(self._aweme_desc)

        # URL 输入
        url_row = QHBoxLayout()
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("粘贴分享链接或口令（长按复制...）")
        self.url_input.setMinimumHeight(font_scale(42))
        self.url_input.returnPressed.connect(self._start)
        self.url_input.textChanged.connect(self._on_url_changed)
        url_row.addWidget(self.url_input)
        clear_btn = QPushButton("✕")
        clear_btn.setFixedSize(font_scale(32), font_scale(42))
        clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        clear_btn.setObjectName("secondaryBtn")
        clear_btn.setToolTip("清除链接")
        clear_btn.clicked.connect(self._clear_all)
        url_row.addWidget(clear_btn)
        self.dl_btn = QPushButton("开始下载")
        self.dl_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.dl_btn.clicked.connect(self._start)
        self.dl_btn.setMinimumHeight(font_scale(42))
        self.dl_btn.setMinimumWidth(font_scale(100))
        self.dl_btn.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum)
        url_row.addWidget(self.dl_btn)
        # BGM 移到画廊弹窗内选择

        self._comment_btn = QPushButton("💬 评论")
        self._comment_btn.setObjectName("secondaryBtn")
        self._comment_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._comment_btn.setEnabled(False)
        self._comment_btn.clicked.connect(self._show_comments)
        self._comment_btn.setMinimumWidth(font_scale(80))
        url_row.addWidget(self._comment_btn)
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

    def _delete_folder(self, dir_path: Path):
        import shutil
        reply = QMessageBox.question(
            self, "确认删除", f"确定删除目录？\n{dir_path.name}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            try:
                shutil.rmtree(dir_path, ignore_errors=True)
            except Exception as e:
                QMessageBox.warning(self, "删除失败", str(e))

    def _refresh_downloaded(self):
        self.downloaded_list.clear()
        out = Path(self.path_input.text().strip()) if self.path_input.text().strip() else OUTPUT_SINGLE
        if not out.exists():
            return
        for d in sorted(out.iterdir(), key=lambda p: p.stat().st_mtime):
            if not d.is_dir():
                continue
            files = sum(1 for _ in d.rglob("*") if _.is_file())
            row = QWidget()
            row.setMinimumHeight(font_scale(26))
            row.setStyleSheet("background: transparent;")
            lay = QHBoxLayout(row)
            lay.setContentsMargins(4, 0, 4, 0)
            lay.setSpacing(6)
            del_btn = QPushButton("X")
            del_btn.setFixedSize(font_scale(20), font_scale(20))
            del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            del_btn.setStyleSheet(
                "QPushButton { color: #EF4444; border: none; background: transparent; "
                "font-size: 12px; font-weight: bold; padding: 0; }"
                "QPushButton:hover { color: #FFF; background: #EF4444; border-radius: 3px; }"
            )
            del_btn.clicked.connect(lambda checked, p=d: self._delete_folder(p))
            lay.addWidget(del_btn)
            label = QLabel(f"{d.name}  [{files}文件]")
            label.setStyleSheet(f"color: #E2E8F0; font-size: {scaled_font(10)}px; border: none;")
            lay.addWidget(label, 1)
            item = QListWidgetItem()
            item.setSizeHint(row.sizeHint())
            item.setData(Qt.ItemDataRole.UserRole, str(d))
            self.downloaded_list.addItem(item)
            self.downloaded_list.setItemWidget(item, row)

    def _open_folder(self):
        item = self.downloaded_list.currentItem()
        out = Path(self.path_input.text().strip()) if self.path_input.text().strip() else OUTPUT_SINGLE
        if item:
            p = item.data(Qt.ItemDataRole.UserRole)
            if p and Path(p).exists():
                os.startfile(p)
        elif out.exists():
            os.startfile(str(out))

    def _on_url_changed(self, text: str):
        """粘贴后 800ms 自动解析"""
        if not text.strip():
            return
        self._auto_timer.start(800)

    def _on_gallery(self, img_list: list, evt):
        """图集选择弹窗（秒开，缩略图异步加载）"""
        from PyQt6.QtWidgets import QDialog, QScrollArea
        from PyQt6.QtGui import QPixmap
        import requests as _req
        from src.environ import USER_AGENT
        import queue as qu

        dlg = QDialog(self)
        dlg.setWindowTitle(f"选择要下载的图片（共{len(img_list)}张）")
        dlg.resize(font_scale(520), font_scale(480))
        dlg.setStyleSheet("QDialog { background: #0A0A14; }")
        layout = QVBoxLayout(dlg)
        layout.setSpacing(6)

        music_cb = QCheckBox("下载BGM")
        music_cb.setChecked(True)
        music_cb.setStyleSheet(f"color: #F59E0B; font-size: {scaled_font(12)}px; font-weight: bold;")
        layout.addWidget(music_cb)

        top = QHBoxLayout()
        sa = QPushButton("全选"); sa.setObjectName("secondaryBtn")
        da = QPushButton("全不选"); da.setObjectName("secondaryBtn")
        top.addWidget(sa); top.addWidget(da); top.addStretch()
        layout.addLayout(top)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: 1px solid #252550; border-radius: 8px; background: #0A0A14; }")
        sw = QWidget()
        sw_layout = QVBoxLayout(sw)
        sw_layout.setSpacing(4)
        sw_layout.setContentsMargins(8, 8, 8, 8)

        cboxes = []
        thumb_sz = font_scale(64)
        _thumb_labels = []
        _all_thumbs = []  # 所有缩略图，用于拖选 hit-test

        # 拖选 + 高亮
        _drag_mode = [None]
        _thumb_checked = "border: 2px solid #E11D48; border-radius: 6px; background: #1A1030;"
        _thumb_unchecked = "border: 1px solid #252550; border-radius: 6px; background: #12122A;"

        class _ThumbLabel(QLabel):
            """可点击+拖选缩略图"""
            def __init__(self, text, cb, parent=None):
                super().__init__(text, parent)
                self._cb = cb  # 关联 QCheckBox

            def mousePressEvent(self, event):
                if event.button() == Qt.MouseButton.LeftButton:
                    _drag_mode[0] = 'select' if not self._cb.isChecked() else 'deselect'
                    self._cb.toggle()
                    self._drag_done = {self._cb}
                super().mousePressEvent(event)

            def mouseMoveEvent(self, event):
                if _drag_mode[0] is not None:
                    gp = event.globalPosition().toPoint()
                    # 遍历所有缩略图，检测光标落在哪个上面
                    for lbl in _all_thumbs:
                        if lbl.geometry().contains(
                            lbl.parent().mapFromGlobal(gp)):
                            cb = lbl._cb
                            if cb not in self._drag_done:
                                if _drag_mode[0] == 'select' and not cb.isChecked():
                                    cb.setChecked(True)
                                elif _drag_mode[0] == 'deselect' and cb.isChecked():
                                    cb.setChecked(False)
                                self._drag_done.add(cb)
                            break
                super().mouseMoveEvent(event)

            def mouseReleaseEvent(self, event):
                if event.button() == Qt.MouseButton.LeftButton:
                    _drag_mode[0] = None
                super().mouseReleaseEvent(event)
        for im in img_list:
            row = QHBoxLayout()
            row.setSpacing(6)
            idx = im["index"]
            label = f"第{idx+1}张" + (" [实况]" if im.get("live") else "")
            cb = QCheckBox(label); cb.setChecked(True)
            cb.setStyleSheet(f"color: #94A3B8; font-size: {scaled_font(12)}px;")
            thumb = _ThumbLabel(str(idx + 1), cb)
            thumb.setFixedSize(thumb_sz, thumb_sz)
            thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
            thumb.setCursor(Qt.CursorShape.PointingHandCursor)
            thumb.setStyleSheet(
                f"color: #475569; font-size: {scaled_font(10)}px; "
                f"{_thumb_checked}"
            )
            # 勾选状态 ↔ 缩略图高亮
            def _sync(c, lbl=thumb, cs=_thumb_checked, us=_thumb_unchecked):
                lbl.setStyleSheet(
                    f"color: #475569; font-size: {scaled_font(10)}px; "
                    f"{cs if c else us}"
                )
            cb.toggled.connect(_sync)
            _all_thumbs.append(thumb)
            row.addWidget(thumb)
            cboxes.append((idx, cb))
            row.addWidget(cb); row.addStretch()
            sw_layout.addLayout(row)
            if im.get("url"):
                _thumb_labels.append((thumb, im["url"]))

        sw_layout.addStretch(); scroll.setWidget(sw)
        layout.addWidget(scroll, 1)

        bottom = QHBoxLayout(); bottom.addStretch()
        cancel = QPushButton("取消"); cancel.setObjectName("secondaryBtn")
        cancel.clicked.connect(dlg.reject); bottom.addWidget(cancel)
        ok = QPushButton("下载选中")
        ok.setCursor(Qt.CursorShape.PointingHandCursor); bottom.addWidget(ok)
        layout.addLayout(bottom)

        sa.clicked.connect(lambda: [cb[1].setChecked(True) for cb in cboxes])
        da.clicked.connect(lambda: [cb[1].setChecked(False) for cb in cboxes])

        # 后台并发加载缩略图（4 线程）
        if _thumb_labels:
            from concurrent.futures import ThreadPoolExecutor
            _results = qu.Queue()
            _done = [False]
            _pending = [len(_thumb_labels)]

            def _fetch_one(lbl, url):
                if _done[0]:
                    return
                try:
                    r = _req.get(url, headers={"User-Agent": USER_AGENT, "Referer": "https://www.douyin.com/"}, timeout=10)
                    _results.put((lbl, r.content))
                except Exception:
                    pass
                finally:
                    _pending[0] -= 1

            from src.settings.store import load as _load_stg
            _workers = 20 if _load_stg().get("high_speed", False) else 6
            _pool = ThreadPoolExecutor(max_workers=_workers)
            for lbl, url in _thumb_labels:
                _pool.submit(_fetch_one, lbl, url)

            def _poll():
                try:
                    while True:
                        lbl, data = _results.get_nowait()
                        if dlg.isVisible():
                            pix = QPixmap(); pix.loadFromData(data)
                            lbl.setPixmap(pix.scaled(thumb_sz, thumb_sz, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
                            lbl.setText("")
                            is_checked = lbl._cb.isChecked()
                            bdr = "2px solid #E11D48" if is_checked else "1px solid #252550"
                            bg = "#1A1030" if is_checked else "#12122A"
                            lbl.setStyleSheet(f"border: {bdr}; border-radius: 6px; background: {bg};")
                except qu.Empty:
                    if _pending[0] > 0:
                        QTimer.singleShot(60, _poll)
                    else:
                        _pool.shutdown(wait=False)
                except Exception:
                    pass
            QTimer.singleShot(30, _poll)
            dlg.finished.connect(lambda: _done.__setitem__(0, True))

        result = {"selected": None}
        def _confirm():
            sel = {idx for idx, cb in cboxes if cb.isChecked()}
            if not sel:
                QMessageBox.information(dlg, "提示", "请至少勾选一张")
                return
            result["selected"] = sel
            result["download_music"] = music_cb.isChecked()
            dlg.accept()
        ok.clicked.connect(_confirm)

        if dlg.exec() == QDialog.DialogCode.Accepted and result["selected"] is not None:
            self.thread._selected_img_indices = result["selected"]
            self.thread.download_music = result.get("download_music", False)
        else:
            self.thread._selected_img_indices = set()
        evt.set()

    def _clear_all(self):
        """清除链接、作者信息和作品简介"""
        self._auto_timer.stop()
        self.url_input.clear()
        self._author_avatar.hide()
        self._author_name.setText("")
        self._author_stats.setText("")
        self._aweme_desc.hide()

    def _show_author(self, info: dict):
        """显示作者头像、昵称、统计信息"""
        self._current_aweme_id = info.get("aweme_id", "")
        self._comment_btn.setEnabled(bool(self._current_aweme_id))

        nickname = info.get("nickname", "")
        avatar_url = info.get("avatar", "")
        desc = info.get("desc", "")
        stats = info.get("stats", "")
        detail = info.get("detail", "")

        self._author_name.setText(nickname)
        self._author_stats.setText(f"{stats}  |  {detail}" if stats else detail)
        if avatar_url:
            try:
                import requests as _req
                from src.environ import USER_AGENT
                from PyQt6.QtGui import QPixmap
                r = _req.get(avatar_url, headers={"User-Agent": USER_AGENT}, timeout=10)
                pix = QPixmap()
                pix.loadFromData(r.content)
                av_sz = self._author_avatar.width() or 30
                pix = self._circle_pixmap(pix, av_sz)
                self._author_avatar.setPixmap(pix)
                self._author_avatar.show()
            except Exception:
                pass

        if desc:
            self._aweme_desc.setText(desc)
            self._aweme_desc.setCursorPosition(0)
            self._aweme_desc.setToolTip(desc)
            self._aweme_desc.show()
        else:
            self._aweme_desc.hide()

    @staticmethod
    def _circle_pixmap(pix: "QPixmap", size: int) -> "QPixmap":
        """将 pixmap 裁剪为圆形"""
        from PyQt6.QtGui import QPainter, QPainterPath
        from PyQt6.QtCore import QRectF
        scaled = pix.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                            Qt.TransformationMode.SmoothTransformation)
        result = type(scaled)(size, size)
        result.fill(Qt.GlobalColor.transparent)
        painter = QPainter(result)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addEllipse(QRectF(0, 0, size, size))
        painter.setClipPath(path)
        painter.drawPixmap(0, 0, scaled)
        painter.end()
        return result

    def _start(self):
        text = self.url_input.text().strip()
        if not text:
            return

        cookie = ensure_cookie(self)
        if not cookie:
            self.status.setText("已取消 - Cookie 未设置")
            return

        save_dir = self.path_input.text().strip() or str(OUTPUT_SINGLE)
        # 清除上一次的作者信息
        self._author_avatar.hide()
        self._author_name.setText("")
        self._author_stats.setText("")
        self._aweme_desc.hide()
        self.dl_btn.setEnabled(False)
        self.dl_btn.setText("下载中...")
        self.progress.setVisible(True)
        self.progress.setValue(0)
        self.log_view.clear()

        self.thread = SingleDownloadThread(text, save_dir, False)  # BGM 在画廊弹窗选
        self.thread.log.connect(self._log)
        self.thread.progress.connect(lambda cur, total: (
            self.progress.setMaximum(total), self.progress.setValue(cur)
        ))
        self.thread.finished.connect(self._done)
        self.thread.author_signal.connect(self._show_author)
        self.thread.gallery_signal.connect(self._on_gallery)
        self._set_downloading(True)
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

    def _show_comments(self):
        """评论区弹窗"""
        aweme_id = getattr(self, '_current_aweme_id', '')
        if not aweme_id:
            return
        self._cmt_rendered = False

        from PyQt6.QtWidgets import QDialog, QScrollArea
        import threading

        dlg = QDialog(self)
        self._cmt_dlg = dlg
        dlg.setWindowTitle("评论")
        dlg.resize(font_scale(480), font_scale(560))
        dlg.setStyleSheet("QDialog { background: #0A0A14; }")
        layout = QVBoxLayout(dlg)

        self._cmt_loading = QLabel("正在加载热评...")
        self._cmt_loading.setStyleSheet("color: #94A3B8; font-size: 14px; padding: 8px;")

        self._cmt_dl_btn = QPushButton("下载图片/表情")
        self._cmt_dl_btn.setObjectName("secondaryBtn")
        self._cmt_dl_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._cmt_dl_btn.setEnabled(False)
        self._cmt_dl_btn.clicked.connect(self._show_media_gallery)

        btn_row = QHBoxLayout()
        btn_row.addWidget(self._cmt_loading, 1)
        btn_row.addWidget(self._cmt_dl_btn)
        layout.addLayout(btn_row)

        self._cmt_scroll = QScrollArea()
        self._cmt_scroll.setWidgetResizable(True)
        self._cmt_scroll.setStyleSheet("QScrollArea { border: 1px solid #252550; border-radius: 8px; background: #0A0A14; }")
        self._cmt_widget = QWidget()
        self._cmt_layout = QVBoxLayout(self._cmt_widget)
        self._cmt_layout.setSpacing(4)
        self._cmt_layout.setContentsMargins(6, 6, 6, 6)
        self._cmt_scroll.setWidget(self._cmt_widget)
        layout.addWidget(self._cmt_scroll, 1)

        def _fetch():
            from src.webview_api import _call_api
            params = (f"aweme_id={aweme_id}&cursor=0&count=30"
                      f"&device_platform=webapp&aid=6383&channel=channel_pc_web"
                      f"&pc_client_type=1&version_code=290100&version_name=29.1.0"
                      f"&cookie_enabled=true")
            data = _call_api(f"https://www.douyin.com/aweme/v1/web/comment/list/?{params}", timeout=30)
            self._comments_ready.emit(data)

        threading.Thread(target=_fetch, daemon=True).start()
        dlg.exec()

    def _apply_comments(self, data: dict):
        """主线程渲染评论"""
        if not hasattr(self, '_cmt_loading') or not self._cmt_loading.isVisible():
            return
        # 图片弹窗打开时不更新评论弹窗，避免置顶
        if getattr(self, '_media_dlg_open', False):
            return
        self._cmt_loading.setText(f"共 {len(data.get('comments',[]))} 条评论")
        self._cmt_dl_btn.setEnabled(True)
        self._cmt_loading.hide()

        if isinstance(data, list):
            comments = data
        elif isinstance(data, dict):
            comments = data.get("comments", [])
        else:
            comments = []
        self._all_comments = comments

        from PyQt6.QtGui import QPixmap
        import requests as _req
        from src.environ import USER_AGENT
        from src.utils import extract_comment_media
        import threading, queue as qu

        # 清空旧内容
        while self._cmt_layout.count():
            item = self._cmt_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        _thumb_queue = []

        for i, c in enumerate(comments):
            user = c.get("user", {})
            nick = user.get("nickname", "用户")
            text = c.get("text", "")
            likes = c.get("digg_count", 0)

            row = QWidget()
            row.setStyleSheet("background:#12122A;border-radius:6px;padding:6px;")
            rl = QVBoxLayout(row)
            rl.setSpacing(3)

            header = QLabel(f"{nick}  ·  ❤ {likes}")
            header.setStyleSheet("color:#E11D48;font-size:11px;font-weight:bold;background:transparent;")
            rl.addWidget(header)

            if text:
                body = QLabel(text)
                body.setStyleSheet("color:#E2E8F0;font-size:12px;background:transparent;")
                body.setWordWrap(True)
                rl.addWidget(body)

            media = extract_comment_media(c)
            has_media = media["images"] or media["stickers"]
            if has_media:
                nr = QHBoxLayout()
                nr.setSpacing(4)
                thumb_sz = font_scale(56)
                for img_url, _ in media["images"][:4]:
                    tl = QLabel("图")
                    tl.setFixedSize(thumb_sz, thumb_sz)
                    tl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                    tl.setStyleSheet("background:#1A1030;border:1px solid #252550;border-radius:4px;color:#475569;font-size:9px;")
                    nr.addWidget(tl)
                    _thumb_queue.append((tl, img_url, thumb_sz))
                for stk_url, _ in media["stickers"][:3]:
                    tl = QLabel("GIF")
                    tl.setFixedSize(thumb_sz, thumb_sz)
                    tl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                    tl.setStyleSheet("background:#1A1030;border:1px solid #E11D48;border-radius:4px;color:#475569;font-size:9px;")
                    nr.addWidget(tl)
                    _thumb_queue.append((tl, stk_url, thumb_sz))
                nr.addStretch()
                rl.addLayout(nr)

            self._cmt_layout.addWidget(row)

        self._cmt_layout.addStretch()

        # 异步加载缩略图
        if _thumb_queue:
            _results = qu.Queue()
            _pending = [len(_thumb_queue)]

            def _worker():
                for lbl, url, sz in _thumb_queue:
                    try:
                        r = _req.get(url, headers={"User-Agent": USER_AGENT, "Referer": "https://www.douyin.com/"}, timeout=10)
                        _results.put((lbl, r.content, sz))
                    except Exception:
                        pass
                    finally:
                        _pending[0] -= 1

            def _poll():
                try:
                    while True:
                        lbl, data, sz = _results.get_nowait()
                        pix = QPixmap(); pix.loadFromData(data)
                        lbl.setPixmap(pix.scaled(sz, sz, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
                        lbl.setText("")
                        lbl.setStyleSheet("border:1px solid #252550;border-radius:4px;")
                except qu.Empty:
                    if _pending[0] > 0:
                        QTimer.singleShot(80, _poll)

            threading.Thread(target=_worker, daemon=True).start()
            QTimer.singleShot(50, _poll)

    def _show_comment_media(self):
        """评论区图片/表情包预览弹窗（可勾选下载）"""
        # 关掉评论弹窗，只保留媒体弹窗
        if hasattr(self, '_cmt_dlg'):
            self._cmt_dlg.close()
        comments = getattr(self, '_all_comments', [])
        from src.utils import extract_comment_media
        # 收集所有媒体
        all_media = []  # [(url, type, comment_idx), ...]
        for i, c in enumerate(comments):
            media = extract_comment_media(c)
            for url, _ in media["images"]:
                all_media.append((url, "img", i))
            for url, _ in media["stickers"]:
                all_media.append((url, "stk", i))
        if not all_media:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.information(self, "提示", "当前评论中没有图片或表情包")
            return

        from PyQt6.QtWidgets import QDialog, QScrollArea, QCheckBox as CB, QGridLayout
        from PyQt6.QtGui import QPixmap
        import requests as _req
        from src.environ import USER_AGENT
        import threading, queue as qu

        dlg = QDialog(self)
        dlg.setWindowTitle(f"评论图片/表情 — 实时加载中...")
        dlg.resize(font_scale(600), font_scale(500))
        dlg.setStyleSheet("QDialog { background: #0A0A14; }")
        layout = QVBoxLayout(dlg)

        # 按钮
        top = QHBoxLayout()
        sa = QPushButton("全选"); sa.setObjectName("secondaryBtn")
        da = QPushButton("全不选"); da.setObjectName("secondaryBtn")
        top.addWidget(sa); top.addWidget(da); top.addStretch()
        cnt_label = QLabel(f"共 {len(all_media)} 个")
        cnt_label.setStyleSheet("color: #64748B; font-size: 12px;")
        top.addWidget(cnt_label)
        layout.addLayout(top)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        sw = QWidget()
        grid = QGridLayout(sw)
        grid.setSpacing(6)
        cbs = []
        thumb_sz = font_scale(80)

        # 高亮样式
        _chk = "border:2px solid #E11D48;border-radius:4px;background:#1A1030;"
        _unc = "border:1px solid #252550;border-radius:4px;background:#12122A;"
        _drag_mode = [None]

        class _ThumbLabel(QLabel):
            def __init__(self, text, cb):
                super().__init__(text)
                self._cb = cb
            def mousePressEvent(self, e):
                if e.button() == Qt.MouseButton.LeftButton:
                    _drag_mode[0] = 'select' if not self._cb.isChecked() else 'deselect'
                    self._cb.toggle()
                    self._drag_done = {self._cb}
                super().mousePressEvent(e)
            def mouseMoveEvent(self, e):
                if _drag_mode[0] is not None:
                    gp = e.globalPosition().toPoint()
                    for cb, _, lbl, _ in cbs:
                        if lbl is not self and lbl.geometry().contains(lbl.parent().mapFromGlobal(gp)):
                            if cb not in self._drag_done:
                                cb.setChecked(_drag_mode[0] == 'select')
                                self._drag_done.add(cb)
                            break
                super().mouseMoveEvent(e)
            def mouseReleaseEvent(self, e):
                if e.button() == Qt.MouseButton.LeftButton:
                    _drag_mode[0] = None
                super().mouseReleaseEvent(e)

        for j, (url, typ, cmt_idx) in enumerate(all_media):
            col = QVBoxLayout()
            col.setSpacing(2)
            cb = CB(f"{'[图]' if typ=='img' else '[GIF]'} {cmt_idx+1}")
            cb.setChecked(True)
            cb.setStyleSheet(f"color:#94A3B8;font-size:{scaled_font(10)}px;")
            tl = _ThumbLabel("加载中...", cb)
            tl.setFixedSize(thumb_sz, thumb_sz)
            tl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            tl.setCursor(Qt.CursorShape.PointingHandCursor)
            tl.setStyleSheet(f"color:#475569;font-size:10px;{_chk}")
            # 高亮同步
            def _sync(c, lbl=tl, chk=_chk, unc=_unc):
                lbl.setStyleSheet(f"color:#475569;font-size:10px;{chk if c else unc}")
            cb.toggled.connect(_sync)
            col.addWidget(tl)
            col.addWidget(cb)
            grid.addLayout(col, j // 5, j % 5)
            cbs.append((cb, url, tl, thumb_sz))

        scroll.setWidget(sw)
        layout.addWidget(scroll, 1)

        # 下载按钮
        dl_btn = QPushButton("下载选中")
        dl_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        dl_btn.setMinimumHeight(font_scale(38))
        layout.addWidget(dl_btn)

        # 全选/全不选
        sa.clicked.connect(lambda: [c[0].setChecked(True) for c in cbs])
        da.clicked.connect(lambda: [c[0].setChecked(False) for c in cbs])

        def _dl_checked():
            selected = [(url, cmt_idx) for cb, url, _, _ in cbs if cb.isChecked()]
            if not selected:
                from PyQt6.QtWidgets import QMessageBox
                QMessageBox.information(dlg, "提示", "请至少勾选一个")
                return
            import os
            save_dir = self.path_input.text().strip() or str(OUTPUT_SINGLE)
            save_path = os.path.join(save_dir, "评论图片_表情包")
            os.makedirs(save_path, exist_ok=True)
            _seq_file = os.path.join(save_path, ".sticker_seq")
            _global_seq = 1
            try:
                if os.path.exists(_seq_file):
                    _global_seq = int(open(_seq_file).read().strip()) + 1
            except Exception:
                pass
            self.log_view.append(f'<span style="color:#F59E0B;">[评论图片] 开始下载 {len(selected)} 个...</span>')
            dlg.accept()

            def _download():
                nonlocal _global_seq
                try:
                    if os.path.exists(_seq_file):
                        _global_seq = int(open(_seq_file).read().strip()) + 1
                except Exception:
                    pass
                _cnt = {}
                for url, cmt_idx in selected:
                    try:
                        if '.gif' in url.lower() or 'animate' in url.lower():
                            ext = '.gif'
                        elif '.png' in url.lower() or 'static' in url.lower():
                            ext = '.png'
                        else:
                            ext = '.jpg'
                        fname = f"sticker_{_global_seq:04d}{ext}"
                        _global_seq += 1
                        r = _req.get(url, headers={"User-Agent": USER_AGENT, "Referer": "https://www.douyin.com/"}, timeout=15)
                        with open(os.path.join(save_path, fname), "wb") as f:
                            f.write(r.content)
                        self._dl_log_signal.emit(f'<span style="color:#22C55E;">[OK] {fname}</span>')
                    except Exception as e:
                        self._dl_log_signal.emit(f'<span style="color:#EF4444;">[FAIL] {e}</span>')
                # 保存最后编号，下次下载不覆盖
                try:
                    open(_seq_file, 'w').write(str(_global_seq - 1))
                except Exception:
                    pass
                self._dl_log_signal.emit(f'<span style="color:#22C55E;">[完成] 已保存到: {save_path}</span>')
                os.startfile(save_path)
            threading.Thread(target=_download, daemon=True).start()

        dl_btn.clicked.connect(_dl_checked)

        # 异步加载缩略图
        _results = qu.Queue()
        _pending = [len(cbs)]

        def _worker():
            for cb, url, lbl, sz in cbs:
                try:
                    r = _req.get(url, headers={"User-Agent": USER_AGENT, "Referer": "https://www.douyin.com/"}, timeout=10)
                    _results.put((lbl, r.content, sz))
                except Exception:
                    pass
                finally:
                    _pending[0] -= 1

        def _poll():
            try:
                while True:
                    lbl, data, sz = _results.get_nowait()
                    pix = QPixmap(); pix.loadFromData(data)
                    lbl.setPixmap(pix.scaled(sz, sz, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
                    lbl.setText("")
                    lbl.setStyleSheet("border:1px solid #252550;border-radius:4px;")
            except qu.Empty:
                if _pending[0] > 0:
                    QTimer.singleShot(80, _poll)

        threading.Thread(target=_worker, daemon=True).start()
        QTimer.singleShot(50, _poll)

        # 非模态 + 定期全量刷新（不逐条追加，避免卡死）
        _last_total = len(all_media)
        def _refresh():
            nonlocal _last_total
            if not dlg.isVisible():
                return
            # 从 _all_comments 重新提取全部媒体
            cur_comments = getattr(self, '_all_comments', [])
            new_all = []
            for i, c in enumerate(cur_comments):
                m = extract_comment_media(c)
                for url, _ in m["images"]:
                    new_all.append((url, "img", i))
                for url, _ in m["stickers"]:
                    new_all.append((url, "stk", i))
            if len(new_all) > _last_total:
                _last_total = len(new_all)
                # 清空重建 grid
                while grid.count():
                    item = grid.takeAt(0)
                    if item.layout():
                        while item.layout().count():
                            w = item.layout().takeAt(0)
                            if w.widget(): w.widget().deleteLater()
                        item.layout().deleteLater()
                cbs.clear()
                for j, (url, typ, cmt_idx) in enumerate(new_all):
                    col = QVBoxLayout(); col.setSpacing(2)
                    cb = CB(f"{'[图]' if typ=='img' else '[GIF]'} {cmt_idx+1}")
                    cb.setChecked(True)
                    cb.setStyleSheet(f"color:#94A3B8;font-size:{scaled_font(10)}px;")
                    tl = _ThumbLabel("加载中...", cb)
                    tl.setFixedSize(thumb_sz, thumb_sz)
                    tl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                    tl.setCursor(Qt.CursorShape.PointingHandCursor)
                    tl.setStyleSheet(f"color:#475569;font-size:10px;{_chk}")
                    def _sync(c, lbl=tl, chk=_chk, unc=_unc):
                        lbl.setStyleSheet(f"color:#475569;font-size:10px;{chk if c else unc}")
                    cb.toggled.connect(_sync)
                    col.addWidget(tl); col.addWidget(cb)
                    grid.addLayout(col, j // 5, j % 5)
                    cbs.append((cb, url, tl, thumb_sz))
                cnt_label.setText(f"共 {len(new_all)} 个")
                dlg.setWindowTitle(f"评论图片/表情 — 共 {len(new_all)} 个")
                # 串行加载缩略图（后台线程 + _dl_log_signal 回主线程）
                def _load_all():
                    for cb, url, tl, sz in cbs:
                        try:
                            r = _req.get(url, headers={"User-Agent": USER_AGENT, "Referer": "https://www.douyin.com/"}, timeout=10)
                            pix = QPixmap(); pix.loadFromData(r.content)
                            self._dl_log_signal.emit(f"__pix__{id(tl)}__{sz}")
                            setattr(tl, '_pix_data', (pix, sz))
                        except Exception:
                            pass
                threading.Thread(target=_load_all, daemon=True).start()
                # 主线程轮询应用 pixmap
                def _apply_pix():
                    for _, _, tl, sz in cbs:
                        data = getattr(tl, '_pix_data', None)
                        if data:
                            pix, s = data
                            tl.setPixmap(pix.scaled(s, s, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
                            tl.setText("")
                            delattr(tl, '_pix_data')
                    QTimer.singleShot(300, _apply_pix)
                QTimer.singleShot(300, _apply_pix)
            QTimer.singleShot(1500, _refresh)

        QTimer.singleShot(1500, _refresh)
        dlg.show()
        def _on_media_close():
            self._media_dlg_open = False
        dlg.finished.connect(_on_media_close)

    def _show_media_gallery(self):
        """评论区图片/表情包预览弹窗（可点选+拖选+下载）"""
        comments = getattr(self, '_all_comments', [])
        from src.utils import extract_comment_media
        all_media = []
        for i, c in enumerate(comments):
            m = extract_comment_media(c)
            for url, _ in m["images"]:
                all_media.append((url, "img", i))
            for url, _ in m["stickers"]:
                all_media.append((url, "stk", i))
        if not all_media:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.information(self, "提示", "热评中没有图片或表情包")
            return

        from PyQt6.QtWidgets import QDialog, QScrollArea, QCheckBox as CB, QGridLayout
        from PyQt6.QtGui import QPixmap
        import requests as _req, os, threading, queue as qu
        from src.environ import USER_AGENT

        dlg = QDialog(self)
        dlg.setWindowTitle(f"评论图片/表情 — 共 {len(all_media)} 个")
        dlg.resize(font_scale(580), font_scale(480))
        dlg.setStyleSheet("QDialog { background: #0A0A14; }")
        layout = QVBoxLayout(dlg)

        top = QHBoxLayout()
        sa = QPushButton("全选"); sa.setObjectName("secondaryBtn")
        da = QPushButton("全不选"); da.setObjectName("secondaryBtn")
        top.addWidget(sa); top.addWidget(da); top.addStretch()
        cnt = QLabel(f"共 {len(all_media)} 个")
        cnt.setStyleSheet("color: #64748B; font-size: 12px;")
        top.addWidget(cnt)
        layout.addLayout(top)

        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        sw = QWidget(); grid = QGridLayout(sw); grid.setSpacing(6)
        cbs = []; thumb_sz = font_scale(80)
        _chk = "border:2px solid #E11D48;border-radius:4px;background:#1A1030;"
        _unc = "border:1px solid #252550;border-radius:4px;background:#12122A;"
        _drag_mode = [None]

        class _TL(QLabel):
            def __init__(s, t, cb): super().__init__(t); s._cb = cb
            def mousePressEvent(s, e):
                if e.button() == Qt.MouseButton.LeftButton:
                    _drag_mode[0] = 'select' if not s._cb.isChecked() else 'deselect'
                    s._cb.toggle(); s._drag_done = {s._cb}
                super().mousePressEvent(e)
            def mouseMoveEvent(s, e):
                if _drag_mode[0] is not None:
                    gp = e.globalPosition().toPoint()
                    for cb, _, lbl, _ in cbs:
                        if lbl is not s and lbl.geometry().contains(lbl.parent().mapFromGlobal(gp)):
                            if cb not in s._drag_done:
                                cb.setChecked(_drag_mode[0]=='select'); s._drag_done.add(cb)
                            break
                super().mouseMoveEvent(e)
            def mouseReleaseEvent(s, e):
                if e.button() == Qt.MouseButton.LeftButton: _drag_mode[0] = None
                super().mouseReleaseEvent(e)

        for j, (url, typ, cmt_idx) in enumerate(all_media):
            col = QVBoxLayout(); col.setSpacing(2)
            cb = CB(f"{'[图]' if typ=='img' else '[GIF]'} {cmt_idx+1}")
            cb.setChecked(True)
            cb.setStyleSheet(f"color:#94A3B8;font-size:{scaled_font(10)}px;")
            tl = _TL("加载中...", cb)
            tl.setFixedSize(thumb_sz, thumb_sz); tl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            tl.setCursor(Qt.CursorShape.PointingHandCursor)
            tl.setStyleSheet(f"color:#475569;font-size:10px;{_chk}")
            def _sync(c, l=tl, chk=_chk, unc=_unc):
                l.setStyleSheet(f"color:#475569;font-size:10px;{chk if c else unc}")
            cb.toggled.connect(_sync)
            col.addWidget(tl); col.addWidget(cb)
            grid.addLayout(col, j//5, j%5)
            cbs.append((cb, url, tl, thumb_sz))
        scroll.setWidget(sw); layout.addWidget(scroll, 1)

        dl_btn = QPushButton("下载选中"); dl_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        dl_btn.setMinimumHeight(font_scale(38)); layout.addWidget(dl_btn)
        sa.clicked.connect(lambda: [c[0].setChecked(True) for c in cbs])
        da.clicked.connect(lambda: [c[0].setChecked(False) for c in cbs])

        def _dl_checked():
            sel = [(url, idx) for cb, url, _, _ in cbs if cb.isChecked()]
            if not sel:
                QMessageBox.information(dlg, "提示", "请至少勾选一个"); return
            save_dir = self.path_input.text().strip() or str(OUTPUT_SINGLE)
            save_path = os.path.join(save_dir, "评论图片_表情包")
            os.makedirs(save_path, exist_ok=True)
            sf = os.path.join(save_path, ".sticker_seq")
            gs = 1
            try:
                if os.path.exists(sf): gs = int(open(sf).read().strip()) + 1
            except: pass
            self.log_view.append(f'<span style="color:#F59E0B;">[下载] {len(sel)} 个...</span>')
            dlg.accept()
            def _dl():
                nonlocal gs
                for url, _ in sel:
                    try:
                        ext = '.gif' if 'animate' in url.lower() else '.png' if 'static' in url.lower() else '.jpg'
                        fn = f"sticker_{gs:04d}{ext}"; gs += 1
                        r = _req.get(url, headers={"User-Agent": USER_AGENT}, timeout=15)
                        with open(os.path.join(save_path, fn), "wb") as f: f.write(r.content)
                        self._dl_log_signal.emit(f'<span style="color:#22C55E;">[OK] {fn}</span>')
                    except Exception as e:
                        self._dl_log_signal.emit(f'<span style="color:#EF4444;">[FAIL] {e}</span>')
                try: open(sf, 'w').write(str(gs-1))
                except: pass
                self._dl_log_signal.emit(f'<span style="color:#22C55E;">[完成] {save_path}</span>')
                os.startfile(save_path)
            threading.Thread(target=_dl, daemon=True).start()
        dl_btn.clicked.connect(_dl_checked)

        _results = qu.Queue(); _pending = [len(cbs)]
        from concurrent.futures import ThreadPoolExecutor as TPE
        def _fetch_one(lbl, url):
            try:
                r = _req.get(url, headers={"User-Agent": USER_AGENT}, timeout=10)
                _results.put((lbl, r.content))
            except: pass
            finally: _pending[0] -= 1
        tp = TPE(max_workers=10)
        for _, url, lbl, sz in cbs:
            tp.submit(_fetch_one, lbl, url)
        def _p():
            try:
                while True:
                    lbl, d = _results.get_nowait()
                    pix = QPixmap(); pix.loadFromData(d)
                    sz = lbl.width() or 80
                    lbl.setPixmap(pix.scaled(sz, sz, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
                    lbl.setText(""); lbl.setStyleSheet("border:1px solid #252550;border-radius:4px;")
            except qu.Empty:
                if _pending[0] > 0: QTimer.singleShot(80, _p)
        QTimer.singleShot(50, _p)
        dlg.exec()

    def _set_downloading(self, active: bool):
        w = self.window()
        if hasattr(w, 'set_download_active'):
            w.set_download_active(active)

    def _done(self, ok: bool, msg: str):
        self._set_downloading(False)
        if ok:
            self.progress.setValue(100)
        self._refresh_downloaded()

        self.dl_btn.setEnabled(True)
        self.dl_btn.setText("开始下载")
        self.status.setText(msg)
        w = self.window()
        if ok and hasattr(w, "tray_notify"):
            w.tray_notify("Origami", "下载完成", duration=3000)
