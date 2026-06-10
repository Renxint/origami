"""测试关闭弹窗 — 最小可复现"""
import sys
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QDialog, QVBoxLayout,
    QLabel, QPushButton, QHBoxLayout, QCheckBox
)
from PyQt6.QtCore import QTimer, QSettings

app = QApplication(sys.argv)

class TestWin(QMainWindow):
    def closeEvent(self, event):
        print("[closeEvent] called", flush=True)

        # 模拟 Origami 的逻辑：无偏好 → 弹窗
        pref = QSettings("Origami", "Origami").value("tray_preference", None)
        print(f"[closeEvent] pref={pref}", flush=True)

        if pref is not None:
            print(f"[closeEvent] has preference, quitting", flush=True)
            app.quit()
            return

        print("[closeEvent] no preference, ignoring close + scheduling dialog", flush=True)
        event.ignore()
        QTimer.singleShot(0, self._show_dlg)

    def _show_dlg(self):
        print("[_show_dlg] called!", flush=True)
        dlg = QDialog(self)
        dlg.setWindowTitle("Test Close")
        dlg.setFixedSize(380, 130)
        layout = QVBoxLayout(dlg)
        layout.addWidget(QLabel("是否最小化到系统托盘而不是退出？"))
        bottom = QHBoxLayout()
        cb = QCheckBox("不再询问")
        bottom.addWidget(cb)
        bottom.addStretch()
        yes = QPushButton("是"); no = QPushButton("否")
        no.setObjectName("secondaryBtn")
        yes.clicked.connect(dlg.accept)
        no.clicked.connect(dlg.reject)
        bottom.addWidget(yes); bottom.addWidget(no)
        layout.addLayout(bottom)

        print("[_show_dlg] dialog shown, waiting...", flush=True)
        result = dlg.exec()
        print(f"[_show_dlg] result={result}", flush=True)

        if result == 1:  # Accepted
            print("[_show_dlg] user chose YES - would hide to tray", flush=True)
            self.hide()
        else:
            print("[_show_dlg] user chose NO - quit", flush=True)
            app.quit()

w = TestWin()
w.setWindowTitle("Close Test - Click X to test")
w.resize(400, 300)
w.show()
print("[main] window shown, click X to test", flush=True)
sys.exit(app.exec())
