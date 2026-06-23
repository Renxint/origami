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
    """pywebview JS-Python 桥：前端通过 window.pywebview.api.xxx() 调用"""

    def login(self):
        """扫码登录 — 在主线程启动 WebView 窗口"""
        from src.cookie import save_cookie
        import webview

        result = {"cookie": "", "done": False}

        def _on_loaded():
            def _check():
                for _ in range(60):
                    time.sleep(2)
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
            return {"ok": True, "cookie_len": len(result["cookie"])}
        return {"ok": False}

    def getApiBase(self):
        """返回 API Server 地址"""
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
        width=420, height=560, min_size=(340, 420),
        on_top=False,
    )

    webview.start()


if __name__ == "__main__":
    run()
