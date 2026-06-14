# -*- mode: python ; coding: utf-8 -*-
"""
Origami — PyInstaller 打包配置 v3 (collect-all PyQt6)
"""
import sys, os, glob
sys.path.insert(0, os.path.dirname(os.path.abspath(SPECPATH)))
from src.config import VERSION

# ── 数据文件 ──
datas = [
    ('sign-server', 'sign-server'),
    ('app.ico', '.'),
    ('translations', 'translations'),
    ('src/gui/assets', 'src/gui/assets'),
]

# ── Node.js 运行时（Puppeteer 必需）──
binaries = []
for np in ['C:/Program Files/nodejs/node.exe', 'C:/Program Files (x86)/nodejs/node.exe']:
    if os.path.exists(np):
        binaries.append((np, '.'))
        break

# ── 隐藏导入 ──
hiddenimports = [
    'PyQt6', 'PyQt6.sip',
    'PyQt6.QtCore', 'PyQt6.QtGui', 'PyQt6.QtWidgets',
    'PyQt6.QtNetwork', 'PyQt6.QtWebEngineWidgets',
    'PyQt6.QtWebEngineCore', 'PyQt6.QtOpenGL',
    'requests', 'certifi', 'urllib3', 'browser_cookie3',
    'src', 'src.environ', 'src.config', 'src.api', 'src.utils',
    'src.cookie', 'src.downloader', 'src.webview_api', 'src.exceptions',
    'src.gui.fonts', 'src.stylesheet',
    'src.settings', 'src.settings.schema', 'src.settings.store',
    'src.platforms', 'src.platforms.base', 'src.platforms.douyin',
    'src.gui', 'src.gui.main_window',
    'src.gui.pages', 'src.gui.pages.mode_page',
    'src.gui.pages.douyin_page', 'src.gui.pages.single_page',
    'src.gui.pages.batch_page', 'src.gui.pages.homepage_page',
    'src.gui.pages.settings_page', 'src.gui.pages.update_page',
    'src.gui.dialogs', 'src.gui.dialogs.cookie_dialog',
    'src.gui.dialogs.font_dialog', 'src.gui.dialogs.webview_login',
    'src.gui.widgets', 'src.gui.widgets.toggle_switch',
]

# certifi
from PyInstaller.utils.hooks import collect_all
tmp = collect_all('certifi')
datas += tmp[0]; binaries += tmp[1]; hiddenimports += tmp[2]

# collect-all PyQt6: 原样收集所有 PyQt6 文件（解决 CArchive 中.pyd加载失败）
for _pkg in ('PyQt6', 'PyQt6-Qt6', 'PyQt6-WebEngine', 'PyQt6-WebEngine-Qt6'):
    tmp = collect_all(_pkg)
    datas += tmp[0]; binaries += tmp[1]; hiddenimports += tmp[2]

# ── 排除 ──
excludes = [
    'numpy','pandas','matplotlib','PIL','lxml','scipy','pillow',
    'tkinter','test','unittest','pydoc','doctest','pdb',
    'PyQt6.QtBluetooth','PyQt6.QtDBus','PyQt6.QtDesigner',
    'PyQt6.QtHelp','PyQt6.QtMultimedia','PyQt6.QtMultimediaWidgets',
    'PyQt6.QtNfc','PyQt6.QtOpenGLWidgets','PyQt6.QtPdfWidgets',
    # 'PyQt6.QtPrintSupport',  # WebEngine 依赖，不能排除
    'PyQt6.QtQml','PyQt6.QtQuick','PyQt6.QtQuick3D',
    'PyQt6.QtQuickWidgets','PyQt6.QtRemoteObjects','PyQt6.QtSensors',
    'PyQt6.QtSerialPort','PyQt6.QtSql','PyQt6.QtSvg','PyQt6.QtSvgWidgets',
    'PyQt6.QtTest','PyQt6.QtTextToSpeech',
    # 'PyQt6.QtWebChannel',  # WebEngine 依赖，不能排除
    'PyQt6.QtWebEngineQuick','PyQt6.QtWebSockets','PyQt6.QtXml',
]

a = Analysis(
    ['main.py'], pathex=[], binaries=binaries, datas=datas,
    hiddenimports=hiddenimports, hookspath=[], hooksconfig={},
    runtime_hooks=[], excludes=excludes, noarchive=False, optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz, a.scripts, [], exclude_binaries=True,
    name='Origami', debug=False,
    bootloader_ignore_signals=False, strip=False,
    upx=False,
    console=False, icon=['app.ico'],
)
# ── 瘦身：去掉调试资源和不必要的 DLL ──
_binaries = []
_skip_patterns = [
    'debug.pak', 'devtools_resources.pak',
    'avcodec', 'avformat', 'avutil', 'swresample', 'swscale',  # FFmpeg（非多媒体不用）
    'opengl32sw',           # 软件 OpenGL 回退
    'Qt6Designer',          # Qt Designer（开发工具）
    'Qt6Pdf', 'Qt6PdfWidgets',  # PDF（不用）
    'Qt6Quick3D', 'Qt6QuickWidgets', 'Qt6QuickControls2',  # QML 3D
    'Qt6Svg', 'Qt6SvgWidgets',     # SVG
    'Qt6Qml', 'Qt6QmlModels', 'Qt6QmlWorkerScript', 'Qt6QmlMeta',  # QML（不用）
    'Qt6NetworkInformation', 'Qt6Nfc', 'Qt6Sensors',
    # 'libcrypto-3',       # Node.js 需要，保留
    '.map',                 # source maps
]
for _b in a.binaries:
    _name = _b[0].lower() if isinstance(_b, tuple) else ''
    if any(_p.lower() in _name.lower() for _p in _skip_patterns):
        continue
    _binaries.append(_b)

_datas = []
for _d in a.datas:
    _name = _d[0].lower() if isinstance(_d, tuple) else ''
    if any(_p.lower() in _name.lower() for _p in _skip_patterns):
        continue
    _datas.append(_d)

coll = COLLECT(
    exe, _binaries, _datas, strip=False,
    upx=False,
    name='Origami',
)
