# -*- coding: utf-8 -*-
"""
Origami — 通用下载器

不依赖 tqdm（GUI 不需要命令行进度条），
纯 requests 流式下载 + 断点续传支持。
"""

import time
import json
import requests as req
from pathlib import Path
from typing import Optional

from src.environ import USER_AGENT

REQUEST_TIMEOUT = 60


def download_file(
    url: str,
    save_path: Path,
    headers: dict = None,
    timeout: int = REQUEST_TIMEOUT,
    skip_existing: bool = True,
) -> bool:
    """
    下载单个文件。

    返回:
        True  = 下载成功或已存在
        False = 下载失败
    """
    if skip_existing and save_path.exists():
        return True

    if headers is None:
        headers = {"User-Agent": USER_AGENT, "Referer": "https://www.douyin.com/"}

    try:
        r = req.get(url, headers=headers, stream=True, timeout=timeout)
        r.raise_for_status()
        with open(save_path, "wb") as f:
            for chunk in r.iter_content(8192):
                if chunk:
                    f.write(chunk)
        return True
    except Exception:
        if save_path.exists():
            save_path.unlink()
        return False


def load_tracker(tracker_path: Path) -> dict:
    """加载下载记录"""
    if tracker_path.exists():
        try:
            return json.loads(tracker_path.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_tracker(tracker_path: Path, tracker: dict):
    """保存下载记录"""
    tracker_path.write_text(
        json.dumps(tracker, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
