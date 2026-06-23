# Origami 主题系统设计文档

> **状态**: 设计完成，待实现
> **日期**: 2026-06-11
> **目标**: 将硬编码暗色主题替换为可切换、可导出/导入的多主题系统

---

## 1. 技术可行性

PyQt6 QSS 是 CSS 2.1 的子集，本设计所有视觉效果仅使用 QSS 支持的属性：

| 使用的属性 | QSS 支持 | 备注 |
|-----------|---------|------|
| `background-color` | 完整 | 所有卡片/按钮/窗口背景 |
| `color` | 完整 | 文字颜色 |
| `border` + `border-color` | 完整 | 卡片边框、输入框边框 |
| `border-radius` | 完整 | 圆角卡片/按钮 |
| `padding` | 完整 | 内边距 |
| `font-size` / `font-weight` | 完整 | 字体设置 |

**不使用**的 CSS3 属性（QSS 不支持）：`box-shadow`、`backdrop-filter`、`gradient`、`transition`、`animation`。

所有 7 套预设主题均在此约束内设计，**可以完整实现**。

---

## 2. 架构概览

```
┌────────────────────────────────────────────────────┐
│  第4层 · 主题文件                                   │
│  themes/*.json — 每个文件一套配色                    │
│  { "name": "薄荷清新", "colors": {...} }            │
├────────────────────────────────────────────────────┤
│  第3层 · ThemeManager (单例)                        │
│  加载/切换/导出/导入/校验                            │
│  src/theme/manager.py                              │
├────────────────────────────────────────────────────┤
│  第2层 · Design Tokens                             │
│  约30个语义化颜色变量                                │
│  src/theme/tokens.py — 定义 + 默认值                │
├────────────────────────────────────────────────────┤
│  第1层 · QSS 模板引擎                               │
│  QSS 字符串含 {placeholder}，format() 填充           │
│  src/theme/template.py — build_stylesheet(tokens)   │
└────────────────────────────────────────────────────┘
```

### 数据流

```
用户点击"切换主题"
  → ThemeManager.load_preset("mint")
  → 读取 themes/mint.json → 解析颜色
  → 合并默认 tokens（缺失的用默认值填充）
  → 调用 template.build_stylesheet(tokens) → 生成 QSS 字符串
  → app.setStyleSheet(qss)
  → app.setPalette(qpalette)  # 同步设置 QPalette 以覆盖系统对话框
  → 更新 settings.json 中的 "theme" 字段
  → 通知订阅者（主窗口、设置页面等刷新 UI）
```

---

## 3. 文件结构

```
src/theme/                      # 新建目录
├── __init__.py                 # 暴露 ThemeManager.instance() 单例
├── manager.py                  # ThemeManager — 加载/切换/导出/导入
├── tokens.py                   # Design Token 定义 + 默认值 + 校验
├── template.py                 # QSS 模板（含 {placeholder}）+ build_stylesheet()
└── presets/                    # 内置 7 套预设
    ├── mint.json               # A. 薄荷清爽
    ├── sky.json                # B. 天空柔光
    ├── soft-dark.json          # C. 柔和暗色
    ├── latte.json              # D. 拿铁暖调
    ├── sakura.json             # E. 樱花物语
    ├── matcha.json             # F. 抹茶素净
    └── twilight.json           # G. 暮光暗色
themes/                         # 用户自定义主题目录（项目根目录）
└── (用户保存/导入的主题 .json)
```

---

## 4. Design Tokens 规范

共 **28 个 token**，覆盖所有 UI 场景。每个主题 JSON 文件只需要定义 `colors` 字典。

### 4.1 完整 Token 列表

```python
# src/theme/tokens.py

# Token 名称 → 描述
TOKEN_SPEC = {
    # ===== 背景层级 (5个) =====
    "bg_window":        "窗口底色 — QMainWindow, QWidget 默认背景",
    "bg_card":          "卡片背景 — 模式选择卡片、列表项",
    "bg_input":         "输入框背景 — QLineEdit, QComboBox, QTextEdit",
    "bg_hover":         "悬停高亮 — QPushButton:hover 非主按钮、列表项:hover",
    "bg_selected":      "选中状态背景 — QListWidget::item:selected",

    # ===== 文字层级 (4个) =====
    "text_primary":     "主文字 — 标题、正文、标签文字",
    "text_secondary":   "次要文字 — 辅助说明、状态提示",
    "text_disabled":    "禁用文字 — QLineEdit:disabled, QPushButton:disabled",
    "text_on_accent":   "主色上的文字 — 主按钮上的文字颜色（通常白色）",

    # ===== 品牌/点缀色 (3个) =====
    "accent":           "主色 — QPushButton 默认背景、focus 边框、选中项",
    "accent_hover":     "主色悬停 — QPushButton:hover 背景",
    "accent_pressed":   "主色按下 — QPushButton:pressed 背景",

    # ===== 边框/分割线 (3个) =====
    "border_default":   "默认边框 — QLineEdit, QComboBox, 卡片边框",
    "border_focus":     "焦点边框 — QLineEdit:focus, QComboBox:focus",
    "divider":          "分割线 — QFrame[HLine], 顶栏底部分割",

    # ===== 功能色 (4个) =====
    "success":          "成功/完成 — 日志 [OK] 颜色，进度条完成",
    "warning":          "警告 — 日志 [WARN] 颜色",
    "error":            "错误 — 日志 [ERROR] 颜色",
    "info":             "信息 — 日志 [INFO]/[翻页] 颜色",

    # ===== 暗色专属 (2个，亮色主题可设为透明色) =====
    "card_border":      "卡片边框色 — 比 border_default 略亮/暗的变体",
    "bg_raised":        "浮层背景 — QMenu, QToolTip 背景（暗色下比窗口亮一层）",

    # ===== 滚动条 (3个) =====
    "scrollbar_bg":     "滚动条轨道背景",
    "scrollbar_handle": "滚动条滑块",
    "scrollbar_hover":  "滚动条滑块悬停",

    # ===== 特殊 (4个) =====
    "danger":           "危险操作按钮背景 — 删除/清空等",
    "danger_hover":     "危险按钮悬停",
    "disabled_bg":      "禁用按钮背景",
    "link":             "超链接/可点击文字 — 设置页链接等",
}
```

