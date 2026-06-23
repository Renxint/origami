# -*- coding: utf-8 -*-
"""
Origami v2 — 入口

用法:
    python -m src.main server            启动 API Server
    python -m src.main server --port 8765 指定端口
    python -m src.main cli single <url>   命令行单视频下载 (M3)
    python -m src.main cli batch <url>    命令行批量下载 (M3)
"""

import sys
import os

# 确保项目根在 sys.path
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def cmd_server(args: list[str]):
    """启动本地 HTTP + WebSocket API Server"""
    from src.server import run_server
    port = 0
    for i, a in enumerate(args):
        if a == "--port" and i + 1 < len(args):
            port = int(args[i + 1])
    run_server(port=port)


def cmd_cli(args: list[str]):
    """命令行下载"""
    if not args:
        print("用法: python -m src.main cli <single|batch> <url>")
        print()
        print("  例: python -m src.main cli single \"https://v.douyin.com/xxx/\"")
        print("  例: python -m src.main cli batch  \"https://www.douyin.com/user/MS4wLjAB...\"")
        print()
        print("  可选参数:")
        print("    --count N    批量下载数量 (默认全部)")
        print("    --dir  PATH  保存目录")
        return

    mode = args[0]
    url = ""
    count = 0
    save_dir = ""

    i = 1
    while i < len(args):
        if args[i] == "--count" and i + 1 < len(args):
            count = int(args[i + 1]); i += 2
        elif args[i] == "--dir" and i + 1 < len(args):
            save_dir = args[i + 1]; i += 2
        elif not url:
            url = args[i]; i += 1
        else:
            i += 1

    if not url:
        print("请提供链接")
        return

    if mode == "single":
        _cli_single(url, save_dir)
    elif mode == "batch":
        _cli_batch(url, count, save_dir)
    else:
        print(f"未知模式: {mode}，可用: single | batch")


def _cli_single(url: str, save_dir: str = ""):
    """CLI 单视频下载"""
    from pathlib import Path
    from src.platforms.douyin import DouyinAdapter
    from src.downloader import download_file
    from src.utils import clean_name
    from src.environ import OUTPUT_SINGLE

    out = Path(save_dir) if save_dir else OUTPUT_SINGLE
    out.mkdir(parents=True, exist_ok=True)

    print(f"[*] 解析链接: {url[:60]}...")
    adapter = DouyinAdapter()
    item_id = adapter.resolve_url(url)
    print(f"[OK] 视频ID: {item_id}")

    print("[*] 获取作品数据...")
    media = adapter.fetch_media(item_id)
    print(f"[OK] {media.title[:40]}  by {media.author}")
    print(f"     类型: {media.item_type}  文件数: {len(media.media_urls)}")

    for i, murl in enumerate(media.media_urls):
        ext = ".mp4" if media.item_type == "video" else ".jpg"
        fname = f"{clean_name(media.title or item_id, 30)}_{i+1}{ext}"
        fpath = out / fname
        print(f"[*] 下载 {i+1}/{len(media.media_urls)}: {fname}...")
        ok = download_file(murl, fpath)
        tag = "OK" if ok else "FAIL"
        print(f"[{tag}] {fpath}")

    print(f"[DONE] 保存到: {out}")


def _cli_batch(url: str, max_count: int = 0, save_dir: str = ""):
    """CLI 批量下载"""
    from pathlib import Path
    from src.platforms.douyin import DouyinAdapter
    from src.downloader import download_file, download_batch
    from src.utils import clean_name
    from src.environ import OUTPUT_BATCH, USER_AGENT
    import time, hashlib

    out = Path(save_dir) if save_dir else OUTPUT_BATCH
    out.mkdir(parents=True, exist_ok=True)

    adapter = DouyinAdapter()

    print(f"[*] 解析主页: {url[:60]}...")
    sec_uid = adapter.resolve_user_url(url)
    print(f"[OK] sec_uid: {sec_uid[:30]}...")

    print("[*] 获取作者信息...")
    author = adapter.fetch_author(sec_uid)
    name = clean_name(author.nickname or sec_uid)
    print(f"[OK] {author.nickname}  作品: {author.post_count}  粉丝: {author.follower_count}")

    author_dir = out / name
    author_dir.mkdir(parents=True, exist_ok=True)

    print("[*] 翻页获取作品列表...")
    all_items = []
    cursor = 0
    page = 0
    while page < 100:
        data = adapter.fetch_posts(sec_uid, max_cursor=cursor, count=18)
        items = data.get("items", [])
        if not items:
            break
        all_items.extend(items)
        page += 1
        print(f"  页{page}: +{len(items)}  累计{len(all_items)}")
        if max_count and len(all_items) >= max_count:
            all_items = all_items[:max_count]
            break
        if not data.get("has_more"):
            break
        cursor = data.get("next_cursor", 0)
        time.sleep(0.5)

    print(f"[OK] 共 {len(all_items)} 个作品")

    stats = {"ok": 0, "fail": 0, "skip": 0}
    for i, item in enumerate(all_items):
        # 获取无水印链接
        aweme_id = item.item_id
        print(f"[{i+1}/{len(all_items)}] {item.title[:30]}...")
        try:
            media = adapter.fetch_media(aweme_id)
        except Exception:
            media = item

        post_dir = author_dir / f"{i+1:03d}_{clean_name(item.title or aweme_id, 30)}"
        post_dir.mkdir(parents=True, exist_ok=True)

        downloaded = False
        for j, murl in enumerate(media.media_urls):
            if media.item_type == "video":
                fpath = post_dir / "video.mp4"
            else:
                fpath = post_dir / f"{j+1:02d}.jpg"
            if download_file(murl, fpath):
                stats["ok"] += 1
                downloaded = True
            else:
                stats["fail"] += 1
            time.sleep(0.1)

        if not downloaded:
            print(f"  [无资源]")

    print(f"[DONE] 视频:{stats['ok']}  失败:{stats['fail']}")
    print(f"       保存到: {author_dir}")


def cmd_dev(args: list[str]):
    """开发辅助命令"""
    if not args:
        print("dev 子命令:")
        print("  dev check-cookie    检查登录状态")
        print("  dev test-signer     测试 Playwright 浏览器发现")
        return
    sub = args[0]
    if sub == "check-cookie":
        from src.cookie import load_cookie, validate_cookie
        cookie = load_cookie()
        print(f"Cookie 长度: {len(cookie)}")
        print(f"Cookie 有效: {validate_cookie(cookie)}")
        if cookie:
            print(f"Cookie 前 80 字符: {cookie[:80]}...")
    elif sub == "test-signer":
        print("signer 测试将在 M2 实现")
    else:
        print(f"未知 dev 命令: {sub}")


def main():
    if len(sys.argv) < 2:
        print("Origami v2 — 用法:")
        print("  python -m src.main server      启动 API Server")
        print("  python -m src.main cli <mode>   命令行下载")
        print("  python -m src.main dev <cmd>    开发工具")
        return

    cmd = sys.argv[1]
    rest = sys.argv[2:]

    if cmd == "server":
        cmd_server(rest)
    elif cmd == "cli":
        cmd_cli(rest)
    elif cmd == "dev":
        cmd_dev(rest)
    else:
        print(f"未知命令: {cmd}")
        print("可用: server | cli | dev")


if __name__ == "__main__":
    main()
