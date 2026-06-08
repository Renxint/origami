# -*- coding: utf-8 -*-
"""
Origami — PyInstaller 构建脚本

用法:
    python build.py              # 打包为单文件 exe
    python build.py --spec-only  # 仅生成 .spec 文件
"""

import sys
import shutil
import subprocess
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent
DIST_DIR = PROJECT_DIR / "dist"
SPEC_FILE = PROJECT_DIR / "Origami.spec"

# 版本信息
from src.config import VERSION


def clean():
    """清理构建产物"""
    for d in [DIST_DIR, PROJECT_DIR / "build", PROJECT_DIR / "__pycache__"]:
        if d.exists():
            shutil.rmtree(d, ignore_errors=True)
    for spec in PROJECT_DIR.glob("*.spec"):
        pass  # 保留 spec


def build():
    """执行 PyInstaller 打包"""
    clean()

    cmd = [
        sys.executable, "-m", "PyInstaller",
        str(SPEC_FILE),
        "--distpath", str(DIST_DIR),
        "--workpath", str(PROJECT_DIR / "build"),
        "--noconfirm",
    ]

    print(f"[Origami] 开始打包 v{VERSION}...")
    result = subprocess.run(cmd, cwd=str(PROJECT_DIR))
    if result.returncode != 0:
        print("[ERROR] 打包失败！")
        sys.exit(1)

    exe = DIST_DIR / "Origami" / "Origami.exe"
    if exe.exists():
        size_mb = exe.stat().st_size / (1024 * 1024)
        print(f"[OK] 打包完成: {exe} ({size_mb:.1f}MB)")
    else:
        print("[WARN] 未找到 Origami.exe，请检查 spec 配置")


if __name__ == "__main__":
    if "--spec-only" in sys.argv:
        print(f"[Origami] spec 文件: {SPEC_FILE}")
    else:
        build()
