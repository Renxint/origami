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
    """命令行下载（M3 实现）"""
    if not args:
        print("用法: python -m src.main cli <single|batch> <url>")
        print()
        print("  例: python -m src.main cli single \"https://v.douyin.com/xxx/\"")
        print("  例: python -m src.main cli batch  \"https://www.douyin.com/user/MS4wLjAB...\"")
        return
    mode = args[0]
    url = args[1] if len(args) > 1 else ""
    if not url:
        print("请提供链接")
        return
    print(f"[Origami v2] CLI {mode}: {url}")
    print("[Origami v2] CLI 模式将在 M3 实现")


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
