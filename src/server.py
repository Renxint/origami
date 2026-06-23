# -*- coding: utf-8 -*-
"""
Origami v2 — API Server

本地 HTTP + WebSocket 服务，前端通过 REST/WS 调用所有后端能力。
基于 aiohttp，绑定 localhost，不暴露到网络。

启动:
    python src/main.py server
    python src/main.py server --port 8765
"""

import json
import asyncio
import weakref
import sys
import os
from pathlib import Path
from typing import Optional

from aiohttp import web, WSMsgType

from src.environ import API_PORT, EXE_DIR, BASE_DIR
from src.config import VERSION

# ═══════════════════════════════════════════════════════════
# Event Bus — 连接 WebSocket ↔ 后台下载线程
# ═══════════════════════════════════════════════════════════

class EventBus:
    """轻量发布/订阅，收集活跃 WebSocket 连接并广播事件"""

    def __init__(self):
        self._ws: weakref.WeakSet = weakref.WeakSet()

    def register(self, ws: web.WebSocketResponse):
        self._ws.add(ws)

    def unregister(self, ws: web.WebSocketResponse):
        self._ws.discard(ws)

    async def broadcast(self, event: dict):
        """向所有连接的 WS 客户端推送事件（失败静默跳过）"""
        payload = json.dumps(event, ensure_ascii=False)
        dead = []
        for ws in list(self._ws):
            try:
                await ws.send_str(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self._ws.discard(ws)

    @property
    def connected(self) -> int:
        return len(self._ws)


# 全局单例
event_bus = EventBus()


def push_event(event: dict):
    """同步包装：从任意线程安全地推送事件到 WS 客户端"""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.create_task(event_bus.broadcast(event))
    except RuntimeError:
        pass


# ═══════════════════════════════════════════════════════════
# Request Helpers
# ═══════════════════════════════════════════════════════════

def json_response(data, status=200):
    return web.json_response(data, status=status)


def error_response(msg: str, status=400, code: str = ""):
    return json_response({"error": msg, "code": code}, status=status)


async def read_body(request: web.Request) -> dict:
    try:
        return await request.json()
    except Exception:
        return {}


# ═══════════════════════════════════════════════════════════
# Route Handlers — 按端点分组
# ═══════════════════════════════════════════════════════════

# ── GET /api/version ──
async def api_version(request: web.Request):
    return json_response({
        "version": VERSION,
        "platforms": list_platform_ids(),
    })

# ── GET /api/settings ──
async def api_get_settings(request: web.Request):
    from src.settings.store import load as load_settings
    return json_response(load_settings())

# ── POST /api/settings ──
async def api_set_settings(request: web.Request):
    from src.settings.store import load as load_settings, save as save_settings
    body = await read_body(request)
    if not body:
        return error_response("empty body")
    settings = load_settings()
    settings.update(body)
    save_settings(settings)
    return json_response({"ok": True})

# ── GET /api/settings/<key> ──
async def api_get_setting(request: web.Request):
    from src.settings.store import load as load_settings
    key = request.match_info.get("key", "")
    settings = load_settings()
    if key not in settings:
        return error_response(f"unknown key: {key}", 404, "NOT_FOUND")
    return json_response({key: settings[key]})

# ── GET /api/cookie ──
async def api_cookie_status(request: web.Request):
    from src.cookie import get_cookie_status
    return json_response(get_cookie_status())

# ── POST /api/login/webview ──
async def api_login_webview(request: web.Request):
    """启动系统 WebView 扫码登录（主线程）→ 保存 Cookie"""
    try:
        import webview
    except ImportError:
        return json_response({"ok": False, "message": "请先安装: pip install pywebview"})

    from src.cookie import save_cookie
    import time as _t, threading

    result = {"cookie": "", "done": False}

    def _on_loaded():
        def _check():
            for _ in range(60):
                _t.sleep(2)
                try:
                    cookies = window.get_cookies()
                    if cookies:
                        parts = [f"{c['name']}={c['value']}" for c in cookies
                                 if c.get("name") and c.get("value")]
                        cs = "; ".join(parts)
                        if "sessionid=" in cs and "ttwid=" in cs:
                            result["cookie"] = cs
                            result["done"] = True
                            window.destroy()
                            return
                except Exception:
                    pass
            result["done"] = True
            try:
                window.destroy()
            except Exception:
                pass
        threading.Thread(target=_check, daemon=True).start()

    window = webview.create_window(
        "Origami — 登录抖音", "https://www.douyin.com/",
        width=420, height=620, on_top=True)
    window.events.loaded += _on_loaded
    webview.start()

    if result["cookie"]:
        save_cookie(result["cookie"])
        return json_response({"ok": True, "cookie_len": len(result["cookie"])})
    return json_response({"ok": False, "message": "登录超时或已取消"})

# ── POST /api/resolve-url ──
async def api_resolve_url(request: web.Request):
    """解析抖音分享链接 → 返回作品 ID 和类型"""
    body = await read_body(request)
    url = body.get("url", "").strip()
    if not url:
        return error_response("missing url")
    try:
        from src.platforms.douyin import DouyinAdapter
        adapter = DouyinAdapter()
        item_id = adapter.resolve_url(url)
        return json_response({
            "ok": True,
            "platform": "douyin",
            "item_id": item_id,
            "type": "video",
        })
    except Exception as e:
        return error_response(str(e), 422)

# ── POST /api/fetch-media ──
async def api_fetch_media(request: web.Request):
    """获取单个作品详情（含无水印链接）"""
    body = await read_body(request)
    item_id = body.get("item_id", "").strip()
    if not item_id:
        return error_response("missing item_id")
    try:
        from src.platforms.douyin import DouyinAdapter
        from src.cookie import load_cookie
        adapter = DouyinAdapter()
        media = adapter.fetch_media(item_id, load_cookie())
        return json_response({
            "ok": True,
            "item_id": media.item_id,
            "item_type": media.item_type,
            "title": media.title,
            "author": media.author,
            "media_urls": media.media_urls,
            "cover_url": media.cover_url,
        })
    except Exception as e:
        return error_response(str(e), 500)

# ── POST /api/fetch-posts ──
async def api_fetch_posts(request: web.Request):
    """翻页获取作品列表"""
    body = await read_body(request)
    author_id = body.get("author_id", "").strip()
    cursor = int(body.get("cursor", 0))
    count = int(body.get("count", 18))
    if not author_id:
        return error_response("missing author_id")
    try:
        from src.platforms.douyin import DouyinAdapter
        from src.cookie import load_cookie
        adapter = DouyinAdapter()
        result = adapter.fetch_posts(
            author_id, load_cookie(), max_cursor=cursor, count=count)
        items = []
        for m in result.get("items", []):
            items.append({
                "item_id": m.item_id,
                "item_type": m.item_type,
                "title": m.title,
                "author": m.author,
                "cover_url": m.cover_url,
            })
        return json_response({
            "ok": True,
            "items": items,
            "has_more": result.get("has_more", False),
            "next_cursor": result.get("next_cursor", 0),
        })
    except Exception as e:
        return error_response(str(e), 500)

# ── POST /api/fetch-author ──
async def api_fetch_author(request: web.Request):
    """获取作者信息"""
    body = await read_body(request)
    author_id = body.get("author_id", "").strip()
    url = body.get("url", "").strip()
    if not author_id and not url:
        return error_response("missing author_id or url")
    try:
        from src.platforms.douyin import DouyinAdapter
        from src.cookie import load_cookie
        adapter = DouyinAdapter()
        sec_uid = author_id
        if url and not sec_uid:
            sec_uid = adapter.resolve_user_url(url)
        author = adapter.fetch_author(sec_uid, load_cookie())
        return json_response({
            "ok": True,
            "author_id": author.author_id,
            "nickname": author.nickname,
            "avatar_url": author.avatar_url,
            "bio": author.bio,
            "post_count": author.post_count,
            "follower_count": author.follower_count,
        })
    except Exception as e:
        return error_response(str(e), 500)

# ── POST /api/fetch-likes ──
async def api_fetch_likes(request: web.Request):
    """翻页获取喜欢列表"""
    body = await read_body(request)
    author_id = body.get("author_id", "").strip()
    cursor = int(body.get("cursor", 0))
    count = int(body.get("count", 18))
    if not author_id:
        return error_response("missing author_id")
    try:
        from src.platforms.douyin import DouyinAdapter
        from src.cookie import load_cookie
        adapter = DouyinAdapter()
        result = adapter.fetch_likes(
            author_id, load_cookie(), max_cursor=cursor, count=count)
        items = []
        for m in result.get("items", []):
            items.append({
                "item_id": m.item_id,
                "item_type": m.item_type,
                "title": m.title,
                "author": m.author,
            })
        return json_response({
            "ok": True,
            "items": items,
            "has_more": result.get("has_more", False),
            "next_cursor": result.get("next_cursor", 0),
        })
    except Exception as e:
        return error_response(str(e), 500)

# ── POST /api/fetch-comments ──
async def api_fetch_comments(request: web.Request):
    """获取作品评论"""
    body = await read_body(request)
    aweme_id = body.get("aweme_id", "").strip()
    cursor = int(body.get("cursor", 0))
    count = int(body.get("count", 20))
    if not aweme_id:
        return error_response("missing aweme_id")
    try:
        from src.platforms.douyin import DouyinAdapter
        from src.cookie import load_cookie
        adapter = DouyinAdapter()
        result = adapter.fetch_comments(
            aweme_id, load_cookie(), cursor=cursor, count=count)
        return json_response({"ok": True, **result})
    except Exception as e:
        return error_response(str(e), 500)

# ── POST /api/download ──
async def api_download(request: web.Request):
    """下载作品（进度通过 WebSocket 实时推送）"""
    body = await read_body(request)
    url = body.get("url", "")
    if not url:
        return error_response("missing url")

    import concurrent.futures
    loop = asyncio.get_event_loop()

    def _do_download():
        from src.platforms.douyin import DouyinAdapter
        from src.downloader import download_file
        from src.cookie import load_cookie
        from src.environ import OUTPUT_SINGLE
        from src.utils import clean_name

        adapter = DouyinAdapter()
        item_id = adapter.resolve_url(url)
        media = adapter.fetch_media(item_id, load_cookie())

        save_dir = Path(body.get("save_dir", str(OUTPUT_SINGLE)))
        save_dir.mkdir(parents=True, exist_ok=True)

        downloaded = []
        total = len(media.media_urls)
        push_event({"event": "download_start", "title": media.title,
                     "author": media.author, "item_type": media.item_type, "total": total})

        for i, murl in enumerate(media.media_urls):
            ext = ".mp4" if media.item_type == "video" else ".jpg"
            fname = f"{clean_name(media.title or item_id, 30)}_{i+1}{ext}"
            fpath = save_dir / fname
            push_event({"event": "log", "level": "info",
                         "msg": f"[{i+1}/{total}] {fname}"})
            ok = download_file(murl, fpath)
            downloaded.append({"file": str(fpath), "ok": ok})
            push_event({"event": "progress", "current": i+1, "total": total,
                         "file": str(fpath), "ok": ok})

        push_event({"event": "download_done", "title": media.title,
                     "files": downloaded, "save_dir": str(save_dir)})
        return {"ok": True, "title": media.title, "author": media.author,
                "files": downloaded}

    try:
        result = await loop.run_in_executor(None, _do_download)
        return json_response(result)
    except Exception as e:
        push_event({"event": "log", "level": "error", "msg": str(e)})
        return error_response(str(e), 500)

# ── POST /api/browse-folder ──
async def api_browse_folder(request: web.Request):
    """弹出系统原生文件夹选择器"""
    # 需要 GUI 线程 — M3 实现
    return json_response({"path": ""})

# ── POST /api/open-folder ──
async def api_open_folder(request: web.Request):
    body = await read_body(request)
    path = body.get("path", "")
    if path and Path(path).exists():
        import subprocess, platform
        if platform.system() == "Windows":
            os.startfile(path)
        elif platform.system() == "Darwin":
            subprocess.run(["open", path])
        else:
            subprocess.run(["xdg-open", path])
        return json_response({"ok": True})
    return error_response("path not found", 404)

# ── WebSocket /ws/events ──
async def ws_events(request: web.Request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    event_bus.register(ws)

    # 发送欢迎消息确认连接
    await ws.send_str(json.dumps({
        "event": "connected",
        "version": VERSION,
    }))

    try:
        async for msg in ws:
            if msg.type == WSMsgType.TEXT:
                # 客户端可以发 ping，暂不处理
                pass
            elif msg.type == WSMsgType.ERROR:
                break
    finally:
        event_bus.unregister(ws)
    return ws


# ═══════════════════════════════════════════════════════════
# App Factory
# ═══════════════════════════════════════════════════════════

def list_platform_ids() -> list[str]:
    try:
        from src.platforms.base import list_platforms
        return list_platforms()
    except Exception:
        return ["douyin"]


def create_app() -> web.Application:
    app = web.Application()

    # CORS: 允许本地任意端口的前端调试
    @web.middleware
    async def cors_middleware(request, handler):
        resp = await handler(request)
        resp.headers["Access-Control-Allow-Origin"] = "*"
        resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
        return resp

    app.middlewares.append(cors_middleware)

    # ── 路由表 ──
    app.router.add_get("/api/version",     api_version)
    app.router.add_get("/api/settings",    api_get_settings)
    app.router.add_post("/api/settings",   api_set_settings)
    app.router.add_get("/api/settings/{key}", api_get_setting)
    app.router.add_get("/api/cookie",      api_cookie_status)
    app.router.add_post("/api/login/webview", api_login_webview)
    app.router.add_post("/api/resolve-url",   api_resolve_url)
    app.router.add_post("/api/fetch-media",   api_fetch_media)
    app.router.add_post("/api/fetch-posts",   api_fetch_posts)
    app.router.add_post("/api/fetch-author",  api_fetch_author)
    app.router.add_post("/api/fetch-likes",   api_fetch_likes)
    app.router.add_post("/api/fetch-comments",api_fetch_comments)
    app.router.add_post("/api/download",      api_download)
    app.router.add_post("/api/browse-folder", api_browse_folder)
    app.router.add_post("/api/open-folder",   api_open_folder)
    app.router.add_get("/ws/events",         ws_events)

    # ── 首页重定向 ──
    async def index_redirect(request):
        raise web.HTTPFound("/pages/home.html")
    app.router.add_get("/", index_redirect)

    # ── 静态文件：ui/ → / ──
    ui_dir = BASE_DIR / "ui"
    if ui_dir.exists():
        app.router.add_static("/", ui_dir, show_index=True)

    return app


def find_available_port(start: int) -> int:
    """从 start 开始扫描，返回第一个可绑定端口"""
    import socket
    for port in range(start, start + 100):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.bind(("127.0.0.1", port))
            s.close()
            return port
        except OSError:
            s.close()
    return start


def run_server(port: int = 0):
    """启动 API Server（阻塞）"""
    if port <= 0:
        port = find_available_port(API_PORT)
    app = create_app()
    print(f"[Origami v2] API Server → http://localhost:{port}")
    print(f"[Origami v2] WebSocket   → ws://localhost:{port}/ws/events")

    # 静默关闭，不刷屏
    import signal as _sig
    def _shutdown(sig, frame):
        raise SystemExit(0)
    _sig.signal(_sig.SIGINT, _shutdown)

    try:
        web.run_app(app, host="127.0.0.1", port=port,
                    print=lambda *_: None, handle_signals=False)
    except SystemExit:
        pass