### 4.2 Token 默认值（fallback）

当主题 JSON 缺少某些 token 时，使用以下暗色默认值填充：

```python
DEFAULT_TOKENS = {
    "bg_window": "#0A0A14",
    "bg_card": "#12122A",
    "bg_input": "#12122A",
    "bg_hover": "#18183A",
    "bg_selected": "#E11D48",
    "text_primary": "#F1F5F9",
    "text_secondary": "#94A3B8",
    "text_disabled": "#475569",
    "text_on_accent": "#FFFFFF",
    "accent": "#E11D48",
    "accent_hover": "#FF3566",
    "accent_pressed": "#C0183D",
    "border_default": "#252550",
    "border_focus": "#E11D48",
    "divider": "#252550",
    "success": "#22C55E",
    "warning": "#F59E0B",
    "error": "#EF4444",
    "info": "#94A3B8",
    "card_border": "#252550",
    "bg_raised": "#1A1A3E",
    "scrollbar_bg": "#0A0A14",
    "scrollbar_handle": "#334155",
    "scrollbar_hover": "#475569",
    "danger": "#DC2626",
    "danger_hover": "#EF4444",
    "disabled_bg": "#1A1A2E",
    "link": "#818CF8",
}
```

---

## 5. 主题 JSON 格式规范

### 5.1 完整 Schema

```json
{
  "name": "薄荷清爽",
  "version": "1.0",
  "type": "light",
  "author": "",
  "description": "",
  "colors": {
    "bg_window": "#FAFCFB",
    "bg_card": "#FFFFFF",
    ...
  }
}
```

- `name` (必填): 主题显示名称
- `version` (必填): 主题格式版本 "1.0"
- `type` (必填): "light" 或 "dark" — 影响 QPalette 基础色
- `author` (可选): 作者名
- `description` (可选): 简短描述
- `colors` (必填): 28 个 token 的颜色值，**允许部分缺失**（缺失的使用默认值）

### 5.2 导出文件扩展名

- 内置预设：`.json`，位于 `src/theme/presets/`
- 用户自定义：`.json`，位于 `themes/`
- 导出分享：`.origamitheme`（内容格式完全相同，就是 JSON，换个后缀方便关联文件类型）

---

## 6. 七套主题预设完整配色

### 6.1 A · 薄荷清爽 (mint) — `type: "light"`

```json
{
  "name": "薄荷清爽",
  "version": "1.0",
  "type": "light",
  "author": "Origami",
  "description": "白色基底 + 薄荷绿点缀，干净理性",
  "colors": {
    "bg_window": "#FAFCFB",
    "bg_card": "#FFFFFF",
    "bg_input": "#F1F5F9",
    "bg_hover": "#F0FDF6",
    "bg_selected": "#10B981",
    "text_primary": "#0F172A",
    "text_secondary": "#64748B",
    "text_disabled": "#94A3B8",
    "text_on_accent": "#FFFFFF",
    "accent": "#10B981",
    "accent_hover": "#059669",
    "accent_pressed": "#047857",
    "border_default": "#E2E8F0",
    "border_focus": "#10B981",
    "divider": "#E8ECF0",
    "success": "#22C55E",
    "warning": "#F59E0B",
    "error": "#EF4444",
    "info": "#94A3B8",
    "card_border": "#E8ECF0",
    "bg_raised": "#FFFFFF",
    "scrollbar_bg": "#F8FAFC",
    "scrollbar_handle": "#CBD5E1",
    "scrollbar_hover": "#94A3B8",
    "danger": "#EF4444",
    "danger_hover": "#DC2626",
    "disabled_bg": "#F1F5F9",
    "link": "#10B981"
  }
}
```

### 6.2 B · 天空柔光 (sky) — `type: "light"`

