# -*- coding: utf-8 -*-
"""
Origami — 主页批量下载页面

独立模块，包含 HomepageDownloadThread。
后续其他平台的主页下载通过平台适配器切换。
"""

import os
import json
import time
import threading
from pathlib import Path

import requests

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QLineEdit, QTextEdit, QProgressBar,
    QListWidget, QListWidgetItem, QSplitter,
    QFileDialog, QMenu, QApplication, QComboBox,
    QMessageBox, QInputDialog,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal

from src.gui.fonts import font_scale, scaled_font
from src.environ import OUTPUT_HOMEPAGE, USER_AGENT
from src.utils import clean_name, pick_best_video_url, parse_sec_user_id
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
# 主页下载线程
# ═══════════════════════════════════════════════════════════
class HomepageDownloadThread(QThread):
    log_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(int, int)
    finished_signal = pyqtSignal(dict)
    paused_signal = pyqtSignal(bool)
    total_signal = pyqtSignal(int)

    def __init__(self, url: str, pending_count_text: str = "全部下载",
                 custom_out_dir: str = ""):
        super().__init__()
        self.url = url
        self.pending_count_text = pending_count_text
        self.custom_out_dir = Path(custom_out_dir) if custom_out_dir else OUTPUT_HOMEPAGE
        self._pause_event = threading.Event()
        self._pause_event.set()
        self._cancelled = False

    def pause(self):
        self._pause_event.clear()
        self.paused_signal.emit(True)
        self.log_signal.emit("[PAUSED]")

    def resume(self):
        self._pause_event.set()
        self.paused_signal.emit(False)
        self.log_signal.emit("[RESUMED]")

    def toggle_pause(self):
        self.resume() if not self._pause_event.is_set() else self.pause()

    def cancel(self):
        self._cancelled = True
        self._pause_event.set()

    def _check_cancel(self) -> bool:
        return self._cancelled

    def _wait(self):
        self._pause_event.wait()

    def run(self):
        from src.api import DouyinAPI
        from src.cookie import load_cookie as _load_cookie

        url = self.url.strip()
        try:
            sec_id = parse_sec_user_id(url)
        except Exception as e:
            self.log_signal.emit(f"[ERROR] {e}")
            self.finished_signal.emit({
                "video": 0, "image": 0, "music": 0,
                "skip": 0, "fail": 0, "cancelled": True,
            })
            return

        self.log_signal.emit(f"[OK] 用户: {sec_id[:24]}...")

        cookie = _load_cookie()
        api = DouyinAPI(cookie_string=cookie)

        profile = api.get_user_profile(sec_id)
        if not profile or (not profile.get("nickname") and not profile.get("uid")):
            self.log_signal.emit(f"[ERROR] 无法获取用户信息，请检查Cookie是否过期")
            self.finished_signal.emit({"video":0,"image":0,"music":0,"skip":0,"fail":0,"cancelled":True})
            return
        self.log_signal.emit(f"[OK] 昵称: {profile.get('nickname','?')} 作品: {profile.get('aweme_count',0)}")
        self.log_signal.emit("[>>] 获取作品列表...")
        all_posts, seen_ids, cursor, author_name = [], set(), 0, profile.get("nickname", "")

        try:
            max_count = int(self.pending_count_text)
        except ValueError:
            max_count = None

        for page in range(1, 50):
            if self._check_cancel():
                self.finished_signal.emit({
                    "video": 0, "image": 0, "music": 0,
                    "skip": 0, "fail": 0, "cancelled": True,
                })
                return
            self._wait()
            data = api.get_user_posts(sec_id, max_cursor=cursor, count=18)
            aweme_list = data.get("aweme_list", [])
            if not aweme_list:
                break
            new = sum(1 for a in aweme_list if a["aweme_id"] not in seen_ids)
            for a in aweme_list:
                if a["aweme_id"] not in seen_ids:
                    seen_ids.add(a["aweme_id"])
                    all_posts.append(a)
            if not author_name and aweme_list:
                author_name = aweme_list[0].get("author", {}).get("nickname", "")
            has_more = data.get("has_more", 0)
            cursor = data.get("max_cursor", 0)
            self.log_signal.emit(
                f"[翻页] P{page}: +{new} 累计{len(all_posts)} has_more={has_more}"
            )
            if max_count and len(all_posts) >= max_count:
                self.log_signal.emit(f"[翻页] 已达目标数量 {max_count}，停止翻页")
                all_posts = all_posts[:max_count]
                break
            if not has_more:
                break
            time.sleep(1.5)

        real_total = len(all_posts)
        self.total_signal.emit(real_total)
        total = len(all_posts)
        self.log_signal.emit(f"[OK] 下载{total}个 | 作者: {author_name}")

        safe_author = clean_name(author_name, 20) or sec_id[:8]
        out_dir = Path(self.custom_out_dir) / safe_author
        out_dir.mkdir(parents=True, exist_ok=True)

        # 保存主页信息
        d_date = time.strftime("%Y-%m-%d %H:%M:%S")
        gm = {0: "未设置", 1: "男", 2: "女"}
        gender = gm.get(profile.get("gender", 0), str(profile.get("gender", "")))
        loc = " ".join(filter(None, [
            profile.get("country", ""), profile.get("province", ""),
            profile.get("city", ""), profile.get("district", ""),
        ]))
        info = [
            f"# {author_name}", "",
            f"## 基本信息", "",
            f"- 抖音号: {profile.get('unique_id', 'N/A')}",
            f"- UID: {profile.get('uid', 'N/A')}",
            f"- 性别: {gender}",
            f"- 年龄: {profile.get('age', 'N/A')}",
            f"- 地区: {loc or 'N/A'}",
            f"- 学校: {profile.get('school', 'N/A')}",
            f"- 简介: {profile.get('desc', 'N/A')}",
            f"- 认证: {profile.get('custom_verify', '') or profile.get('enterprise_verify_reason', '') or '无'}",
            f"", f"## 数据统计", "",
            f"- 作品数: {profile.get('aweme_count', 'N/A')}",
            f"- 粉丝数: {profile.get('follower_count', 'N/A')}",
            f"- 关注数: {profile.get('following_count', 'N/A')}",
            f"- 获赞数: {profile.get('favoriting_count', 'N/A')}",
            f"- 被赞数: {profile.get('total_favorited', 'N/A')}",
            f"", f"## 下载信息", "",
            f"- 主页链接: {self.url.strip()}",
            f"- 下载日期: {d_date}",
            f"- 头像: {profile.get('avatar_url', 'N/A')}", "",
        ]
        (out_dir / "主页信息.md").write_text("\n".join(info), encoding="utf-8")

        tracker = {}
        tp = out_dir / ".downloaded.json"
        if tp.exists():
            try:
                tracker = json.loads(tp.read_text(encoding="utf-8"))
            except Exception:
                pass

        headers = {"User-Agent": USER_AGENT, "Referer": "https://www.douyin.com/"}
        stats = {"video": 0, "image": 0, "music": 0, "skip": 0, "fail": 0}

        for i, post in enumerate(all_posts):
            if self._check_cancel():
                break
            self._wait()
            aweme_id = post.get("aweme_id", "")
            desc = clean_name(post.get("desc", "")) or aweme_id
            folder = f"{i+1:03d}_{desc}"
            post_dir = out_dir / folder
            self.progress_signal.emit(i + 1, total)

            if aweme_id in tracker:
                stats["skip"] += 1
                continue

            post_dir.mkdir(parents=True, exist_ok=True)
            self.log_signal.emit(f"[{i+1}/{total}] {desc[:40]}")

            (post_dir / "desc.md").write_text(post.get("desc", ""), encoding="utf-8")
            has_v = bool(post.get("video"))
            has_i = bool(post.get("images"))
            has_rv = False

            if has_v:
                best = pick_best_video_url(post["video"])
                if best:
                    has_rv = True
                    if self._dl(best, post_dir / "video.mp4", headers):
                        stats["video"] += 1
                    else:
                        stats["fail"] += 1
            if not has_rv:
                music = post.get("music") or {}
                mp = music.get("play_url")
                mp_urls = (
                    mp.get("url_list") if isinstance(mp, dict)
                    else ([mp] if isinstance(mp, str) and mp else [])
                )
                if mp_urls:
                    if self._dl(mp_urls[0], post_dir / "music.mp3", headers):
                        stats["music"] += 1
                    else:
                        stats["fail"] += 1
            if has_i:
                for j, img in enumerate(post["images"]):
                    if self._check_cancel():
                        break
                    self._wait()
                    urls = img.get("url_list", [])
                    img_url = next(
                        (u for u in urls if "jpeg" in u.lower() or "jpg" in u.lower()),
                        urls[0] if urls else "",
                    )
                    if not img_url:
                        continue
                    is_live = img.get("live_photo_type", 0) == 1
                    tag = "_实况" if is_live else ""
                    if self._dl(img_url, post_dir / f"{j+1:02d}{tag}.jpg", headers):
                        stats["image"] += 1
                    else:
                        stats["fail"] += 1
                    if is_live:
                        lv = img.get("video") or {}
                        live_url = pick_best_video_url(lv)
                        if live_url:
                            if self._dl(live_url, post_dir / f"{j+1:02d}{tag}.mp4", headers):
                                stats["video"] += 1
                            else:
                                stats["fail"] += 1

            tracker[aweme_id] = {
                "desc": desc,
                "folder": folder,
                "time": time.strftime("%Y-%m-%d %H:%M:%S"),
            }

        tp.write_text(json.dumps(tracker, ensure_ascii=False, indent=2), encoding="utf-8")

        self.log_signal.emit("===== DONE =====")
        self.log_signal.emit(
            f"视频:{stats['video']} 图片:{stats['image']} "
            f"音乐:{stats['music']} 跳过:{stats['skip']} 失败:{stats['fail']}"
        )
        stats["cancelled"] = self._cancelled
        self.finished_signal.emit(stats)

    def _dl(self, url: str, path: Path, headers: dict) -> bool:
        if path.exists():
            return True
        try:
            r = requests.get(url, headers=headers, stream=True, timeout=60)
            r.raise_for_status()
            with open(path, "wb") as f:
                for chunk in r.iter_content(8192):
                    f.write(chunk)
            return True
        except Exception:
            if path.exists():
                path.unlink()
            return False


