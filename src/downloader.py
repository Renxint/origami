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


def download_batch(tasks: list, max_workers: int = 6) -> tuple:
    """并发下载一组文件

    Args:
        tasks: [(url, path, headers), ...]  headers 可为 None
        max_workers: 并发线程数

    Returns:
        (success_count, fail_count)
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    pending = [(url, path, headers) for url, path, headers in tasks
               if not path.exists()]
    if not pending:
        return 0, 0

    def _dl(url, path, headers):
        if headers is None:
            headers = {"User-Agent": USER_AGENT, "Referer": "https://www.douyin.com/"}
        try:
            r = req.get(url, headers=headers, stream=True, timeout=REQUEST_TIMEOUT)
            r.raise_for_status()
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "wb") as f:
                for chunk in r.iter_content(8192):
                    if chunk:
                        f.write(chunk)
            return True
        except Exception:
            if path.exists():
                path.unlink()
            return False

    ok, fail = 0, 0
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_dl, url, path, headers): (url, path)
                   for url, path, headers in pending}
        for f in as_completed(futures):
            if f.result():
                ok += 1
            else:
                fail += 1
    return ok, fail


def save_tracker(tracker_path: Path, tracker: dict):
    """保存下载记录"""
    tracker_path.write_text(
        json.dumps(tracker, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