```json
{
  "name": "天空柔光",
  "version": "1.0",
  "type": "light",
  "author": "Origami",
  "description": "淡蓝灰底 + 天蓝点缀，专业可靠",
  "colors": {
    "bg_window": "#F8FAFC",
    "bg_card": "#FFFFFF",
    "bg_input": "#F1F5F9",
    "bg_hover": "#EFF6FF",
    "bg_selected": "#3B82F6",
    "text_primary": "#1E293B",
    "text_secondary": "#64748B",
    "text_disabled": "#94A3B8",
    "text_on_accent": "#FFFFFF",
    "accent": "#3B82F6",
    "accent_hover": "#2563EB",
    "accent_pressed": "#1D4ED8",
    "border_default": "#E2E8F0",
    "border_focus": "#3B82F6",
    "divider": "#E8ECF0",
    "success": "#22C55E",
    "warning": "#F59E0B",
    "error": "#EF4444",
    "info": "#94A3B8",
    "card_border": "#E8ECF0",
    "bg_raised": "#FFFFFF",
    "scrollbar_bg": "#F8FAFC",
    "scrollbar_handle": "#CBD5E1",
    "scrollbar_hover": "#94A3B8",
    "danger": "#EF4444",
    "danger_hover": "#DC2626",
    "disabled_bg": "#F1F5F9",
    "link": "#3B82F6"
  }
}
```

### 6.3 C · 柔和暗色 (soft-dark) — `type: "dark"`

```json
{
  "name": "柔和暗色",
  "version": "1.0",
  "type": "dark",
  "author": "Origami",
  "description": "深灰基底 + 薰衣草紫点缀，柔和护眼",
  "colors": {
    "bg_window": "#1A1B2E",
    "bg_card": "#202238",
    "bg_input": "#202238",
    "bg_hover": "#2D2F4A",
    "bg_selected": "#818CF8",
    "text_primary": "#E2E8F0",
    "text_secondary": "#94A3B8",
    "text_disabled": "#4B5563",
    "text_on_accent": "#FFFFFF",
    "accent": "#818CF8",
    "accent_hover": "#A5B4FC",
    "accent_pressed": "#6366F1",
    "border_default": "#2A2C44",
    "border_focus": "#818CF8",
    "divider": "#2A2C44",
    "success": "#4ADE80",
    "warning": "#FBBF24",
    "error": "#F87171",
    "info": "#94A3B8",
    "card_border": "#2A2C44",
    "bg_raised": "#2D2F4A",
    "scrollbar_bg": "#1A1B2E",
    "scrollbar_handle": "#4B5563",
    "scrollbar_hover": "#6B7280",
    "danger": "#EF4444",
    "danger_hover": "#DC2626",
    "disabled_bg": "#1E2030",
    "link": "#818CF8"
  }
}
```

### 6.4 D · 拿铁暖调 (latte) — `type: "light"`

```json
{
  "name": "拿铁暖调",
  "version": "1.0",
  "type": "light",
  "author": "Origami",
  "description": "米白基底 + 焦糖橙点缀，温暖治愈",
  "colors": {
    "bg_window": "#FFFBF5",
    "bg_card": "#FFFFFF",
    "bg_input": "#FDF6ED",
    "bg_hover": "#FFF0E5",
    "bg_selected": "#E88D4A",
    "text_primary": "#3D2E1E",
    "text_secondary": "#8B7355",
    "text_disabled": "#B8A898",
    "text_on_accent": "#FFFFFF",
    "accent": "#E88D4A",
    "accent_hover": "#D4783A",
    "accent_pressed": "#C0682A",
    "border_default": "#F0E4D8",
    "border_focus": "#E88D4A",
    "divider": "#F0E4D8",
    "success": "#65A30D",
    "warning": "#D97706",
    "error": "#DC2626",
    "info": "#A89B8C",
    "card_border": "#F0E4D8",
    "bg_raised": "#FFFFFF",
    "scrollbar_bg": "#FFFBF5",
    "scrollbar_handle": "#D4C4B0",
    "scrollbar_hover": "#B8A898",
    "danger": "#DC2626",
    "danger_hover": "#B91C1C",
    "disabled_bg": "#FDF6ED",
    "link": "#E88D4A"
  }
}
```

### 6.5 E · 樱花物语 (sakura) — `type: "light"`

```json
{
  "name": "樱花物语",
  "version": "1.0",
  "type": "light",
  "author": "Origami",
  "description": "纯白粉底 + 柔粉点缀，甜美可爱",
  "colors": {
    "bg_window": "#FFF5F7",
    "bg_card": "#FFFFFF",
    "bg_input": "#FFF0F3",
    "bg_hover": "#FFEBF0",
    "bg_selected": "#F472B6",
    "text_primary": "#2D1820",
    "text_secondary": "#8B6478",
    "text_disabled": "#C4A0AC",
    "text_on_accent": "#FFFFFF",
    "accent": "#F472B6",
    "accent_hover": "#EC4899",
    "accent_pressed": "#DB2777",
    "border_default": "#F5E0E8",
    "border_focus": "#F472B6",
    "divider": "#F5E0E8",
    "success": "#22C55E",
    "warning": "#F59E0B",
    "error": "#EF4444",
    "info": "#C4A0AC",
    "card_border": "#F5E0E8",
    "bg_raised": "#FFFFFF",
    "scrollbar_bg": "#FFF5F7",
    "scrollbar_handle": "#E8CCD4",
    "scrollbar_hover": "#C4A0AC",
    "danger": "#EF4444",
    "danger_hover": "#DC2626",
    "disabled_bg": "#FFF0F3",
    "link": "#F472B6"
  }
}
```

