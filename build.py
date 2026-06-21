# -*- coding: utf-8 -*-
"""
Origami — PyInstaller 构建脚本

用法:
    python build.py                   # 完整版打包
    python build.py --installer       # 完整版 + 安装包
    python build.py --installer --light  # 轻量版 + 安装包 + webengine.zip
"""

import sys
import shutil
import subprocess
import zipfile
from pathlib import Path

# CI runner 编码兼容
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

PROJECT_DIR = Path(__file__).resolve().parent
DIST_DIR = PROJECT_DIR / "dist_out"

from src.config import VERSION

# Inno Setup 路径（本地 + CI runner）
ISCC_PATHS = [
    Path("D:/Program Files (x86)/Inno Setup 6/ISCC.exe"),
    Path("C:/Program Files (x86)/Inno Setup 6/ISCC.exe"),
]


def clean():
    """清理构建产物（保留旧版 setup.exe）"""
    # 只删编译缓存和源代码目录，不删 setup.exe
    for d in [PROJECT_DIR / "build", PROJECT_DIR / "__pycache__"]:
        if d.exists():
            shutil.rmtree(d, ignore_errors=True)
    # 只删 dist_out 里的 Origami 目录（不含 setup.exe）
    _build_dir = DIST_DIR / "Origami"
    if _build_dir.exists():
        shutil.rmtree(_build_dir, ignore_errors=True)


def build(spec_file: Path, label: str = ""):
    """执行 PyInstaller 打包"""
    clean()
    cmd = [
        sys.executable, "-m", "PyInstaller",
        str(spec_file),
        "--distpath", str(DIST_DIR),
        "--workpath", str(PROJECT_DIR / "build"),
        "--noconfirm",
    ]
    tag = f" [{label}]" if label else ""
    print(f"[Origami] 开始打包{tag} v{VERSION}...")
    result = subprocess.run(cmd, cwd=str(PROJECT_DIR))
    if result.returncode != 0:
        print(f"[ERROR] 打包失败！")
        sys.exit(1)
    exe = (DIST_DIR / "Origami" / "Origami.exe")
    if exe.exists():
        print(f"[OK] 打包完成 ({exe.stat().st_size / 1024 / 1024:.1f}MB)")


def create_installer(is_light: bool = False):
    """PyInstaller 打包完成后，调用 Inno Setup 生成 setup.exe"""
    iscc = None
    for p in ISCC_PATHS:
        if p.exists():
            iscc = str(p)
            break

    if not iscc:
        print("[WARN] 未找到 Inno Setup (ISCC.exe)，跳过安装包生成")
        return

    iss_file = PROJECT_DIR / ("installer_light.iss" if is_light else "installer.iss")
    tag = " [轻量版]" if is_light else ""
    print(f"[Origami] 生成安装包{tag} v{VERSION}...")
    result = subprocess.run(
        [iscc, f"/DMyAppVersion={VERSION}", str(iss_file)],
        cwd=str(PROJECT_DIR),
    )
    if result.returncode == 0:
        expected = f"Origami_v{VERSION}_setup.exe"
        setup = DIST_DIR / expected
        if setup.exists():
            size_mb = setup.stat().st_size / (1024 * 1024)
            print(f"[OK] 安装包: {setup} ({size_mb:.1f}MB)")
    else:
        print("[WARN] 安装包生成失败，请检查 Inno Setup 配置")


def create_webengine_zip():
    """从完整版构建产物中打包 WebEngine 组件"""
    src_bin = PROJECT_DIR / "dist_out" / "Origami" / "_internal" / "PyQt6" / "Qt6" / "bin"
    if not src_bin.exists():
        print("[WARN] 未找到完整版构建产物，跳过 webengine.zip")
        return

    zip_path = DIST_DIR / "webengine.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for dll in sorted(src_bin.glob("Qt6WebEngine*.dll")):
            zf.write(dll, dll.name)
            print(f"  + {dll.name}")
        for dll in sorted(src_bin.glob("Qt6WebChannel*.dll")):
            zf.write(dll, dll.name)
            print(f"  + {dll.name}")
        for pak in sorted(src_bin.glob("qtwebengine*.pak")):
            zf.write(pak, pak.name)
            print(f"  + {pak.name}")

    size_mb = zip_path.stat().st_size / (1024 * 1024)
    print(f"[OK] webengine.zip ({size_mb:.1f}MB)")


if __name__ == "__main__":
    is_light = "--light" in sys.argv
    do_installer = "--installer" in sys.argv

    if is_light:
        print("[Origami] Step 1/2: 完整版（提取 WebEngine DLL）")
        build(PROJECT_DIR / "Origami.spec", "full")
        create_webengine_zip()

        print("[Origami] Step 2/2: 轻量版（不含 WebEngine）")
        build(PROJECT_DIR / "Origami_light.spec", "light")
        # 删除 WebEngine DLL（由组件包提供）
        _light_bin = DIST_DIR / "Origami_light" / "_internal" / "PyQt6" / "Qt6" / "bin"
        for _pat in ("Qt6WebEngine*.dll", "Qt6WebChannel*.dll"):
            for _f in _light_bin.glob(_pat):
                _f.unlink()
                print(f"  - {_f.name}")
        if do_installer:
            create_installer(is_light=True)
    else:
        build(PROJECT_DIR / "Origami.spec", "full")
        if do_installer:
            create_installer()
