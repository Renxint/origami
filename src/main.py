# -*- coding: utf-8 -*-
"""
Origami v2 — 入口

用法:
    python -m src.main server             启动 API Server
    python -m src.main server --port 8765 指定端口
    python -m src.main cli <mode> <url>   命令行下载
    python -m src.main login              扫码登录
"""

import sys
import os
import re
import time
import warnings

warnings.filterwarnings("ignore", category=ResourceWarning)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# ── 安全输出：过滤 emoji ──

def _s(s, n=0):
    s = str(s)
    # 过滤 GBK 不支持的字符: emoji, 变体选择器, ZWJ
    r = ''.join(c for c in s if ord(c) < 0x10000 and ord(c) not in (
        0xFE0F, 0x200D, 0xFE00, 0xFE01, 0xFE02, 0xFE03, 0xFE04))
    return r[:n] if n and len(r) > n else r


def cmd_server(args: list[str]):
    from src.server import run_server
    port = 0
    for i, a in enumerate(args):
        if a == "--port" and i + 1 < len(args):
            port = int(args[i + 1])
    run_server(port=port)


def cmd_cli(args: list[str]):
    KNOWN_MODES = {"single","batch","like","collection","music"}
    if not args:
        print(f"用法: python -m src.main cli [<模式>] <链接>")
        print(f"  模式（可选，不填则自动识别）: {' | '.join(sorted(KNOWN_MODES))}")
        print(f"\n  例: python -m src.main cli \"https://v.douyin.com/xxx/\"")
        print(f"  例: python -m src.main cli single \"https://v.douyin.com/xxx/\"")
        print(f"  例: python -m src.main cli like \"https://www.douyin.com/user/self\"")
        print("\n  可选参数:  --count N  --dir PATH  --images 1,3,5")
        return

    # 解析参数
    mode = args[0] if args[0] in KNOWN_MODES else ""; url = ""; count = 0; save_dir = ""
    i = 1 if mode else 0
    while i < len(args):
        if args[i] == "--count" and i+1 < len(args): count = int(args[i+1]); i += 2
        elif args[i] == "--dir" and i+1 < len(args): save_dir = args[i+1]; i += 2
        elif not url: url = args[i]; i += 1
        else: i += 1

    if not url: return print("请提供链接")
    # 从分享口令文本中提取链接
    if "http" in url:
        m = re.search(r'(https?://[^\s]+)', url)
        if m: url = m.group(1).rstrip('.,;:!?）」)】')

    # 平台识别
    platform = _detect_platform(url)
    if not platform:
        return print(f"[ERROR] 未识别的平台链接: {_s(url, 60)}")
    if platform != "douyin":
        return print(f"[提示] {platform} 平台适配器尚未实现，仅支持抖音")

    # 自动识别链接类型
    if not mode:
        # 短链 → 302 展开
        resolved = url
        if "v.douyin.com" in url:
            import requests as _r
            from src.environ import USER_AGENT
            try:
                s = _r.Session(); s.headers.update({"User-Agent": USER_AGENT})
                r = s.get(url, allow_redirects=True, timeout=10, stream=True); r.close()
                resolved = r.url
            except Exception: pass
        # 判断类型（顺序重要：先精确再模糊）
        if "modal_id=" in resolved or "/video/" in resolved or "/note/" in resolved:
            mode = "single"
        elif "/user/" in resolved:
            mode = "batch"
        else:
            mode = "single"  # 兜底当单作品
        print(f"[*] 自动识别: {mode}")

    if mode == "single": _cli_single(url, save_dir, args)
    elif mode == "batch": _cli_batch(url, count, save_dir)
    elif mode == "like": _cli_like(url, count, save_dir)
    elif mode == "collection": _cli_collection(url, count, save_dir)
    elif mode == "music": _cli_music(url, count, save_dir)
    else: print(f"未知模式: {mode}")


# ══════════ CLI — 单作品 ══════════