### 6.6 F · 抹茶素净 (matcha) — `type: "light"`

```json
{
  "name": "抹茶素净",
  "version": "1.0",
  "type": "light",
  "author": "Origami",
  "description": "极白基底 + 淡绿灰点缀，侘寂极简",
  "colors": {
    "bg_window": "#F9FAF8",
    "bg_card": "#FFFFFF",
    "bg_input": "#F2F5F0",
    "bg_hover": "#EDF5EC",
    "bg_selected": "#7D9F7A",
    "text_primary": "#1A2E1A",
    "text_secondary": "#6B7D6B",
    "text_disabled": "#A8B5A6",
    "text_on_accent": "#FFFFFF",
    "accent": "#7D9F7A",
    "accent_hover": "#6B8F68",
    "accent_pressed": "#5A7F56",
    "border_default": "#E4EAE2",
    "border_focus": "#7D9F7A",
    "divider": "#E4EAE2",
    "success": "#65A30D",
    "warning": "#D97706",
    "error": "#DC2626",
    "info": "#94A398",
    "card_border": "#E4EAE2",
    "bg_raised": "#FFFFFF",
    "scrollbar_bg": "#F9FAF8",
    "scrollbar_handle": "#CDD5CA",
    "scrollbar_hover": "#A8B5A6",
    "danger": "#DC2626",
    "danger_hover": "#B91C1C",
    "disabled_bg": "#F2F5F0",
    "link": "#7D9F7A"
  }
}
```

### 6.7 G · 暮光暗色 (twilight) — `type: "dark"`

```json
{
  "name": "暮光暗色",
  "version": "1.0",
  "type": "dark",
  "author": "Origami",
  "description": "石墨黑 + 青蓝点缀，现代酷感",
  "colors": {
    "bg_window": "#1E1E24",
    "bg_card": "#242630",
    "bg_input": "#242630",
    "bg_hover": "#2A2D3A",
    "bg_selected": "#22D3EE",
    "text_primary": "#E8E8ED",
    "text_secondary": "#6B6B7E",
    "text_disabled": "#5A5A6E",
    "text_on_accent": "#0F172A",
    "accent": "#22D3EE",
    "accent_hover": "#67E8F9",
    "accent_pressed": "#06B6D4",
    "border_default": "#2E3040",
    "border_focus": "#22D3EE",
    "divider": "#2E3040",
    "success": "#4ADE80",
    "warning": "#FBBF24",
    "error": "#F87171",
    "info": "#6B6B7E",
    "card_border": "#2E3040",
    "bg_raised": "#2A2D3A",
    "scrollbar_bg": "#1E1E24",
    "scrollbar_handle": "#4A4A5A",
    "scrollbar_hover": "#6B6B7E",
    "danger": "#EF4444",
    "danger_hover": "#DC2626",
    "disabled_bg": "#22222A",
    "link": "#22D3EE"
  }
}
```

---

## 7. QSS 模板设计

### 7.1 改造策略

当前 `src/stylesheet.py` 的 `build_stylesheet(base_pt)` 函数保持结构不变，改为接受 tokens 参数：

