# -*- coding: utf-8 -*-
"""
Origami — PyInstaller 构建脚本

用法:
    python build.py              # 打包为目录
    python build.py --installer  # 打包 + Inno Setup 安装包
    python build.py --zip        # 附加：提取 webengine.zip（供以后签名用）
"""

import sys
import shutil
import subprocess
import zipfile
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

PROJECT_DIR = Path(__file__).resolve().parent
DIST_DIR = PROJECT_DIR / "dist_out"
SPEC_FILE = PROJECT_DIR / "Origami.spec"

from src.config import VERSION

ISCC_PATHS = [
    Path("D:/Program Files (x86)/Inno Setup 6/ISCC.exe"),
    Path("C:/Program Files (x86)/Inno Setup 6/ISCC.exe"),
]


def clean():
    for d in [PROJECT_DIR / "build", PROJECT_DIR / "__pycache__"]:
        if d.exists():
            shutil.rmtree(d, ignore_errors=True)
    _build_dir = DIST_DIR / "Origami"
    if _build_dir.exists():
        shutil.rmtree(_build_dir, ignore_errors=True)


def build():
    clean()
    cmd = [sys.executable, "-m", "PyInstaller", str(SPEC_FILE),
           "--distpath", str(DIST_DIR), "--workpath", str(PROJECT_DIR / "build"), "--noconfirm"]
    print(f"[Origami] 打包 v{VERSION}...")
    result = subprocess.run(cmd, cwd=str(PROJECT_DIR))
    if result.returncode != 0:
        print("[ERROR] 打包失败！"), sys.exit(1)
    exe = DIST_DIR / "Origami" / "Origami.exe"
    if exe.exists():
        print(f"[OK] 打包完成 ({exe.stat().st_size / 1024 / 1024:.1f}MB)")


def create_installer():
    iscc = next((str(p) for p in ISCC_PATHS if p.exists()), None)
    if not iscc:
        print("[WARN] 未找到 Inno Setup，跳过安装包"); return
    iss_file = PROJECT_DIR / "installer.iss"
    print(f"[Origami] 生成安装包 v{VERSION}...")
    subprocess.run([iscc, f"/DMyAppVersion={VERSION}", str(iss_file)], cwd=str(PROJECT_DIR))
    setup = DIST_DIR / f"Origami_v{VERSION}_setup.exe"
    if setup.exists():
        print(f"[OK] 安装包: {setup} ({setup.stat().st_size / 1024 / 1024:.1f}MB)")


def create_webengine_zip():
    src_bin = DIST_DIR / "Origami" / "_internal" / "PyQt6" / "Qt6" / "bin"
    if not src_bin.exists():
        print("[WARN] 未找到构建产物，跳过 webengine.zip"); return
    zip_path = DIST_DIR / "webengine.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for pat in ("Qt6WebEngine*.dll", "Qt6WebChannel*.dll"):
            for f in sorted(src_bin.glob(pat)):
                zf.write(f, f.name)
                print(f"  + {f.name}")
    print(f"[OK] webengine.zip ({zip_path.stat().st_size / 1024 / 1024:.1f}MB)")


if __name__ == "__main__":
    build()
    if "--installer" in sys.argv:
        create_installer()
    if "--zip" in sys.argv:
        create_webengine_zip()
