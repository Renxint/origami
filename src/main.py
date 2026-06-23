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
import warnings

# 静默 playwright 关闭时的 EPIPE 噪音
warnings.filterwarnings("ignore", category=ResourceWarning)

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
        print("    --count N       批量下载数量 (默认全部)")
        print("    --dir  PATH     保存目录")
        print("    --images 1,3,5  单作品图集：只下载指定序号 (如 1,3,5-8)")
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
        _cli_single(url, save_dir, args)
    elif mode == "batch":
        _cli_batch(url, count, save_dir)
    else:
        print(f"未知模式: {mode}，可用: single | batch")


def _cli_single(url: str, save_dir: str = "", args: list = None):
    """CLI 单视频下载"""
    from pathlib import Path
    from src.platforms.douyin import DouyinAdapter
    from src.downloader import download_file
    from src.utils import clean_name
    from src.environ import OUTPUT_SINGLE

    # 解析 --images 参数
    img_filter = None
    if args:
        for j, a in enumerate(args):
            if a == "--images" and j + 1 < len(args):
                img_filter = _parse_image_range(args[j + 1])
                break

    out = Path(save_dir) if save_dir else OUTPUT_SINGLE
    out.mkdir(parents=True, exist_ok=True)

    print(f"[*] 解析链接: {url[:60]}...")
    adapter = DouyinAdapter()
    item_id = adapter.resolve_url(url)
    print(f"[OK] 视频ID: {item_id}")

    print("[*] 获取作品数据...")
    media = adapter.fetch_media(item_id)
    type_emoji = {"video": "🎬", "image": "🖼️", "gallery": "🖼️"}
    emoji = type_emoji.get(media.item_type, "📦")
    type_cn = {"video": "视频", "image": "单图", "gallery": f"图集({len(media.media_urls)}图)"}
    cn = type_cn.get(media.item_type, media.item_type)
    print(f"[OK] {media.title[:40]}  by {media.author}")
    print(f"     {emoji} {cn}")

    selected = list(enumerate(media.media_urls))
    if img_filter is not None:
        selected = [(i, u) for i, u in selected if i in img_filter]
        print(f"     筛选: {len(selected)}/{len(media.media_urls)} 张")

    # 建子目录（和 GUI 一致：作者（标题）/）
    safe_author = clean_name(media.author, 20)
    safe_title = clean_name(media.title or item_id, 40)
    post_dir = out / f"{safe_author}（{safe_title}）"
    post_dir.mkdir(parents=True, exist_ok=True)

    for idx, (i, murl) in enumerate(selected):
        ext = ".mp4" if media.item_type == "video" else ".jpg"
        label = f"{i+1:02d}" if len(selected) > 9 else str(i+1)
        fname = f"{label}{ext}"
        fpath = post_dir / fname
        print(f"[*] 下载 {idx+1}/{len(selected)}: {fname}...")
        ok = download_file(murl, fpath)
        tag = "OK" if ok else "FAIL"
        print(f"[{tag}] {fpath}")

    # 写描述文件
    (post_dir / "desc.txt").write_text(media.title or item_id, encoding="utf-8")
    print(f"[DONE] 保存到: {post_dir}")


def _write_profile_md(data_dir, author, profile, avatar_url, cover_url, source_url):
    """写 主页简介.md + 下载头像/封面（对齐 GUI）"""
    import time as _t
    import requests as _r
    nickname = author.nickname
    lines = [
        f"# {nickname}", "",
        "## 基本信息", "",
        f"| 项目 | 内容 |",
        f"|------|------|",
        f"| 抖音号 | {profile.get('unique_id', 'N/A')} |",
        f"| 作品 | {author.post_count} |",
        f"| 粉丝 | {author.follower_count} |",
        f"| 简介 | {profile.get('desc', 'N/A')} |",
        "", "## 下载信息", "",
        f"- 主页链接: {source_url}",
        f"- 下载日期: {_t.strftime('%Y-%m-%d %H:%M:%S')}",
    ]
    (data_dir / "主页简介.md").write_text("\n".join(lines), encoding="utf-8")
    if avatar_url:
        try:
            r = _r.get(avatar_url, headers={"User-Agent": USER_AGENT}, timeout=15)
            (data_dir / "avatar.jpg").write_bytes(r.content)
        except Exception:
            pass
    if cover_url:
        try:
            r = _r.get(cover_url, headers={"User-Agent": USER_AGENT}, timeout=15)
            (data_dir / "cover.jpg").write_bytes(r.content)
        except Exception:
            pass


def _parse_image_range(spec: str) -> set:
    """解析 --images 参数: '1,3,5-8' → {0, 2, 4, 5, 6, 7}（转为 0-based）"""
    result = set()
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            a, b = part.split("-", 1)
            for n in range(int(a.strip()), int(b.strip()) + 1):
                result.add(n - 1)  # 转为 0-based
        else:
            result.add(int(part) - 1)
    return result