```python
# src/theme/template.py

def build_stylesheet(tokens: dict, base_pt: int = 11) -> str:
    """
    根据 tokens 生成完整 QSS 样式表。

    参数:
        tokens: 28 个颜色 token 的完整字典
        base_pt: 基础字号 (pt)
    返回:
        完整的 QSS 字符串
    """
    s = base_pt
    sm = max(7, base_pt - 1)
    xs = max(6, base_pt - 2)
    lg = base_pt + 2
    mono = max(7, base_pt - 1)
    py = max(2, base_pt // 3)
    px = max(4, base_pt // 2 + 1)

    t = tokens  # 别名，方便模板中使用

    return f"""
/* ═══════════════ Origami 全局样式 ═══════════════ */
QMainWindow, QWidget {{
    background-color: {t["bg_window"]};
    color: {t["text_primary"]};
    font-size: {s}pt;
}}

/* ── 输入框 ── */
QLineEdit {{
    background-color: {t["bg_input"]};
    color: {t["text_primary"]};
    border: 1px solid {t["border_default"]};
    border-radius: 8px;
    padding: {py+2}px {px+2}px;
    font-size: {s}pt;
}}
QLineEdit:focus {{
    border: 1px solid {t["border_focus"]};
    background: {t["bg_card"]};
}}
QLineEdit:disabled {{
    background: {t["disabled_bg"]};
    color: {t["text_disabled"]};
    border-color: {t["border_default"]};
}}

/* ── 主按钮 ── */
QPushButton {{
    background-color: {t["accent"]};
    color: {t["text_on_accent"]};
    border: none;
    border-radius: 8px;
    padding: {py+2}px {px+6}px;
    font-size: {s}pt;
    font-weight: bold;
}}
QPushButton:hover {{ background-color: {t["accent_hover"]}; }}
QPushButton:pressed {{ background: {t["accent_pressed"]}; }}

/* ── 次按钮 ── */
QPushButton#secondaryBtn {{
    background-color: {t["bg_card"]};
    border: 1px solid {t["border_default"]};
    color: {t["text_primary"]};
    font-weight: normal;
}}
QPushButton#secondaryBtn:hover {{ background-color: {t["bg_hover"]}; }}
QPushButton#secondaryBtn:pressed {{ background: {t["bg_input"]}; }}

/* ── 模式选择卡片 ── */
QPushButton#modeBtn {{
    background-color: {t["bg_card"]};
    color: {t["text_primary"]};
    border: 2px solid {t["card_border"]};
    border-radius: 16px;
    padding: {py+12}px;
    font-size: {lg}pt;
    text-align: left;
}}
QPushButton#modeBtn:hover {{
    background-color: {t["bg_hover"]};
    border-color: {t["accent"]};
}}
QPushButton#modeBtn:pressed {{
    background: {t["bg_input"]};
    border-color: {t["accent_pressed"]};
}}

/* ── 幽灵按钮 ── */
QPushButton#ghostBtn {{
    background: transparent;
    color: {t["text_secondary"]};
    border: 1px solid transparent;
    font-weight: normal;
}}
QPushButton#ghostBtn:hover {{
    background: {t["bg_hover"]};
    color: {t["text_primary"]};
    border-color: {t["border_default"]};
}}

/* ── 禁用按钮 ── */
QPushButton:disabled {{
    background: {t["disabled_bg"]};
    color: {t["text_disabled"]};
    border-color: {t["border_default"]};
}}

/* ── 日志区域 ── */
QTextEdit {{
    background-color: {t["bg_input"]};
    color: {t["text_secondary"]};
    border: 1px solid {t["border_default"]};
    border-radius: 8px;
    padding: {py}px;
    font-family: 'Consolas', 'Courier New', monospace;
    font-size: {mono}pt;
}}

/* ── 进度条 ── */
QProgressBar {{
    background-color: {t["bg_input"]};
    border: 1px solid {t["border_default"]};
    border-radius: 4px;
    min-height: {max(4, py)}px;
    text-align: center;
    font-size: {max(7, s-1)}pt;
    color: {t["text_primary"]};
}}
QProgressBar::chunk {{
    background-color: {t["accent"]};
    border-radius: 3px;
}}

/* ── 标签 ── */
QLabel {{ color: {t["text_secondary"]}; font-size: {s}pt; }}

/* ── 下拉框 ── */
QComboBox {{
    background-color: {t["bg_input"]};
    color: {t["text_primary"]};
    border: 1px solid {t["border_default"]};
    border-radius: 8px;
    padding: {py}px {px}px;
    font-size: {s}pt;
    min-width: 90px;
}}
QComboBox:hover {{ border: 1px solid {t["accent"]}; }}
QComboBox::drop-down {{ border: none; width: 24px; }}
QComboBox::down-arrow {{
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 6px solid {t["text_secondary"]};
    margin-right: 6px;
}}
QComboBox QAbstractItemView {{
    background: {t["bg_card"]};
    color: {t["text_primary"]};
    border: 1px solid {t["border_default"]};
    selection-background: {t["accent"]};
    outline: none;
    padding: 4px;
}}

/* ── 列表 ── */
QListWidget {{
    background-color: {t["bg_card"]};
    border: 1px solid {t["border_default"]};
    border-radius: 8px;
    padding: 4px;
    font-size: {s}pt;
    outline: none;
}}
QListWidget::item {{
    padding: {py+2}px {px+2}px;
    border-radius: 6px;
    margin: 1px 0;
}}
QListWidget::item:selected {{ background: {t["bg_selected"]}; color: {t["text_on_accent"]}; }}
QListWidget::item:hover {{ background: {t["bg_hover"]}; }}

/* ── 分割器 ── */
QSplitter::handle {{ background-color: {t["divider"]}; width: 2px; }}

/* ── 滚动条 ── */
QScrollBar:vertical {{
    background: {t["scrollbar_bg"]};
    width: 8px;
    border-radius: 4px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {t["scrollbar_handle"]};
    border-radius: 4px;
    min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{ background: {t["scrollbar_hover"]}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}

QScrollBar:horizontal {{
    background: {t["scrollbar_bg"]};
    height: 8px;
}}
QScrollBar::handle:horizontal {{
    background: {t["scrollbar_handle"]};
    border-radius: 4px;
    min-width: 30px;
}}
QScrollBar::handle:horizontal:hover {{ background: {t["scrollbar_hover"]}; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}

/* ── 菜单 ── */
QMenu {{
    background: {t["bg_raised"]};
    color: {t["text_primary"]};
    border: 1px solid {t["border_default"]};
    border-radius: 8px;
    padding: 4px;
    font-size: {sm}pt;
}}
QMenu::item {{
    padding: {py+1}px {px+10}px {py+1}px {px+2}px;
    border-radius: 4px;
}}
QMenu::item:selected {{ background: {t["accent"]}; }}

/* ── 工具提示 ── */
QToolTip {{
    background: {t["bg_raised"]};
    color: {t["text_primary"]};
    border: 1px solid {t["border_default"]};
    border-radius: 6px;
    padding: {py+1}px {px+2}px;
    font-size: {xs}pt;
}}

/* ── 对话框 ── */
QMessageBox {{ background: {t["bg_window"]}; }}
QMessageBox QLabel {{ color: {t["text_primary"]}; font-size: {s}pt; }}
QMessageBox QPushButton {{ min-width: 80px; padding: {py+1}px {px+4}px; }}

/* ── 滚动区域 ── */
QScrollArea {{ background: transparent; border: none; }}
"""
```

