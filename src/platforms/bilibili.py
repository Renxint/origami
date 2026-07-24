# -*- coding: utf-8 -*-
"""
Origami - B 站平台适配器

B站 API 特点:
  - 视频信息 / 流地址: 不需要登录，但需要 Referer + UA
  - 用户空间 / 作品列表: 需要 WBI 签名 (img_key + sub_key from nav)
  - 番剧 / 电影: 需要 Cookie
"""

import re
import hashlib
import time
import functools
from typing import Optional
from urllib.parse import urlencode

import requests as _r

from src.platforms.base import (
    PlatformAdapter, MediaItem, AuthorInfo, register_platform,
)
from src.environ import USER_AGENT

BILIBILI_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
               "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36")


# ═══════════════════════════════════════════════════════════
# WBI 签名
# ═══════════════════════════════════════════════════════════

_wbi_cache: tuple[str, str, float] = ("", "", 0)


def _get_wbi_keys() -> tuple[str, str]:
    """获取 WBI 签名所需的 img_key 和 sub_key (12h TTL)"""
    global _wbi_cache
    now = time.time()
    if _wbi_cache[0] and (now - _wbi_cache[2]) < 43200:  # 12 hours
        return _wbi_cache[0], _wbi_cache[1]
    try:
        resp = _r.get("https://api.bilibili.com/x/web-interface/nav",
                      headers={"User-Agent": BILIBILI_UA, "Referer": "https://www.bilibili.com/"},
                      timeout=10)
        data = resp.json().get("data", {}) or {}
        wbi = data.get("wbi_img", {}) or {}
        img_url = wbi.get("img_url", "")
        sub_url = wbi.get("sub_url", "")
        img_key = img_url.rsplit("/", 1)[-1].split(".")[0] if img_url else ""
        sub_key = sub_url.rsplit("/", 1)[-1].split(".")[0] if sub_url else ""
        _wbi_cache = (img_key, sub_key, now)
        return img_key, sub_key
    except Exception:
        return "", ""


_WBI_MIX_TABLE = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35,
    27, 43, 5, 49, 33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13,
    37, 48, 7, 16, 24, 55, 40, 61, 26, 17, 0, 1, 60, 51, 30, 4,
    22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11, 36, 20, 34, 44, 52,
]


def _mix_wbi_keys(img_key: str, sub_key: str) -> str:
    """WBI mixin key — 标准 64 位置换表取前 32 位"""
    raw = img_key + sub_key
    return "".join(raw[i] for i in _WBI_MIX_TABLE[:32] if i < len(raw))


def sign_params(params: dict) -> dict:
    """为参数字典添加 WBI 签名 (w_rid + wts)

    算法:
      1. 参数添加 wts 时间戳
      2. 按键名排序
      3. 值过滤 !'()* 并用 encodeURIComponent 语义编码
      4. & 拼接 → 追加 mixin_key → MD5 → w_rid
    """
    from urllib.parse import quote
    img_key, sub_key = _get_wbi_keys()
    if not img_key or not sub_key:
        return params
    mix = _mix_wbi_keys(img_key, sub_key)
    p = dict(params)
    p["wts"] = str(int(time.time()))
    sorted_keys = sorted(p.keys())
    parts = []
    for k in sorted_keys:
        v = str(p[k]).translate(str.maketrans("", "", "!'()*"))
        parts.append(f"{k}={quote(v, safe='')}")
    query = "&".join(parts)
    digest = hashlib.md5((query + mix).encode()).hexdigest()
    p["w_rid"] = digest
    return p


def wbi_get(url: str, params: dict, headers: dict = None, timeout: int = 15) -> dict:
    """带 WBI 签名的 GET 请求"""
    signed = sign_params(params)
    h = {"User-Agent": BILIBILI_UA, "Referer": "https://www.bilibili.com/"}
    if headers:
        h.update(headers)
    try:
        resp = _r.get(url, params=signed, headers=h, timeout=timeout)
        return resp.json()
    except Exception:
        return {}


# ═══════════════════════════════════════════════════════════
# Adapter
# ═══════════════════════════════════════════════════════════