def _cli_batch(url: str, max_count: int = 0, save_dir: str = ""):
    """CLI 批量下载"""
    from pathlib import Path
    from src.platforms.douyin import DouyinAdapter
    from src.downloader import download_file
    from src.utils import clean_name
    from src.environ import OUTPUT_OTHER, USER_AGENT
    import time, re, requests as _r

    out = Path(save_dir) if save_dir else OUTPUT_OTHER
    out.mkdir(parents=True, exist_ok=True)

    adapter = DouyinAdapter()

    # 从口令文本中提取链接并解析短链
    print(f"[*] 解析主页: {url[:60]}...")
    # 1. 提取短链或完整URL
    short_patterns = [
        r'https?://v\.douyin\.com/[A-Za-z0-9_\-/]+',
        r'https?://(?:www\.)?douyin\.com/user/MS4wLjAB[A-Za-z0-9_\-]+',
        r'https?://(?:www\.)?iesdouyin\.com/share/user/MS4wLjAB[A-Za-z0-9_\-]+',
    ]
    found = ""
    for pat in short_patterns:
        m = re.search(pat, url)
        if m:
            found = m.group(0)
            break
    if not found:
        print("[ERROR] 未识别抖音主页链接")
        return

    # 2. 短链 → 302 解析
    if "v.douyin.com" in found:
        s = _r.Session()
        s.headers.update({"User-Agent": USER_AGENT})
        r = s.get(found, allow_redirects=True, timeout=15, stream=True)
        r.close()
        found = r.url
        print(f"[*] 短链解析: {found[:60]}...")

    sec_uid = adapter.resolve_user_url(found)
    print(f"[OK] sec_uid: {sec_uid[:30]}...")

    print("[*] 获取作者信息...")
    author = adapter.fetch_author(sec_uid)
    name = clean_name(author.nickname or sec_uid)
    print(f"[OK] {author.nickname}  作品: {author.post_count}  粉丝: {author.follower_count}")

    author_dir = out / name
    author_dir.mkdir(parents=True, exist_ok=True)
    data_dir = author_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    # 写主页简介 + 下载头像/封面
    profile = author.extra.get("profile", {})
    from src.api import _get_avatar
    avatar_url = _get_avatar(profile)
    cover_url = profile.get("cover_url", "")
    _write_profile_md(data_dir, author, profile, avatar_url, cover_url, found)

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

    # 标记原始序号（翻页顺序，0=最新）
    for _i, _it in enumerate(all_items):
        _it.extra["_orig_idx"] = _i

    print(f"[OK] 共 {len(all_items)} 个作品")

    # 对齐 GUI 扁平结构：{pos}_{hash}_{index}.jpg
    # 编号基于作者实际作品总数，而非本次下载数量
    import hashlib
    from src.utils import pick_best_video_url
    stats = {"ok": 0, "fail": 0, "skip": 0}
    _orig_total = author.post_count or len(all_items)

    for i, item in enumerate(all_items):
        aweme_id = item.item_id
        desc = clean_name(item.title or aweme_id, 30)
        short = hashlib.md5(str(aweme_id).encode()).hexdigest()[:4]
        _oi = item.extra.get("_orig_idx", i)
        pos = f"{_orig_total - _oi:04d}_{short}_"  # GUI 格式
        num = f"{i+1:03d}"

        print(f"[{num}/{len(all_items)}] {item.title[:30]}...")

        # 获取无水印详情
        try:
            media = adapter.fetch_media(aweme_id)
        except Exception:
            media = item

        downloaded = False
        aweme = media.extra.get("aweme", {})
        video = aweme.get("video")
        images = aweme.get("images") or []

        if video and not images:
            url = pick_best_video_url(video)
            if url and download_file(url, author_dir / f"{pos}{desc}.mp4"):
                stats["ok"] += 1
                downloaded = True
            else:
                stats["fail"] += 1
        elif images:
            for j, img in enumerate(images):
                urls = img.get("url_list", [])
                img_url = urls[-1] if urls else ""
                if img_url and download_file(img_url, author_dir / f"{pos}{j+1}.jpg"):
                    stats["ok"] += 1
                    downloaded = True
                else:
                    stats["fail"] += 1
        elif media.media_urls:
            for j, murl in enumerate(media.media_urls):
                ext = ".mp4" if media.item_type == "video" else ".jpg"
                if download_file(murl, author_dir / f"{pos}{j+1}{ext}"):
                    stats["ok"] += 1
                    downloaded = True
                else:
                    stats["fail"] += 1

        if not downloaded:
            print(f"  [无资源]")

    # 写作品目录
    lines = [f"# {name}", "", f"共 {len(all_items)} 个作品", ""]
    for idx, it in enumerate(all_items):
        aw = it.extra.get("aweme", {})
        d = clean_name(it.title or it.item_id)
        v = aw.get("video")
        imgs = aw.get("images") or []
        typ = "视频" if (v and not imgs) else f"图集({len(imgs)}图)" if imgs else "未知"
        lines.append(f"{idx+1}. [{typ}] {d}")
    (author_dir / f"作品目录_{time.strftime('%Y%m%d_%H%M%S')}.md").write_text("\n".join(lines), encoding="utf-8")

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