---

## 8. ThemeManager 实现规格

### 8.1 类设计

```python
# src/theme/manager.py

class ThemeManager:
    """
    主题管理器单例。

    用法:
        from src.theme import ThemeManager
        tm = ThemeManager.instance()

        # 切换主题
        tm.load_preset("mint").apply()

        # 导出当前主题
        tm.export_to("/path/to/my-theme.origamitheme")

        # 导入主题
        tm.import_from("/path/to/shared-theme.json")

        # 列出所有可用主题
        presets, customs = tm.list_all()
    """

    # 单例
    _instance = None

    # preset 目录路径
    PRESETS_DIR: Path

    # 用户自定义主题目录
    CUSTOM_DIR: Path

    # 当前加载的主题数据
    _current: dict  # 完整的 {name, type, colors: {...}}

    # 当前生成的 QSS 缓存
    _qss_cache: str

    @classmethod
    def instance(cls) -> "ThemeManager": ...

    def load_preset(self, name: str) -> "ThemeManager": ...
    def load_file(self, path: Path) -> "ThemeManager": ...
    def apply(self) -> None: ...
    def export_to(self, path: Path) -> None: ...
    def import_from(self, path: Path) -> str: ...
    def list_all(self) -> tuple[list[dict], list[dict]]: ...
    @property
    def current(self) -> dict: ...
    @property
    def current_name(self) -> str: ...
    @property
    def tokens(self) -> dict: ...
```

### 8.2 核心方法行为

**`load_preset(name)`**
1. 查找 `src/theme/presets/{name}.json`
2. 读取 JSON，解析 name/type/colors
3. 用 `DEFAULT_TOKENS` 填充缺失的颜色 token
4. 存入 `_current`
5. 返回 self（链式调用）

**`load_file(path)`**
1. 读取任意路径的 `.json` / `.origamitheme` 文件
2. 同样填充缺失 token
3. 存入 `_current`
4. 返回 self

**`apply()`**
1. 根据 `_current["type"]` 构建对应的 `QPalette`
2. 调用 `template.build_stylesheet(tokens, base_pt)` 生成 QSS
3. `QApplication.instance().setStyleSheet(qss)`
4. `QApplication.instance().setPalette(palette)`
5. 更新 `settings.json` 中的 `"theme"` 字段：`{"preset": name}` 或 `{"custom": "/path/to/file"}`
6. 通知所有订阅者

**`export_to(path)`**
- 将当前 `_current` 序列化为 JSON 写入 path
- 移除内部填充的默认值（只导出主题文件本身的 colors）

**`import_from(path)`**
1. 校验文件格式（必须包含 name、colors）
2. 复制到 `themes/` 目录
3. 返回主题名称

**`list_all()`**
- 返回 `(presets_list, customs_list)`
- 每个条目：`{"id": "...", "name": "...", "type": "light|dark"}`

### 8.3 初始化流程

```python
def _init(self):
    """从 settings.json 恢复上次主题"""
    settings = load_settings()
    theme_config = settings.get("theme", {})
    preset = theme_config.get("preset", "soft-dark")
    custom = theme_config.get("custom", "")

    if custom and Path(custom).exists():
        self.load_file(Path(custom))
    else:
        self.load_preset(preset)
    self.apply()
```

---

## 9. QPalette 同步策略

QSS 不能控制的系统对话框等组件，需要用 QPalette 覆盖。根据主题 type 构建：

```python
def _build_palette(theme_type: str, tokens: dict) -> QPalette:
    palette = QPalette()

    if theme_type == "light":
        palette.setColor(QPalette.ColorRole.Window, QColor(tokens["bg_window"]))
        palette.setColor(QPalette.ColorRole.WindowText, QColor(tokens["text_primary"]))
        palette.setColor(QPalette.ColorRole.Base, QColor(tokens["bg_card"]))
        palette.setColor(QPalette.ColorRole.Text, QColor(tokens["text_primary"]))
        palette.setColor(QPalette.ColorRole.Button, QColor(tokens["bg_card"]))
        palette.setColor(QPalette.ColorRole.ButtonText, QColor(tokens["text_primary"]))
        palette.setColor(QPalette.ColorRole.Highlight, QColor(tokens["accent"]))
        palette.setColor(QPalette.ColorRole.HighlightedText, QColor(tokens["text_on_accent"]))
    else:  # dark
        # 同上，使用暗色对应的 tokens
        ...

    return palette
```

---

## 10. Settings 集成

在 `src/settings/schema.py` 中添加 `theme` 字段：

```python
"theme": {
    "default": {"preset": "soft-dark", "custom": ""},
    "type": dict,
    "desc": "当前主题配置，包含 preset 名称或 custom 文件路径",
},
```

---

## 11. 字号与主题独立

