# -*- coding: utf-8 -*-
"""
Origami v2 — Desktop Shell

入口：python src/desktop.py
用户看到独立的桌面窗口，API Server 在后台运行。
"""

import sys
import os
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


class DesktopApi:
    """pywebview JS-Python 桥"""

    def __init__(self):
        self._window = None

    def set_window(self, w):
        self._window = w

    def startLogin(self):
        """导航到抖音 → 轮询 Cookie → 保存 → 回首页"""
        w = self._window
        if not w:
            return {"ok": False, "error": "no_window"}

        from src.cookie import save_cookie
        w.load_url("https://www.douyin.com/")

        def _poll():
            for _ in range(60):
                time.sleep(2)
                try:
                    cookies = w.get_cookies()
                    parts = [f"{c['name']}={c['value']}" for c in cookies
                             if c.get("name") and c.get("value")]
                    cs = "; ".join(parts)
                    if "sessionid=" in cs and "ttwid=" in cs:
                        save_cookie(cs)
                        w.load_url(f"http://127.0.0.1:{_port}/pages/home.html")
                        return
                except Exception:
                    pass
            w.load_url(f"http://127.0.0.1:{_port}/pages/home.html")

        threading.Thread(target=_poll, daemon=True).start()
        return {"ok": True}

    def getApiBase(self):
        return f"http://127.0.0.1:{_port}"

    def getWsUrl(self):
        return f"ws://127.0.0.1:{_port}/ws/events"


_port = 8765


def run():
    global _port
    """启动桌面应用"""
    # 1. 后台启动 API Server
    from src.server import create_app, find_available_port, API_PORT
    from aiohttp import web

    _port = find_available_port(API_PORT)
    app = create_app()

    def _start_server():
        web.run_app(app, host="127.0.0.1", port=_port, print=lambda *_: None)

    threading.Thread(target=_start_server, daemon=True, name="api-server").start()

    # 等 server 就绪
    import requests
    for _ in range(20):
        try:
            requests.get(f"http://127.0.0.1:{_port}/api/version", timeout=1)
            break
        except Exception:
            time.sleep(0.5)

    print(f"[Origami] http://127.0.0.1:{_port}")

    # 2. 前台 pywebview 窗口
    import webview

    api = DesktopApi()
    window = webview.create_window(
        "Origami",
        f"http://127.0.0.1:{_port}/pages/home.html",
        js_api=api,
        width=800, height=600, min_size=(520, 420),
    )
    api.set_window(window)

    webview.start()


if __name__ == "__main__":
    run()
