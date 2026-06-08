# -*- coding: utf-8 -*-
"""
Origami — 平台适配器

新增平台只需三步：
  1. 创建 src/platforms/newplatform.py
  2. 继承 PlatformAdapter 实现抽象方法
  3. 在文件末尾调用 register_platform(NewPlatform)

GUI 自动识别所有已注册平台。
"""
from src.platforms.base import (
    PlatformAdapter, MediaItem, AuthorInfo,
    PLATFORM_REGISTRY, register_platform, get_platform, list_platforms,
)

# 注册内置平台（导入即注册）
import src.platforms.douyin
