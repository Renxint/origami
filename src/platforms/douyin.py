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
        aweme = self._fetch_detail_http(item_id, cookie)

        desc = aweme.get("desc", "") or item_id
        author_info = aweme.get("author", {})
        author = author_info.get("nickname", "")
        author_id = author_info.get("sec_uid", "") or author_info.get("uid", "")
        # 封面
        cover_url = ""
        cover = aweme.get("video", {}).get("cover", {}) or aweme.get("video", {}).get("origin_cover", {})
        if cover:
            covers = cover.get("url_list", [])
            cover_url = covers[0] if covers else ""

        media_urls = []
        item_type = "video"
        text_content = ""

        video = aweme.get("video")
        images = aweme.get("images") or []
        media_type = aweme.get("media_type", 0)  # 4=视频, 68=图文

        # 判断是否为文章/笔记：media_type=68(图文) 43(文本+音乐) 或 video无bit_rate(无视频流)
        def _extract_note_text(aw):
            # 1. article_info — 文章详情
            ai = aw.get("article_info", {})
            if isinstance(ai, dict):
                # markdown 格式正文（优先）
                ac_raw = ai.get("article_content", "")
                if isinstance(ac_raw, str) and ac_raw:
                    try:
                        ac_obj = json.loads(ac_raw)
                        body = ac_obj.get("markdown") or ac_obj.get("long_article_abstract", "")
                        if body: return body
                    except Exception:
                        pass
                # 标题和元信息
                ai_title = ai.get("article_title", "")
                if ai_title and not ai_title in ("",):
                    return ai_title  # 只有标题没有正文时
            # 2. content / preview_title / desc
            for key in ("content", "preview_title", "desc"):
                c = aw.get(key, "")
                if isinstance(c, str) and c.strip():
                    return c
            # 3. text_extra（字幕列表）
            te = aw.get("text_extra") or []
            if isinstance(te, list) and te:
                parts = [t.get("text", "") if isinstance(t, dict) else str(t) for t in te]
                text = "\n\n".join(p for p in parts if p.strip())
                if text: return text
            return ""

        has_real_video = video and (video.get("bit_rate") or video.get("play_addr_h264"))
        is_note = (media_type in (68, 43)
                   or (video and not has_real_video and not images))

        if is_note:
            item_type = "note"
            body = _extract_note_text(aweme) or aweme.get("desc", "")
            # 拼接完整文章：标题 + 元信息 + 正文
            ai = aweme.get("article_info", {})
            art_title = ai.get("article_title", "") or aweme.get("preview_title", "") or desc
            read_time = ai.get("read_time", 0)
            create_time = aweme.get("create_time", 0)
            date_str = ""
            if create_time:
                import datetime
                date_str = datetime.datetime.fromtimestamp(create_time).strftime("%Y-%m-%d")
            header = f"# {art_title}\n\n"
            if date_str or read_time:
                meta_parts = []
                if date_str: meta_parts.append(date_str)
                if read_time: meta_parts.append(f"阅读需要{read_time}分钟")
                header += "> " + " · ".join(meta_parts) + "\n\n"
            header += f"> 作者：{author}\n\n"
            text_content = header + body
            for img in images:
                urls = img.get("url_list", [])
                img_url = next((u for u in urls if "webp" in u.lower()), None) \
                       or next((u for u in urls if "jpeg" in u.lower()), None) \
                       or next((u for u in urls if "jpg" in u.lower()), None) \
                       or (urls[0] if urls else "")
                if img_url: media_urls.append(img_url)
        elif has_real_video:
            url = pick_best_video_url(video)
            if url:
                media_urls.append(url)
                item_type = "video" if not images else "video"
            elif images:
                # video 存在但无有效视频流（如 mp3 背景音乐）→ 降级为图集
                item_type = "gallery"
                for img in images:
                    urls = img.get("url_list", [])
                    img_url = next((u for u in urls if "webp" in u.lower()), None) \
                       or next((u for u in urls if "jpeg" in u.lower()), None) \
                       or next((u for u in urls if "jpg" in u.lower()), None) \
                       or (urls[0] if urls else "")
                    if img_url:
                        media_urls.append(img_url)
            if not media_urls:
                item_type = "video"  # 有 video 对象但没有可播放 URL
        elif images:
            item_type = "gallery"
            for img in images:
                urls = img.get("url_list", [])
                img_url = next((u for u in urls if "webp" in u.lower()), None) \
                       or next((u for u in urls if "jpeg" in u.lower()), None) \
                       or next((u for u in urls if "jpg" in u.lower()), None) \
                       or (urls[0] if urls else "")
                if img_url:
                    media_urls.append(img_url)

        return MediaItem(
            platform="douyin",
            item_id=item_id,
            item_type=item_type,
            title=desc,
            author=author,
            author_id=author_id,
            cover_url=cover_url,
            media_urls=media_urls,
            text_content=text_content,
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

        # 性别映射
        gender_map = {0: "未设置", 1: "男", 2: "女"}
        gender = profile.get("gender", 0)

        return AuthorInfo(
            platform="douyin",
            author_id=author_id,
            nickname=profile.get("nickname", ""),
            unique_id=profile.get("unique_id", ""),
            short_id=profile.get("short_id", ""),
            uid=profile.get("uid", ""),
            avatar_url=profile.get("avatar_url", ""),
            cover_url=profile.get("cover_url", ""),
            bio=profile.get("desc", ""),
            post_count=profile.get("aweme_count", 0),
            follower_count=profile.get("follower_count", 0),
            following_count=profile.get("following_count", 0),
            favoriting_count=profile.get("favoriting_count", 0),
            total_favorited=profile.get("total_favorited", 0),
            country=profile.get("country", ""),
            province=profile.get("province", ""),
            city=profile.get("city", ""),
            ip_location=profile.get("ip_location", ""),
            gender=gender,
            age=profile.get("age", -1),
            verify=profile.get("custom_verify", "") or profile.get("enterprise_verify_reason", ""),
            tags=profile.get("tags", []),
            extra={"profile": profile},
        )

    def fetch_posts(
        self, author_id: str, cookie: str = "",
        max_cursor: int = 0, count: int = 18
    ) -> dict:
        """翻页获取作品列表（纯 HTTP）"""
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

    def fetch_user_collection(self, cookie: str = "",
                               cursor: int = 0, count: int = 18) -> dict:
        """翻页获取当前登录用户的收藏作品列表（POST，仅自己可见）

        同时拉取 disabled_item_ids（图集/实况等非视频类型），
        通过 aweme/detail 端点逐个获取完整数据。
        """
        import requests as _r
        cookie = cookie or self._load_cookie()
        resp = _r.post(
            "https://www.douyin.com/aweme/v1/web/aweme/listcollection/",
            headers={
                "User-Agent": USER_AGENT,
                "Cookie": cookie,
                "Referer": "https://www.douyin.com/",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={"cursor": str(cursor), "count": str(count)},
            timeout=20,
        )
        data = resp.json()
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
        # 拉取 disabled 作品（图集/实况等，API 过滤掉的类型）
        # 插在每页最前面——disabled 是较新的收藏，API 把它们从列表中剔除了
        disabled_ids = data.get("disabled_item_ids", []) or []
        disabled_items = []
        for did in disabled_ids:
            try:
                media = self.fetch_media(did, cookie)
                disabled_items.append(media)
            except Exception:
                pass
        items = disabled_items + items
        return {
            "items": items,
            "has_more": bool(data.get("has_more", 0)),
            "next_cursor": data.get("max_cursor", 0) or data.get("cursor", 0),
        }

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

    def fetch_music(self, author_id: str, cookie: str = "",
                    max_cursor: int = 0, count: int = 18) -> dict:
        """翻页获取收藏的音乐列表"""
        import requests as _r
        cookie = cookie or self._load_cookie()
        params = (
            f"sec_user_id={author_id}&max_cursor={max_cursor}&count={count}"
            f"&aid=6383&device_platform=webapp&version_code=290100"
            f"&version_name=29.1.0&cookie_enabled=true"
        )
        url = f"https://www.douyin.com/aweme/v1/web/music/listcollection/?{params}"
        resp = _r.get(url, headers={
            "User-Agent": USER_AGENT,
            "Cookie": cookie,
            "Referer": "https://www.douyin.com/",
        }, timeout=20)
        data = resp.json()
        music_list = data.get("mc_list", []) or data.get("music_list", [])
        items = []
        for m in music_list:
            music_info = m.get("music_info", m)
            play = music_info.get("play_url", {}) or {}
            urls = play.get("url_list", [])
            items.append({
                "music_id": music_info.get("id_str", ""),
                "title": music_info.get("title", ""),
                "author": music_info.get("author", ""),
                "url": urls[0] if urls else "",
                "duration": music_info.get("duration", 0),
            })
        return {
            "items": items,
            "has_more": bool(data.get("has_more", 0)),
            "next_cursor": data.get("max_cursor", 0) or data.get("cursor", 0),
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

    def _fetch_detail_http(self, aweme_id: str, cookie: str = "") -> dict:
        """纯 HTTP 调用 aweme/detail 获取作品详情（不需要 Playwright）"""
        import requests as _r
        from src.environ import USER_AGENT

        params = (
            f"aweme_id={aweme_id}&aid=6383&device_platform=webapp"
            f"&version_code=290100&version_name=29.1.0"
            f"&cookie_enabled=true&screen_width=1920&screen_height=1080"
            f"&browser_language=zh-CN&browser_platform=Win32"
            f"&browser_name=Edge&browser_version=130.0.0.0"
            f"&browser_online=true&engine_name=Blink&engine_version=130.0.0.0"
            f"&os_name=Windows&os_version=10&cpu_core_num=12"
            f"&device_memory=8&platform=PC&downlink=10"
            f"&effective_type=4g&round_trip_time=100"
        )
        url = f"https://www.douyin.com/aweme/v1/web/aweme/detail/?{params}"

        headers = {
            "User-Agent": USER_AGENT,
            "Cookie": cookie or self._load_cookie(),
            "Referer": "https://www.douyin.com/",
        }
        try:
            resp = _r.get(url, headers=headers, timeout=20)
            data = resp.json()
        except Exception as e:
            raise RuntimeError(f"获取视频数据失败: {e}")

        status = data.get("status_code", -1)
        if status != 0:
            raise RuntimeError(
                f"API 返回异常 status_code={status} msg={data.get('status_msg', '')}"
            )
        aweme = data.get("aweme_detail", {})
        if not aweme:
            raise RuntimeError("API 未返回作品数据，请检查 Cookie 是否有效")
        return aweme


# 注册
register_platform(DouyinAdapter)
