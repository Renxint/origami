# -*- coding: utf-8 -*-
"""Origami - WebView login subprocess.

Usage: python login_webview.py <cookie_output_path>

Runs pywebview on the MAIN thread (required by pywebview) in a standalone
process.  Opens a window to douyin.com, waits for the user to scan the QR
code, then writes the cookie string to <cookie_output_path> and exits.
"""

import sys
import os
import time
import threading
import traceback

# Suppress pywebview internal cookie-parsing noise on stderr
sys.stderr = open(os.devnull, "w")


def main():
    if len(sys.argv) < 2:
        print("Usage: python login_webview.py <output_path>", file=sys.stderr)
        sys.exit(1)

    output_path = sys.argv[1]

    try:
        import webview
    except ImportError:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write("ERROR: pywebview not installed")
        sys.exit(2)

    result = {"cookie": "", "done": False}
    w = None

    def _on_loaded():
        def _check():
            debug_log = output_path + ".debug"
            for i in range(120):
                time.sleep(1.5)
                if result["done"]:
                    return
                try:
                    cookies = w.get_cookies()
                except Exception as e:
                    with open(debug_log, "a", encoding="utf-8") as f:
                        f.write(f"[{i}] get_cookies EXC: {e}\n")
                    continue
                # Also try JS as fallback (won't get HttpOnly, but helps debug)
                js_cookie = ""
                try:
                    js_cookie = w.evaluate_js("document.cookie") or ""
                except Exception:
                    pass

                # cookies is a list of SimpleCookie objects (each has 1 key = cookie name)
                parts = []
                names = []
                for sc in (cookies or []):
                    try:
                        for key in sc.keys():
                            morsel = sc[key]
                            if key and morsel.value:
                                parts.append(f"{key}={morsel.value}")
                                names.append(key)
                    except Exception:
                        pass
                cs = "; ".join(parts)

                if not cookies:
                    with open(debug_log, "a", encoding="utf-8") as f:
                        f.write(f"[{i}] get_cookies=0 js='{js_cookie[:80]}'\n")
                    # Fallback: use JS cookie if native API returns nothing
                    if js_cookie and "ttwid=" in js_cookie:
                        result["cookie"] = js_cookie
                        result["done"] = True
                        try: w.destroy()
                        except: pass
                        return
                else:
                    with open(debug_log, "a", encoding="utf-8") as f:
                        f.write(f"[{i}] total={len(cookies)} names={names} js='{js_cookie[:40]}'\n")
                if "sessionid=" in cs and "ttwid=" in cs:
                    result["cookie"] = cs
                    result["done"] = True
                    try:
                        w.destroy()
                    except Exception:
                        pass
                    return
            # Timeout
            result["done"] = True
            try:
                w.destroy()
            except Exception:
                pass

        threading.Thread(target=_check, daemon=True).start()

    try:
        w = webview.create_window(
            "Origami - Login",
            "https://www.douyin.com/",
            width=800, height=600, on_top=True)
        w.events.loaded += _on_loaded

        # Set window icon (Windows) — avoid python logo in taskbar
        if sys.platform == "win32":
            def _set_icon():
                import ctypes
                from ctypes import wintypes
                ico = os.path.join(os.path.dirname(os.path.dirname(
                    os.path.abspath(__file__))), "ui", "assets", "logo.ico")
                if not os.path.exists(ico):
                    return
                user32 = ctypes.windll.user32
                user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
                user32.FindWindowW.restype = wintypes.HWND
                # Find window by title, retry up to 3s
                hwnd = None
                for _ in range(30):
                    time.sleep(0.1)
                    hwnd = user32.FindWindowW(None, "Origami - Login")
                    if hwnd:
                        break
                if hwnd:
                    LR_LOADFROMFILE = 0x00000010
                    IMAGE_ICON = 1
                    hicon = user32.LoadImageW(0, ico, IMAGE_ICON, 0, 0, LR_LOADFROMFILE)
                    if hicon:
                        WM_SETICON = 0x0080
                        ICON_BIG = 1
                        ICON_SMALL = 0
                        user32.SendMessageW(hwnd, WM_SETICON, ICON_BIG, hicon)
                        user32.SendMessageW(hwnd, WM_SETICON, ICON_SMALL, hicon)
            threading.Thread(target=_set_icon, daemon=True).start()

        webview.start()
    except Exception:
        traceback.print_exc(file=sys.stderr)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write("ERROR: webview crashed")
        sys.exit(3)

    if result["cookie"]:
        try:
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(result["cookie"])
        except Exception:
            traceback.print_exc(file=sys.stderr)
            sys.exit(4)
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
