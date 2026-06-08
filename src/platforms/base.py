# -*- coding: utf-8 -*-
"""
Origami — 平台适配器基类

所有平台（抖音/B站/微博/YouTube...）必须实现此接口。
新增平台 = 继承 PlatformAdapter + 实现抽象方法 + 注册到 PLATFORM_REGISTRY。

借鉴 clawd-on-desk 的 theme schema：定义清晰的接口契约。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class MediaItem:
    """单个媒体作品"""
    platform: str           # 平台标识: douyin / bilibili / weibo ...
    item_id: str            # 平台内唯一 ID
    item_type: str          # video / image / audio / live / gallery
    title: str = ""
    author: str = ""
    author_id: str = ""
    cover_url: str = ""
    media_urls: list[str] = field(default_factory=list)   # 下载链接
    extra: dict = field(default_factory=dict)              # 平台特有字段


@dataclass
class AuthorInfo:
    """创作者信息"""
    platform: str
    author_id: str
    nickname: str = ""
    avatar_url: str = ""
    bio: str = ""
    post_count: int = 0
    follower_count: int = 0
    extra: dict = field(default_factory=dict)


class PlatformAdapter(ABC):
    """
    平台适配器抽象基类。

    每个平台实现必须提供：
      - platform_id: 唯一标识
      - platform_name: 显示名称
      - resolve_url(): 从分享链接提取内容 ID
      - fetch_media(): 获取单个作品数据
      - fetch_author(): 获取创作者信息
      - fetch_posts(): 获取作品列表（翻页）

    可选覆盖：
      - fetch_collection(): 收藏夹下载
      - fetch_topic(): 话题/挑战赛下载
      - check_cookie(): Cookie 有效性检测
      - get_login_url(): 返回扫码登录 URL
    """

    # ── 子类必须定义 ──
    platform_id: str = ""
    platform_name: str = ""

    @abstractmethod
    def resolve_url(self, url: str) -> str:
        """从分享链接提取内容 ID"""
        ...

    @abstractmethod
    def fetch_media(self, item_id: str, cookie: str = "") -> MediaItem:
        """获取单个作品数据（含无水印下载链接）"""
        ...

    @abstractmethod
    def fetch_author(self, author_id: str, cookie: str = "") -> AuthorInfo:
        """获取创作者信息"""
        ...

    @abstractmethod
    def fetch_posts(
        self, author_id: str, cookie: str = "",
        max_cursor: int = 0, count: int = 18
    ) -> dict:
        """
        翻页获取作品列表。

        返回:
            {
                "items": [MediaItem, ...],
                "has_more": bool,
                "next_cursor": int,
                "total": int | None,
            }
        """
        ...

    # ── 可选覆盖 ──

    def check_cookie(self, cookie: str) -> bool:
        """检测 Cookie 是否有效（默认始终返回 True）"""
        return True

    def get_login_url(self) -> str:
        """返回扫码登录页面 URL（用于 WebView）"""
        return ""

    def fetch_collection(
        self, collection_id: str, cookie: str = "",
        max_cursor: int = 0, count: int = 18
    ) -> dict:
        """获取收藏夹内容（可选）"""
        raise NotImplementedError(f"{self.platform_name} 暂不支持收藏夹下载")

    def fetch_topic(
        self, topic_id: str, cookie: str = "",
        max_cursor: int = 0, count: int = 18
    ) -> dict:
        """获取话题/挑战赛内容（可选）"""
        raise NotImplementedError(f"{self.platform_name} 暂不支持话题下载")


# ── 平台注册表 ────────────────────────────────────────────
PLATFORM_REGISTRY: dict[str, type[PlatformAdapter]] = {}


def register_platform(adapter_cls: type[PlatformAdapter]):
    """注册平台适配器"""
    PLATFORM_REGISTRY[adapter_cls.platform_id] = adapter_cls


def get_platform(platform_id: str) -> Optional[PlatformAdapter]:
    """获取平台适配器实例"""
    cls = PLATFORM_REGISTRY.get(platform_id)
    return cls() if cls else None


def list_platforms() -> list[str]:
    """列出所有已注册平台"""
    return list(PLATFORM_REGISTRY.keys())
