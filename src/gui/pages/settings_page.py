# -*- coding: utf-8 -*-
"""
Origami — 设置页面（侧边栏 + 内容区）

借鉴 clawd-on-desk 的布局：
  左侧 200px 侧边栏 — 分类导航（带图标 + 激活态）
  右侧 内容区 — QStackedWidget 切换面板
  每个面板内用 section rows 布局（label | control 对齐）

为多平台预留：平台面板可动态添加平台配置块。
"""

import time

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFrame, QFileDialog,
    QScrollArea, QCheckBox, QApplication,
    QListWidget, QListWidgetItem, QStackedWidget,
    QSizePolicy, QSpacerItem, QComboBox,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QKeySequence
from PyQt6.QtGui import QFont

from src.gui.fonts import font_scale, scaled_font
from src.environ import OUTPUT_SINGLE, OUTPUT_BATCH
from src.config import VERSION
from src.cookie import get_cookie_status, load_cookie, save_cookie
from src.settings.store import load as load_settings, save as save_settings, set as store_set
from src.gui.dialogs.font_dialog import choose_font_dialog
from src.gui.dialogs.cookie_dialog import show_login_dialog


# ═══════════════════════════════════════════════════════════
# 样式常量（借鉴 clawd-on-desk 的 tokens）
# ═══════════════════════════════════════════════════════════
SIDEBAR_STYLE = """
    QListWidget {
        background: #0E0E1E;
        border: none;
        border-right: 1px solid #1E1E3E;
        padding: 8px 4px;
        outline: none;
    }
    QListWidget::item {
        color: #94A3B8;
        padding: 8px 12px;
        border-radius: 6px;
        margin: 1px 4px;
    }
    QListWidget::item:hover {
        background: #18183A;
        color: #E2E8F0;
    }
    QListWidget::item:selected {
        background: #E11D48;
        color: #000000;
        font-weight: bold;
    }
"""

ROW_LABEL_STYLE = "color: #94A3B8; min-width: 90px;"
ROW_VALUE_STYLE = (
    "color: #64748B; "
    "background: #0B0B1A; border: 1px solid #252550; "
    "border-radius: 6px; padding: 5px 10px;"
)
SUB_HINT_STYLE = "color: #64748B; padding: 2px 0 0 100px;"


# ═══════════════════════════════════════════════════════════
# 设置面板基类（继承 QScrollArea，暴露内部 QVBoxLayout）
# ═══════════════════════════════════════════════════════════

class SettingsPanel(QScrollArea):
    """滚动面板，.content 访问内部 VBoxLayout"""

    def __init__(self):
        super().__init__()
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        self._inner = QWidget()
        self.content = QVBoxLayout(self._inner)
        self.content.setContentsMargins(28, 20, 36, 20)
        self.content.setSpacing(6)
        self.setWidget(self._inner)

    def add_stretch(self):
        self.content.addStretch()