def _cli_single(url: str, save_dir: str = "", args: list = None):
    from pathlib import Path
    from src.platforms.douyin import DouyinAdapter
    from src.downloader import download_file
    from src.utils import clean_name
    from src.environ import OUTPUT_SINGLE

    img_filter = None
    if args:
        for j, a in enumerate(args):
            if a == "--images" and j+1 < len(args):
                img_filter = _parse_image_range(args[j+1]); break

    out = Path(save_dir) if save_dir else OUTPUT_SINGLE
    out.mkdir(parents=True, exist_ok=True)

    print(f"[*] 解析链接: {_s(url, 60)}...")
    adapter = DouyinAdapter()
    # 尝试常规解析，失败则从 URL 参数提取
    item_id = ""
    try: item_id = adapter.resolve_url(url)
    except Exception:
        # 从 modal_id / video_id 参数提取
        for key in ("modal_id", "video_id", "aweme_id", "item_id"):
            m = re.search(rf'[?&]{key}=(\d+)', url)
            if m: item_id = m.group(1); break
    if not item_id:
        return print(f"[ERROR] 无法解析链接: {_s(url, 60)}")
    print(f"[OK] 视频ID: {item_id}")

    print("[*] 获取作品数据...")
    media = adapter.fetch_media(item_id)
    tag = {"video":"[视频]","image":"[图片]","gallery":f"[图集 x{len(media.media_urls)}]","note":"[文章]"}.get(media.item_type,"[?]")
    print(f"[OK] {_s(media.title, 40)}  by {_s(media.author)}")
    print(f"     {tag}")
    if img_filter:
        print(f"     筛选: {len(img_filter)}/{len(media.media_urls)} 张")

    safe_author = clean_name(media.author, 20)
    safe_title = clean_name(media.title or item_id, 40)
    post_dir = out / f"{safe_author}（{safe_title}）"
    post_dir.mkdir(parents=True, exist_ok=True)

    if media.item_type == "note":
        (post_dir / "article.txt").write_text(media.text_content or media.title, encoding="utf-8")
        print(f"[OK] 文章已保存: {_s(str(post_dir / 'article.txt'))}")
        print(f"     字数: {len(media.text_content)}")
    else:
        selected = list(enumerate(media.media_urls))
        if img_filter: selected = [(i,u) for i,u in selected if i in img_filter]
        aweme = media.extra.get("aweme", {})
        images = aweme.get("images") or []
        for idx, (i, murl) in enumerate(selected):
            ext = ".mp4" if media.item_type == "video" else ".jpg"
            label = f"{i+1:02d}" if len(selected) > 9 else str(i+1)
            img_data = images[i] if i < len(images) else {}
            is_live = img_data.get("live_photo_type",0) == 1 or bool(img_data.get("video"))
            live_tag = "_实况" if is_live else ""
            fname = f"{label}{live_tag}{ext}"
            fpath = post_dir / fname
            print(f"[*] 下载 {idx+1}/{len(selected)}: {fname}...")
            ok = download_file(murl, fpath)
            print(f"[{'OK' if ok else 'FAIL'}] {_s(str(fpath))}")
            if is_live:
                lv = img_data.get("video") or {}
                live_url = next((u for url_lst in (
                    lv.get("play_addr",{}).get("url_list",[]),
                    lv.get("play_addr_h264",{}).get("url_list",[]),
                    lv.get("download_addr",{}).get("url_list",[]),
                ) for u in (url_lst or [])), None)
                if live_url:
                    lpath = post_dir / f"{label}{live_tag}.mp4"
                    print(f"[*] 实况视频: {label}{live_tag}.mp4...")
                    lok = download_file(live_url, lpath)
                    print(f"[{'OK' if lok else 'FAIL'}] {_s(str(lpath))}")
        (post_dir / "desc.txt").write_text(media.title or item_id, encoding="utf-8")

    print(f"[DONE] 保存到: {_s(str(post_dir))}")


# ══════════ CLI — 批量 ══════════

