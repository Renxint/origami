# -*- coding: utf-8 -*-
"""
Origami — 更新页面（全屏遮罩 + 进度条）
"""

import sys
import os
import subprocess
import time
import zipfile
from pathlib import Path

import requests

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel,
    QPushButton, QProgressBar,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer

from src.gui.fonts import font_scale, scaled_font
from src.environ import EXE_DIR, CREATE_NO_WINDOW


class UpdateThread(QThread):
    """后台下载更新线程"""
    progress = pyqtSignal(int, int)
    status = pyqtSignal(str)
    finished = pyqtSignal(bool, str)

    def __init__(self, url: str, new_dir: Path):
        super().__init__()
        self.url = url
        self.new_dir = new_dir

    def run(self):
        import shutil
        zip_path = self.new_dir.parent / "_update_dl.zip"
        max_retry = 3
        try:
            if self.new_dir.exists():
                shutil.rmtree(self.new_dir, ignore_errors=True)
            self.new_dir.mkdir(parents=True, exist_ok=True)

            for attempt in range(1, max_retry + 1):
                try:
                    self.status.emit(f"正在下载... ({attempt}/{max_retry})")
                    r = requests.get(self.url, stream=True, timeout=600)
                    r.raise_for_status()
                    total = int(r.headers.get("content-length", 0))
                    dl = 0
                    with open(zip_path, "wb") as f:
                        for chunk in r.iter_content(8192):
                            if not chunk:
                                continue
                            f.write(chunk)
                            dl += len(chunk)
                            self.progress.emit(dl, total)
                    if not zipfile.is_zipfile(zip_path):
                        raise RuntimeError("下载文件损坏，非有效ZIP")
                    break
                except Exception as e:
                    zip_path.unlink(missing_ok=True)
                    if attempt >= max_retry:
                        raise RuntimeError(f"下载失败（已重试{max_retry}次）: {e}")
                    self.status.emit(f"下载失败，{3-attempt}秒后重试...")
                    time.sleep(3)

            self.status.emit("正在解压...")
            with zipfile.ZipFile(zip_path, "r") as z:
                for m in z.namelist():
                    parts = m.split("/", 1)
                    if len(parts) < 2:
                        continue
                    rel = parts[1]
                    if ".." in rel or rel.startswith("/"):
                        raise RuntimeError(f"ZIP包含危险路径: {rel}")
                    t = self.new_dir / rel
                    if m.endswith("/"):
                        t.mkdir(parents=True, exist_ok=True)
                    else:
                        t.parent.mkdir(parents=True, exist_ok=True)
                        with z.open(m) as src, open(t, "wb") as dst:
                            dst.write(src.read())

            zip_path.unlink(missing_ok=True)

            exe_files = list(self.new_dir.glob("*.exe"))
            if not exe_files:
                raise RuntimeError("更新包中未找到exe文件，无法完成更新")

            self.finished.emit(True, "下载完成")
        except Exception as e:
            zip_path.unlink(missing_ok=True)
            self.finished.emit(False, str(e))


class UpdatePage(QWidget):
    """全屏遮罩更新页"""
    cancel_clicked = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setStyleSheet("background: rgba(0,0,0,0.88);")
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(20)

        self.icon_label = QLabel("[...]")
        self.icon_label.setStyleSheet(f"font-size: {scaled_font(48)}px;")
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.icon_label)

        self.status_label = QLabel("准备更新...")
        self.status_label.setStyleSheet(
            f"font-size: {scaled_font(18)}px; font-weight:bold; color:#F1F5F9;"
        )
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedSize(font_scale(360), font_scale(10))
        self.progress_bar.setStyleSheet(
            "QProgressBar{background:#12122A;border:1px solid #252550;border-radius:5px;} "
            "QProgressBar::chunk{background:#FFFFFF;border-radius:4px;}"
        )
        layout.addWidget(self.progress_bar, alignment=Qt.AlignmentFlag.AlignCenter)

        self.detail_label = QLabel("")
        self.detail_label.setStyleSheet(f"font-size: {scaled_font(12)}px; color:#64748B;")
        self.detail_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.detail_label)

        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.setObjectName("secondaryBtn")
        self.cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cancel_btn.setMinimumSize(font_scale(100), font_scale(36))
        self.cancel_btn.clicked.connect(self.cancel_clicked)
        layout.addWidget(self.cancel_btn, alignment=Qt.AlignmentFlag.AlignCenter)

    def start_update(self, url: str):
        new_dir = EXE_DIR.parent / "_update"
        self.thread = UpdateThread(url, new_dir)
        self.thread.status.connect(self.status_label.setText)
        self.thread.progress.connect(self._on_progress)
        self.thread.finished.connect(self._on_finished)
        self.thread.start()
        self.cancel_btn.setEnabled(True)

    def _on_progress(self, dl: int, total: int):
        if total > 0:
            pct = dl * 100 // total
            self.progress_bar.setValue(pct)
            self.detail_label.setText(
                f"{dl/1024/1024:.1f}MB / {total/1024/1024:.1f}MB"
            )
        else:
            self.detail_label.setText(f"{dl/1024/1024:.0f}KB")

    def _on_finished(self, ok: bool, msg: str):
        if ok:
            self.status_label.setText("安装完成，即将重启...")
            self.progress_bar.setValue(100)
            self.cancel_btn.setEnabled(False)
            QTimer.singleShot(1500, self._do_restart)
        else:
            self.status_label.setText(f"更新失败: {msg}")
            self.cancel_btn.setText("返回")

    def _do_restart(self):
        from src.webview_api import stop_server
        stop_server()
        exe = Path(sys.executable)
        subprocess.Popen(
            [str(exe)], cwd=str(exe.parent),
            creationflags=CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        os._exit(0)
