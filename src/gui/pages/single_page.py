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
    QFileDialog, QMenu, QApplication,
    QFrame,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt6.QtWidgets import QSizePolicy
from PyQt6.QtGui import QAction

from src.fonts import font_scale, scaled_font
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
        try:
            self.log.emit("[>>] 解析链接...")
            aweme_id = self._resolve(self.raw_text)
            self.log.emit(f"[OK] 视频ID: {aweme_id}")

            cookie = load_cookie()

            self.log.emit("[>>] 获取数据 (启动浏览器 ~15s)...")
            aweme = self._fetch(aweme_id, cookie)

            desc = aweme.get("desc", "") or aweme_id
            author_info = aweme.get("author", {})
            author = author_info.get("nickname", "")
            avatar = (author_info.get("avatar_thumb", {}) or {}).get("url_list", [""])[0] or ""
            uid = author_info.get("unique_id", "")

            # 只显示头像 + 昵称 + 抖音号 + 作品简介（不额外调 API）
            detail = f"抖音号：{uid}" if uid else ""
            self.author_signal.emit({
                "nickname": author,
                "avatar": avatar,
                "desc": desc,
                "stats": "",
                "detail": detail,
                "bio": "",
            })
            self.log.emit(f"  作者: {author}")
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


# ═══════════════════════════════════════════════════════════
# 单视频页面
# ═══════════════════════════════════════════════════════════
class SinglePage(QWidget):
    back_clicked = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.thread = None
        self._auto_timer = QTimer()
        self._auto_timer.setSingleShot(True)
        self._auto_timer.timeout.connect(self._start)
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
        layout.addLayout(top)

        # 作品简介
        self._aweme_desc = QLabel("")
        self._aweme_desc.setStyleSheet(
            f"color: #64748B; font-size: {scaled_font(11)}px; "
            "padding: 0px 4px;"
        )
        self._aweme_desc.setWordWrap(True)
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
        self._music_cb = QCheckBox("下载BGM")
        self._music_cb.setStyleSheet(f"color: #64748B; font-size: {scaled_font(10)}px;")
        url_row.addWidget(self._music_cb)
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
        for im in img_list:
            row = QHBoxLayout()
            row.setSpacing(6)
            thumb = QLabel(str(im["index"] + 1))
            thumb.setFixedSize(thumb_sz, thumb_sz)
            thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
            thumb.setStyleSheet(
                f"color: #475569; font-size: {scaled_font(10)}px; "
                "background: #12122A; border: 1px solid #252550; border-radius: 6px;"
            )
            row.addWidget(thumb)
            idx = im["index"]
            label = f"第{idx+1}张" + (" [实况]" if im.get("live") else "")
            cb = QCheckBox(label); cb.setChecked(True)
            cb.setStyleSheet(f"color: #94A3B8; font-size: {scaled_font(12)}px;")
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

        # 后台线程加载缩略图
        if _thumb_labels:
            _results = qu.Queue()
            _done = [False]
            def _worker():
                for lbl, url in _thumb_labels:
                    if _done[0]: break
                    try:
                        r = _req.get(url, headers={"User-Agent": USER_AGENT, "Referer": "https://www.douyin.com/"}, timeout=10)
                        _results.put((lbl, r.content))
                    except Exception: pass
            def _poll():
                try:
                    while True:
                        lbl, data = _results.get_nowait()
                        if dlg.isVisible():
                            pix = QPixmap(); pix.loadFromData(data)
                            lbl.setPixmap(pix.scaled(thumb_sz, thumb_sz, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
                            lbl.setText("")
                            lbl.setStyleSheet("border: 1px solid #252550; border-radius: 6px;")
                except qu.Empty:
                    if _worker_thread.is_alive():
                        QTimer.singleShot(60, _poll)
                except Exception: pass
            _worker_thread = threading.Thread(target=_worker, daemon=True)
            _worker_thread.start()
            QTimer.singleShot(30, _poll)
            dlg.finished.connect(lambda: _done.__setitem__(0, True))

        result = {"selected": None}
        def _confirm():
            sel = {idx for idx, cb in cboxes if cb.isChecked()}
            if not sel:
                QMessageBox.information(dlg, "提示", "请至少勾选一张")
                return
            result["selected"] = sel; dlg.accept()
        ok.clicked.connect(_confirm)

        if dlg.exec() == QDialog.DialogCode.Accepted and result["selected"] is not None:
            self.thread._selected_img_indices = result["selected"]
        else:
            self.thread._selected_img_indices = set()
        evt.set()

    def _clear_all(self):
        """清除链接、作者信息和作品简介"""
        self._auto_timer.stop()
        self.url_input.clear()
        self._author_avatar.hide()
        self._author_name.setText("")
        self._aweme_desc.hide()

    def _show_author(self, info: dict):
        """显示作者头像和昵称（右上角紧凑显示）"""
        nickname = info.get("nickname", "")
        avatar_url = info.get("avatar", "")
        desc = info.get("desc", "")

        self._author_name.setText(nickname)
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
            self._aweme_desc.setText(f"简介：{desc}")
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
        self._aweme_desc.hide()
        self.dl_btn.setEnabled(False)
        self.dl_btn.setText("下载中...")
        self.progress.setVisible(True)
        self.progress.setValue(0)
        self.log_view.clear()

        self.thread = SingleDownloadThread(text, save_dir, self._music_cb.isChecked())
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
