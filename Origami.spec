# -*- mode: python ; coding: utf-8 -*-
"""
Origami — PyInstaller 打包配置

优化策略：
- 排除无用 Qt 模块（-15~20MB）
- UPX 压缩（-10~15MB）
- sign-server 随包分发（仅视频签名时需要）
- 排除 numpy/pandas/matplotlib/tkinter 等无用库
"""

from PyInstaller.utils.hooks import collect_all
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(SPECPATH)))
from src.config import VERSION

# ── 数据文件 ──────────────────────────────────────────────
datas = [
    ('sign-server', 'sign-server'),   # Node.js 签名服务
    ('app.ico', '.'),                  # 应用图标
    ('translations', 'translations'),  # Qt 中文翻译
]

# ── 二进制文件 ────────────────────────────────────────────
# Node.js 运行时（用于 Puppeteer 签名）
binaries = []
node_paths = [
    'C:/Program Files/nodejs/node.exe',
    'C:/Program Files (x86)/nodejs/node.exe',
]
for np in node_paths:
    if os.path.exists(np):
        binaries.append((np, '.'))
        break

# ── 隐藏导入 ──────────────────────────────────────────────
hiddenimports = [
    # PyQt6
    'PyQt6', 'PyQt6.QtCore', 'PyQt6.QtGui', 'PyQt6.QtWidgets',
    'PyQt6.QtNetwork', 'PyQt6.QtWebEngineWidgets',
    # HTTP / 网络
    'requests', 'certifi', 'urllib3',
    # Cookie 提取
    'browser_cookie3',
    # Origami 源码
    'src', 'src.environ', 'src.config', 'src.api', 'src.utils',
    'src.cookie', 'src.downloader', 'src.webview_api',
    'src.fonts', 'src.stylesheet',
    'src.settings', 'src.settings.schema', 'src.settings.store',
    'src.platforms', 'src.platforms.base', 'src.platforms.douyin',
    'src.gui', 'src.gui.main_window',
    'src.gui.pages', 'src.gui.pages.mode_page',
    'src.gui.pages.douyin_page', 'src.gui.pages.single_page',
    'src.gui.pages.homepage_page', 'src.gui.pages.settings_page',
    'src.gui.pages.update_page',
    'src.gui.dialogs', 'src.gui.dialogs.cookie_dialog',
    'src.gui.dialogs.font_dialog',
    'src.gui.widgets', 'src.gui.widgets.toggle_switch',
]

# certifi 证书文件
tmp_ret = collect_all('certifi')
datas += tmp_ret[0]
binaries += tmp_ret[1]
hiddenimports += tmp_ret[2]

# ── 排除列表 ──────────────────────────────────────────────
# 无用的 Python 库
python_excludes = [
    'numpy', 'pandas', 'matplotlib', 'PIL', 'lxml',
    'scipy', 'pillow', 'tkinter', 'test', 'unittest',
    'pydoc', 'doctest', 'pdb',
]

# 无用的 PyQt6 模块
qt_excludes = [
    'PyQt6.QtBluetooth', 'PyQt6.QtDBus', 'PyQt6.QtDesigner',
    'PyQt6.QtHelp', 'PyQt6.QtMultimedia', 'PyQt6.QtMultimediaWidgets',
    'PyQt6.QtNfc', 'PyQt6.QtOpenGL', 'PyQt6.QtOpenGLWidgets',
    'PyQt6.QtPdf', 'PyQt6.QtPdfWidgets',
    'PyQt6.QtPositioning', 'PyQt6.QtPrintSupport',
    'PyQt6.QtQml', 'PyQt6.QtQuick', 'PyQt6.QtQuick3D',
    'PyQt6.QtQuickWidgets', 'PyQt6.QtRemoteObjects',
    'PyQt6.QtSensors', 'PyQt6.QtSerialPort',
    'PyQt6.QtSql', 'PyQt6.QtSvg', 'PyQt6.QtSvgWidgets',
    'PyQt6.QtTest', 'PyQt6.QtTextToSpeech',
    'PyQt6.QtWebChannel', 'PyQt6.QtWebEngine',
    'PyQt6.QtWebEngineCore', 'PyQt6.QtWebEngineQuick',
    'PyQt6.QtWebSockets', 'PyQt6.QtXml',
]

excludes = python_excludes + qt_excludes

# ── Analysis ──────────────────────────────────────────────
a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

# ── EXE ───────────────────────────────────────────────────
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=f'Origami_v{VERSION}',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=['node.exe'],  # UPX 会损坏 Node.js
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['app.ico'],
)

# ── COLLECT ───────────────────────────────────────────────
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=['node.exe'],
    name=f'Origami_v{VERSION}',
)