**重要设计决策**：字号（font_size）与主题（theme）是两个独立设置，互不影响。

- 字号变更 → 只需重新 `build_stylesheet(tokens, new_pt)`，tokens 不变
- 主题变更 → 只需重新 `build_stylesheet(new_tokens, current_pt)`，base_pt 不变

当前 `src/fonts.py` 和当前字号调整逻辑**完全不需要改动**。

---

## 12. 导出/导入功能

### 用户操作流程

**导出**：
1. 设置页 → 主题选择器 → 点击「导出主题」
2. 弹出 `QFileDialog.getSaveFileName(filter="Origami Theme (*.origamitheme)")`
3. `ThemeManager.instance().export_to(selected_path)`

**导入**：
1. 设置页 → 主题选择器 → 点击「导入主题」
2. 弹出 `QFileDialog.getOpenFileName(filter="Theme Files (*.json *.origamitheme)")`
3. 校验文件 → 复制到 `themes/` 目录 → 加入列表 → 自动应用

**重置**：
1. 点击预设主题 → 直接 `load_preset("mint").apply()`

---

## 13. 实现步骤

按顺序执行，每步完成后验证再继续：

### Step 1: 创建目录结构
- 创建 `src/theme/` 目录及 `__init__.py`
- 创建 `src/theme/presets/` 目录
- 创建项目根目录 `themes/` 目录
- 在 `.gitignore` 中添加 `.superpowers/`

### Step 2: 编写 `src/theme/tokens.py`
- 定义 `TOKEN_SPEC` (token 名称 → 描述)
- 定义 `DEFAULT_TOKENS` (28个默认值)
- 定义 `get_defaults()` 和 `validate_tokens(colors)` 函数

### Step 3: 编写 `src/theme/template.py`
- 复制当前 `src/stylesheet.py` 的 `build_stylesheet()` 函数
- 将所有硬编码颜色替换为 `{t["token_name"]}` 占位符
- 函数签名改为 `build_stylesheet(tokens: dict, base_pt: int)`

### Step 4: 编写 7 个预设 JSON 文件
- 按第 6 节的配色值创建 `src/theme/presets/*.json`

### Step 5: 编写 `src/theme/manager.py`
- 实现 `ThemeManager` 单例类
- 实现 `load_preset`, `load_file`, `apply`, `export_to`, `import_from`, `list_all`
- 实现 `_build_palette` 辅助函数

### Step 6: 编写 `src/theme/__init__.py`
- 暴露 `ThemeManager` 单例访问入口

### Step 7: 改造 `main.py`
- 删除硬编码的 `QPalette` 设置代码（约15行）
- 删除 `from src.stylesheet import build_stylesheet` 导入
- 替换为：
  ```python
  from src.theme import ThemeManager
  tm = ThemeManager.instance()  # 自动从 settings 恢复上次主题
  tm.apply()
  ```

### Step 8: 改造 `src/gui/main_window.py`
- `_apply_font()` 方法内，`build_stylesheet(pt)` 改为 `template.build_stylesheet(tm.tokens, pt)`
- 添加主题变更刷新逻辑

### Step 9: 改造设置页面
- 在 `src/gui/pages/settings_page.py` 添加主题选择区域
- 列出所有 preset + 自定义主题
- 添加「导出」「导入」按钮
- 选择主题后调用 `ThemeManager.instance().load_preset(id).apply()`

### Step 10: 清理
- 删除 `src/stylesheet.py`（功能被 `src/theme/template.py` 替代）
- 确保所有 `from src.stylesheet import build_stylesheet` 改到新路径

### Step 11: 测试验证
- 启动 → 默认柔和暗色主题
- 切换 7 套主题各一次，确认无报错
- 导出当前主题 → 删除 → 重新导入 → 确认正常工作
- 字号调整 → 切换主题 → 确认字号不受影响

---

## 14. 兼容性说明

- Python 3.12+ — 无新增依赖
- PyQt6 >= 6.5 — 仅使用已有 API
- 不引入新第三方库
- 现有功能（下载/登录/剪贴板监听/自动更新）不受影响
- 现有 settings.json 自动迁移（`store.load()` 会合并新字段默认值）

---

## 15. 附录：颜色 Token 速查

