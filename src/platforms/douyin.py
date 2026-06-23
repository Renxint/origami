# -*- coding: utf-8 -*-
"""
Origami — 抖音平台适配器

基于已验证的 src/api.py + sign-server 方案。
短链 → 302 解析 → sec_uid → 用户信息 / 作品翻页 → 视频详情签名。

不需要 a_bogus / msToken，仅需 Cookie + 设备指纹即可翻页。
视频详情（获取无水印链接）仍需 sign-server。
"""

import re
import json
import time
from pathlib import Path

import requests

from src.platforms.base import PlatformAdapter, MediaItem, AuthorInfo, register_platform
from src.environ import USER_AGENT
from src.utils import clean_name, pick_best_video_url
from src.cookie import load_cookie


class DouyinAdapter(PlatformAdapter):
    platform_id = "douyin"
    platform_name = "抖音"

    # ── URL 解析 ──────────────────────────────────────────

    def resolve_url(self, url: str) -> str:
        """
        从分享链接提取内容 ID。

        支持:
          - https://v.douyin.com/xxx/  (短链)
          - https://www.douyin.com/video/123456
          - https://www.douyin.com/note/123456
          - 分享口令文本（自动提取短链）
        """
        # 提取链接
        patterns = [
            r'https?://v\.douyin\.com/[A-Za-z0-9_\-/]+',
            r'https?://(?:www\.)?douyin\.com/(?:video|note)/(\d+)',
        ]
        for pat in patterns:
            m = re.search(pat, url)
            if m:
                extracted = m.group(0)
                break
        else:
            raise ValueError("未识别抖音链接")

        # 如果是短链，走 302 重定向
        m = re.search(r'/(?:video|note)/(\d+)', extracted)
        if m:
            return m.group(1)

        if "v.douyin.com" in extracted:
            s = requests.Session()
            s.headers.update({"User-Agent": USER_AGENT})
            r = s.get(extracted, allow_redirects=True, timeout=15, stream=True)
            r.close()
            m = re.search(r'/(?:video|note)/(\d+)', r.url)
            if m:
                return m.group(1)

        raise ValueError(f"无法解析: {extracted}")

    def resolve_user_url(self, url: str) -> str:
        """从主页链接提取 sec_user_id"""
        m = re.search(r'/user/(MS4wLjAB[A-Za-z0-9_\-]+)', url.strip())
        if m:
            return m.group(1)
        raise ValueError(f"无法提取 sec_user_id: {url}")

    # ── 单视频 ────────────────────────────────────────────

    def fetch_media(self, item_id: str, cookie: str = "") -> MediaItem:
        """获取视频详情 + 无水印链接（需 sign-server）"""
        cookie = cookie or self._load_cookie()
        aweme = self._call_sign_server(item_id, cookie)

        desc = aweme.get("desc", "") or item_id
        author = aweme.get("author", {}).get("nickname", "")

        media_urls = []
        item_type = "video"

        video = aweme.get("video")
        if video:
            url = pick_best_video_url(video)
            if url:
                media_urls.append(url)
                item_type = "video"

        images = aweme.get("images") or []
        if images:
            item_type = "gallery" if video else "image"
            for img in images:
                urls = img.get("url_list", [])
                img_url = next((u for u in urls if "jpeg" in u.lower() or "jpg" in u.lower()), urls[0] if urls else "")
                if img_url:
                    media_urls.append(img_url)

        return MediaItem(
            platform="douyin",
            item_id=item_id,
            item_type=item_type,
            title=desc,
            author=author,
            media_urls=media_urls,
            extra={"aweme": aweme},
        )

    # ── 用户主页 ──────────────────────────────────────────

    def fetch_author(self, author_id: str, cookie: str = "") -> AuthorInfo:
        """获取用户信息（纯 HTTP，不需要签名）"""
        from src.api import DouyinAPI
        cookie = cookie or self._load_cookie()
        api = DouyinAPI(cookie_string=cookie)
        profile = api.get_user_profile(author_id)

        if not profile or profile.get("_error"):
            raise RuntimeError(profile.get("_error", "无法获取用户信息，请检查Cookie"))

        return AuthorInfo(
            platform="douyin",
            author_id=author_id,
            nickname=profile.get("nickname", ""),
            avatar_url=profile.get("avatar_url", ""),
            bio=profile.get("desc", ""),
            post_count=profile.get("aweme_count", 0),
            follower_count=profile.get("follower_count", 0),
            extra={"profile": profile},
        )

    def fetch_posts(
        self, author_id: str, cookie: str = "",
        max_cursor: int = 0, count: int = 18
    ) -> dict:
        """翻页获取作品列表（纯 HTTP，不需要签名）"""
        from src.api import DouyinAPI
        cookie = cookie or self._load_cookie()
        api = DouyinAPI(cookie_string=cookie)
        data = api.get_user_posts(author_id, max_cursor=max_cursor, count=count)

        aweme_list = data.get("aweme_list", [])
        items = []
        for aweme in aweme_list:
            items.append(MediaItem(
                platform="douyin",
                item_id=aweme.get("aweme_id", ""),
                item_type="video" if aweme.get("video") else ("image" if aweme.get("images") else "unknown"),
                title=aweme.get("desc", ""),
                author=aweme.get("author", {}).get("nickname", ""),
                extra={"aweme": aweme},
            ))

        return {
            "items": items,
            "has_more": bool(data.get("has_more", 0)),
            "next_cursor": data.get("max_cursor", 0),
            "total": None,
        }

    # ── 喜欢列表 ──────────────────────────────────────────

    def fetch_likes(
        self, author_id: str, cookie: str = "",
        max_cursor: int = 0, count: int = 18
    ) -> dict:
        """翻页获取喜欢列表（需签名，走 Puppeteer）"""
        from src.webview_api import get_user_likes
        data = get_user_likes(author_id, max_cursor=max_cursor, count=count)

        aweme_list = data.get("aweme_list", [])
        items = []
        for aweme in aweme_list:
            items.append(MediaItem(
                platform="douyin",
                item_id=aweme.get("aweme_id", ""),
                item_type="video" if aweme.get("video") else ("image" if aweme.get("images") else "unknown"),
                title=aweme.get("desc", ""),
                author=aweme.get("author", {}).get("nickname", ""),
                extra={"aweme": aweme},
            ))

        return {
            "items": items,
            "has_more": bool(data.get("has_more", 0)),
            "next_cursor": data.get("max_cursor", 0),
            "total": None,
        }

    def fetch_comments(self, aweme_id: str, cookie: str = "",
                       cursor: int = 0, count: int = 20) -> dict:
        """获取作品评论列表（HTTP，不需要签名）"""
        from src.api import DouyinAPI
        cookie = cookie or self._load_cookie()
        api = DouyinAPI(cookie_string=cookie)
        return api.get_comments(aweme_id, cursor=cursor, count=count)

    def fetch_favorites(self, favorite_id: str, cookie: str = "",
                        max_cursor: int = 0, count: int = 18) -> dict:
        """翻页获取收藏夹作品列表"""
        from src.api import DouyinAPI
        cookie = cookie or self._load_cookie()
        api = DouyinAPI(cookie_string=cookie)
        data = api.get_favorite_items(favorite_id, max_cursor=max_cursor, count=count)
        aweme_list = data.get("aweme_list", [])
        items = []
        for aw in aweme_list:
            items.append(MediaItem(
                platform="douyin",
                item_id=aw.get("aweme_id", ""),
                item_type="video" if aw.get("video") else ("image" if aw.get("images") else "unknown"),
                title=aw.get("desc", ""),
                author=aw.get("author", {}).get("nickname", ""),
                extra={"aweme": aw},
            ))
        return {
            "items": items,
            "has_more": bool(data.get("has_more", 0)),
            "next_cursor": data.get("max_cursor", 0),
            "total": None,
        }

    def get_own_author_id(self, cookie: str = "") -> str:
        """获取当前登录用户的 sec_uid"""
        from src.api import DouyinAPI
        cookie = cookie or self._load_cookie()
        api = DouyinAPI(cookie_string=cookie)
        return api.get_own_sec_uid()

    # ── Cookie ────────────────────────────────────────────

    def check_cookie(self, cookie: str) -> bool:
        """检查 Cookie 有效性：必须含 sessionid + ttwid"""
        return bool(cookie) and "sessionid=" in cookie and "ttwid=" in cookie

    def get_login_url(self) -> str:
        return "https://www.douyin.com/"

    # ── 内部方法 ──────────────────────────────────────────

    def _load_cookie(self) -> str:
        return load_cookie()

    def _call_sign_server(self, aweme_id: str, cookie: str) -> dict:
        """通过 Playwright 常驻浏览器获取视频签名数据（替代旧 Node.js bootstrap.js）"""
        from src.webview_api import call_server

        for attempt in (1, 2):
            data = call_server("video", aweme_id=aweme_id)
            if "_error" not in data:
                return data.get("aweme_detail", {})

            err = data.get("_error", "")
            if "browser" in err.lower() and attempt == 1:
                time.sleep(5)
                continue
            raise RuntimeError(err or "获取视频数据失败")

        raise RuntimeError("获取视频数据失败")


# 注册
register_platform(DouyinAdapter)