class SettingsPage(QWidget):
    """设置页面：侧边栏 + 面板切换"""

    back_clicked = pyqtSignal()
    font_changed = pyqtSignal(QFont)
    cookie_updated = pyqtSignal()
    shortcuts_changed = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._panels = {}        # panel_id → QWidget
        self._panel_builders = {}  # panel_id → build function
        self._build()



    # ── 主体布局 ─────────────────────────────────────────

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ── 顶栏 ──
        top = QHBoxLayout()
        top.setContentsMargins(16, 12, 16, 12)
        back = QPushButton("  < 返回")
        back.setObjectName("secondaryBtn")
        back.setCursor(Qt.CursorShape.PointingHandCursor)
        back.clicked.connect(self.back_clicked)
        back.setMinimumSize(font_scale(80), font_scale(32))
        top.addWidget(back)

        icon_lbl = QLabel()
        from src.environ import BASE_DIR
        ico_path = BASE_DIR / "app.ico"
        if ico_path.exists():
            from PyQt6.QtGui import QIcon
            icon = QIcon(str(ico_path))
            for sz in (256, 128, 72, 48, 32):
                pix = icon.pixmap(sz, sz)
                if not pix.isNull():
                    icon_lbl.setPixmap(pix.scaled(28, 28, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
                    break
            icon_lbl.setFixedSize(36, 36)
        else:
            icon_lbl = QLabel("O")
            icon_lbl.setStyleSheet(
                f"font-size: {scaled_font(22)}px; font-weight:800; color:#FFFFFF; "
                "background:#1A1A1A; border-radius:8px; "
                "min-width:36px; max-width:36px; min-height:36px; max-height:36px;"
            )
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        top.addWidget(icon_lbl)

        title = QLabel("设置")
        title.setStyleSheet(f"font-size: {scaled_font(18)}px; font-weight:bold; color:#FFFFFF;")
        top.addWidget(title)
        top.addStretch()
        outer.addLayout(top)

        # ── 分隔线 ──
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("background: #1E1E3E; max-height: 1px; border: none;")
        outer.addWidget(sep)

        # ── 主体：侧边栏 + 内容区 ──
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)

        # 侧边栏
        self.sidebar = QListWidget()
        self.sidebar.setFixedWidth(font_scale(190))
        self.sidebar.setStyleSheet(SIDEBAR_STYLE)
        self.sidebar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.sidebar.currentRowChanged.connect(self._on_sidebar_changed)
        body.addWidget(self.sidebar)

        # 分隔
        vsep = QFrame()
        vsep.setFrameShape(QFrame.Shape.VLine)
        vsep.setStyleSheet("background: #1E1E3E; max-width: 1px; border: none;")
        body.addWidget(vsep)

        # 内容区
        self.content = QStackedWidget()
        self.content.setStyleSheet("background: #0A0A14;")
        body.addWidget(self.content, 1)

        outer.addLayout(body, 1)

        # ── 构建面板 ──
        self._register_panels()
        self.sidebar.setCurrentRow(0)

    # ── 面板注册 ─────────────────────────────────────────

    def _register_panels(self):
        """注册所有设置面板（新增面板只需加一行）"""
        self._add_sidebar_item("  通用", "Aa")
        self._add_panel("general", self._build_general_panel)

        self._add_sidebar_item("  下载", "[v]")
        self._add_panel("download", self._build_download_panel)

        self._add_sidebar_item("  平台", "[>]")
        self._add_panel("platforms", self._build_platforms_panel)

        self._add_sidebar_item("  快捷键", "[K]")
        self._add_panel("shortcuts", self._build_shortcuts_panel)

        self._add_sidebar_item("  关于", "[i]")
        self._add_panel("about", self._build_about_panel)

    def _add_sidebar_item(self, text: str, icon: str):
        """添加侧边栏项"""
        from PyQt6.QtCore import QMargins
        item = QListWidgetItem(f"{icon}  {text}")
        sh = item.sizeHint()
        item.setSizeHint(sh.grownBy(QMargins(0, 2, 0, 2)))
        self.sidebar.addItem(item)

    def _add_panel(self, panel_id: str, builder):
        """注册面板构建函数（延迟构建，首次切换时才创建）"""
        self._panel_builders[panel_id] = builder
        self._panels[panel_id] = None  # 占位

    def _on_sidebar_changed(self, index: int):
        """侧边栏切换 → 懒加载对应面板"""
        if index < 0:
            return
        panel_ids = list(self._panel_builders.keys())
        if index >= len(panel_ids):
            return
        pid = panel_ids[index]

        # 懒构建：首次切换到该面板时才创建
        if self._panels[pid] is None:
            try:
                panel = self._panel_builders[pid]()
                self._panels[pid] = panel
                self.content.addWidget(panel)
            except Exception:
                import traceback
                traceback.print_exc()
                return

        self.content.setCurrentWidget(self._panels[pid])

    # ═══════════════════════════════════════════════════════
    # 面板：通用（借鉴 clawd-on-desk General tab 的 section + row 布局）
    # ═══════════════════════════════════════════════════════

    def _build_general_panel(self) -> QWidget:
        panel = self._wrap_panel()

        # ── 外观 ──
        self._section_title(panel, "外观")
        self._font_row(panel)
        self._auto_raise_row(panel)
        self._high_speed_row(panel)
        self._tray_row(panel)

        panel.add_stretch()
        return panel

    def _font_row(self, panel: SettingsPanel):
        """字体：滑块调大小 + 按钮选字体"""
        saved = load_settings()
        cf = QFont(saved.get("font_family", ""))
        if saved.get("font_size"):
            cf.setPointSize(saved["font_size"])
        else:
            cf = self.font()

        # 标签
        lb = QLabel("字体")
        lb.setStyleSheet(ROW_LABEL_STYLE)
        lb.setFixedWidth(font_scale(60))
        panel.content.addWidget(lb)

        # 当前字体预览
        self.font_value_label = QLabel(f"{cf.family()}  {cf.pointSize()}pt")
        self.font_value_label.setStyleSheet(ROW_VALUE_STYLE)
        self.font_value_label.setWordWrap(True)
        panel.content.addWidget(self.font_value_label)

        # 字号滑块
        from PyQt6.QtWidgets import QSlider
        slider_row = QHBoxLayout()
        slider_row.setSpacing(10)

        size_hint = QLabel("字号")
        size_hint.setStyleSheet(f"color: #64748B; font-size: {scaled_font(11)}px; min-width: 30px;")
        slider_row.addWidget(size_hint)

        self.font_slider = QSlider(Qt.Orientation.Horizontal)
        self.font_slider.setRange(8, 24)
        self.font_slider.setValue(cf.pointSize())
        self.font_slider.setCursor(Qt.CursorShape.PointingHandCursor)
        self.font_slider.setStyleSheet(f"""
            QSlider::groove:horizontal {{
                background: #1E1E3A; height: 6px; border-radius: 3px;
            }}
            QSlider::handle:horizontal {{
                background: #E11D48; width: 16px; height: 16px;
                margin: -5px 0; border-radius: 8px;
            }}
            QSlider::handle:horizontal:hover {{ background: #FF3566; }}
            QSlider::sub-page:horizontal {{
                background: #E11D48; height: 6px; border-radius: 3px;
            }}
        """)
        self.font_slider.valueChanged.connect(self._on_slider_changed)
        slider_row.addWidget(self.font_slider, 1)

        self.font_size_label = QLabel(f"{cf.pointSize()}pt")
        self.font_size_label.setStyleSheet(
            "color: #F1F5F9; font-size: {scaled_font(13)}px; font-weight: bold; min-width: 32px;"
        )
        self.font_size_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        slider_row.addWidget(self.font_size_label)

        panel.content.addLayout(slider_row)

        # 字体选择按钮
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn = QPushButton("选择字体")
        btn.setObjectName("secondaryBtn")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(self._choose_font)
        btn_row.addWidget(btn)
        panel.content.addLayout(btn_row)

    def _on_slider_changed(self, value: int):
        """字号滑块实时生效"""
        self.font_size_label.setText(f"{value}pt")
        # 更新预览
        saved = load_settings()
        family = saved.get("font_family", "")
        if not family:
            family = self.font().family()
        self.font_value_label.setText(f"{family}  {value}pt")
        # 延迟保存 + 应用（拖动时防抖）
        if hasattr(self, "_slider_timer") and self._slider_timer:
            self._slider_timer.stop()
        from PyQt6.QtCore import QTimer
        self._slider_timer = QTimer()
        self._slider_timer.setSingleShot(True)
        self._slider_timer.timeout.connect(lambda: self._apply_font_size(value))
        self._slider_timer.start(300)

    def _apply_font_size(self, size: int):
        """应用字号到全局"""
        saved = load_settings()
        family = saved.get("font_family", "") or self.font().family()
        store_set("font_family", family)
        store_set("font_size", size)
        font = QFont(family, size)
        self.font_changed.emit(font)

    def _auto_raise_row(self, panel: SettingsPanel):
        """剪贴板检测开关"""
        self._switch_row(panel, "自动识别剪贴板链接",
            "复制抖音链接时自动填入并跳转到对应页面",
            load_settings().get("auto_raise", True),
            self._on_auto_raise_toggled)

    def _on_auto_raise_toggled(self, enabled: bool):
        from src.settings.store import set as store_set
        store_set("auto_raise", enabled)

    def _high_speed_row(self, panel: SettingsPanel):
        """高速模式开关"""
        self._switch_row(panel, "高速模式 ⚡",
            "提高加载并发数，速度更快但有一定风控风险",
            load_settings().get("high_speed", False),
            self._on_high_speed_toggled)

    def _on_high_speed_toggled(self, enabled: bool):
        from src.settings.store import set as store_set
        store_set("high_speed", enabled)
        if enabled:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(
                self, "高速模式",
                "已开启高速模式，加载速度更快。\n\n"
                "⚠ 注意：高并发请求可能触发平台风控，\n"
                "建议仅在使用频率较低时开启。")

    def _tray_row(self, panel: SettingsPanel):
        """系统托盘开关（clawd-on-desk switch row）"""
        saved = load_settings()
        pref = load_settings().get("close_preference", "")
        desc = "关闭窗口时最小化到托盘，双击托盘图标恢复"
        if pref == "tray":
            desc += " (已记住：保留到托盘)"
        elif pref == "quit":
            desc += " (已记住：直接退出)"

        self._switch_row(panel, "系统托盘",
            desc,
            load_settings().get("tray_enabled", False),
            self._on_tray_toggled)

    def _on_tray_toggled(self, enabled: bool):
        from src.settings.store import set as store_set
        store_set("tray_enabled", enabled)
        # 立即生效：通知 MainWindow 创建/销毁托盘
        w = self.window()
        if hasattr(w, '_setup_tray'):
            w._setup_tray()

    # ── 通用行组件 ──

    def _info_row(self, panel: SettingsPanel, label: str, value: str,
                  btn_text: str = "", callback=None):
        """label | value | button 行"""
        row = QHBoxLayout()
        row.setSpacing(12)
        lb = QLabel(label)
        lb.setStyleSheet(ROW_LABEL_STYLE)
        lb.setFixedWidth(font_scale(60))
        row.addWidget(lb)

        val = QLabel(value)
        val.setStyleSheet(ROW_VALUE_STYLE)
        val.setWordWrap(True)
        row.addWidget(val, 1)

        if btn_text and callback:
            btn = QPushButton(btn_text)
            btn.setObjectName("secondaryBtn")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFixedWidth(font_scale(64))
            btn.clicked.connect(callback)
            row.addWidget(btn)

        panel.content.addLayout(row)

    def _switch_row(self, panel: SettingsPanel, label: str, desc: str,
                    checked: bool, callback):
        """label + desc | switch 行（clawd-on-desk 核心模式）"""
        row = QHBoxLayout()
        row.setSpacing(12)

        # 左侧文字
        text_wrap = QVBoxLayout()
        text_wrap.setSpacing(2)
        lb = QLabel(label)
        lb.setStyleSheet(f"color: #E2E8F0; font-size: {scaled_font(12)}px; font-weight: 500;")
        text_wrap.addWidget(lb)
        ds = QLabel(desc)
        ds.setStyleSheet(f"color: #64748B; font-size: {scaled_font(10)}px;")
        ds.setWordWrap(True)
        text_wrap.addWidget(ds)
        row.addLayout(text_wrap, 1)

        # 右侧开关
        cb = QCheckBox()
        cb.setChecked(checked)
        cb.setCursor(Qt.CursorShape.PointingHandCursor)
        cb.stateChanged.connect(
            lambda s: callback(s == Qt.CheckState.Checked.value)
        )
        cb.setStyleSheet("""
            QCheckBox::indicator {
                width: 40px; height: 22px; border-radius: 11px;
                border: 2px solid #334155;
                background-color: #1E1E3A;
            }
            QCheckBox::indicator:checked {
                background-color: #E11D48; border-color: #E11D48;
            }
        """)
        row.addWidget(cb)

        panel.content.addLayout(row)
        panel.content.addSpacing(4)

    # ═══════════════════════════════════════════════════════
    # 面板：下载
    # ═══════════════════════════════════════════════════════

    def _build_download_panel(self) -> QWidget:
        panel = self._wrap_panel()

        self._section_title(panel, "保存路径")
        saved = load_settings()
        for label, key, default_path in [
            ("单视频", "single", str(OUTPUT_SINGLE)),
            ("主页下载", "homepage", str(OUTPUT_BATCH)),
        ]:
            row = QHBoxLayout()
            row.setSpacing(12)
            lb = QLabel(label)
            lb.setStyleSheet(ROW_LABEL_STYLE)
            row.addWidget(lb)

            current_path = saved.get("download_paths", {}).get(key, "")
            pl = QLabel(current_path or "(默认目录)")
            pl.setStyleSheet(ROW_VALUE_STYLE)
            pl.setWordWrap(True)
            row.addWidget(pl, 1)

            btn = QPushButton("更改")
            btn.setObjectName("secondaryBtn")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFixedWidth(font_scale(64))
            btn.clicked.connect(lambda checked, k=key, lbl=pl: self._change_path(k, lbl))
            row.addWidget(btn)

            rst = QPushButton("重置")
            rst.setObjectName("ghostBtn")
            rst.setCursor(Qt.CursorShape.PointingHandCursor)
            rst.setFixedWidth(font_scale(56))
            rst.clicked.connect(lambda checked, k=key, lbl=pl, dp=default_path:
                                self._reset_path(k, lbl, dp))
            row.addWidget(rst)

            panel.content.addLayout(row)

        panel.add_stretch()
        return panel

    # ═══════════════════════════════════════════════════════
    # 面板：平台（Cookie + 各平台接入）
    def _build_platforms_panel(self) -> QWidget:
        panel = self._wrap_panel()

        self._section_title(panel, "登录状态")
        self._cookie_row(panel)

        self._section_title(panel, "已接入平台")
        self._platform_card(panel, "douyin.png", "抖音", True)
        self._platform_card(panel, "bilibili.png", "B站", False)

        panel.add_stretch()
        return panel

    def _cookie_row(self, panel):
        self.cookie_status_label = QLabel()
        self.cookie_status_label.setStyleSheet(f"font-size: {scaled_font(12)}px; padding: 4px 0;")
        panel.content.addWidget(self.cookie_status_label)

        self.cookie_time_label = QLabel()
        self.cookie_time_label.setStyleSheet(f"color: #64748B; font-size: {scaled_font(10)}px; padding: 2px 0;")
        panel.content.addWidget(self.cookie_time_label)

        row = QHBoxLayout()
        row.setSpacing(8)
        self._login_btn = QPushButton("登录")
        self._login_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._login_btn.setMinimumHeight(font_scale(34))
        self._login_btn.clicked.connect(self._on_login_btn_clicked)
        row.addWidget(self._login_btn)
        row.addStretch()
        panel.content.addLayout(row)

        self.refresh_cookie_status()

    def _platform_card(self, panel, svg_file: str, name: str, active: bool):
        from PyQt6.QtGui import QPixmap
        from pathlib import Path

        icons_dir = Path(__file__).resolve().parent.parent / "assets" / "icons"
        icon_path = icons_dir / svg_file

        row = QHBoxLayout()
        row.setSpacing(12)
        row.setContentsMargins(0, 6, 0, 6)

        icon_sz = font_scale(36)
        icon_label = QLabel()
        icon_label.setFixedSize(icon_sz, icon_sz)
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if icon_path.exists():
            pix = QPixmap(str(icon_path)).scaled(icon_sz, icon_sz, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            icon_label.setPixmap(pix)
        else:
            icon_label.setText(name[0])
            icon_label.setStyleSheet(
                f"font-size: {scaled_font(16)}px; font-weight: 800; "
                f"color: #E11D48; background: #1A1030; border-radius: 8px;"
            )
        row.addWidget(icon_label)

        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        tl = QLabel(name)
        tl.setStyleSheet(f"color: #E2E8F0; font-size: {scaled_font(13)}px; font-weight: 500;")
        text_col.addWidget(tl)

        if active:
            badge = QLabel("已接入")
            badge.setStyleSheet(f"color: #22C55E; font-size: {scaled_font(10)}px;")
        else:
            badge = QLabel("即将支持")
            badge.setStyleSheet(f"color: #475569; font-size: {scaled_font(10)}px;")
        text_col.addWidget(badge)
        row.addLayout(text_col, 1)

        panel.content.addLayout(row)

    # ═══════════════════════════════════════════════════════
    # 面板：主题（对标 BairesDev AI Colors 卡片网格）
    # ═══════════════════════════════════════════════════════

    def _build_shortcuts_panel(self) -> QWidget:
        panel = self._wrap_panel()

        # ── Header：标题 + 重置全部按钮 ──
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 8)
        title = QLabel("快捷键")
        title.setStyleSheet(
            f"font-size: {scaled_font(15)}px; font-weight: 700; color: #F1F5F9;"
        )
        header.addWidget(title)
        header.addStretch()
        reset_all = QPushButton("重置全部")
        reset_all.setObjectName("secondaryBtn")
        reset_all.setCursor(Qt.CursorShape.PointingHandCursor)
        reset_all.clicked.connect(self._reset_all_settings)
        header.addWidget(reset_all)
        panel.content.addLayout(header)

        subtitle = QLabel("点击输入框直接录制新快捷键，即时生效无需重启")
        subtitle.setStyleSheet(
            f"color: #94A3B8; font-size: {scaled_font(12)}px; padding-bottom: 8px;"
        )
        subtitle.setWordWrap(True)
        panel.content.addWidget(subtitle)

        # ── 自定义快捷键行 ──
        shortcuts = [
            ("home",        "回到首页",    "Ctrl+H",  "从任意页面导航回主页"),
            ("settings",    "打开设置",    "Ctrl+,",  "打开设置面板"),
            ("quit",        "退出程序",    "Ctrl+Q",  "完全退出 Origami"),
            ("toggle_tray", "托盘最小化",  "Esc",     "最小化到系统托盘"),
        ]
        cfg = load_settings().get("shortcuts", {})
        for cfg_key, label, default_key, desc in shortcuts:
            self._shortcut_row(panel, cfg, cfg_key, label, default_key, desc)

        panel.add_stretch()
        hint = QLabel("点击输入框 → 按下组合键 → 即时生效，无需重启")
        hint.setStyleSheet(f"color: #64748B; font-size: {scaled_font(10)}px; padding-top: 6px;")
        panel.content.addWidget(hint)
        return panel

    def _shortcut_row(self, panel: SettingsPanel, cfg: dict,
                      cfg_key: str, label: str, default_key: str, desc: str = ""):
        """自定义快捷键行：row-text | row-control"""
        row = QHBoxLayout()
        row.setContentsMargins(0, 4, 0, 4)
        row.setSpacing(20)

        # ── 左侧 row-text：名称 + 描述 ──
        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        lb = QLabel(label)
        lb.setStyleSheet(
            f"color: #E2E8F0; font-size: {scaled_font(13)}px; font-weight: 500;"
        )
        text_col.addWidget(lb)
        if desc:
            ds = QLabel(desc)
            ds.setStyleSheet(
                f"color: #64748B; font-size: {scaled_font(10)}px;"
            )
            text_col.addWidget(ds)
        row.addLayout(text_col)
        row.addStretch()

        # ── 右侧 row-control：快捷键 + 按钮组 ──
        ctrl = QHBoxLayout()
        ctrl.setSpacing(8)

        # 快捷键输入（QKeySequenceEdit 天然支持录制）
        from PyQt6.QtWidgets import QKeySequenceEdit
        kbd = QKeySequenceEdit()
        kbd.setKeySequence(QKeySequence(cfg.get(cfg_key, "")))
        kbd.setStyleSheet(
            f"color: #E2E8F0; font-size: {scaled_font(13)}px; "
            "background: #18183A; border: 1px solid #334155; "
            "border-radius: 6px; padding: 5px 10px; "
            "font-family: Consolas, monospace; min-width: 80px;"
        )
        kbd.setMaximumWidth(font_scale(120))
        kbd.editingFinished.connect(
            lambda k=cfg_key, kb=kbd: self._save_shortcut(k, kb))
        ctrl.addWidget(kbd)

        # 清除 / 重置
        for btn_text, tooltip in [
            ("清除", "删除当前快捷键绑定"),
            ("重置", "恢复为默认快捷键"),
        ]:
            btn = QPushButton(btn_text)
            btn.setObjectName("secondaryBtn")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setToolTip(tooltip)
            if btn_text == "清除":
                btn.clicked.connect(lambda checked, k=cfg_key, kb=kbd: self._clear_shortcut(k, kb))
            else:
                btn.clicked.connect(lambda checked, k=cfg_key, kb=kbd: self._reset_shortcut(k, kb))
            ctrl.addWidget(btn)

        row.addLayout(ctrl)
        panel.content.addLayout(row)
        # 分隔线
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("background: #1E1E3E; max-height: 1px; border: none;")
        panel.content.addWidget(sep)

    def _reset_all_settings(self):
        from PyQt6.QtWidgets import QMessageBox
        r = QMessageBox.warning(self, "重置全部设置",
            "确定要重置所有设置为默认值吗？\n此操作不可撤销。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if r == QMessageBox.StandardButton.Yes:
            from src.settings.store import save
            from src.settings.schema import get_defaults
            save(get_defaults())
            QMessageBox.information(self, "完成", "已恢复默认设置，重启后生效。")

    # 常见系统快捷键（避免冲突提示）
    _SYSTEM_KEYS = {
        "Ctrl+C", "Ctrl+V", "Ctrl+X", "Ctrl+Z",
        "Alt+F4", "Alt+Tab", "Ctrl+Alt+Del",
    }

    def _save_shortcut(self, key: str, kbd):
        combo = kbd.keySequence().toString()
        if combo and combo in self._SYSTEM_KEYS:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "快捷键冲突",
                f"{combo} 是系统常用快捷键，可能会被拦截不生效。\n建议使用其他组合键。")
        cfg = load_settings().get("shortcuts", {})
        if combo:
            cfg[key] = combo
        else:
            cfg.pop(key, None)
        from src.settings.store import set as sset
        sset("shortcuts", cfg)
        self.shortcuts_changed.emit()

    def _clear_shortcut(self, key: str, kbd):
        cfg = load_settings().get("shortcuts", {})
        cfg.pop(key, None)
        from src.settings.store import set as sset
        sset("shortcuts", cfg)
        kbd.clear()
        self.shortcuts_changed.emit()

    def _reset_shortcut(self, key: str, kbd):
        from src.settings.schema import get_defaults
        default = get_defaults()["shortcuts"].get(key, "")
        cfg = load_settings().get("shortcuts", {})
        cfg[key] = default
        from src.settings.store import set as sset
        sset("shortcuts", cfg)
        kbd.setKeySequence(QKeySequence(default))
        self.shortcuts_changed.emit()

    def _fixed_key_row(self, panel: SettingsPanel, label: str, key: str):
        """系统固定快捷键行（灰色不可自定义）"""
        row = QHBoxLayout()
        row.setContentsMargins(0, 2, 0, 2)
        row.setSpacing(20)

        lb = QLabel(label)
        lb.setStyleSheet(
            f"color: #64748B; font-size: {scaled_font(12)}px;"
        )
        row.addWidget(lb)
        row.addStretch()

        kbd = QLabel(key)
        kbd.setStyleSheet(
            f"color: #64748B; font-size: {scaled_font(11)}px; "
            "background: #0E0E1E; border: 1px solid #1E1E3E; "
            "border-radius: 4px; padding: 3px 10px; "
            "font-family: Consolas, monospace;"
        )
        kbd.setAlignment(Qt.AlignmentFlag.AlignCenter)
        row.addWidget(kbd)
        panel.content.addLayout(row)

    # ═══════════════════════════════════════════════════════
    # 面板：关于（借鉴 clawd-on-desk 的 hero + info rows 布局）
    # ═══════════════════════════════════════════════════════

    def _build_about_panel(self) -> QWidget:
        panel = self._wrap_panel()

        # ── Hero ──
        hero = QVBoxLayout()
        hero.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hero.setSpacing(8)

        # 图标 + 名称同行居中
        name_row = QHBoxLayout()
        name_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name_row.setSpacing(12)

        self._about_clicks = 0
        from src.environ import BASE_DIR
        ico_path = BASE_DIR / "app.ico"
        if ico_path.exists():
            from PyQt6.QtGui import QIcon
            logo = QLabel()
            icon = QIcon(str(ico_path))
            for sz in (256, 128, 72, 48, 32):
                pix = icon.pixmap(sz, sz)
                if not pix.isNull():
                    logo.setPixmap(pix.scaled(48, 48, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
                    break
            logo.setFixedSize(48, 48)
        else:
            logo = QLabel("O")
            logo.setStyleSheet(
                f"font-size: {scaled_font(36)}px; font-weight: 800; color: #E11D48; "
                "background: #1A1030; border-radius: 24px; "
                "min-width: 48px; max-width: 48px; min-height: 48px; max-height: 48px;"
            )
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo.setCursor(Qt.CursorShape.PointingHandCursor)
        logo.mousePressEvent = lambda e: self._on_logo_click()
        name_row.addWidget(logo)

        title = QLabel("Origami")
        title.setStyleSheet(f"font-size: {scaled_font(26)}px; font-weight: 700; color: #F1F5F9;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name_row.addWidget(title)

        hero.addLayout(name_row)

        tagline = QLabel("多功能内容下载工具")
        tagline.setStyleSheet(f"font-size: {scaled_font(13)}px; color: #94A3B8;")
        tagline.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tagline.setWordWrap(True)
        hero.addWidget(tagline)

        hero.addSpacing(4)
        panel.content.addLayout(hero)

        # 分隔线
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("background: #252550; max-height: 1px; border: none; margin: 0 0 8px 0;")
        panel.content.addWidget(sep)

        # ── Info Rows（label | value 对齐 + 底部分隔线） ──

        # 版本号
        self._about_info_row(panel, "版本", f"v{VERSION}")
        # 更新按钮
        update_row = QHBoxLayout()
        update_row.setContentsMargins(0, 4, 0, 4)
        update_row.addStretch()
        update_btn = QPushButton("检查更新")
        update_btn.setObjectName("secondaryBtn")
        update_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        update_btn.clicked.connect(self._check_update_from_about)
        update_row.addWidget(update_btn)
        panel.content.addLayout(update_row)

        # 仓库
        self._about_link_row(panel, "仓库", "github.com/Renxint/origami",
                             "https://github.com/Renxint/origami")
        self._about_link_row(panel, "镜像", "gitee.com/Renxint/origami",
                             "https://gitee.com/Renxint/origami")
        # 反馈
        self._about_link_row(panel, "反馈", "GitHub Issues",
                             "https://github.com/Renxint/origami/issues")
        # 作者
        self._about_info_row(panel, "作者", "Renxint")
        # 许可
        self._about_info_row(panel, "许可", "MIT License")

        # 免责声明
        panel.content.addSpacing(8)
        disclaimer = QLabel(
            "本工具仅供个人学习、研究、欣赏用途。\n"
            "用户应遵守相关法律法规及平台服务协议，\n"
            "不得将本工具用于任何违法或侵权活动。\n"
            "使用者自行承担所有责任。"
        )
        disclaimer.setStyleSheet(
            f"color: #EF4444; font-size: {scaled_font(10)}px; "
            "background: #1A1010; border: 1px solid #3B1111; "
            "border-radius: 8px; padding: 12px;"
        )
        disclaimer.setWordWrap(True)
        panel.content.addWidget(disclaimer)

        panel.content.addSpacing(4)

        # ── 技术栈 ──
        self._section_title(panel, "技术栈")

        tech_text = QLabel("Python 3.12  ·  PyQt6  ·  Node.js\n"
                           "requests  ·  Puppeteer")
        tech_text.setStyleSheet(f"color: #64748B; font-size: {scaled_font(11)}px; line-height: 1.6;")
        panel.content.addWidget(tech_text)
        panel.content.addSpacing(4)

        # ── 隐私声明 ──
        privacy = QLabel("完全本地运行，数据不上传至任何服务器")
        privacy.setStyleSheet(f"color: #475569; font-size: {scaled_font(10)}px;")
        privacy.setAlignment(Qt.AlignmentFlag.AlignCenter)
        privacy.setWordWrap(True)
        panel.content.addWidget(privacy)

        panel.add_stretch()

        # ── Footer ──
        footer_sep = QFrame()
        footer_sep.setFrameShape(QFrame.Shape.HLine)
        footer_sep.setStyleSheet("background: #252550; max-height: 1px; border: none; margin: 8px 0 12px 0;")
        panel.content.addWidget(footer_sep)

        footer = QLabel("Origami · 折纸")
        footer.setStyleSheet(f"color: #475569; font-size: {scaled_font(10)}px;")
        footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        panel.content.addWidget(footer)

        copyright_lbl = QLabel("(c) 2026 Renxint")
        copyright_lbl.setStyleSheet(f"color: #334155; font-size: {scaled_font(10)}px;")
        copyright_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        panel.content.addWidget(copyright_lbl)

        return panel

    def _about_info_row(self, panel: SettingsPanel, label: str, value: str):
        """创建 label | value 信息行（clawd-on-desk 风格）"""
        row = QHBoxLayout()
        row.setSpacing(16)
        lb = QLabel(label)
        lb.setStyleSheet(f"color: #94A3B8; font-size: {scaled_font(12)}px;")
        lb.setFixedWidth(font_scale(50))
        row.addWidget(lb)
        val = QLabel(value)
        val.setStyleSheet(f"color: #F1F5F9; font-size: {scaled_font(12)}px;")
        val.setAlignment(Qt.AlignmentFlag.AlignRight)
        row.addWidget(val, 1)
        panel.content.addLayout(row)

    def _about_link_row(self, panel: SettingsPanel, label: str,
                        text: str, url: str):
        """创建可点击链接行"""
        row = QHBoxLayout()
        row.setSpacing(16)
        lb = QLabel(label)
        lb.setStyleSheet(f"color: #94A3B8; font-size: {scaled_font(12)}px;")
        lb.setFixedWidth(font_scale(50))
        row.addWidget(lb)
        link = QLabel(f"<a href='{url}' style='color:#FFFFFF; text-decoration:none;'>"
                      f"{text}</a>")
        link.setOpenExternalLinks(True)
        link.setStyleSheet(f"font-size: {scaled_font(12)}px;")
        link.setAlignment(Qt.AlignmentFlag.AlignRight)
        row.addWidget(link, 1)
        panel.content.addLayout(row)

    def _on_logo_click(self):
        """Logo 点击彩蛋：7次弹 toast"""
        self._about_clicks += 1
        if self._about_clicks >= 7:
            self._about_clicks = 0
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.information(
                self, "",
                "你就是想看看点了会怎样对不对？"
            )

    def _check_update_from_about(self):
        """从关于页检查更新"""
        w = self.window()
        if hasattr(w, "_check_version"):
            w._check_version()

    # ═══════════════════════════════════════════════════════
    # 工具方法
    # ═══════════════════════════════════════════════════════

    def _wrap_panel(self) -> SettingsPanel:
        """创建设置面板"""
        return SettingsPanel()

    def _section_title(self, panel: SettingsPanel, text: str):
        """添加段落标题（clawd-on-desk 风格：小号大写低对比度）"""
        s = scaled_font(10)
        lb = QLabel(text)
        lb.setStyleSheet(
            f"font-size: {s}px; font-weight: 700; color: #64748B; "
            "text-transform: uppercase; letter-spacing: 1px; "
            "padding: 16px 0 6px 0;"
        )
        panel.content.addWidget(lb)

    # ── Cookie 状态 ──

    def refresh_cookie_status(self):
        """刷新状态显示 + 按钮文字"""
        if not hasattr(self, "cookie_status_label") or not hasattr(self, "cookie_time_label"):
            return
        cs = get_cookie_status()
        if cs["ok"]:
            dot, txt = "#22C55E", "已登录"
            btn_text = "退出登录"
        elif cs["length"] > 0:
            dot, txt = "#F59E0B", "登录可能已过期"
            btn_text = "重新登录"
        else:
            dot, txt = "#EF4444", "未登录"
            btn_text = "登录"

        # 更新按钮
        if hasattr(self, "_login_btn"):
            self._login_btn.setText(btn_text)

        pt = QApplication.instance().font().pointSize()
        self.cookie_status_label.setText(
            f'<span style="color:{dot};font-size:{pt+2}pt;">●</span> '
            f'<span style="color:#F1F5F9;font-size:{pt}pt;">{txt}</span> '
            f'<span style="color:#64748B;font-size:{pt}pt;">({cs["length"]}字符)</span>'
        )
        if cs["mtime"]:
            ts = time.strftime("%Y-%m-%d %H:%M", time.localtime(cs["mtime"]))
            age = (time.time() - cs["mtime"]) / 86400
            hint = " (可能已过期)" if age > 7 else ""
            self.cookie_time_label.setText(f"最后更新: {ts}{hint}")
        else:
            self.cookie_time_label.setText("尚未设置 Cookie")

    # ── 事件 ──

    def _choose_font(self):
        saved = load_settings()
        cf = QFont(saved.get("font_family", ""))
        if saved.get("font_size"):
            cf.setPointSize(saved["font_size"])
        else:
            cf = self.font()
        accepted, font = choose_font_dialog(self, cf)
        if accepted:
            store_set("font_family", font.family())
            store_set("font_size", font.pointSize())
            if hasattr(self, "font_value_label") and self.font_value_label:
                self.font_value_label.setText(f"{font.family()}  {font.pointSize()}pt")
            self.font_changed.emit(font)

    def _change_path(self, key: str, label: QLabel):
        current = load_settings().get("download_paths", {}).get(key, "")
        folder = QFileDialog.getExistingDirectory(self, f"选择保存目录", current)
        if folder:
            settings = load_settings()
            paths = settings.get("download_paths", {})
            paths[key] = folder
            settings["download_paths"] = paths
            save_settings(settings)
            label.setText(folder)

    def _reset_path(self, key: str, label: QLabel, default_path: str):
        """恢复默认路径"""
        settings = load_settings()
        paths = settings.get("download_paths", {})
        paths.pop(key, None)
        settings["download_paths"] = paths
        save_settings(settings)
        label.setText("(默认目录)")

    def _on_login_btn_clicked(self):
        """登录/退出/重新登录"""
        cs = get_cookie_status()
        if cs["ok"]:
            # 退出登录
            from PyQt6.QtWidgets import QMessageBox
            reply = QMessageBox.question(
                self, "退出登录",
                "确定清除登录信息？清除后需重新登录才能下载。",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes:
                save_cookie("")
                self.refresh_cookie_status()
                self.cookie_updated.emit()
        else:
            # 登录 / 重新登录
            show_login_dialog(self)
            self.refresh_cookie_status()
            self.cookie_updated.emit()

    def _set_cookie(self):
        show_login_dialog(self)
        self.refresh_cookie_status()
        self.cookie_updated.emit()

    def _clear_cookie(self):
        from PyQt6.QtWidgets import QMessageBox
        reply = QMessageBox.question(
            self, "清除 Cookie",
            "确定清除已保存的 Cookie？\n清除后需重新获取才能下载。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            save_cookie("")
            self.refresh_cookie_status()
            self.cookie_updated.emit()