| Token | 用途 | 出现在哪些控件 |
|-------|------|-------------|
| `bg_window` | 窗口背景 | QMainWindow, QWidget 全局 |
| `bg_card` | 卡片背景 | 模式卡片、设置面板、列表空状态 |
| `bg_input` | 输入背景 | QLineEdit, QTextEdit, QComboBox |
| `bg_hover` | 悬停高亮 | 列表项:hover, 次按钮:hover |
| `bg_selected` | 选中状态 | QListWidget::item:selected |
| `text_primary` | 主文字 | 标题、按钮文字、输入文字 |
| `text_secondary` | 次要文字 | 辅助说明、状态、QLabel 默认 |
| `text_disabled` | 禁用文字 | :disabled 伪状态 |
| `text_on_accent` | 主色上文字 | 主按钮文字、选中项文字 |
| `accent` | 主色 | 按钮背景、focus 边框、选中 |
| `accent_hover` | 主色悬停 | 按钮:hover |
| `accent_pressed` | 主色按下 | 按钮:pressed |
| `border_default` | 默认边框 | 输入框、下拉框、卡片 |
| `border_focus` | 焦点边框 | 输入框:focus |
| `divider` | 分割线 | QFrame[HLine], QSplitter |
| `success` | 成功色 | 日志 [OK] 文字 |
| `warning` | 警告色 | 日志 [WARN] 文字 |
| `error` | 错误色 | 日志 [ERROR] 文字 |
| `info` | 信息色 | 日志 [翻页]/[INFO] 文字 |
| `card_border` | 卡片边框 | modeBtn 默认边框 |
| `bg_raised` | 浮层背景 | QMenu, QToolTip |
| `scrollbar_bg` | 滚动条轨道 | QScrollBar |
| `scrollbar_handle` | 滚动条滑块 | QScrollBar::handle |
| `scrollbar_hover` | 滑块悬停 | QScrollBar::handle:hover |
| `danger` | 危险按钮 | 删除操作按钮 |
| `danger_hover` | 危险悬停 | 危险按钮:hover |
| `disabled_bg` | 禁用背景 | QPushButton:disabled |
| `link` | 链接色 | 设置页超链接 |

---

## 16. 主页面布局规格

### 16.1 窗口比例

**竖版窗口** — 默认尺寸约 400×520px（宽高比约 3:4），最小 340×420px。

```
┌─────────────────┐
│  Origami  v0.1  │  ← 顶栏：应用名 + 版本号
├─────────────────┤
│                 │
│    选择平台      │  ← 标题：居中，font-weight:700
│   选一个开始     │  ← 副标题：居中，text_secondary
│                 │
│  ┌──────┐ ┌───┐ │
│  │ 图标  │ │图 │ │
│  │      │ │标 │ │  ← 两张方形卡片 横排居中
│  │ 抖音  │ │B站│ │     宽约 85px，高约 85px
│  └──────┘ └───┘ │     border-radius:14px
│                 │
│ 未登录      设置  │  ← 底栏：登录状态 + 设置按钮
└─────────────────┘
```

### 16.2 页面元素

| 区域 | 控件 | QSS objectName | 说明 |
|------|------|---------------|------|
| 顶栏 | QHBoxLayout | — | 左：应用名 QLabel，右：版本号 QLabel |
| 标题 | QVBoxLayout | — | 居中，主标题 + 副标题 |
| 卡片区 | QHBoxLayout | — | 两张 QPushButton，objectName: `platformCard` |
| 底栏 | QHBoxLayout | — | 左：登录状态 QLabel，右：设置 QPushButton#ghostBtn |

### 16.3 平台卡片样式

```python
# 选中（已实现的平台，如抖音）
QPushButton#platformCard {
    background: {bg_hover};
    border: 2px solid {accent};
    border-radius: 14px;
    padding: 16px 10px;
    font-size: {s}pt;
    font-weight: 700;
    color: {accent};
}
QPushButton#platformCard:hover {
    background: {bg_card};
    border-color: {accent_hover};
}

# 未选中（尚未实现的平台，如 B站）
QPushButton#platformCardPending {
    background: {bg_card};
    border: 2px solid {border_default};
    border-radius: 14px;
    padding: 16px 10px;
    font-size: {s}pt;
    font-weight: 600;
    color: {text_disabled};
}
QPushButton#platformCardPending:hover {
    border-color: {accent};
    color: {text_secondary};
}
```

### 16.4 卡片布局逻辑

- 只有 2 个平台 → 两张卡片等宽横排，间距 8-10px
- 将来平台增加到 3-4 个 → 改为 `QGridLayout` 2×2
- 窗口宽度 < 380px → 卡片改为竖排
- 每张卡片内容：上方平台图标（后期替换为 PNG/SVG），下方平台名称
- 已实现的平台显示 platformCard 样式，未实现的显示 platformCardPending 样式

### 16.5 顶栏与底栏

**顶栏**：
- 左对齐：应用名 "Origami"，font-weight:700，text_primary
- 右对齐：版本号，font-size 较小，text_disabled
- 底部一条分割线（divider 颜色，1px）

**底栏**：
- 左对齐：登录状态文字（"未登录"/"已登录"），text_secondary
- 右对齐：设置按钮（ghostBtn 样式），文字"设置"
- 顶部一条分割线

### 16.6 QStackedWidget 索引

当前页面索引保持不变：

| 索引 | 页面 | 说明 |
|------|------|------|
| 0 | ModePage（首页） | 平台选择 — 本规格描述的主页面 |
| 1 | DouyinPage | 抖音功能页（单视频/批量选择） |
| 2 | SinglePage | 单视频下载 |
| 3 | BatchPage | 主页批量下载 |
| 4 | SettingsPage | 设置页 |
| 5 | UpdatePage | 版本更新 |

### 16.7 当前待实现平台

| 平台 | platform_id | 状态 | 卡片样式 |
|------|-----------|------|---------|
| 抖音 | douyin | 已实现 | platformCard（选中态） |
| B站 | bilibili | 待实现 | platformCardPending（灰色） |

后续新增平台时，在 ModePage 中动态生成卡片，根据 `PLATFORM_REGISTRY` 判断是否已实现。
