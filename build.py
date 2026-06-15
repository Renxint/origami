# -*- coding: utf-8 -*-
"""
Origami — PyInstaller 构建脚本

用法:
    python build.py              # 打包为目录
    python build.py --installer  # 打包 + 生成 Inno Setup 安装包
    python build.py --spec-only  # 仅生成 .spec 文件
"""

import sys
import shutil
import subprocess
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent
DIST_DIR = PROJECT_DIR / "dist_out"
SPEC_FILE = PROJECT_DIR / "Origami.spec"

from src.config import VERSION

# Inno Setup 路径（本地 + CI runner）
ISCC_PATHS = [
    Path("D:/Program Files (x86)/Inno Setup 6/ISCC.exe"),
    Path("C:/Program Files (x86)/Inno Setup 6/ISCC.exe"),
]


def clean():
    """清理构建产物"""
    for d in [DIST_DIR, PROJECT_DIR / "build", PROJECT_DIR / "__pycache__"]:
        if d.exists():
            shutil.rmtree(d, ignore_errors=True)


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

    build_dir = DIST_DIR / f"Origami_v{VERSION}"
    exe = build_dir / f"Origami_v{VERSION}.exe"
    if exe.exists():
        size_mb = exe.stat().st_size / (1024 * 1024)
        print(f"[OK] 打包完成 ({size_mb:.1f}MB)")
    else:
        print(f"[WARN] 未找到 {exe.name}，请检查 spec 配置")


def create_installer():
    """PyInstaller 打包完成后，调用 Inno Setup 生成 setup.exe"""
    iscc = None
    for p in ISCC_PATHS:
        if p.exists():
            iscc = str(p)
            break

    if not iscc:
        print("[WARN] 未找到 Inno Setup (ISCC.exe)，跳过安装包生成")
        print("       安装 Inno Setup: https://jrsoftware.org/isdl.php")
        return

    iss_file = PROJECT_DIR / "installer.iss"
    print(f"[Origami] 生成安装包 v{VERSION}...")
    result = subprocess.run(
        [iscc, f"/DMyAppVersion={VERSION}", str(iss_file)],
        cwd=str(PROJECT_DIR),
    )
    if result.returncode == 0:
        setup = DIST_DIR / f"Origami_v{VERSION}_setup.exe"
        if setup.exists():
            size_mb = setup.stat().st_size / (1024 * 1024)
            print(f"[OK] 安装包: {setup} ({size_mb:.1f}MB)")
    else:
        print("[WARN] 安装包生成失败，请检查 Inno Setup 配置")


if __name__ == "__main__":
    if "--spec-only" in sys.argv:
        print(f"[Origami] spec 文件: {SPEC_FILE}")
    else:
        build()
        if "--installer" in sys.argv:
            create_installer()