# ═══════════════════════════════════════════════════════════
# 主页下载页面
# ═══════════════════════════════════════════════════════════
class HomepagePage(QWidget):
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

        title = QLabel("主页批量下载")
        title.setStyleSheet(f"font-size: {scaled_font(20)}px; font-weight: bold; color: #E11D48;")
        top.addWidget(title)
        top.addStretch()
        layout.addLayout(top)

        # URL 行
        url_row = QHBoxLayout()
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("粘贴主页链接或分享口令（长按复制...）")
        self.url_input.setMinimumHeight(font_scale(42))
        self.url_input.returnPressed.connect(self._start)
        url_row.addWidget(self.url_input)
        self.dl_btn = QPushButton("开始下载")
        self.dl_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.dl_btn.clicked.connect(self._start)
        self.dl_btn.setMinimumHeight(font_scale(42))
        url_row.addWidget(self.dl_btn)
        self.pause_btn = QPushButton("暂停")
        self.pause_btn.setObjectName("secondaryBtn")
        self.pause_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.pause_btn.setEnabled(False)
        self.pause_btn.clicked.connect(self._pause)
        url_row.addWidget(self.pause_btn)
        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.setObjectName("secondaryBtn")
        self.cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self._cancel)
        url_row.addWidget(self.cancel_btn)
        layout.addLayout(url_row)

        # 数量 + 路径
        ctrl = QHBoxLayout()
        ctrl.setSpacing(10)
        ctrl.addWidget(QLabel("数量"))
        self.count_combo = QComboBox()
        self.count_combo.addItems(["全部下载", "10", "20", "50", "100", "自定义..."])
        self.count_combo.setEditable(True)
        self.count_combo.setCurrentText("全部下载")
        ctrl.addWidget(self.count_combo)
        ctrl.addSpacing(20)
        ctrl.addWidget(QLabel("保存到"))
        self.path_input = QLineEdit()
        settings = load_settings()
        self.path_input.setText(
            settings.get("download_paths", {}).get("homepage", "")
            or str(OUTPUT_HOMEPAGE)
        )
        ctrl.addWidget(self.path_input)
        browse = QPushButton("浏览...")
        browse.setObjectName("secondaryBtn")
        browse.setCursor(Qt.CursorShape.PointingHandCursor)
        browse.setMinimumHeight(font_scale(36))
        browse.clicked.connect(lambda: self._browse(self.path_input))
        ctrl.addWidget(browse)
        layout.addLayout(ctrl)

        # 进度条
        self.progress = QProgressBar()
        self.progress.setMinimumHeight(font_scale(6))
        self.progress.setMinimumWidth(font_scale(120))
        self.progress.setVisible(False)
        layout.addWidget(self.progress)

        # 主体
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
        self.user_list = QListWidget()
        self.user_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.user_list.customContextMenuRequested.connect(self._on_context_menu)
        self.user_list.itemDoubleClicked.connect(self._open_folder)
        rl.addWidget(self.user_list)
        open_btn = QPushButton("打开目录")
        open_btn.setObjectName("secondaryBtn")
        open_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        open_btn.clicked.connect(self._open_folder)
        rl.addWidget(open_btn)
        refresh_btn = QPushButton("刷新")
        refresh_btn.setObjectName("secondaryBtn")
        refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        refresh_btn.clicked.connect(self._refresh_users)
        rl.addWidget(refresh_btn)
        splitter.addWidget(right)
        splitter.setSizes([550, 300])
        layout.addWidget(splitter, 1)

        # 状态
        self.status = QLabel("就绪")
        self.status.setStyleSheet(f"color: #64748B; font-size: {scaled_font(11)}px; padding: 4px 0;")
        layout.addWidget(self.status)

        self._refresh_users()

    def _browse(self, input_widget: QLineEdit):
        folder = QFileDialog.getExistingDirectory(self, "选择保存目录", input_widget.text())
        if folder:
            input_widget.setText(folder)

    def _parse_input(self, raw: str) -> str:
        """解析用户输入：分享口令 / 短链 / 完整URL → 返回完整主页URL"""
        import re
        import requests as req
        from src.environ import USER_AGENT

        # 1. 提取短链或完整URL
        short_patterns = [
            r'https?://v\.douyin\.com/[A-Za-z0-9_\-/]+',
            r'https?://(?:www\.)?douyin\.com/user/MS4wLjAB[A-Za-z0-9_\-]+',
            r'https?://(?:www\.)?iesdouyin\.com/share/user/MS4wLjAB[A-Za-z0-9_\-]+',
        ]
        found_url = ""
        for pat in short_patterns:
            m = re.search(pat, raw)
            if m:
                found_url = m.group(0)
                break

        if not found_url:
            return ""

        # 2. 短链 → 302 解析为完整 URL
        if "v.douyin.com" in found_url:
            try:
                s = req.Session()
                s.headers.update({"User-Agent": USER_AGENT})
                r = s.get(found_url, allow_redirects=True, timeout=15, stream=True)
                r.close()
                found_url = r.url
            except Exception:
                return found_url  # 解析失败，返回原始短链

        return found_url

    def _start(self):
        raw = self.url_input.text().strip()
        if not raw:
            return

        # 解析输入：支持分享口令 + 短链 + 完整URL
        url = self._parse_input(raw)
        if not url:
            self.status.setText("未识别抖音主页链接，请检查输入")
            return

        # Cookie 循环：无效则弹窗更新
        while True:
            cookie = ensure_cookie(self)
            if not cookie:
                self.status.setText("已取消 - Cookie 未设置")
                return

            from src.api import DouyinAPI
            api = DouyinAPI(cookie_string=cookie)
            test = api.get_user_profile(
                "MS4wLjABAAAAnsZ-gU2aYmYUiMq2a1dTwH0Bst9fK3s9mEpQnvVsosI"
            )
            if test.get("nickname"):
                break

            show_login_dialog(self)
            continue

        path_text = self.path_input.text().strip()
        custom_dir = Path(path_text) if path_text else OUTPUT_HOMEPAGE
        try:
            custom_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            QMessageBox.warning(self, "路径错误", str(e))
            return

        self.dl_btn.setEnabled(False)
        self.dl_btn.setText("下载中...")
        self.pause_btn.setEnabled(True)
        self.cancel_btn.setEnabled(True)
        self.progress.setVisible(True)
        self.progress.setValue(0)
        self.log_view.clear()
        self._log(f"[>>] 原始输入: {raw}")
        self._log(f"[>>] 解析结果: {url}")

        self.thread = HomepageDownloadThread(
            url, self.count_combo.currentText().strip(), str(custom_dir)
        )
        self.thread.log_signal.connect(self._log)
        self.thread.progress_signal.connect(
            lambda c, t: (self.progress.setMaximum(t), self.progress.setValue(c))
        )
        self.thread.paused_signal.connect(
            lambda p: self.pause_btn.setText("继续" if p else "暂停")
        )
        self.thread.finished_signal.connect(self._done)
        self.thread.total_signal.connect(
            lambda t: self.count_combo.setCurrentText(f"全部下载({t}个)")
        )
        self.thread.start()

    def _pause(self):
        if self.thread and self.thread.isRunning():
            self.thread.toggle_pause()

    def _cancel(self):
        if self.thread and self.thread.isRunning():
            self.cancel_btn.setEnabled(False)
            self.pause_btn.setEnabled(False)
            self.thread.cancel()

    def _log(self, msg: str):
        self.log_view.append(colored_log(msg))
        sb = self.log_view.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _on_context_menu(self, pos):
        item = self.user_list.itemAt(pos)
        if not item:
            return
        menu = QMenu(self)
        a1 = menu.addAction("打开文件夹")
        a2 = menu.addAction("复制路径")
        action = menu.exec(self.user_list.mapToGlobal(pos))
        p = item.data(Qt.ItemDataRole.UserRole)
        if not p:
            return
        if action == a1 and Path(p).exists():
            os.startfile(p)
        elif action == a2:
            QApplication.clipboard().setText(p)

    def _done(self, stats: dict):
        # 先完成进度条
        if stats.get("video", 0) + stats.get("image", 0) > 0:
            self.progress.setValue(self.progress.maximum() or 100)
        self._refresh_users()

        self.dl_btn.setEnabled(True)
        self.dl_btn.setText("开始下载")
        self.pause_btn.setEnabled(False)
        self.cancel_btn.setEnabled(False)
        self.pause_btn.setText("暂停")
        if stats.get("cancelled"):
            self.status.setText("已取消")
        else:
            total = stats.get("video", 0) + stats.get("image", 0)
            self.status.setText(
                f"视频:{stats.get('video', 0)} 图片:{stats.get('image', 0)} "
                f"跳过:{stats.get('skip', 0)}"
            )
            w = self.window()
            if total > 0 and hasattr(w, "tray_notify"):
                w.tray_notify(
                    "Origami",
                    f"下载完成 - 视频{stats.get('video', 0)} 图片{stats.get('image', 0)}",
                    duration=3000,
                )

    def _refresh_users(self):
        self.user_list.clear()
        out = OUTPUT_HOMEPAGE
        if not out.exists():
            return
        for d in sorted(out.iterdir(), reverse=True):
            if not d.is_dir():
                continue
            tracker = d / ".downloaded.json"
            posts = 0
            if tracker.exists():
                try:
                    posts = len(json.loads(tracker.read_text(encoding="utf-8")))
                except Exception:
                    pass
            files = sum(
                1 for _ in d.rglob("*")
                if _.is_file() and _.name != ".downloaded.json"
            )
            item = QListWidgetItem(f"{d.name}  [{posts}作品, {files}文件]")
            item.setData(Qt.ItemDataRole.UserRole, str(d))
            self.user_list.addItem(item)

    def _open_folder(self):
        item = self.user_list.currentItem()
        if item:
            p = item.data(Qt.ItemDataRole.UserRole)
            if p and Path(p).exists():
                os.startfile(p)
        elif OUTPUT_HOMEPAGE.exists():
            os.startfile(str(OUTPUT_HOMEPAGE))
