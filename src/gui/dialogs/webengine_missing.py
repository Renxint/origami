# -*- coding: utf-8 -*-
"""
Origami — WebEngine 组件缺失处理

当 PyQt6-WebEngine DLL 缺失时，弹窗引导用户下载组件包。
"""
import sys
import hashlib
import threading
from pathlib import Path

import requests

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QProgressBar, QMessageBox,
)
from PyQt6.QtCore import Qt, pyqtSignal, QObject
from PyQt6.QtGui import QFont

from src.gui.fonts import scaled_font
from src.environ import BASE_DIR

# ── 下载配置 ────────────────────────────────────────────
WEBENGINE_DOWNLOAD_URL = (
    "https://github.com/Renxint/origami/releases/latest/download/webengine.zip"
)
WEBENGINE_SHA256_URL = WEBENGINE_DOWNLOAD_URL + ".sha256"

# 目标目录：frozen 时在 _internal/PyQt6/Qt6/bin，开发时搜 site-packages
if getattr(sys, "frozen", False):
    _WEBENGINE_DIR = BASE_DIR / "PyQt6" / "Qt6" / "bin"
else:
    import site as _site
    _WEBENGINE_DIR = None
    for _sp in _site.getsitepackages():
        _cand = Path(_sp) / "PyQt6" / "Qt6" / "bin"
        if (_cand / "Qt6WebEngineCore.dll").exists():
            _WEBENGINE_DIR = _cand
            break

# 兜底：如果找不到，用 sys.prefix + Lib/site-packages
if _WEBENGINE_DIR is None:
    _WEBENGINE_DIR = Path(sys.prefix) / "Lib" / "site-packages" / "PyQt6" / "Qt6" / "bin"

_WEBENGINE_MARKER = _WEBENGINE_DIR / "Qt6WebEngineCore.dll" if _WEBENGINE_DIR else None


def webengine_available() -> bool:
    """检查 WebEngine 组件是否存在"""
    if _WEBENGINE_MARKER is None:
        return False
    return _WEBENGINE_MARKER.exists()


class _DownloadSignals(QObject):
    progress = pyqtSignal(int)       # 百分比 0-100
    finished = pyqtSignal(bool, str)  # ok, message
    speed = pyqtSignal(str)           # 速度文本


def _verify_sha256(filepath: Path, expected: str) -> bool:
    """校验文件 SHA256"""
    if not expected:
        return True
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(8192):
            h.update(chunk)
    return h.hexdigest().lower() == expected.lower()


def _download_worker(zip_path: Path, signals: _DownloadSignals):
    """后台线程：下载 + 校验 + 解压"""
    try:
        # 1. 获取 SHA256
        expected_sha = ""
        try:
            r = requests.get(WEBENGINE_SHA256_URL, timeout=10)
            expected_sha = r.text.strip().split()[0]
        except Exception:
            pass

        # 2. 下载
        resp = requests.get(WEBENGINE_DOWNLOAD_URL, stream=True, timeout=30)
        total = int(resp.headers.get("content-length", 0))
        downloaded = 0
        with open(zip_path, "wb") as f:
            for chunk in resp.iter_content(8192):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total:
                        signals.progress.emit(int(downloaded / total * 90))
                    if downloaded > 1024 * 1024:
                        signals.speed.emit(f"{downloaded / 1024 / 1024:.1f} MB / {total / 1024 / 1024:.1f} MB")

        signals.progress.emit(92)

        # 3. 校验
        if expected_sha and not _verify_sha256(zip_path, expected_sha):
            signals.finished.emit(False, "SHA256 校验失败，文件可能损坏")
            return

        signals.progress.emit(95)

        # 4. 解压到目标目录
        import zipfile
        _WEBENGINE_DIR.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(_WEBENGINE_DIR)

        zip_path.unlink(missing_ok=True)
        signals.progress.emit(100)
        signals.finished.emit(True, "组件安装完成，请重启软件以启用扫码登录")
    except Exception as e:
        signals.finished.emit(False, f"下载失败: {e}")