class BilibiliAdapter(PlatformAdapter):
    platform_id = "bilibili"
    platform_name = "B站"

    def resolve_url(self, url: str) -> str:
        """从 B 站链接提取 BV 号"""
        # b23.tv 短链 → 先重定向
        real_url = url
        if "b23.tv" in url:
            m = re.search(r'(https?://b23\.tv/[A-Za-z0-9]+)', url)
            short = m.group(0) if m else url.strip()
            try:
                s = _r.Session()
                s.headers.update({"User-Agent": BILIBILI_UA})
                r = s.get(short, allow_redirects=True, timeout=15, stream=True)
                r.close()
                real_url = r.url
            except Exception:
                pass

        # 提取 BV/AV 号
        m = re.search(r'BV([A-Za-z0-9]{10})', real_url)
        if m:
            return "BV" + m.group(1)

        m = re.search(r'/av(\d+)', real_url, re.IGNORECASE)
        if m:
            return f"av{m.group(1)}"

        raise ValueError(f"无法提取 BV/AV 号: {url[:80]}")

    # ── 单视频 ──────────────────────────────────────────

    def fetch_media(self, item_id: str, cookie: str = "") -> MediaItem:
        """获取视频详情 + 下载链接"""
        params = {"bvid": item_id} if item_id.startswith("BV") else {"aid": item_id.replace("av", "")}
        headers = {"User-Agent": BILIBILI_UA, "Referer": "https://www.bilibili.com/"}
        if cookie:
            headers["Cookie"] = cookie

        # 视频信息
        r = _r.get("https://api.bilibili.com/x/web-interface/view",
                   params=params, headers=headers, timeout=15)
        info = r.json()
        if info.get("code") != 0:
            raise RuntimeError(f"B站API错误: {info.get('message', '未知')}")

        d = info.get("data", {})
        cid = d.get("cid", 0)
        title = d.get("title", "")
        author = d.get("owner", {}).get("name", "")
        author_id = str(d.get("owner", {}).get("mid", ""))
        cover_url = d.get("pic", "")

        # 视频流 — 画质优先：从高到低遍历，同 qn 优先 durl（单文件省事）
        # 检查实际返回画质不低于请求画质，防止 B站降级
        QN_ORDER = [127, 126, 125, 120, 116, 112, 80, 64, 32]
        media_urls = []
        play = None
        for qn in QN_ORDER:
            qn_s = str(qn)
            # 先试 durl（单文件），再试 DASH（音视频分离）
            for fnval in ("1", "4048"):
                stream_params = {
                    "bvid": item_id, "cid": str(cid), "qn": qn_s,
                    "fnval": fnval, "fourk": "1",
                }
                r2 = _r.get("https://api.bilibili.com/x/player/playurl",
                            params=stream_params, headers=headers, timeout=15)
                p = r2.json().get("data", {}) or {}
                actual_qn = p.get("quality", 0)
                if actual_qn < qn:
                    continue  # 画质被降级，跳过
                dash = p.get("dash", {}) or {}
                durl = p.get("durl") or []

                if durl:
                    play = p
                    for du in durl:
                        url = du.get("url", "")
                        if url: media_urls.append(url)
                    break
                elif dash.get("video"):
                    play = p
                    videos = sorted(dash["video"], key=lambda v: v.get("bandwidth", 0), reverse=True)
                    audios = sorted(dash.get("audio") or [], key=lambda a: a.get("bandwidth", 0), reverse=True)
                    for v in videos[:1]:
                        url = v.get("base_url") or v.get("baseUrl", "")
                        if url: media_urls.append(url)
                    for a in audios[:1]:
                        url = a.get("base_url") or a.get("baseUrl", "")
                        if url: media_urls.append(url)
                    break
            if media_urls:
                break

        if not media_urls:
            raise RuntimeError("未提取到视频流地址")

        return MediaItem(
            platform="bilibili",
            item_id=item_id,
            item_type="video",
            title=title,
            author=author,
            author_id=author_id,
            cover_url=cover_url,
            media_urls=media_urls,
            extra={"cid": cid, "info": d, "play": play},
        )

    # ── 用户主页 ──────────────────────────────────────

    def fetch_author(self, author_id: str, cookie: str = "") -> AuthorInfo:
        """获取用户信息"""
        params = {"mid": author_id}
        headers = {"User-Agent": BILIBILI_UA, "Referer": "https://www.bilibili.com/"}
        if cookie:
            headers["Cookie"] = cookie

        data = wbi_get("https://api.bilibili.com/x/space/wbi/acc/info",
                       params, headers=headers)
        if data.get("code") != 0:
            raise RuntimeError(f"获取用户信息失败: {data.get('message', '未知')}")

        u = data.get("data", {})
        return AuthorInfo(
            platform="bilibili",
            author_id=author_id,
            nickname=u.get("name", ""),
            avatar_url=u.get("avatar", ""),
            cover_url=u.get("top_photo", ""),
            bio=u.get("sign", ""),
            follower_count=u.get("follower", 0),
            following_count=u.get("following", 0),
            post_count=u.get("video_count", 0),
            gender=u.get("sex", 0),
            uid=str(u.get("uid", "")),
            extra={"raw": u},
        )

    def fetch_posts(
        self, author_id: str, cookie: str = "",
        max_cursor: int = 1, count: int = 18
    ) -> dict:
        """翻页获取用户视频列表"""
        params = {
            "mid": author_id,
            "ps": str(count),
            "pn": str(max_cursor),
            "order": "pubdate",
        }
        headers = {"User-Agent": BILIBILI_UA, "Referer": "https://www.bilibili.com/"}
        if cookie:
            headers["Cookie"] = cookie

        data = wbi_get("https://api.bilibili.com/x/space/wbi/arc/search",
                       params, headers=headers)
        if data.get("code") != 0:
            raise RuntimeError(f"获取作品列表失败: {data.get('message', '未知')}")

        page = data.get("data", {}) or {}
        vlist = page.get("list", {}).get("vlist", []) if isinstance(page.get("list"), dict) else []
        items = []
        for v in vlist:
            items.append(MediaItem(
                platform="bilibili",
                item_id=f"BV{v.get('bvid', '')}",
                item_type="video",
                title=v.get("title", ""),
                author=v.get("author", ""),
                author_id=str(v.get("mid", "")),
                cover_url=v.get("pic", ""),
                extra={"raw": v},
            ))

        total = page.get("page", {}).get("count", 0) if isinstance(page.get("page"), dict) else 0
        pn = page.get("page", {}).get("pn", 0) if isinstance(page.get("page"), dict) else 0
        return {
            "items": items,
            "has_more": len(items) >= count,
            "next_cursor": pn + 1,
            "total": total,
        }

    # ── Cookie 校验 ────────────────────────────────────

    def check_cookie(self, cookie: str) -> bool:
        """检查 B站 Cookie 是否有效"""
        try:
            r = _r.get("https://api.bilibili.com/x/web-interface/nav",
                       headers={"User-Agent": BILIBILI_UA, "Cookie": cookie},
                       timeout=10)
            data = r.json()
            return data.get("code") == 0 and data.get("data", {}).get("isLogin", False)
        except Exception:
            return False

    def get_login_url(self) -> str:
        """B站扫码登录页"""
        return "https://www.bilibili.com/"


# ── 注册 ──
register_platform(BilibiliAdapter)
