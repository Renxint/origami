# -*- coding: utf-8 -*-
"""
Origami — 批量作品下载页面

双模式：
  - 下载他人主页：URL 输入 + 翻页下载（复用 HomepageDownloadThread 逻辑）
  - 下载自己主页：自动获取 sec_uid + 子标签（作品/喜欢）
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
    QListWidget, QListWidgetItem, QSplitter, QFrame,
    QFileDialog, QMenu, QApplication,
    QMessageBox, QStackedWidget, QDialog,
    QSizePolicy, QCheckBox,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer, QSize
from PyQt6.QtGui import QAction, QFont

from src.fonts import font_scale, scaled_font
from src.environ import OUTPUT_OWN, OUTPUT_OTHER, USER_AGENT
from src.utils import clean_name, pick_best_video_url, parse_sec_user_id
from src.cookie import load_cookie, save_cookie
from src.gui.dialogs.cookie_dialog import show_login_dialog

# ═══════════════════════════════════════════════════════════
# 批量下载线程（作品 / 喜欢通用）
# ═══════════════════════════════════════════════════════════

class BatchDownloadThread(QThread):
    """批量下载线程，支持 posts 和 likes 两种模式"""

    log_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(int, int)   # (current, total)
    finished_signal = pyqtSignal(dict)        # stats dict
    paused_signal = pyqtSignal(bool)          # True=paused, False=resumed
    total_signal = pyqtSignal(int)            # total count after pagination

    def __init__(self, sec_uid: str, mode: str, save_dir: str,
                 is_own: bool = False, selected_ids: set = None,
                 pre_items: list = None, source_url: str = "",
                 max_pages: int = 500):
        super().__init__()
        self.sec_uid = sec_uid
        self.mode = mode           # 'posts' | 'likes'
        self.save_dir = Path(save_dir)
        self.is_own = is_own
        self.selected_ids = selected_ids
        self.pre_items = pre_items  # 预加载的作品列表，有则跳过翻页
        self.source_url = source_url
        self.max_pages = max_pages
        self._pause_event = threading.Event()
        self._pause_event.set()
        self._cancelled = False
        self._paused = False

    def pause(self):
        self._paused = True
        self._pause_event.clear()
        self.paused_signal.emit(True)

    def resume(self):
        self._paused = False
        self._pause_event.set()
        self.paused_signal.emit(False)

    def toggle_pause(self):
        if self._paused:
            self.resume()
        else:
            self.pause()

    def cancel(self):
        self._cancelled = True
        if self._paused:
            self.resume()

    def _check_cancel(self):
        if self._cancelled:
            raise InterruptedError("已取消")

    def _wait(self):
        self._pause_event.wait()

    def run(self):
        from src.platforms.douyin import DouyinAdapter
        from src.platforms.base import MediaItem
        from src.api import _get_avatar
        from src.environ import USER_AGENT

        adapter = DouyinAdapter()
        cookie = load_cookie()
        stats = {"video": 0, "image": 0, "music": 0, "skip": 0, "fail": 0, "cancelled": False}

        try:
            # 获取用户信息
            author = None
            author_name = ""
            try:
                author = adapter.fetch_author(self.sec_uid, cookie)
                author_name = clean_name(author.nickname or self.sec_uid)
            except Exception:
                author_name = clean_name(self.sec_uid)

            # ── 目录结构 ──
            account_dir = self.save_dir / author_name
            if self.is_own:
                sub = "作品" if self.mode == "posts" else "喜欢"
                save_root = account_dir / sub
            else:
                save_root = account_dir

            save_root.mkdir(parents=True, exist_ok=True)
            data_dir = save_root / "data"
            data_dir.mkdir(parents=True, exist_ok=True)

            # ── 写主页简介 ──
            if author:
                self._write_profile(data_dir, author, cookie, self.source_url)
                if self.is_own:
                    account_data = account_dir / "data"
                    account_data.mkdir(parents=True, exist_ok=True)
                    self._write_profile(account_data, author, cookie, self.source_url)

            # ── 获取作品列表 ──
            if self.pre_items:
                # 已有预加载数据，直接转 MediaItem
                all_items = []
                for aw in self.pre_items:
                    all_items.append(MediaItem(
                        platform="douyin",
                        item_id=aw.get("aweme_id", ""),
                        item_type="实况" if aw.get("is_live_photo") else (
                            "gallery" if aw.get("images") else "video"),
                        title=aw.get("desc", ""),
                        author=aw.get("author", {}).get("nickname", ""),
                        extra={"aweme": aw},
                    ))
            else:
                self.log_signal.emit(
                    f'<span style="color:#F59E0B;">[翻页]</span> 正在获取'
                    f'{"作品" if self.mode == "posts" else "喜欢"}列表...'
                )
                all_items = []
                cursor = 0
                page = 0
                while page < self.max_pages:
                    self._check_cancel(); self._wait()
                    try:
                        data = (adapter.fetch_posts(self.sec_uid, cookie, max_cursor=cursor, count=18)
                                if self.mode == 'posts' else
                                adapter.fetch_likes(self.sec_uid, cookie, max_cursor=cursor, count=18))
                    except Exception as e:
                        self.log_signal.emit(f'<span style="color:#EF4444;">[翻页失败]</span> {e}')
                        break
                    items = data.get("items", [])
                    all_items.extend(items)
                    page += 1
                    self.log_signal.emit(
                        f'<span style="color:#94A3B8;">[第{page}页]</span> '
                        f'获取 {len(items)} 个，累计 {len(all_items)} 个'
                    )
                    if not data.get("has_more"):
                        break
                    cursor = data.get("next_cursor", 0)

            # 筛选勾选的作品（支持 aweme_id 和 aweme_id:img_idx 格式）
            if self.selected_ids:
                # 过滤掉可能的 None 值
                clean_sids = {s for s in self.selected_ids if s and isinstance(s, str)}
                img_filter = {}
                plain_ids = set()
                for sid in clean_sids:
                    if ':' in sid:
                        aw_id, idx = sid.split(':', 1)
                        img_filter.setdefault(aw_id, set()).add(int(idx))
                        plain_ids.add(aw_id)
                    else:
                        plain_ids.add(sid)
                # 过滤：aweme_id 在选中，或有单图选中
                filtered = []
                for i in all_items:
                    if i.item_id in plain_ids:
                        if i.item_id in img_filter:
                            aw = i.extra.get("aweme", {})
                            if isinstance(aw, dict):
                                aw["_img_filter"] = img_filter[i.item_id]
                        filtered.append(i)
                all_items = filtered
                self.log_signal.emit(
                    f'<span style="color:#F59E0B;">[筛选]</span> 已过滤，待下载 {len(all_items)} 个'
                )

            total = len(all_items)
            self.total_signal.emit(total)
            self.log_signal.emit(
                f'<span style="color:#22C55E;">[完成]</span> 共 {total} 个'
                f'{"作品" if self.mode == "posts" else "喜欢"}'
            )

            # 下载追踪
            tracker_file = data_dir / ".downloaded.json"
            downloaded_ids = set()
            if tracker_file.exists():
                try:
                    downloaded_ids = set(json.loads(tracker_file.read_text(encoding="utf-8")))
                except Exception:
                    pass

            # ── 作品目录辅助函数（取消时也调用）──
            def _write_catalog():
                try:
                    lines = [f"# {author_name}", "", f"共 {len(all_items)} 个作品", ""]
                    for idx, it in enumerate(all_items):
                        aw = it.extra.get("aweme", {})
                        d = clean_name(it.title or it.item_id)
                        v = aw.get("video")
                        imgs = aw.get("images") or []
                        is_lv = aw.get("is_live_photo", False) or aw.get("media_type") == 42
                        lv_imgs = [img for img in imgs if img.get("live_photo_type") == 1]
                        if is_lv and lv_imgs:
                            typ = f"实况({len(lv_imgs)}组)"
                        elif bool(v) and not imgs:
                            typ = "视频"
                        elif imgs:
                            hl = sum(1 for img in imgs if img.get("live_photo_type") == 1)
                            typ = f"图集({len(imgs)}图" + (f" 含{hl}实况)" if hl else ")")
                        else:
                            typ = "未知"
                        status = "已下载" if it.item_id in downloaded_ids else "跳过"
                        lines.append(f"{idx+1}. [{typ}] [{status}] {d}")
                    (save_root / "作品目录.md").write_text("\n".join(lines), encoding="utf-8")
                except Exception:
                    pass

            # ── 逐个下载 ──
            for i, item in enumerate(all_items):
                self._check_cancel(); self._wait()

                aweme = item.extra.get("aweme", {})
                aweme_id = item.item_id
                desc = clean_name(item.title or aweme_id)

                if aweme_id in downloaded_ids:
                    # 验证文件是否真的存在（用户可能删了文件夹）
                    prefix5 = (desc.strip()[:5] or "0").ljust(5, "0")
                    any_file = (
                        any(save_root.glob(f"{desc}.*"))
                        or any(save_root.glob(f"{prefix5}_*"))
                    )
                    if not any_file:
                        downloaded_ids.discard(aweme_id)
                    else:
                        stats["skip"] += 1
                        self.progress_signal.emit(i + 1, total)
                        self.log_signal.emit(
                            f'[{i+1}/{total}] <span style="color:#94A3B8;">[跳过]</span> {desc} (已下载)'
                        )
                        continue

                try:
                    downloaded = False
                    video = aweme.get("video")
                    images = aweme.get("images") or []
                    # 实况判断: is_live_photo 或 media_type==42 (图集media_type=2)
                    is_live = (
                        aweme.get("is_live_photo", False)
                        or aweme.get("media_type") == 42
                    )

                    # 图片命名前缀：描述前5字，不够用0补足5位
                    def _img_prefix(d: str) -> str:
                        # 取纯文本前5个字符，空的用0占位
                        prefix = d.strip()[:5] if d.strip() else "0"
                        return prefix.ljust(5, "0")

                    pfx = _img_prefix(desc)

                    # ── 纯视频 ──
                    is_pure_video = bool(video) and not images and not is_live
                    if is_pure_video:
                        # 纯视频：直接提取 URL，失败降级 BGM
                        url = pick_best_video_url(video) or ""
                        if url:
                            self.log_signal.emit(
                                f'[{i+1}/{total}] <span style="color:#F59E0B;">[视频]</span> {desc}'
                            )
                            self._dl(url, save_root / f"{desc}.mp4")
                            stats["video"] += 1
                            downloaded = True
                        else:
                            music = aweme.get("music", {})
                            music_url = (music.get("play_url") or {}).get("url_list", [""])[0] if music else ""
                            if music_url:
                                self.log_signal.emit(
                                    f'[{i+1}/{total}] <span style="color:#F59E0B;">[音频]</span> {desc}'
                                )
                                self._dl(music_url, save_root / f"{desc}.mp3")
                                stats["music"] += 1
                                downloaded = True

                    elif is_live:
                        # 实况：只需每张图片的实况封面 + 实况视频
                        live_imgs = [(j, img) for j, img in enumerate(images)
                                     if img.get("live_photo_type") == 1 and (img.get("video") or {})]
                        if not live_imgs:
                            # 没有真正的实况图片 → 降级为图集
                            self.log_signal.emit(
                                f'[{i+1}/{total}] <span style="color:#F59E0B;">[图集]</span> {desc} ({len(images)}图)'
                            )
                            for j, img in enumerate(images):
                                urls = img.get("url_list", [])
                                img_url = next(
                                    (u for u in urls if "jpeg" in u.lower() or "jpg" in u.lower()),
                                    urls[0] if urls else ""
                                )
                                if img_url:
                                    self._dl(img_url, save_root / f"{pfx}_{j+1}.jpg")
                                    stats["image"] += 1
                                    downloaded = True
                        else:
                            self.log_signal.emit(
                                f'[{i+1}/{total}] <span style="color:#F59E0B;">[实况]</span> {desc} ({len(live_imgs)}组)'
                            )
                            img_filter = aweme.get("_img_filter", None)
                            for j, img in enumerate(images):
                                if img_filter is not None and j not in img_filter:
                                    continue
                                iv = img.get("video") or {}
                                if img.get("live_photo_type") != 1 or not iv:
                                    continue
                                # 实况封面
                                for _ck in ("cover", "origin_cover"):
                                    _c = iv.get(_ck) or {}
                                    _cu = (_c.get("url_list") or [""])[0]
                                    if _cu:
                                        self._dl(_cu, save_root / f"{pfx}_{j+1}_封面.jpg")
                                        stats["image"] += 1
                                        downloaded = True
                                        break
                                # 实况视频
                                lv = pick_best_video_url(iv) or ""
                                if not lv:
                                    lv = ((iv.get("download_addr") or {}).get("url_list") or [""])[0]
                                if not lv:
                                    lv = ((iv.get("play_addr") or {}).get("url_list") or [""])[0]
                                if lv:
                                    self._dl(lv, save_root / f"{pfx}_{j+1}_实况.mp4")
                                    stats["video"] += 1

                    # ── 图片（图集 + 混在其中的实况照片，统一用 pfx_N 命名）──
                    elif images:
                        # 统计图集中混入的实况照片
                        live_in_gallery = [(j, img) for j, img in enumerate(images)
                                          if img.get("live_photo_type") == 1 and (img.get("video") or {})]
                        live_tag = f" 含{len(live_in_gallery)}实况" if live_in_gallery else ""
                        self.log_signal.emit(
                            f'[{i+1}/{total}] <span style="color:#F59E0B;">[图集]</span> {desc} ({len(images)}图{live_tag})'
                        )
                        img_filter = aweme.get("_img_filter", None)
                        for j, img in enumerate(images):
                            if img_filter is not None and j not in img_filter:
                                continue
                            # 静态图
                            urls = img.get("url_list", [])
                            img_url = next(
                                (u for u in urls if "jpeg" in u.lower() or "jpg" in u.lower()),
                                urls[0] if urls else ""
                            )
                            if img_url:
                                self._dl(img_url, save_root / f"{pfx}_{j+1}.jpg")
                                stats["image"] += 1
                                downloaded = True
                            # 图集中混入的实况照片 → 额外下载视频
                            iv = img.get("video") or {}
                            if img.get("live_photo_type") == 1 and iv:
                                for _ck in ("cover", "origin_cover"):
                                    _c = iv.get(_ck) or {}
                                    _cu = (_c.get("url_list") or [""])[0]
                                    if _cu:
                                        self._dl(_cu, save_root / f"{pfx}_{j+1}_封面.jpg")
                                        stats["image"] += 1
                                        break
                                lv = pick_best_video_url(iv) or ""
                                if not lv:
                                    lv = ((iv.get("download_addr") or {}).get("url_list") or [""])[0]
                                if not lv:
                                    lv = ((iv.get("play_addr") or {}).get("url_list") or [""])[0]
                                if lv:
                                    self._dl(lv, save_root / f"{pfx}_{j+1}_实况.mp4")
                                    stats["video"] += 1

                    if not downloaded:
                        stats["fail"] += 1
                        self.log_signal.emit(
                            f'[{i+1}/{total}] <span style="color:#EF4444;">[无资源]</span> {desc}'
                        )
                    else:
                        downloaded_ids.add(aweme_id)

                except Exception as e:
                    stats["fail"] += 1
                    self.log_signal.emit(
                        f'[{i+1}/{total}] <span style="color:#EF4444;">[失败]</span> {desc}: {e}'
                    )

                self.progress_signal.emit(i + 1, total)

            # 保存追踪
            try:
                tracker_file.write_text(
                    json.dumps(list(downloaded_ids), ensure_ascii=False), encoding="utf-8"
                )
            except Exception:
                pass

            _write_catalog()

            # 完成总结
            self.log_signal.emit(
                f'===== 下载完成 ====='
            )
            self.log_signal.emit(
                f'视频:{stats["video"]} 图片:{stats["image"]} '
                f'音乐:{stats["music"]} 跳过:{stats["skip"]} 失败:{stats["fail"]}'
            )

        except InterruptedError:
            stats["cancelled"] = True
            self.log_signal.emit('<span style="color:#F59E0B;">[已取消]</span>')
            # 取消时也更新目录
            try:
                _write_catalog()
            except Exception:
                pass
        except Exception as e:
            self.log_signal.emit(f'<span style="color:#EF4444;">[错误]</span> {e}')
        finally:
            self.finished_signal.emit(stats)

    def _write_profile(self, data_dir: Path, author, cookie: str,
                       source_url: str = ""):
        """写 主页简介.md（完整信息 + 头像 + 封面）"""
        from src.api import _get_avatar
        from src.environ import USER_AGENT
        import requests as req
        import time as _time

        profile = author.extra.get("profile", {})
        nickname = author.nickname or profile.get("nickname", "")
        unique_id = profile.get("unique_id", "")
        short_id = profile.get("short_id", "")
        uid = profile.get("uid", "")
        bio = profile.get("desc", "")
        gender_map = {0: "未设置", 1: "男", 2: "女"}
        gender = gender_map.get(profile.get("gender", 0), "")
        age = profile.get("age", -1)
        region = "-".join(filter(None, [
            profile.get("country", ""),
            profile.get("province", ""),
            profile.get("city", ""),
            profile.get("district", ""),
        ])) or "N/A"
        ip_location = profile.get("ip_location", "")
        school = profile.get("school", "")
        verify = profile.get("custom_verify", "") or profile.get("enterprise_verify_reason", "")
        is_star = profile.get("is_star", False)
        verification_type = profile.get("verification_type", 0)
        tags = profile.get("personal_tags", [])
        birthday_hidden = profile.get("birthday_hide_level", 0)
        secret = profile.get("secret", 0)

        # 数据统计
        post_count = author.post_count
        follower_count = author.follower_count
        following_count = profile.get("following_count", 0)
        favoriting_count = profile.get("favoriting_count", 0)
        total_favorited = profile.get("total_favorited", 0)
        max_follower = profile.get("max_follower_count", 0)
        dongtai = profile.get("dongtai_count", 0)

        # 其他
        live_status = profile.get("live_status", 0)
        commerce_level = profile.get("commerce_user_level", 0)
        has_commerce = profile.get("with_commerce_entry", False)
        musician = profile.get("original_musician", {})
        share_info = profile.get("share_info", {})

        avatar_url = _get_avatar(profile)
        cover_url = profile.get("cover_url", "")

        def _fmt(n):
            if n is None or n < 0: return "N/A"
            if n >= 10000:
                return f"{n/10000:.1f}万"
            return str(n)

        md = data_dir / "主页简介.md"
        lines = [
            f"# {nickname}",
            "",
            "## 基本信息",
            "",
            f"| 项目 | 内容 |",
            f"|------|------|",
            f"| 抖音号 | {unique_id or short_id or 'N/A'} |",
            f"| UID | {uid} |",
            f"| 性别 | {gender} |",
            f"| 年龄 | {age if age > 0 else 'N/A'} |",
            f"| 地区 | {region} |",
        ]
        if ip_location:
            lines.append(f"| IP属地 | {ip_location} |")
        if school:
            lines.append(f"| 学校 | {school} |")
        if bio:
            lines.append(f"| 简介 | {bio} |")
        if tags:
            lines.append(f"| 标签 | {', '.join(tags)} |")
        verify_text = verify
        if is_star:
            verify_text = f"⭐ 明星 ({verify_text})" if verify_text else "⭐ 明星"
        lines.append(f"| 认证 | {verify_text or '无'} |")
        if birthday_hidden:
            lines.append(f"| 生日 | 已隐藏 |")
        if secret:
            lines.append(f"| 私密账号 | 是 |")

        lines.extend([
            "",
            "## 数据统计",
            "",
            f"| 项目 | 数值 |",
            f"|------|------|",
            f"| 作品 | {post_count} |",
            f"| 粉丝 | {_fmt(follower_count)} |",
            f"| 最高粉丝 | {_fmt(max_follower)} |",
            f"| 关注 | {_fmt(following_count)} |",
            f"| 获赞 | {_fmt(favoriting_count)} |",
            f"| 被赞 | {_fmt(total_favorited)} |",
        ])
        if dongtai:
            lines.append(f"| 动态 | {dongtai} |")

        lines.extend(["", "## 其他信息", ""])
        if live_status:
            lines.append(f"- 直播状态: {'🔴 直播中' if live_status == 1 else '已结束/未开播'} (code={live_status})")
        if commerce_level:
            lines.append(f"- 电商等级: {commerce_level}")
        if has_commerce:
            lines.append(f"- 商品橱窗: 已开通")
        if musician:
            mc = musician.get("music_count", 0)
            mu = musician.get("music_used_count", 0)
            mdg = musician.get("digg_count", 0)
            if mc or mu:
                lines.append(f"- 原创音乐: {mc} 首, 被使用 {mu} 次, 获赞 {mdg}")

        lines.extend([
            "",
            "## 下载信息",
            "",
        ])
        if source_url:
            lines.append(f"- 主页链接: {source_url}")
        lines.append(f"- sec_uid: {profile.get('sec_uid', '')}")
        lines.append(f"- 下载日期: {_time.strftime('%Y-%m-%d %H:%M:%S')}")
        if avatar_url:
            lines.append(f"- 头像: {avatar_url}")
        if cover_url:
            lines.append(f"- 封面: {cover_url}")

        # 下载头像
        lines.append("")
        if avatar_url:
            try:
                r = req.get(avatar_url, headers={"User-Agent": USER_AGENT}, timeout=15)
                (data_dir / "avatar.jpg").write_bytes(r.content)
                lines.append("*(头像已保存)*")
            except Exception:
                pass
        # 下载封面
        if cover_url:
            try:
                r = req.get(cover_url, headers={"User-Agent": USER_AGENT}, timeout=15)
                (data_dir / "cover.jpg").write_bytes(r.content)
                lines.append("*(封面已保存)*")
            except Exception:
                pass

        md.write_text("\n".join(lines), encoding="utf-8")

    def _dl(self, url: str, path: Path):
        """流式下载单个文件，跳过已存在（文件占用重试3次）"""
        if path.exists():
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        r = requests.get(url, stream=True, timeout=120,
                         headers={
                             "User-Agent": USER_AGENT,
                             "Referer": "https://www.douyin.com/",
                         })
        r.raise_for_status()
        for attempt in range(3):
            try:
                with open(path, "wb") as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        if self._cancelled:
                            path.unlink(missing_ok=True)
                            raise InterruptedError("下载中断")
                        f.write(chunk)
                return
            except (PermissionError, OSError) as e:
                if attempt < 2:
                    import time as _t
                    _t.sleep(1)
                else:
                    raise e


# ═══════════════════════════════════════════════════════════
# 批量下载页面
# ═══════════════════════════════════════════════════════════

class BatchPage(QWidget):
    """批量作品下载页：他人主页 / 自己主页"""

    back_clicked = pyqtSignal()
    # 后台线程 → 主线程通信（pyqtSignal 跨线程自动 QueuedConnection）
    _bg_log = pyqtSignal(str, str)            # (msg, color)
    _bg_info = pyqtSignal(str)                # status text
    _bg_reset_ui = pyqtSignal()               # 重置上次下载的 UI 状态
    _bg_author_loaded = pyqtSignal(object, object, object, str)  # (author, profile, avatar_data, sec_uid)

    @staticmethod
    def _circle_pixmap(pix: "QPixmap", size: int) -> "QPixmap":
        """将 pixmap 裁剪为圆形"""
        from PyQt6.QtGui import QPainter, QPainterPath, QBrush
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

    def __init__(self):
        super().__init__()
        self.thread = None
        self._own_sec_uid = ""
        self._other_all_items = []   # 他人：翻页统计后保存的全部作品
        self._selected_ids = set()   # 他人：用户勾选的作品 ID
        self._loaded_sec_uid = ""    # 已加载的用户 sec_uid
        self._own_posts_items = []   # 自己：作品列表（预加载缓存）
        self._own_likes_items = []   # 自己：喜欢列表（预加载缓存）
        self._own_selected_ids = set()
        self._own_posts_loaded = False
        self._own_likes_loaded = False
        self._url_debounce = QTimer()
        self._url_debounce.setSingleShot(True)
        self._url_debounce.setInterval(800)
        self._url_debounce.timeout.connect(self._on_url_debounced)
        # 目录自动刷新（每3秒）
        self._refresh_timer = QTimer()
        self._refresh_timer.setInterval(3000)
        self._refresh_timer.timeout.connect(self._auto_refresh)
        self._refresh_timer.start()
        # 连接后台线程→主线程信号
        self._bg_log.connect(self._other_log_msg)
        self._bg_info.connect(self._set_other_info)
        self._bg_reset_ui.connect(self._reset_other_ui)
        self._bg_author_loaded.connect(self._on_bg_author_loaded)
        self._build()

    # ── 主体布局 ─────────────────────────────────────────

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 12, 16, 16)
        outer.setSpacing(10)

        # 顶栏（返回 + 标题 + 标签切换）
        top = QHBoxLayout()
        top.setSpacing(8)
        back = QPushButton("  < 返回")
        back.setObjectName("secondaryBtn")
        back.setCursor(Qt.CursorShape.PointingHandCursor)
        back.clicked.connect(self.back_clicked.emit)
        back.setMinimumSize(font_scale(80), font_scale(34))
        top.addWidget(back)

        title = QLabel("批量作品下载")
        title.setStyleSheet(f"font-size: {scaled_font(18)}px; font-weight: bold; color: #E11D48;")
        top.addWidget(title)

        self._tab_other = QPushButton("下载他人主页")
        self._tab_other.setCheckable(True)
        self._tab_other.setChecked(True)
        self._tab_other.setCursor(Qt.CursorShape.PointingHandCursor)
        self._tab_other.clicked.connect(lambda: self._switch_tab(0))
        top.addWidget(self._tab_other)

        self._tab_own = QPushButton("下载自己主页")
        self._tab_own.setCheckable(True)
        self._tab_own.setCursor(Qt.CursorShape.PointingHandCursor)
        self._tab_own.clicked.connect(lambda: self._switch_tab(1))
        top.addWidget(self._tab_own)

        top.addStretch()
        self._style_tabs()
        outer.addLayout(top)

        # 内容区
        self._content = QStackedWidget()
        self._content.addWidget(self._build_other_panel())
        self._content.addWidget(self._build_own_panel())
        outer.addWidget(self._content, 1)

        # 底部状态
        self._status = QLabel("就绪")
        self._status.setStyleSheet(f"color: #64748B; font-size: {scaled_font(11)}px; padding: 4px 0;")
        outer.addWidget(self._status)

    def _style_tabs(self):
        """更新标签样式"""
        pt = QApplication.instance().font().pointSize()
        for btn in (self._tab_other, self._tab_own):
            if btn.isChecked():
                btn.setStyleSheet(
                    f"font-size: {pt-1}pt; font-weight: bold; color: #FFFFFF; "
                    f"background: #E11D48; border: none; border-radius: 6px; "
                    f"padding: 5px 14px;"
                )
            else:
                btn.setStyleSheet(
                    f"font-size: {pt-1}pt; color: #64748B; "
                    f"background: #12122A; border: 1px solid #252550; "
                    f"border-radius: 6px; padding: 5px 14px;"
                )

    def _switch_tab(self, idx: int):
        self._tab_other.setChecked(idx == 0)
        self._tab_own.setChecked(idx == 1)
        self._style_tabs()
        self._content.setCurrentIndex(idx)
        if idx == 1:
            self._detect_own()

    # ══════════════════════════════════════════
    # 面板 0：下载他人主页
    # ══════════════════════════════════════════

    def _build_other_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(8)

        # ── 左右分栏：作者信息 | 下载控制 ──
        main_row = QHBoxLayout()
        main_row.setSpacing(14)

        # 左侧：作者信息卡片
        left_card = QFrame()
        left_card.setStyleSheet(
            "QFrame { background: #0E0E1C; border: 1px solid #1E1E3E; border-radius: 10px; }"
        )
        left_lay = QHBoxLayout(left_card)
        left_lay.setContentsMargins(10, 8, 10, 8)
        left_lay.setSpacing(10)
        self._other_avatar = QLabel()
        av_sz = font_scale(42)
        self._other_avatar.setFixedSize(av_sz, av_sz)
        self._other_avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._other_avatar.setStyleSheet(
            f"border: 2px solid #334155; border-radius: {av_sz//2}px;"
        )
        self._other_avatar.hide()
        left_lay.addWidget(self._other_avatar)
        info_col = QVBoxLayout()
        info_col.setSpacing(1)
        self._other_name = QLabel("")
        self._other_name.setStyleSheet(
            f"color: #F1F5F9; font-size: {scaled_font(12)}px; font-weight: bold; "
            "border: none; background: transparent;"
        )
        info_col.addWidget(self._other_name)
        self._other_stats = QLabel("")
        self._other_stats.setStyleSheet(
            f"color: #94A3B8; font-size: {scaled_font(10)}px; "
            "border: none; background: transparent;"
        )
        info_col.addWidget(self._other_stats)
        self._other_detail = QLabel("")
        self._other_detail.setStyleSheet(
            f"color: #94A3B8; font-size: {scaled_font(10)}px; "
            "border: none; background: transparent;"
        )
        info_col.addWidget(self._other_detail)
        self._other_bio = QLabel("")
        self._other_bio.setStyleSheet(
            f"color: #64748B; font-size: {scaled_font(9)}px; "
            "border: none; background: transparent;"
        )
        self._other_bio.setWordWrap(False)
        info_col.addWidget(self._other_bio)
        left_lay.addLayout(info_col, 1)
        main_row.addWidget(left_card, 3)

        # 右侧：链接 + 下载控制
        right_col = QVBoxLayout()
        right_col.setSpacing(6)
        self._other_url = QLineEdit()
        self._other_url.setPlaceholderText("粘贴主页链接（自动加载）...")
        self._other_url.setMinimumHeight(font_scale(34))
        self._other_url.returnPressed.connect(self._on_url_entered)
        self._other_url.textChanged.connect(self._on_url_text_changed)
        right_col.addWidget(self._other_url)
        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)
        self._other_select_btn = QPushButton("查看列表")
        self._other_select_btn.setObjectName("secondaryBtn")
        self._other_select_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._other_select_btn.clicked.connect(self._show_select_dialog)
        self._other_select_btn.hide()
        btn_row.addWidget(self._other_select_btn)
        self._other_pause_btn = QPushButton("暂停")
        self._other_pause_btn.setObjectName("secondaryBtn")
        self._other_pause_btn.setEnabled(False)
        self._other_pause_btn.clicked.connect(self._toggle_other_pause)
        btn_row.addWidget(self._other_pause_btn)
        self._other_cancel_btn = QPushButton("取消")
        self._other_cancel_btn.setObjectName("secondaryBtn")
        self._other_cancel_btn.setEnabled(False)
        self._other_cancel_btn.clicked.connect(self._cancel_other)
        btn_row.addWidget(self._other_cancel_btn)
        other_clear = QPushButton("✕")
        other_clear.setFixedSize(font_scale(26), font_scale(34))
        other_clear.setCursor(Qt.CursorShape.PointingHandCursor)
        other_clear.setObjectName("secondaryBtn")
        other_clear.clicked.connect(lambda: self._clear_other())
        btn_row.addWidget(other_clear)
        btn_row.addStretch()
        right_col.addLayout(btn_row)
        main_row.addLayout(right_col, 4)
        layout.addLayout(main_row)

        # 保存路径
        ctrl_row = QHBoxLayout()
        ctrl_row.setSpacing(6)
        ctrl_row.addWidget(QLabel("保存到"))
        self._other_path = QLineEdit()
        self._other_path.setText(str(OUTPUT_OTHER))
        self._other_path.setMinimumHeight(font_scale(30))
        ctrl_row.addWidget(self._other_path, 1)
        browse = QPushButton("浏览")
        browse.setObjectName("secondaryBtn")
        browse.setMinimumHeight(font_scale(30))
        browse.clicked.connect(lambda: self._choose_other_path())
        ctrl_row.addWidget(browse)
        layout.addLayout(ctrl_row)

        # 进度条
        self._other_progress = QProgressBar()
        self._other_progress.setMinimumHeight(font_scale(6))
        self._other_progress.setMinimumWidth(font_scale(120))
        self._other_progress.hide()
        layout.addWidget(self._other_progress)

        # 主区域（日志 + 已下载）
        splitter = QSplitter(Qt.Orientation.Horizontal)
        # 日志
        log_wrap = QWidget()
        log_layout = QVBoxLayout(log_wrap)
        log_layout.setContentsMargins(0, 0, 0, 0)
        log_layout.addWidget(QLabel("下载日志"))
        self._other_log = QTextEdit()
        self._other_log.setReadOnly(True)
        log_layout.addWidget(self._other_log)
        splitter.addWidget(log_wrap)
        # 已下载
        dl_wrap = QWidget()
        dl_layout = QVBoxLayout(dl_wrap)
        dl_layout.setContentsMargins(0, 0, 0, 0)
        dl_layout.addWidget(QLabel("已下载"))
        self._other_list = QListWidget()
        self._other_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._other_list.customContextMenuRequested.connect(
            lambda pos: self._list_menu(self._other_list, pos))
        self._other_list.itemDoubleClicked.connect(self._open_selected_folder)
        dl_layout.addWidget(self._other_list)
        splitter.addWidget(dl_wrap)
        splitter.setSizes([400, 200])
        layout.addWidget(splitter, 1)

        return panel

    # ══════════════════════════════════════════
    # 面板 1：下载自己主页
    # ══════════════════════════════════════════

    def _build_own_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(8)

        # 头像
        self._own_avatar = QLabel()
        av_sz = font_scale(56)
        self._own_avatar.setFixedSize(av_sz, av_sz)
        self._own_avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._own_avatar.setStyleSheet(
            f"border: 2px solid #334155; border-radius: {av_sz//2}px;"
        )
        self._own_avatar.hide()

        # 身份信息 + 子标签
        info_row = QHBoxLayout()
        info_row.setSpacing(12)
        info_row.addWidget(self._own_avatar)
        self._own_info = QLabel("正在获取账号信息...")
        self._own_info.setStyleSheet(f"color: #94A3B8; font-size: {scaled_font(12)}px;")
        info_row.addWidget(self._own_info)

        # 子标签：作品 / 喜欢
        self._sub_posts = QPushButton("作品")
        self._sub_posts.setCheckable(True)
        self._sub_posts.setChecked(True)
        self._sub_posts.setCursor(Qt.CursorShape.PointingHandCursor)
        self._sub_posts.clicked.connect(lambda: self._switch_sub(0))
        info_row.addWidget(self._sub_posts)

        self._sub_likes = QPushButton("喜欢")
        self._sub_likes.setCheckable(True)
        self._sub_likes.setCursor(Qt.CursorShape.PointingHandCursor)
        self._sub_likes.clicked.connect(lambda: self._switch_sub(1))
        info_row.addWidget(self._sub_likes)

        info_row.addStretch()
        layout.addLayout(info_row)
        self._style_sub_tabs()

        # 下载 + 暂停/取消
        action_row = QHBoxLayout()
        action_row.setSpacing(6)
        self._own_dl_btn = QPushButton("开始下载")
        self._own_dl_btn.setMinimumHeight(font_scale(38))
        self._own_dl_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._own_dl_btn.clicked.connect(self._start_own)
        action_row.addWidget(self._own_dl_btn)
        self._own_pause_btn = QPushButton("暂停")
        self._own_pause_btn.setObjectName("secondaryBtn")
        self._own_pause_btn.setEnabled(False)
        self._own_pause_btn.clicked.connect(self._toggle_own_pause)
        action_row.addWidget(self._own_pause_btn)
        self._own_cancel_btn = QPushButton("取消")
        self._own_cancel_btn.setObjectName("secondaryBtn")
        self._own_cancel_btn.setEnabled(False)
        self._own_cancel_btn.clicked.connect(self._cancel_own)
        action_row.addWidget(self._own_cancel_btn)
        self._own_select_btn = QPushButton("查看列表")
        self._own_select_btn.setObjectName("secondaryBtn")
        self._own_select_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._own_select_btn.clicked.connect(self._show_own_select_dialog)
        self._own_select_btn.hide()
        action_row.addWidget(self._own_select_btn)
        layout.addLayout(action_row)

        # 保存路径
        path_row = QHBoxLayout()
        path_row.setSpacing(6)
        path_row.addWidget(QLabel("保存到"))
        self._own_path = QLineEdit()
        self._own_path.setText(str(OUTPUT_OWN))
        self._own_path.setMinimumHeight(font_scale(30))
        path_row.addWidget(self._own_path, 1)
        browse = QPushButton("浏览")
        browse.setObjectName("secondaryBtn")
        browse.setMinimumHeight(font_scale(30))
        browse.clicked.connect(lambda: self._choose_own_path())
        path_row.addWidget(browse)
        layout.addLayout(path_row)

        # 进度条
        self._own_progress = QProgressBar()
        self._own_progress.setMinimumHeight(font_scale(6))
        self._own_progress.setMinimumWidth(font_scale(120))
        self._own_progress.hide()
        layout.addWidget(self._own_progress)

        # 主区域
        splitter = QSplitter(Qt.Orientation.Horizontal)
        log_wrap = QWidget()
        log_layout = QVBoxLayout(log_wrap)
        log_layout.setContentsMargins(0, 0, 0, 0)
        log_layout.addWidget(QLabel("下载日志"))
        self._own_log = QTextEdit()
        self._own_log.setReadOnly(True)
        log_layout.addWidget(self._own_log)
        splitter.addWidget(log_wrap)
        dl_wrap = QWidget()
        dl_layout = QVBoxLayout(dl_wrap)
        dl_layout.setContentsMargins(0, 0, 0, 0)
        dl_layout.addWidget(QLabel("已下载"))
        self._own_list = QListWidget()
        self._own_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._own_list.customContextMenuRequested.connect(
            lambda pos: self._list_menu(self._own_list, pos))
        self._own_list.itemDoubleClicked.connect(self._open_selected_folder)
        dl_layout.addWidget(self._own_list)
        splitter.addWidget(dl_wrap)
        splitter.setSizes([400, 200])
        layout.addWidget(splitter, 1)

        return panel

    def _style_sub_tabs(self):
        """子标签样式"""
        pt = QApplication.instance().font().pointSize()
        for btn in (self._sub_posts, self._sub_likes):
            if btn.isChecked():
                btn.setStyleSheet(
                    f"font-size: {pt}pt; font-weight: bold; color: #FFFFFF; "
                    f"background: #E11D48; border: none; border-radius: 6px; "
                    f"padding: 6px 16px;"
                )
            else:
                btn.setStyleSheet(
                    f"font-size: {pt}pt; color: #64748B; "
                    f"background: #12122A; border: 1px solid #252550; "
                    f"border-radius: 6px; padding: 6px 16px;"
                )

    def _switch_sub(self, idx: int):
        self._sub_posts.setChecked(idx == 0)
        self._sub_likes.setChecked(idx == 1)
        self._style_sub_tabs()

    # ── 自己身份检测 ──────────────────────────────────────

    def _detect_own(self):
        """切换到"自己主页"时，自动获取 sec_uid 和个人信息"""
        if self._own_sec_uid:
            return
        cookie = load_cookie()
        if not cookie or "sessionid=" not in cookie:
            self._own_info.setText("⚠ 未登录，请先在首页登录")
            return
        try:
            from src.platforms.douyin import DouyinAdapter
            from src.api import _get_avatar
            from src.environ import USER_AGENT
            import requests as req
            from PyQt6.QtGui import QPixmap

            adapter = DouyinAdapter()
            sec_uid = adapter.get_own_author_id(cookie)
            if sec_uid:
                self._own_sec_uid = sec_uid
                try:
                    author = adapter.fetch_author(sec_uid, cookie)
                    profile = author.extra.get("profile", {})
                    likes_total = profile.get("favoriting_count", 0)
                    self._own_info.setText(
                        f"{author.nickname}  |  "
                        f"作品: {author.post_count}  |  "
                        f"粉丝: {author.follower_count}  |  "
                        f"喜欢: {likes_total}"
                    )
                    self._sub_posts.setText(f"作品 ({author.post_count})")
                    self._sub_likes.setText(f"喜欢 ({likes_total})")

                    avatar_url = _get_avatar(profile)
                    if avatar_url:
                        av_sz = self._own_avatar.width() or 56
                        cache_path = Path(__file__).resolve().parent.parent.parent.parent / "data" / "own_avatar.jpg"
                        try:
                            r = req.get(avatar_url, headers={"User-Agent": USER_AGENT}, timeout=15)
                            cache_path.parent.mkdir(parents=True, exist_ok=True)
                            cache_path.write_bytes(r.content)
                            pix = QPixmap(str(cache_path))
                            self._own_avatar.setPixmap(
                                self._circle_pixmap(pix, av_sz))
                            self._own_avatar.show()
                        except Exception:
                            self._own_avatar.hide()

                    # 预加载：先统计作品（HTTP 快），再统计喜欢（Puppeteer 慢）
                    if not self._own_posts_loaded:
                        self._count_own_items(sec_uid, 'posts')
                    if not self._own_likes_loaded:
                        QTimer.singleShot(2000, lambda: self._count_own_items(sec_uid, 'likes'))
                except Exception:
                    self._own_info.setText(f"已识别 (sec_uid: {sec_uid[:20]}...)")
            else:
                self._own_info.setText("⚠ 无法获取账号信息，请检查登录状态")
        except Exception as e:
            self._own_info.setText(f"⚠ 获取失败: {e}")

    def _switch_sub(self, idx: int):
        self._sub_posts.setChecked(idx == 0)
        self._sub_likes.setChecked(idx == 1)
        self._style_sub_tabs()
        if not self._own_sec_uid:
            return
        mode = 'posts' if idx == 0 else 'likes'
        cached = self._own_posts_items if mode == 'posts' else self._own_likes_items
        if cached:
            # 已有缓存，直接显示
            self._own_select_btn.setText(f"查看列表 ({len(cached)})")
            self._own_select_btn.show()
        else:
            self._count_own_items(self._own_sec_uid, mode)

    def _count_own_items(self, sec_uid: str, mode: str):
        """后台翻页统计自己的作品/喜欢（线程版，不卡 UI）"""
        store = self._own_posts_items if mode == 'posts' else self._own_likes_items
        store.clear()
        self._own_selected_ids = set()
        self._own_select_btn.hide()

        tag = "作品" if mode == 'posts' else "喜欢"
        self._own_log_msg(f'[统计] 后台统计自己的{tag}...', '#F59E0B')

        cookie = load_cookie()

        def _run():
            if mode == 'posts':
                from src.api import DouyinAPI
                api = DouyinAPI(cookie_string=cookie)
            else:
                from src.platforms.douyin import DouyinAdapter
                adapter = DouyinAdapter()
            total = 0
            cursor = 0
            page = 0
            while page < 100:
                try:
                    if mode == 'posts':
                        data = api.get_user_posts(sec_uid, max_cursor=cursor, count=18)
                        items = data.get("aweme_list", [])
                    else:
                        data = adapter.fetch_likes(sec_uid, cookie, max_cursor=cursor, count=18)
                        items = data.get("items", [])
                        if isinstance(items, list) and items and hasattr(items[0], 'extra'):
                            items = [i.extra.get("aweme", {}) for i in items]
                except Exception as e:
                    self._own_log_msg(f'[统计] 中断: {e}', '#EF4444')
                    return

                if not items and page == 0:
                    self._own_log_msg(f'[统计] 暂无{tag}', '#94A3B8')
                    QTimer.singleShot(0, lambda: self._own_select_btn.setText(f"查看列表 (0)"))
                    QTimer.singleShot(0, lambda: self._own_select_btn.show())
                    return

                store.extend(items)
                total += len(items)
                page += 1
                has_more = data.get("has_more", 0)
                cursor = data.get("next_cursor", data.get("max_cursor", 0))
                if not has_more:
                    break
                time.sleep(0.3 if mode == 'posts' else 1.5)

            if mode == 'posts':
                self._own_posts_loaded = True
            else:
                self._own_likes_loaded = True
            self._own_log_msg(f'[统计] 共 {total} 个自己的{tag}', '#22C55E')
            cur_mode = 'posts' if self._sub_posts.isChecked() else 'likes'
            if cur_mode == mode:
                QTimer.singleShot(0, lambda: self._own_select_btn.setText(f"查看列表 ({total})"))
                QTimer.singleShot(0, lambda: self._own_select_btn.show())

        threading.Thread(target=_run, daemon=True).start()

    def _show_own_select_dialog(self):
        """弹出自己的作品选择对话框"""
        cur = self._own_posts_items if self._sub_posts.isChecked() else self._own_likes_items
        if not cur:
            return
        self._show_item_select_dialog(
            cur, self._own_selected_ids,
            "选择要下载的作品 — 自己主页",
            lambda: self._own_select_btn.setText(
                f"已选 {len(self._own_selected_ids)}/{len(cur)}"
            ),
            lambda msg: self._own_log_msg(msg, '#22C55E'),
        )

    def _show_item_select_dialog(self, all_items: list, selected_ids: set,
                                  title: str, update_cb, log_cb):
        """通用作品选择弹窗（QListWidget + 异步 icon）"""
        from PyQt6.QtGui import QPixmap, QIcon
        import requests as _req
        from src.environ import USER_AGENT

        dlg = QDialog(self)
        dlg.setWindowTitle(title)
        dlg.resize(font_scale(600), font_scale(520))
        dlg.setStyleSheet("QDialog { background: #0A0A14; }")
        layout = QVBoxLayout(dlg)
        layout.setSpacing(6)

        top_row = QHBoxLayout()
        sel_all = QPushButton("全选"); sel_all.setObjectName("secondaryBtn")
        desel_all = QPushButton("全不选"); desel_all.setObjectName("secondaryBtn")
        top_row.addWidget(sel_all); top_row.addWidget(desel_all); top_row.addStretch()
        cnt = QLabel(f"共 {len(all_items)} 个作品")
        cnt.setStyleSheet(f"color: #64748B; font-size: {scaled_font(11)}px;")
        top_row.addWidget(cnt)
        layout.addLayout(top_row)

        _thumb_queue = []
        _gallery_items = []  # (listItem, checkbox, img_id)
        icon_sz = font_scale(48)

        lst = QListWidget()
        lst.setIconSize(QSize(icon_sz, icon_sz))
        lst.setStyleSheet(
            "QListWidget { background: #0A0A14; border: 1px solid #252550; border-radius: 8px; }"
            f"QListWidget::item {{ padding: 8px 10px; min-height: {icon_sz + 16}px; border-bottom: 1px solid #1E1E3A; }}"
            "QListWidget::item:hover { background: #12122A; }"
        )
        for aw in all_items:
            aweme_id = aw.get('aweme_id', '')
            desc = aw.get('desc', '') or '(无描述)'
            images = aw.get("images") or []
            is_live = aw.get("is_live_photo", False)
            video = aw.get("video")
            checked = aweme_id in selected_ids or not selected_ids

            if images:
                # 图集：一行缩略图 + 主勾选框控制全选/全不选
                img_row = QWidget()
                img_lay = QHBoxLayout(img_row)
                img_lay.setContentsMargins(4, 4, 4, 4)
                img_lay.setSpacing(4)
                # 主勾选框（控制整个图集）
                gal_cb = QCheckBox()
                gal_cb.setChecked(checked)
                gal_cb.setStyleSheet("QCheckBox { spacing: 0px; }")
                img_lay.addWidget(gal_cb)
                img_cbs = []  # 子勾选框列表
                for j, img in enumerate(images[:8]):
                    img_id = f"{aweme_id}:{j}"
                    col = QVBoxLayout()
                    col.setSpacing(2)
                    urls = img.get("url_list", [])
                    img_url = next((u for u in urls if "jpeg" in u.lower() or "jpg" in u.lower()), urls[0] if urls else "")
                    tl = QLabel(f"{j+1}")
                    tl.setFixedSize(icon_sz, icon_sz)
                    tl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                    tl.setStyleSheet(
                        f"color: #475569; font-size: {scaled_font(8)}px; "
                        "background: #12122A; border: 1px solid #252550; border-radius: 4px;"
                    )
                    col.addWidget(tl)
                    if img_url:
                        _thumb_queue.append((tl, img_url, icon_sz))
                    icb = QCheckBox()
                    icb.setChecked(checked)
                    icb.setStyleSheet("QCheckBox { spacing: 0px; }")
                    col.addWidget(icb, 0, Qt.AlignmentFlag.AlignCenter)
                    img_lay.addLayout(col)
                    img_cbs.append((icb, img_id))
                img_lay.addStretch()
                # 主勾选框 ↔ 子勾选框联动
                gal_cb.setTristate(False)
                def _on_master(checked, master=gal_cb, cbs=img_cbs):
                    # clicked: 从 Partial 点击 → 直接 Checked
                    if master.checkState() == Qt.CheckState.PartiallyChecked:
                        master.blockSignals(True)
                        master.setCheckState(Qt.CheckState.Checked)
                        master.blockSignals(False)
                        checked = True
                    for cb, _ in cbs:
                        cb.setChecked(checked)
                gal_cb.clicked.connect(_on_master)
                def _on_child(checked, master=gal_cb, cbs=img_cbs):
                    all_on = all(cb.isChecked() for cb, _ in cbs)
                    none_on = not any(cb.isChecked() for cb, _ in cbs)
                    master.blockSignals(True)
                    if all_on:
                        master.setCheckState(Qt.CheckState.Checked)
                    elif none_on:
                        master.setCheckState(Qt.CheckState.Unchecked)
                    else:
                        master.setCheckState(Qt.CheckState.PartiallyChecked)
                    master.blockSignals(False)
                for cb, _ in img_cbs:
                    cb.toggled.connect(_on_child)
                for cb, img_id in img_cbs:
                    _gallery_items.append((None, cb, img_id))
                item = QListWidgetItem()
                item.setSizeHint(img_row.sizeHint())
                lst.addItem(item)
                lst.setItemWidget(item, img_row)
            else:
                # 视频：普通列表项 + icon
                itype = "实况" if is_live else "视频"
                item = QListWidgetItem()
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
                item.setText(f"[{itype}] {desc[:50]}")
                item.setData(Qt.ItemDataRole.UserRole, aweme_id)
                lst.addItem(item)
                thumb_url = ""
                if video:
                    cover = video.get("cover") or video.get("origin_cover") or {}
                    covers = cover.get("url_list", [])
                    thumb_url = covers[0] if covers else ""
                if thumb_url:
                    _thumb_queue.append((item, thumb_url, icon_sz))  # 正方形统一尺寸

        layout.addWidget(lst, 1)

        def _select_all():
            for i in range(lst.count()):
                it = lst.item(i)
                if it.flags() & Qt.ItemFlag.ItemIsUserCheckable:
                    it.setCheckState(Qt.CheckState.Checked)
            # 递归找所有子 QCheckBox
            def _all_cbs(w: QWidget):
                for child in w.findChildren(QCheckBox):
                    child.setChecked(True)
            _all_cbs(lst)
        def _deselect_all():
            for i in range(lst.count()):
                it = lst.item(i)
                if it.flags() & Qt.ItemFlag.ItemIsUserCheckable:
                    it.setCheckState(Qt.CheckState.Unchecked)
            def _none_cbs(w: QWidget):
                for child in w.findChildren(QCheckBox):
                    child.setChecked(False)
            _none_cbs(lst)
        sel_all.clicked.connect(_select_all)
        desel_all.clicked.connect(_deselect_all)

        bottom = QHBoxLayout(); bottom.addStretch()
        cancel_btn = QPushButton("取消"); cancel_btn.setObjectName("secondaryBtn")
        cancel_btn.clicked.connect(dlg.reject); bottom.addWidget(cancel_btn)
        dl_btn = QPushButton("下载选中"); dl_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        bottom.addWidget(dl_btn); layout.addLayout(bottom)

        def _confirm():
            selected = set()
            for i in range(lst.count()):
                it = lst.item(i)
                if it.checkState() == Qt.CheckState.Checked:
                    selected.add(it.data(Qt.ItemDataRole.UserRole))
            for _, cb, img_id in _gallery_items:
                if cb.isChecked():
                    selected.add(img_id)
            if not selected:
                QMessageBox.information(dlg, "提示", "请至少勾选一个")
                return
            selected_ids.clear(); selected_ids.update(selected)
            log_cb(f'[选择] 已勾选 {len(selected)} 个加入下载队列')
            update_cb()
            dlg.accept()
            # 弹窗关闭后立即开始下载
            QTimer.singleShot(100, self._start_selected_download)
        dl_btn.clicked.connect(_confirm)

        # 异步加载缩略图
        # 后台线程下载缩略图，不卡 UI 滚动
        if _thumb_queue:
            import queue as qu
            _results = qu.Queue()
            _done = [False]
            def _worker():
                for target, url, sz in _thumb_queue:
                    if _done[0]: break
                    try:
                        r = _req.get(url, headers={"User-Agent": USER_AGENT, "Referer": "https://www.douyin.com/"}, timeout=10)
                        pix = QPixmap(); pix.loadFromData(r.content)
                        _results.put((target, pix, sz))
                    except Exception: pass
            def _poll():
                try:
                    while True:
                        target, pix, sz = _results.get_nowait()
                        if dlg.isVisible():
                            sp = pix.scaled(sz, sz, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                            if isinstance(target, QListWidgetItem):
                                target.setIcon(QIcon(sp))
                            else:
                                target.setPixmap(sp)
                                target.setText("")
                                target.setStyleSheet("border: 1px solid #252550; border-radius: 4px;")
                except qu.Empty:
                    if _worker_thread.is_alive():
                        QTimer.singleShot(80, _poll)
                except Exception: pass
            _worker_thread = threading.Thread(target=_worker, daemon=True)
            _worker_thread.start()
            QTimer.singleShot(50, _poll)
            dlg.finished.connect(lambda: _done.__setitem__(0, True))

        dlg.exec()

    # ══════════════════════════════════════════
    # 他人主页 — 下载逻辑
    # ══════════════════════════════════════════

    def _ensure_cookie(self) -> bool:
        cookie = load_cookie()
        if not cookie or "sessionid=" not in cookie:
            show_login_dialog(self)
            cookie = load_cookie()
        return bool(cookie and "sessionid=" in cookie)

    def _parse_input(self, raw: str) -> str:
        """从输入文本中提取主页 URL"""
        import re
        patterns = [
            r'https?://(?:www\.)?douyin\.com/user/(MS4wLjAB[A-Za-z0-9_\-]+)',
            r'https?://(?:www\.)?iesdouyin\.com/share/user/(MS4wLjAB[A-Za-z0-9_\-]+)',
            r'https?://v\.douyin\.com/[A-Za-z0-9_\-/]+',
        ]
        for pat in patterns:
            m = re.search(pat, raw)
            if m:
                url = m.group(0)
                if "v.douyin.com" in url:
                    s = requests.Session()
                    s.headers.update({"User-Agent": USER_AGENT})
                    r = s.get(url, allow_redirects=True, timeout=15, stream=True)
                    r.close()
                    url = r.url
                return url
        return raw.strip()

    def _fetch_other_author(self, sec_uid: str):
        """获取他人头像 + 信息"""
        try:
            from src.platforms.douyin import DouyinAdapter
            from src.api import _get_avatar
            from src.environ import USER_AGENT
            import requests as req
            from PyQt6.QtGui import QPixmap

            cookie = load_cookie()
            adapter = DouyinAdapter()
            self._other_log_msg('[>>] 正在获取主页信息...', '#F59E0B')
            author = adapter.fetch_author(sec_uid, cookie)
            profile = author.extra.get("profile", {})

            # 详细信息
            nickname = author.nickname
            unique_id = profile.get("unique_id", "")
            bio = profile.get("desc", "")
            gender = {0: "未知", 1: "男", 2: "女"}.get(profile.get("gender", 0), "")
            age = profile.get("age", "")
            region = "-".join(filter(None, [
                profile.get("country", ""),
                profile.get("province", ""),
                profile.get("city", ""),
            ]))
            school = profile.get("school", "")
            verify = profile.get("custom_verify", "") or profile.get("enterprise_verify_reason", "")

            # 抖音原生排版：昵称 → 数据 → 详情 → 简介
            def _fmt(n: int) -> str:
                if n >= 10000:
                    return f"{n/10000:.1f}万"
                return str(n)

            flw = _fmt(author.follower_count)
            fav = _fmt(profile.get('total_favorited', 0))
            fwg = _fmt(profile.get('following_count', 0))
            ip_loc = profile.get("district", "") or profile.get("province", "") or ""

            stats = f"关注 {fwg}  |  粉丝 {flw}  |  获赞 {fav}"
            det = f"抖音号：{unique_id}"
            if ip_loc:
                det += f"  IP属地：{ip_loc}"
            if age and str(age) not in ("0", "-1", ""):
                det += f"  {age}岁"
            self._set_other_info(nickname, stats, det, bio)

            log_lines = [
                f'[OK] {nickname}  关注: {fwg}  粉丝: {flw}  获赞: {fav}',
            ]
            if ip_loc:
                log_lines.append(f'    IP属地: {ip_loc}  年龄: {age if age and str(age) not in ("0","-1","") else "N/A"}')
            if bio:
                log_lines.append(f'    简介: {bio[:80]}')
            for line in log_lines:
                self._other_log_msg(line, '#22C55E')

            avatar_url = _get_avatar(profile)
            if avatar_url:
                av_sz = self._other_avatar.width() or 52
                try:
                    r = req.get(avatar_url, headers={"User-Agent": USER_AGENT}, timeout=15)
                    pix = QPixmap()
                    pix.loadFromData(r.content)
                    pix = pix.scaled(av_sz, av_sz, Qt.AspectRatioMode.KeepAspectRatio,
                                     Qt.TransformationMode.SmoothTransformation)
                    self._other_avatar.setPixmap(
                        self._circle_pixmap(pix, av_sz))
                    self._other_avatar.show()
                    self._other_log_msg('[OK] 头像已加载', '#22C55E')
                except Exception:
                    self._other_avatar.hide()

            # 后台翻页统计实际可用作品数（独立 try，不影响主流程）
            try:
                self._count_other_posts(sec_uid, author)
            except Exception:
                pass
        except Exception as e:
            self._set_other_info("无法获取用户信息")
            self._other_log_msg(f'[FAIL] 获取主页信息失败: {e}', '#EF4444')

    def _count_other_posts(self, sec_uid: str, author):
        """后台翻页统计实际可用作品数"""
        from src.api import DouyinAPI

        profile = author.extra.get("profile", {})
        profile_count = author.post_count

        self._other_log_msg(
            f'[统计] 开始翻页统计可用作品 (资料显示 {profile_count} 个)...',
            '#F59E0B'
        )

        self._other_all_items = []
        self._selected_ids = set()
        self._loaded_sec_uid = sec_uid
        api = DouyinAPI(cookie_string=load_cookie())

        total = 0
        cursor = 0
        page = 0

        def _next_page():
            nonlocal total, cursor, page
            try:
                data = api.get_user_posts(sec_uid, max_cursor=cursor, count=18)
                items = data.get("aweme_list", [])
                if not items and page == 0:
                    self._other_log_msg('[统计] 无法获取作品列表', '#EF4444')
                    return
                for aw in items:
                    self._other_all_items.append(aw)  # 存完整 aweme dict
                total += len(items)
                page += 1
                has_more = data.get("has_more", 0)
                cursor = data.get("max_cursor", 0)
                if has_more and page < 100:
                    QTimer.singleShot(200, _next_page)
                else:
                    diff = ""
                    if profile_count and total != profile_count:
                        diff = f" (资料显示 {profile_count}，差额 {profile_count - total})"
                    self._other_log_msg(
                        f'[统计] 翻页完成: 共 {total} 个可用作品{diff}',
                        '#22C55E'
                    )
                    # 用抖音原生格式 + 实际统计数
                    def _fmt(n: int) -> str:
                        if n >= 10000:
                            return f"{n/10000:.1f}万"
                        return str(n)
                    flw = _fmt(author.follower_count)
                    fav = _fmt(profile.get('total_favorited', 0))
                    fwg = _fmt(profile.get('following_count', 0))
                    ip_loc = profile.get("district", "") or profile.get("province", "") or ""
                    stats = f"关注 {fwg}  |  粉丝 {flw}  |  获赞 {fav}"
                    det = f"抖音号：{profile.get('unique_id', '')}"
                    if ip_loc:
                        det += f"  IP属地：{ip_loc}"
                    age = profile.get("age", "")
                    if age and str(age) not in ("0", "-1", ""):
                        det += f"  {age}岁"
                    bio = profile.get("desc", "")
                    self._set_other_info(author.nickname, stats, det, bio)
                    if diff:
                        self._other_log_msg(
                            f'[统计] 可用 {total} 个作品{diff.strip()}', '#94A3B8'
                        )
                    self._other_select_btn.setText(f"查看列表 ({total})")
                    self._other_select_btn.show()
                    QTimer.singleShot(300, self._show_select_dialog)
            except Exception as e:
                self._other_log_msg(f'[统计] 翻页中断: {e}', '#EF4444')

        QTimer.singleShot(300, _next_page)

    def _set_downloading(self, active: bool):
        """通知主窗口暂停/恢复剪贴板检测"""
        w = self.window()
        if hasattr(w, 'set_download_active'):
            w.set_download_active(active)

    def _set_other_info(self, name: str = "", stats: str = "",
                        detail: str = "", bio: str = ""):
        """设置他人主页四行信息"""
        if hasattr(self, '_other_name'):
            self._other_name.setText(name)
            self._other_stats.setText(stats)
            self._other_detail.setText(detail)
            # 用 QFontMetrics 精确裁剪到一行
            if bio:
                fm = self._other_bio.fontMetrics()
                # 防止布局未完成时 width() 为 0
                avail = self._other_bio.width()
                if avail < 100:
                    avail = self.width() - font_scale(110)
                self._other_bio.setText(
                    fm.elidedText(bio, Qt.TextElideMode.ElideRight, max(100, avail)))
            else:
                self._other_bio.setText("")

    def _on_bg_author_loaded(self, author, profile: dict, avatar_data, sec_uid: str):
        """后台线程加载完作者信息后的 UI 更新（在主线程执行）"""
        self._apply_author_info(author, profile, avatar_data)
        try:
            self._count_other_posts(sec_uid, author)
        except Exception:
            pass

    def _apply_author_info(self, author, profile: dict, avatar_data):
        """主线程更新作者信息 UI（头像 + 四行标签）"""
        from PyQt6.QtGui import QPixmap
        nickname = author.nickname
        unique_id = profile.get("unique_id", "")
        bio = profile.get("desc", "")

        def _fmt(n):
            return f"{n/10000:.1f}万" if n >= 10000 else str(n)
        stats = (f"关注 {_fmt(profile.get('following_count',0))}  |  "
                 f"粉丝 {_fmt(author.follower_count)}  |  "
                 f"获赞 {_fmt(profile.get('total_favorited',0))}")
        det = f"抖音号：{unique_id}"
        ip_loc = profile.get("district", "") or profile.get("province", "")
        if ip_loc:
            det += f"  IP属地：{ip_loc}"
        age = profile.get("age", "")
        if age and str(age) not in ("0", "-1", ""):
            det += f"  {age}岁"
        b = ""
        if bio:
            b = bio[:36] + ".更多" if len(bio) > 36 else bio
        self._set_other_info(nickname, stats, det, b)

        if avatar_data:
            av_sz = self._other_avatar.width() or 42
            pix = QPixmap(); pix.loadFromData(avatar_data)
            self._other_avatar.setPixmap(self._circle_pixmap(pix, av_sz))
            self._other_avatar.show()
        self._other_log_msg(f'[OK] {nickname} (抖音号: {unique_id})', '#22C55E')

    def _other_log_msg(self, msg: str, color: str = '#94A3B8'):
        """向他人主页日志区追加彩色消息"""
        self._other_log.append(f'<span style="color:{color};">{msg}</span>')

    def _own_log_msg(self, msg: str, color: str = '#94A3B8'):
        """向自己主页日志区追加彩色消息"""
        self._own_log.append(f'<span style="color:{color};">{msg}</span>')

    def _show_select_dialog(self):
        """弹出他人作品选择对话框"""
        if not self._other_all_items:
            return
        # 下载中不弹窗
        if self.thread and self.thread.isRunning():
            return
        self._show_item_select_dialog(
            self._other_all_items, self._selected_ids,
            "选择要下载的作品 — 他人主页",
            lambda: self._other_select_btn.setText(
                f"已选 {len(self._selected_ids)}/{len(self._other_all_items)}"
            ),
            lambda msg: self._other_log_msg(msg, '#22C55E'),
        )

    def _reset_other_ui(self):
        """重置他人主页 UI 状态（新链接检测时调用，保留 URL 不清空）"""
        if self.thread and self.thread.isRunning():
            self.thread.cancel()
            self.thread.wait(1000)
        self._set_downloading(False)
        self._set_other_info("")
        self._other_avatar.hide()
        self._other_log.clear()
        self._other_all_items = []
        self._selected_ids = set()
        self._loaded_sec_uid = ""
        self._other_select_btn.hide()
        self._other_pause_btn.setEnabled(False)
        self._other_cancel_btn.setEnabled(False)
        self._other_progress.hide()
        self._other_progress.setValue(0)

    def _clear_other(self):
        """清除他人主页全部内容并停止下载"""
        self._reset_other_ui()
        self._other_url.clear()

    def _auto_fetch_other(self, raw: str):
        """剪贴板检测到链接后，后台解析并加载主页信息"""
        # 先重置上一次下载的残留状态（进度条、按钮、列表等）
        self._bg_reset_ui.emit()
        self._bg_log.emit('[检测] 剪贴板发现抖音链接', '#F59E0B')
        # HTTP 工作在调用线程（已经是后台线程），UI 更新通过 pyqtSignal 切主线程
        try:
            cookie = load_cookie()
            has_session = "sessionid=" in (cookie or "")
            if not cookie or not has_session:
                self._bg_info.emit("⚠ 未登录")
                return
            url = self._parse_input(raw)
            self._bg_log.emit(f'[解析] {url[:80]}', '#94A3B8')
            sec_uid = parse_sec_user_id(url)
            self._bg_log.emit(f'[识别] sec_uid: {sec_uid[:30]}...', '#94A3B8')
            # 拉取主页信息 + 头像（全部在后台线程）
            from src.platforms.douyin import DouyinAdapter
            from src.api import _get_avatar
            from src.environ import USER_AGENT
            import requests as _req
            adapter = DouyinAdapter()
            author = adapter.fetch_author(sec_uid, cookie)
            profile = author.extra.get("profile", {})
            avatar_url = _get_avatar(profile)
            avatar_data = None
            if avatar_url:
                try:
                    r = _req.get(avatar_url, headers={"User-Agent": USER_AGENT}, timeout=15)
                    avatar_data = r.content
                except Exception:
                    pass
            # UI 更新通过信号发射到主线程（pyqtSignal 跨线程自动 QueuedConnection）
            self._bg_author_loaded.emit(author, profile, avatar_data, sec_uid)
        except ValueError:
            self._bg_info.emit("无法解析链接")
            self._bg_log.emit('[FAIL] 无法从输入中提取主页链接', '#EF4444')
        except Exception as e:
            err_msg = str(e) if str(e) else "未知错误"
            self._bg_info.emit(f"获取失败: {err_msg[:30]}")
            self._bg_log.emit(f'[FAIL] {err_msg}', '#EF4444')

    # ── URL 输入自动加载 ─────────────────────────────────

    def _on_url_text_changed(self, text: str):
        """URL 输入变化 → 防抖后自动拉取主页信息"""
        if not text.strip():
            return
        self._url_debounce.stop()
        self._url_debounce.start()

    def _on_url_debounced(self):
        """防抖到期，触发自动拉取"""
        raw = self._other_url.text().strip()
        if not raw:
            return
        # 只要有 douyin.com 就尝试拉取（短链由 _trigger_fetch → _parse_input 解析）
        if "douyin.com" not in raw:
            return
        self._trigger_fetch(raw)

    def _on_url_entered(self):
        """回车立即触发"""
        raw = self._other_url.text().strip()
        if not raw:
            return
        self._url_debounce.stop()
        self._trigger_fetch(raw)

    def _trigger_fetch(self, raw: str):
        """触发后台拉取主页信息"""
        self._url_debounce.stop()  # 阻止防抖重复触发
        if not self._ensure_cookie():
            return
        url = self._parse_input(raw)
        try:
            sec_uid = parse_sec_user_id(url)
        except ValueError:
            self._bg_info.emit("无法解析链接")
            return
        # 相同 sec_uid 不重复加载
        if sec_uid == self._loaded_sec_uid and self._other_all_items:
            return
        self._loaded_sec_uid = sec_uid
        threading.Thread(target=lambda: self._auto_fetch_other(url), daemon=True).start()

    # ── 选中下载 ──────────────────────────────────────────

    def _start_selected_download(self):
        """弹窗勾选确认后，启动批量下载（由 _show_select_dialog 的回调触发）"""
        raw = self._other_url.text().strip()
        if not raw or not self._loaded_sec_uid:
            return
        if not self._ensure_cookie():
            return
        url = self._parse_input(raw)
        save_dir = self._other_path.text().strip() or str(OUTPUT_OTHER)

        self._other_pause_btn.setEnabled(True)
        self._other_cancel_btn.setEnabled(True)
        self._other_pause_btn.setText("暂停")
        self._other_progress.show()
        self._other_log_msg("-----------------------", '#334155')
        self._other_log_msg(f"[下载] 已选 {len(self._selected_ids)} 个，开始下载", '#F59E0B')

        selected = self._selected_ids if self._selected_ids else None
        pre_items = self._other_all_items if self._other_all_items else None
        self.thread = BatchDownloadThread(
            self._loaded_sec_uid, 'posts', save_dir, selected_ids=selected,
            pre_items=pre_items, source_url=url,
        )
        self.thread.log_signal.connect(self._other_log_append)
        self.thread.progress_signal.connect(self._other_progress_update)
        self.thread.total_signal.connect(lambda t: self._other_progress.setMaximum(t))
        self.thread.paused_signal.connect(self._other_on_paused)
        self.thread.finished_signal.connect(self._other_done)
        self._set_downloading(True)
        self.thread.start()

    def _toggle_other_pause(self):
        if self.thread:
            self.thread.toggle_pause()

    def _cancel_other(self):
        if self.thread:
            self.thread.cancel()

    def _other_log_append(self, msg: str):
        self._other_log.append(msg)

    def _other_progress_update(self, cur: int, total: int):
        self._other_progress.setMaximum(total)
        self._other_progress.setValue(cur)

    def _other_on_paused(self, paused: bool):
        self._other_pause_btn.setText("继续" if paused else "暂停")

    def _other_done(self, stats: dict):
        self._set_downloading(False)
        self._other_pause_btn.setEnabled(False)
        self._other_cancel_btn.setEnabled(False)
        self._other_progress.setValue(self._other_progress.maximum())
        self._refresh_other_list()

        parts = []
        if stats.get("video"):
            parts.append(f"视频×{stats['video']}")
        if stats.get("image"):
            parts.append(f"图片×{stats['image']}")
        if stats.get("skip"):
            parts.append(f"跳过×{stats['skip']}")
        tag = "已取消 | " if stats.get("cancelled") else ""
        self._status.setText(f"{tag}{' | '.join(parts)}")

        if stats.get("video") or stats.get("image"):
            w = self.window()
            if hasattr(w, "tray_notify"):
                w.tray_notify("Origami", f"下载完成：{', '.join(parts)}")

    # ══════════════════════════════════════════
    # 自己主页 — 下载逻辑
    # ══════════════════════════════════════════

    def _start_own(self):
        if not self._own_sec_uid:
            self._detect_own()
            if not self._own_sec_uid:
                QMessageBox.warning(self, "错误", "无法获取账号信息，请检查登录状态")
                return
        if not self._ensure_cookie():
            return

        mode = 'posts' if self._sub_posts.isChecked() else 'likes'
        save_dir = self._own_path.text().strip() or str(OUTPUT_OWN)

        self._own_dl_btn.setEnabled(False)
        self._own_pause_btn.setEnabled(True)
        self._own_cancel_btn.setEnabled(True)
        self._own_pause_btn.setText("暂停")
        self._own_progress.show()
        self._own_log.clear()

        own_sel = self._own_selected_ids if self._own_selected_ids else None
        pre = (self._own_posts_items if mode == 'posts' else self._own_likes_items) or None
        self.thread = BatchDownloadThread(
            self._own_sec_uid, mode, save_dir, is_own=True,
            selected_ids=own_sel, pre_items=pre,
        )
        self.thread.log_signal.connect(self._own_log_append)
        self.thread.progress_signal.connect(self._own_progress_update)
        self.thread.total_signal.connect(lambda t: self._own_progress.setMaximum(t))
        self.thread.paused_signal.connect(self._own_on_paused)
        self.thread.finished_signal.connect(self._own_done)
        self._set_downloading(True)
        self.thread.start()

    def _toggle_own_pause(self):
        if self.thread:
            self.thread.toggle_pause()

    def _cancel_own(self):
        if self.thread:
            self.thread.cancel()

    def _own_log_append(self, msg: str):
        self._own_log.append(msg)

    def _own_progress_update(self, cur: int, total: int):
        self._own_progress.setMaximum(total)
        self._own_progress.setValue(cur)

    def _own_on_paused(self, paused: bool):
        self._own_pause_btn.setText("继续" if paused else "暂停")

    def _own_done(self, stats: dict):
        self._set_downloading(False)
        self._own_dl_btn.setEnabled(True)
        self._own_pause_btn.setEnabled(False)
        self._own_cancel_btn.setEnabled(False)
        self._own_progress.setValue(self._own_progress.maximum())
        self._refresh_own_list()

        parts = []
        if stats.get("video"):
            parts.append(f"视频×{stats['video']}")
        if stats.get("image"):
            parts.append(f"图片×{stats['image']}")
        if stats.get("skip"):
            parts.append(f"跳过×{stats['skip']}")
        tag = "已取消 | " if stats.get("cancelled") else ""
        self._status.setText(f"{tag}{' | '.join(parts)}")

        if stats.get("video") or stats.get("image"):
            w = self.window()
            if hasattr(w, "tray_notify"):
                w.tray_notify("Origami", f"下载完成：{', '.join(parts)}")

    # ══════════════════════════════════════════
    # 工具方法
    # ══════════════════════════════════════════

    def _choose_other_path(self):
        folder = QFileDialog.getExistingDirectory(self, "选择保存目录", self._other_path.text())
        if folder:
            self._other_path.setText(folder)

    def _choose_own_path(self):
        folder = QFileDialog.getExistingDirectory(self, "选择保存目录", self._own_path.text())
        if folder:
            self._own_path.setText(folder)

    def _open_selected_folder(self):
        """双击列表项 → 打开该目录"""
        lst = self.sender()
        if lst is None:
            return
        item = lst.currentItem()
        if item:
            path = item.data(Qt.ItemDataRole.UserRole) or item.toolTip()
            if path and os.path.exists(path):
                os.startfile(path)

    def _open_folder(self, path: str):
        os.startfile(path) if os.path.exists(path) else None

    def _list_menu(self, lst: QListWidget, pos):
        item = lst.itemAt(pos)
        if not item:
            return
        menu = QMenu()
        a1 = menu.addAction("打开所在文件夹")
        a1.triggered.connect(lambda: self._open_folder(item.toolTip()))
        a2 = menu.addAction("复制路径")
        a2.triggered.connect(lambda: QApplication.clipboard().setText(item.toolTip()))
        menu.exec(lst.mapToGlobal(pos))

    def _auto_refresh(self):
        """定时自动刷新两个列表"""
        try:
            self._refresh_other_list()
        except Exception:
            pass
        try:
            self._refresh_own_list()
        except Exception:
            pass

    def _make_list_row(self, name: str, dir_path: Path, count: int, files: int) -> QWidget:
        """创建列表行：删除按钮 + 名称 + 文件数"""
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
        del_btn.clicked.connect(lambda checked, p=dir_path: self._delete_folder(p))
        lay.addWidget(del_btn)
        label = QLabel(f"{name}  [{count}作品, {files}文件]")
        label.setStyleSheet(f"color: #E2E8F0; font-size: {scaled_font(10)}px; border: none;")
        lay.addWidget(label, 1)
        return row

    def _delete_folder(self, dir_path: Path):
        """删除目录（确认后）"""
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

    def _refresh_other_list(self):
        self._other_list.clear()
        path = Path(self._other_path.text() or str(OUTPUT_OTHER))
        if not path.exists():
            return
        for d in sorted(path.iterdir(), reverse=True):
            if d.is_dir():
                tracker = d / ".downloaded.json"
                count = 0
                if tracker.exists():
                    try:
                        count = len(json.loads(tracker.read_text(encoding="utf-8")))
                    except Exception:
                        pass
                files = sum(1 for _ in d.rglob("*") if _.is_file() and _.name != ".downloaded.json")
                row = self._make_list_row(d.name, d, count, files)
                item = QListWidgetItem()
                item.setSizeHint(row.sizeHint())
                item.setData(Qt.ItemDataRole.UserRole, str(d))
                item.setToolTip(str(d))
                self._other_list.addItem(item)
                self._other_list.setItemWidget(item, row)

    def _refresh_own_list(self):
        self._own_list.clear()
        path = Path(self._own_path.text() or str(OUTPUT_OWN))
        if not path.exists():
            return
        for d in sorted(path.iterdir(), reverse=True):
            if d.is_dir():
                tracker = d / ".downloaded.json"
                count = 0
                if tracker.exists():
                    try:
                        count = len(json.loads(tracker.read_text(encoding="utf-8")))
                    except Exception:
                        pass
                files = sum(1 for _ in d.rglob("*") if _.is_file() and _.name != ".downloaded.json")
                row = self._make_list_row(d.name, d, count, files)
                item = QListWidgetItem()
                item.setSizeHint(row.sizeHint())
                item.setData(Qt.ItemDataRole.UserRole, str(d))
                item.setToolTip(str(d))
                self._own_list.addItem(item)
                self._own_list.setItemWidget(item, row)