def show_webengine_missing_dialog(parent=None) -> bool:
    """
    弹窗：组件缺失，引导下载。

    返回 True 表示下载成功（需重启），False 表示用户取消。
    """
    dlg = QDialog(parent)
    dlg.setWindowTitle("组件缺失")
    dlg.resize(480, 340)
    dlg.setMinimumSize(400, 300)
    dlg.setStyleSheet("QDialog { background: #0A0A14; }")

    layout = QVBoxLayout(dlg)
    layout.setContentsMargins(24, 24, 24, 20)
    layout.setSpacing(14)

    # 图标
    icon = QLabel("!")
    icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
    icon.setStyleSheet(
        "font-size: 36px; font-weight: 900; color: #F59E0B; "
        "background: #1A1030; border-radius: 32px; "
        "min-width: 64px; max-width: 64px; min-height: 64px; max-height: 64px;"
    )
    layout.addWidget(icon, alignment=Qt.AlignmentFlag.AlignCenter)

    # 标题
    title = QLabel("需要浏览器组件")
    title.setAlignment(Qt.AlignmentFlag.AlignCenter)
    title.setStyleSheet(
        f"font-size: {scaled_font(17)}px; font-weight: 700; color: #F1F5F9;"
    )
    layout.addWidget(title)

    # 描述
    desc = QLabel(
        "扫码登录功能需要大约 100MB 的浏览器组件。\n"
        "点击下载将自动获取并安装，完成后需重启软件。\n\n"
        "你也可以从 Release 页面手动下载完整版（已内置组件）。"
    )
    desc.setWordWrap(True)
    desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
    desc.setStyleSheet(f"font-size: {scaled_font(12)}px; color: #94A3B8; line-height: 1.6;")
    layout.addWidget(desc)

    # 进度条（下载时显示）
    progress = QProgressBar()
    progress.setRange(0, 100)
    progress.setValue(0)
    progress.setVisible(False)
    progress.setStyleSheet("""
        QProgressBar { background: #1E1E3E; border: 1px solid #252550; border-radius: 6px; height: 10px; text-align: center; }
        QProgressBar::chunk { background: #E11D48; border-radius: 5px; }
    """)
    layout.addWidget(progress)

    # 速度
    speed_label = QLabel("")
    speed_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    speed_label.setStyleSheet(f"font-size: {scaled_font(10)}px; color: #64748B;")
    speed_label.setVisible(False)
    layout.addWidget(speed_label)

    layout.addStretch()

    # ── 下载按钮（居中）──
    dl_btn = QPushButton("下载（推荐）")
    dl_btn.setCursor(Qt.CursorShape.PointingHandCursor)
    dl_btn.setMinimumSize(160, 40)
    dl_btn.setStyleSheet(
        "QPushButton { background: #E11D48; color: #FFF; border: none; "
        "border-radius: 8px; font-size: 14px; font-weight: 700; padding: 10px 24px; }"
        "QPushButton:hover { background: #FF3566; }"
    )
    layout.addWidget(dl_btn, alignment=Qt.AlignmentFlag.AlignCenter)

    # ── 底部按钮 ──
    bottom_row = QHBoxLayout()
    bottom_row.setSpacing(10)

    page_btn = QPushButton("打开下载页面")
    page_btn.setObjectName("secondaryBtn")
    page_btn.setCursor(Qt.CursorShape.PointingHandCursor)
    page_btn.clicked.connect(lambda: (
        __import__("webbrowser").open("https://github.com/Renxint/origami/releases")
    ))
    bottom_row.addWidget(page_btn)

    bottom_row.addStretch()

    later_btn = QPushButton("稍后")
    later_btn.setObjectName("secondaryBtn")
    later_btn.setCursor(Qt.CursorShape.PointingHandCursor)
    later_btn.clicked.connect(dlg.reject)
    bottom_row.addWidget(later_btn)

    layout.addLayout(bottom_row)

    # ── 下载逻辑 ──
    result = {"ok": False}

    def start_download():
        dl_btn.setEnabled(False)
        dl_btn.setText("下载中...")
        page_btn.setEnabled(False)
        progress.setVisible(True)
        speed_label.setVisible(True)

        import tempfile
        zip_path = Path(tempfile.gettempdir()) / "origami_webengine.zip"

        signals = _DownloadSignals()

        def on_progress(pct):
            progress.setValue(pct)
            speed_label.setText(f"已下载 {pct}%")

        def on_speed(text):
            speed_label.setText(text)

        def on_finished(ok, msg):
            progress.setVisible(False)
            speed_label.setVisible(False)
            if ok:
                result["ok"] = True
                QMessageBox.information(
                    dlg, "下载完成",
                    "浏览器组件安装完成！\n\n请重启 Origami 后即可使用扫码登录。"
                )
                dlg.accept()
            else:
                dl_btn.setEnabled(True)
                dl_btn.setText("重试")
                page_btn.setEnabled(True)
                speed_label.setText(msg)

        signals.progress.connect(on_progress)
        signals.speed.connect(on_speed)
        signals.finished.connect(on_finished)

        threading.Thread(
            target=_download_worker, args=(zip_path, signals), daemon=True
        ).start()

    dl_btn.clicked.connect(start_download)
    dlg.exec()
    return result["ok"]