def _cli_batch(url: str, max_count: int = 0, save_dir: str = ""):
    from pathlib import Path
    from src.platforms.douyin import DouyinAdapter
    from src.downloader import download_file
    from src.utils import clean_name, pick_best_video_url
    from src.environ import OUTPUT_OTHER, USER_AGENT
    import hashlib, requests as _r, json as _json

    out = Path(save_dir) if save_dir else OUTPUT_OTHER
    out.mkdir(parents=True, exist_ok=True)
    adapter = DouyinAdapter()

    print(f"[*] 解析主页: {_s(url, 60)}...")
    short_pats = [r'https?://v\.douyin\.com/[A-Za-z0-9_\-/]+',
                  r'https?://(?:www\.)?douyin\.com/user/MS4wLjAB[A-Za-z0-9_\-]+',
                  r'https?://(?:www\.)?iesdouyin\.com/share/user/MS4wLjAB[A-Za-z0-9_\-]+']
    found = ""
    for pat in short_pats:
        m = re.search(pat, url)
        if m: found = m.group(0); break
    if not found: return print("[ERROR] 未识别抖音主页链接")
    if "v.douyin.com" in found:
        s = _r.Session(); s.headers.update({"User-Agent": USER_AGENT})
        r = s.get(found, allow_redirects=True, timeout=15, stream=True); r.close()
        found = r.url; print(f"[*] 短链解析: {_s(found, 60)}...")
    sec_uid = adapter.resolve_user_url(found)
    print(f"[OK] sec_uid: {sec_uid[:30]}...")

    print("[*] 获取作者信息...")
    author = adapter.fetch_author(sec_uid)
    name = clean_name(author.nickname or sec_uid)
    print(f"[OK] {_s(author.nickname)}  作品:{author.post_count}  粉丝:{author.follower_count}")
    author_dir = out / name; data_dir = author_dir / "data"; data_dir.mkdir(parents=True, exist_ok=True)
    profile = author.extra.get("profile", {})
    _write_profile_md(data_dir, author, profile, "", "", found)

    print("[*] 翻页获取作品列表...")
    all_items = []; cursor = 0; page = 0
    while True:
        data = adapter.fetch_posts(sec_uid, max_cursor=cursor, count=18)
        items = data.get("items", [])
        if not items: break
        all_items.extend(items); page += 1
        print(f"  页{page}: +{len(items)}  累计{len(all_items)}")
        if max_count and len(all_items) >= max_count: all_items = all_items[:max_count]; break
        if not data.get("has_more"): break
        cursor = data.get("next_cursor", 0)
        if not cursor: break; time.sleep(0.2)
    for _i, _it in enumerate(all_items): _it.extra["_orig_idx"] = _i
    print(f"[OK] 共 {len(all_items)} 个作品")

    tracker_file = data_dir / ".downloaded.json"
    downloaded_ids = set()
    if tracker_file.exists():
        try: downloaded_ids = set(_json.loads(tracker_file.read_text(encoding="utf-8")))
        except: pass

    from concurrent.futures import ThreadPoolExecutor, as_completed
    import threading as _thr
    _stats_lock = _thr.Lock()

    stats = {"ok":0,"fail":0,"skip":0}
    _orig_total = author.post_count or len(all_items)

    # 第一步：收集所有下载任务
    tasks = []  # (url, path, aweme_id)
    _skip_ids = set()

    for i, item in enumerate(all_items):
        aweme_id = item.item_id; desc = clean_name(item.title or aweme_id, 30)
        short = hashlib.md5(str(aweme_id).encode()).hexdigest()[:4]
        _oi = item.extra.get("_orig_idx", i)
        pos = f"{_orig_total - _oi:04d}_{short}_"
        if aweme_id in downloaded_ids:
            if any(author_dir.glob(f"*_{short}_*")): stats["skip"] += 1; _skip_ids.add(aweme_id); continue
            else: downloaded_ids.discard(aweme_id)
        # 获取无水印数据
        try:
            media = adapter.fetch_media(aweme_id)
            aw = media.extra.get("aweme", {})
        except Exception:
            aw = item.extra.get("aweme", {})
        video = aw.get("video"); images = aw.get("images") or []
        if video and not images:
            url = pick_best_video_url(video)
            if url: tasks.append((url, author_dir / f"{pos}{desc}.mp4", aweme_id))
        elif images:
            for j, img in enumerate(images):
                urls = img.get("url_list",[])
                img_url = next((u for u in urls if "webp" in u.lower()),None) or next((u for u in urls if "jpeg" in u.lower()),None) or next((u for u in urls if "jpg" in u.lower()),None) or (urls[0] if urls else "")
                if img_url:
                    is_live = img.get("live_photo_type",0) == 1 or bool(img.get("video"))
                    live_tag = "_实况" if is_live else ""
                    tasks.append((img_url, author_dir / f"{pos}{j+1}{live_tag}.jpg", aweme_id))
                    if is_live:
                        lv = img.get("video") or {}
                        live_url = next((u for url_lst in (
                            lv.get("play_addr",{}).get("url_list",[]),
                            lv.get("play_addr_h264",{}).get("url_list",[]),
                        ) for u in (url_lst or [])), None)
                        if live_url:
                            tasks.append((live_url, author_dir / f"{pos}{j+1}{live_tag}.mp4", aweme_id))

    print(f"[*] 共 {len(tasks)} 个下载任务，并发执行...")

    # 第二步：多线程并发下载
    _downloaded = set()
    _total_tasks = len(tasks)
    _done = [0]

    def _dl_one(task):
        url, path, awid = task
        ok = download_file(url, path)
        with _stats_lock:
            _done[0] += 1
            if ok:
                stats["ok"] += 1
                _downloaded.add(awid)
            else:
                stats["fail"] += 1
            if _done[0] % 10 == 0 or _done[0] == _total_tasks:
                print(f"  进度: {_done[0]}/{_total_tasks}")

    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(_dl_one, t) for t in tasks]
        for f in as_completed(futures):
            f.result()  # 传播异常

    downloaded_ids.update(_downloaded)
    downloaded_ids.difference_update(_skip_ids)
    tracker_file.write_text(_json.dumps(list(downloaded_ids), ensure_ascii=False), encoding="utf-8")

    lines = [f"# {name}", "", f"共 {len(all_items)} 个作品", ""]
    for idx, it in enumerate(all_items):
        aw = it.extra.get("aweme",{}); d = clean_name(it.title or it.item_id)
        v = aw.get("video"); imgs = aw.get("images") or []
        typ = "视频" if (v and not imgs) else f"图集({len(imgs)}图)" if imgs else "未知"
        lines.append(f"{idx+1}. [{typ}] {d}")
    (author_dir / f"作品目录_{time.strftime('%Y%m%d_%H%M%S')}.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"[DONE] 视频:{stats['ok']}  失败:{stats['fail']}  跳过:{stats['skip']}")
    print(f"       保存到: {_s(str(author_dir))}")


# ══════════ CLI — like / collection ══════════

def _cli_like(url, max_count=0, save_dir=""):
    _cli_list_download(url, max_count, save_dir, "like", "喜欢")

def _cli_collection(url, max_count=0, save_dir=""):
    _cli_list_download(url, max_count, save_dir, "collection", "收藏")

def _cli_list_download(url, max_count, save_dir, mode, tag):
    from pathlib import Path
    from src.platforms.douyin import DouyinAdapter
    from src.downloader import download_file
    from src.utils import clean_name, pick_best_video_url
    from src.environ import OUTPUT_OTHER
    import hashlib, json as _json

    out = Path(save_dir) if save_dir else OUTPUT_OTHER
    out.mkdir(parents=True, exist_ok=True)
    adapter = DouyinAdapter()
    sec_uid = _resolve_user_url(url)
    print(f"[*] sec_uid: {sec_uid[:30]}...")

    all_items = []; cursor = 0; page = 0
    while True:
        data = adapter.fetch_likes(sec_uid, max_cursor=cursor, count=18) if mode == "like" \
               else adapter.fetch_favorites(sec_uid, max_cursor=cursor, count=18)
        items = data.get("items", [])
        if not items: break
        all_items.extend(items); page += 1
        total = len(all_items)
        print(f"  页{page}: +{len(items)}  累计{total}")
        if max_count and total >= max_count: all_items = all_items[:max_count]; break
        if not data.get("has_more"): break
        cursor = data.get("next_cursor", 0)
        if not cursor: break; time.sleep(0.2)
    print(f"[OK] 共 {len(all_items)} 个{tag}")

    try: author_info = adapter.fetch_author(sec_uid); author_name = clean_name(author_info.nickname or sec_uid[:12], 30)
    except: author_name = clean_name(sec_uid[:12], 12)
    author_dir = out / author_name / tag; data_dir = author_dir / "data"; data_dir.mkdir(parents=True, exist_ok=True)

    tracker_file = data_dir / ".downloaded.json"
    downloaded_ids = set()
    if tracker_file.exists():
        try: downloaded_ids = set(_json.loads(tracker_file.read_text(encoding="utf-8")))
        except: pass

    stats = {"ok":0,"fail":0,"skip":0}
    for i, item in enumerate(all_items):
        aweme_id = item.item_id
        if aweme_id in downloaded_ids: stats["skip"] += 1; continue
        short = hashlib.md5(str(aweme_id).encode()).hexdigest()[:4]
        desc = clean_name(item.title or aweme_id, 30)
        print(f"[{i+1:03d}/{len(all_items)}] {_s(desc, 30)}...")
        downloaded = False; aw = item.extra.get("aweme",{})
        video = aw.get("video"); images = aw.get("images") or []
        if video and not images:
            url = pick_best_video_url(video)
            if url and download_file(url, author_dir / f"{i+1:04d}_{short}_{desc}.mp4"): stats["ok"] += 1; downloaded = True
            else: stats["fail"] += 1
        elif images:
            for j, img in enumerate(images):
                urls = img.get("url_list",[])
                img_url = next((u for u in urls if "webp" in u.lower()),None) or next((u for u in urls if "jpeg" in u.lower()),None) or next((u for u in urls if "jpg" in u.lower()),None) or (urls[0] if urls else "")
                if img_url and download_file(img_url, author_dir / f"{i+1:04d}_{short}_{j+1:02d}.jpg"): stats["ok"] += 1; downloaded = True
                else: stats["fail"] += 1
        if downloaded: downloaded_ids.add(aweme_id)
    tracker_file.write_text(_json.dumps(list(downloaded_ids), ensure_ascii=False), encoding="utf-8")
    print(f"[DONE] {tag}:{stats['ok']}  失败:{stats['fail']}  跳过:{stats['skip']}")
    print(f"       保存到: {_s(str(author_dir))}")


# ══════════ CLI — music ══════════

def _cli_music(url, max_count=0, save_dir=""):
    from pathlib import Path
    from src.platforms.douyin import DouyinAdapter
    from src.downloader import download_file
    from src.utils import clean_name
    from src.environ import OUTPUT_MUSIC

    adapter = DouyinAdapter()
    sec_uid = _resolve_user_url(url)
    print(f"[*] sec_uid: {sec_uid[:30]}...")
    try: author_info = adapter.fetch_author(sec_uid); author_name = clean_name(author_info.nickname or sec_uid[:12], 30)
    except: author_name = clean_name(sec_uid[:12], 12)
    out = (Path(save_dir) if save_dir else OUTPUT_MUSIC) / author_name / "音乐"
    out.mkdir(parents=True, exist_ok=True)

    all_items = []; cursor = 0; page = 0
    while True:
        data = adapter.fetch_music(sec_uid, max_cursor=cursor, count=18)
        items = data.get("items", [])
        if not items: break
        all_items.extend(items); page += 1
        total = len(all_items)
        print(f"  页{page}: +{len(items)}  累计{total}")
        if max_count and total >= max_count: all_items = all_items[:max_count]; break
        if not data.get("has_more"): break
        cursor = data.get("next_cursor", 0)
        if not cursor: break; time.sleep(0.2)
    print(f"[OK] 共 {len(all_items)} 首音乐")

    ok = 0
    for i, m in enumerate(all_items):
        title = clean_name(m.get("title", m.get("music_id","")), 40)
        murl = m.get("url","")
        if not murl: continue
        ext = ".mp3" if "mp3" in murl.lower() else ".m4a"
        fname = f"{i+1:03d}_{title}{ext}"
        fpath = out / fname
        print(f"[{i+1}/{len(all_items)}] {_s(fname, 60)}...")
        if download_file(murl, fpath): ok += 1
    print(f"[DONE] 音乐:{ok}/{len(all_items)}  保存到: {_s(str(out))}")


# ══════════ 平台识别 ══════════

def _detect_platform(url: str) -> str:
    """识别链接所属平台，返回 'douyin' / 'bilibili' / 'weibo' / '' """
    url_lower = url.lower()
    # 抖音
    if any(k in url_lower for k in ("douyin.com", "iesdouyin.com", "v.douyin.com")):
        return "douyin"
    # B站
    if any(k in url_lower for k in ("bilibili.com", "b23.tv")):
        return "bilibili"
    # 微博
    if any(k in url_lower for k in ("weibo.com", "t.cn")):
        return "weibo"
    return ""


# ══════════ 用户 ID 解析 ══════════

def _resolve_user_url(url: str) -> str:
    import requests as _r
    from src.platforms.douyin import DouyinAdapter
    from src.environ import USER_AGENT
    adapter = DouyinAdapter()
    if "/user/self" in url:
        own_id = adapter.get_own_author_id()
        if own_id: return own_id
        raise ValueError("无法获取自己的用户 ID，请检查 Cookie")
    try: return adapter.resolve_url(url)
    except: pass
    if "v.douyin.com" in url:
        s = _r.Session(); s.headers.update({"User-Agent": USER_AGENT})
        r = s.get(url, allow_redirects=True, timeout=15, stream=True); r.close(); url = r.url
    for pat in [r'sec_user_id=([A-Za-z0-9_\-]+)', r'/user/(MS4wLjAB[A-Za-z0-9_\-]+)']:
        m = re.search(pat, url)
        if m: return m.group(1)
    raise ValueError(f"无法从链接中提取用户 ID: {url[:60]}")


# ══════════ 辅助 ══════════

def _parse_image_range(spec: str) -> set:
    result = set()
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            a, b = part.split("-", 1)
            for n in range(int(a.strip()), int(b.strip())+1): result.add(n-1)
        else: result.add(int(part)-1)
    return result


def _write_profile_md(data_dir, author, profile, avatar_url, cover_url, source_url):
    import requests as _r
    from src.environ import USER_AGENT as _UA
    nickname = author.nickname or profile.get("nickname","")
    unique_id = profile.get("unique_id",""); short_id = profile.get("short_id","")
    uid = profile.get("uid",""); bio = profile.get("desc","")
    gender = {0:"未设置",1:"男",2:"女"}.get(profile.get("gender",0),"")
    age = profile.get("age",-1)
    region = "-".join(filter(None,[profile.get("country",""),profile.get("province",""),profile.get("city",""),profile.get("district","")])) or "N/A"
    ip_location = profile.get("ip_location",""); school = profile.get("school","")
    verify = profile.get("custom_verify","") or profile.get("enterprise_verify_reason","")
    tags = profile.get("personal_tags",[])
    def _fmt(n):
        if n is None or n<0: return "N/A"
        if n>=10000: return f"{n/10000:.1f}万"
        return str(n)
    lines = [f"# {nickname}","","## 基本信息","",f"| 项目 | 内容 |",f"|------|------|",
             f"| 抖音号 | {unique_id or short_id or 'N/A'} |",f"| UID | {uid} |",
             f"| 性别 | {gender} |",f"| 年龄 | {age if age>0 else 'N/A'} |",f"| 地区 | {region} |"]
    if ip_location: lines.append(f"| IP属地 | {ip_location} |")
    if school: lines.append(f"| 学校 | {school} |")
    if bio: lines.append(f"| 简介 | {bio} |")
    if tags: lines.append(f"| 标签 | {', '.join(tags)} |")
    lines.append(f"| 认证 | {verify or '无'} |")
    lines.extend(["","## 数据统计","",f"| 项目 | 数值 |",f"|------|------|",
                  f"| 作品 | {author.post_count} |",f"| 粉丝 | {_fmt(author.follower_count)} |",
                  f"| 关注 | {_fmt(profile.get('following_count',0))} |",
                  f"| 获赞 | {_fmt(profile.get('favoriting_count',0))} |",
                  f"| 被赞 | {_fmt(profile.get('total_favorited',0))} |","","## 下载信息",""])
    if source_url: lines.append(f"- 主页链接: {source_url}")
    lines.append(f"- sec_uid: {profile.get('sec_uid','')}")
    lines.append(f"- 下载日期: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    if avatar_url: lines.append(f"- 头像: {avatar_url}")
    if cover_url: lines.append(f"- 封面: {cover_url}")
    _dl_headers = {"User-Agent": _UA, "Referer": "https://www.douyin.com/"}
    from src.cookie import load_cookie; _ck = load_cookie()
    if _ck: _dl_headers["Cookie"] = _ck
    lines.append("")
    if avatar_url:
        try: r = _r.get(avatar_url, headers=_dl_headers, timeout=15); (data_dir/"avatar.jpg").write_bytes(r.content); lines.append("*(头像已保存)*")
        except Exception as e: lines.append(f"*(头像下载失败: {e})*")
    if cover_url:
        try: r = _r.get(cover_url, headers=_dl_headers, timeout=15); (data_dir/"cover.jpg").write_bytes(r.content); lines.append("*(封面已保存)*")
        except Exception as e: lines.append(f"*(封面下载失败: {e})*")
    (data_dir/"主页简介.md").write_text("\n".join(lines), encoding="utf-8")


# ══════════ 登录 ══════════

def cmd_login():
    from src.cookie import save_cookie, load_cookie
    from src.signer import BrowserFinder
    from playwright.sync_api import sync_playwright
    browser_path = BrowserFinder.find()
    if not browser_path: return print("[!] 未找到可用浏览器，请安装 Chrome 或 Edge")
    print("正在打开浏览器...\n请在浏览器中扫码登录抖音，成功后自动关闭")
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=browser_path, headless=False,
            args=["--no-sandbox"])
        context = browser.new_context(viewport={"width":1280,"height":800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/141.0.0.0 Safari/537.36")
        page = context.new_page(); page.goto("https://www.douyin.com/")
        for _ in range(120):
            time.sleep(1)
            try:
                cookies = context.cookies()
                parts = [f"{c['name']}={c['value']}" for c in cookies]
                cs = "; ".join(parts)
                if "sessionid=" in cs and "ttwid=" in cs:
                    save_cookie(cs); print(f"[OK] 登录成功！Cookie 已保存 ({len(cs)} 字符)"); break
            except: pass
        else: print("[!] 登录超时")
        browser.close()


def cmd_dev(args: list[str]):
    if not args:
        print("dev 子命令:  check-cookie  test-signer"); return
    sub = args[0]
    if sub == "check-cookie":
        from src.cookie import load_cookie, validate_cookie
        cookie = load_cookie()
        print(f"Cookie 长度: {len(cookie)}\nCookie 有效: {validate_cookie(cookie)}")
        if cookie: print(f"前 80 字符: {cookie[:80]}...")
    elif sub == "test-signer": print("signer 测试将在 M2 实现")
    else: print(f"未知 dev 命令: {sub}")


# ══════════ 入口 ══════════

def main():
    if len(sys.argv) < 2:
        print("Origami v2 — 用法:")
        print("  python -m src.main login        扫码登录")
        print("  python -m src.main server       启动 API Server")
        print("  python -m src.main cli <mode>   命令行下载")
        print("  python -m src.main dev <cmd>    开发工具")
        return
    cmd = sys.argv[1]; rest = sys.argv[2:]
    if cmd == "server": cmd_server(rest)
    elif cmd == "cli": cmd_cli(rest)
    elif cmd == "login": cmd_login()
    elif cmd == "dev": cmd_dev(rest)
    else: print(f"未知命令: {cmd}\n可用: server | cli | login | dev")


if __name__ == "__main__":
    main()
