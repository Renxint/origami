# Mineradio 卡片设计深度分析 — 对 Origami 的借鉴

> **分析日期**: 2026-06-24
> **分析对象**: [Mineradio v1.1.0](https://github.com/XxHuberrr/Mineradio) — Electron 沉浸式音乐播放器
> **目标**: 提炼 Mineradio 的卡片 UI 设计模式，评估哪些可以落地到 Origami (PyQt6 + QSS)
> **关联文档**: [[theme-design]] · [[同类项目对比分析]]

---

## 0. 快速摘要

Mineradio 的卡片好看，核心是 **四层叠加 + 色调变量系统 + 悬浮多重反馈**：

```
┌─────────────────────────────────────────┐
│ ① 玻璃基底  backdrop-filter blur + saturate  │
├─────────────────────────────────────────┤
│ ② 内发光    inset 0 1px 0 rgba(白,6%)      │  ← 模拟玻璃边缘高光线
├─────────────────────────────────────────┤
│ ③ 渐变装饰  ::before 对角线 / ::after 条纹   │
├─────────────────────────────────────────┤
│ ④ 阴影景深  多层叠加（深影 + 色调光晕）       │
└─────────────────────────────────────────┘
```

QSS 不支持 backdrop-filter / box-shadow / animation / 伪元素，但**设计原则都可通过 PyQt6 原生手段实现**。

---

## 1. Mineradio 卡片设计解构

### 1.1 核心卡片组件

Mineradio 首页有三类卡片：

| 组件 | CSS 类 | 用途 |
|------|--------|------|
| 大卡片 | `.home-card` | 天气电台 / 每日推荐 / 私人电台 — 2列网格 |
| 小卡片 | `.home-tile` | 继续听 / 听歌画像 / 我的歌单 — 5列横排 |
| 列表卡片 | `.pl-card` | 歌单列表项 — 头像 + 标题 + 元信息 |
| 预设卡片 | `.preset-card` | 视觉预设选择 — 2列网格 |

### 1.2 `.home-card` 完整 CSS 规格

```css
.home-card {
  /* 色调变量 — 每张卡片可独立配色 */
  --tone-a: #00f5d4;   /* 主色调（青） */
  --tone-b: #2442ff;   /* 辅色调（蓝） */
  --tone-c: #f8f4ee;   /* 点缀色（暖白） */

  /* 尺寸 */
  min-height: 152px;
  padding: 17px;

  /* 玻璃基底 */
  background: linear-gradient(142deg, rgba(18,21,26,.66), rgba(8,9,13,.76));
  backdrop-filter: blur(24px) saturate(1.12);

  /* 边框 — 极淡 */
  border: 1px solid rgba(255,255,255, 0.085);
  border-radius: 22px;

  /* 阴影 — 多层 */
  box-shadow:
    0 20px 64px rgba(0,0,0,.28),           /* 环境阴影 */
    inset 0 1px 0 rgba(255,255,255,.060);   /* 顶部高光线 */

  /* 交互 */
  cursor: pointer;
  transition: transform .22s cubic-bezier(.16,1,.3,1),
              border-color .22s, background .22s, box-shadow .22s;
}
```

### 1.3 伪元素装饰

```css
/* ::before — 对角线渐变打光 */
.home-card::before {
  content: '';
  position: absolute; inset: 0;
  background:
    linear-gradient(118deg,
      color-mix(in srgb, var(--tone-a) 22%, transparent),
      transparent 38%,
      color-mix(in srgb, var(--tone-b) 16%, transparent) 74%,
      transparent),
    linear-gradient(90deg,
      rgba(255,255,255,.035) 0 1px,
      transparent 1px 38px);   /* 细竖线纹理 */
  opacity: .86; pointer-events: none;
}

/* ::after — 右侧装饰条纹（模拟唱片纹理） */
.home-card::after {
  content: '';
  position: absolute;
  right: 114px; bottom: 18px;
  width: 38px; height: 70px;
  border-radius: 999px;
  background: repeating-linear-gradient(0deg,
    color-mix(in srgb, var(--tone-c) 64%, rgba(255,255,255,.26)) 0 4px,
    transparent 4px 10px);
  opacity: .20;
  transform: skewX(-10deg);
}
```

### 1.4 Hover 四重反馈

```css
.home-card:hover {
  transform: translateY(-3px);               /* ① 物理上浮 */
  border-color: color-mix(in srgb, var(--tone-a) 42%, rgba白18%)); /* ② 边框染色调 */
  background: linear-gradient(142deg, rgba(36,33,39,.72), rgba(10,10,14,.84)); /* ③ 背景变亮 */
  box-shadow:
    0 28px 84px rgba(0,0,0,.36),            /* ④ 阴影加深 */
    0 0 34px color-mix(in srgb, var(--tone-a) 16%, transparent), /* 色调光晕 */
    inset 0 1px 0 rgba(255,255,255,.085);   /* 内高光增强 */
}
```

**关键洞察**：不是改一个属性，而是四个属性同时变化 → 用户感知"卡片活了"。

### 1.5 空闲浮动动画

```css
body.empty-home-active .home-card {
  animation: home-card-float 7.4s ease-in-out infinite;
}
/* 错开延迟 → 波浪效果 */
body.empty-home-active .home-card:nth-of-type(2) { animation-delay: -1.4s; }
body.empty-home-active .home-card:nth-of-type(3) { animation-delay: -2.6s; }

@keyframes home-card-float {
  0%, 100% { transform: translateY(0); }
  50%      { transform: translateY(-2px); }
}
```

### 1.6 封面图旋转

```css
.home-card-art {
  position: absolute;
  right: 13px; bottom: 13px;
  width: 108px; height: 108px;
  border-radius: 24px;
  transform: rotate(3deg);  /* ← 关键：微微旋转 → "随手放置"的实体感 */
  box-shadow:
    0 18px 50px rgba(0,0,0,.36),
    inset 0 1px 0 rgba(255,255,255,.16);
}
```

### 1.7 色调变量系统

同一套 CSS，不同卡片用 `data-home-tone` 切换调色板：

```css
.home-card                        { --tone-a:#00f5d4; --tone-b:#2442ff; --tone-c:#f8f4ee; }
.home-card[data-home-tone="mix"]  { --tone-a:#9db8cf; --tone-b:#00f5d4; --tone-c:#2442ff; }
.home-card[data-home-tone="local"]{ --tone-a:#f8f4ee; --tone-b:#00f5d4; --tone-c:#2442ff; }
```

所有子元素颜色都从 `--tone-a/b/c` 派生：边框色、光晕色、装饰条色、标签色、封面渐变色。

---

## 2. QSS 可行性评估

### 2.1 QSS 支持的功能（可直接翻译）

| Mineradio CSS | QSS 等价 | 说明 |
|---------------|---------|------|
| `background: rgba()` | `background-color: rgba()` | 完全支持 |
| `border-radius: 22px` | `border-radius: 22px` | 完全支持 |
| `border: 1px solid rgba()` | `border: 1px solid rgba()` | 完全支持 |
| `padding` | `padding` | 完全支持 |
| `font-size/weight` | `font-size/weight` | 完全支持 |
| `color` | `color` | 完全支持 |
| 色调变量 | Python 侧 dict → QSS 字符串 format | 动态生成 QSS |

### 2.2 QSS 不支持，需 PyQt 原生实现

| Mineradio CSS | QSS | PyQt 替代方案 | 难度 |
|---------------|-----|-------------|------|
| `backdrop-filter: blur()` | ❌ | `QGraphicsBlurEffect` 对底层 widget | ⭐⭐⭐ |
| `box-shadow` (外层) | ❌ | `QGraphicsDropShadowEffect` | ⭐ |
| `inset box-shadow` (内阴影) | ❌ | 自定义 `paintEvent` + `QLinearGradient` | ⭐⭐ |
| `::before / ::after` 伪元素 | ❌ | Overlay widget 或 `paintEvent` | ⭐⭐ |
| `color-mix()` | ❌ | Python 侧预计算颜色（`QColor.lighter/darker` 或手动混合） | ⭐ |
| `transition` | ❌ | 不需要（hover 是即时切换，无动画） | — |
| `animation / @keyframes` | ❌ | `QPropertyAnimation` | ⭐⭐ |
| `transform: rotate(3deg)` | ❌ | `QPainter::rotate()` + `drawPixmap()` | ⭐ |
| `linear-gradient()` | ❌（QSS 部分支持但不稳定） | `paintEvent` 中用 `QLinearGradient` | ⭐⭐ |

### 2.3 实现策略

| 效果 | 推荐方案 | 成本 |
|------|---------|------|
| 半透明玻璃背景 | 直接用 `rgba()` 背景色，不做 blur（纯色暗底上 blur 不可见，跳过） | 免费 |
| 顶部高光线 | `paintEvent` 画一条 1px 的白色渐变线，或用一个高 1px 的 QFrame | ⭐ |
| 多层阴影 | `QGraphicsDropShadowEffect` — PyQt 内置 | ⭐ |
| 悬浮上浮 | `QPropertyAnimation` 动画 `pos` 或 `geometry`，配合 `eventFilter` 监听 hover | ⭐⭐ |
| 色调变量系统 | Python `dataclass CardTone` + 动态 QSS 生成（本质上是 [[theme-design]] 的扩展） | ⭐⭐ |
| 封面微旋转 | `QPixmap` + `QPainter::rotate(3)` 预渲染 | ⭐ |
| 空闲呼吸动画 | `QPropertyAnimation` + staggered `QTimer` | ⭐⭐ |

---

## 3. 设计原则提炼（与框架无关）

以下原则适用于任何 UI 框架，包括 PyQt6：

### 原则 1：多层景深 > 单层平面

不要只用一种背景色。至少叠两层：
- 卡片背景（稍亮） + 内高光线（1px 白色半透明） → 立刻有"厚度"

### 原则 2：悬浮反馈要"四维同步"

hover 时同时改：位置（上浮）、边框（染色）、背景（变亮）、阴影（扩散+光晕）。
只改一个属性 = 感觉是 bug；四个同时改 = 感觉是设计。

### 原则 3：色调变量 > 硬编码颜色

定义少量语义色调变量（如 tone_a / tone_b / tone_c），所有子元素颜色从中派生。
好处：一套 CSS 结构，N 套配色方案；新加平台卡片只需换调色板。

### 原则 4：装饰元素宁少勿多，但要"有"

Mineradio 每张卡片只有两个装饰元素（对角线渐变 + 右侧条纹），但足以打破"纯色矩形"的单调感。
关键：装饰用透明度压低到 0.2-0.25，不能抢内容的风头。

### 原则 5：微旋转打破"数字感"

封面图转 3° → 从"对齐的像素"变成"随手放的照片"。这是最便宜但最有效的"人性化"手段。

### 原则 6：缓动函数决定品质感

`cubic-bezier(.16, 1, .3, 1)` — 快速启动 + 轻微过冲 + 柔和落地。
QPropertyAnimation 用 `QEasingCurve.OutBack` 可近似。

---

## 4. 直接照搬清单

### 4.1 不依赖新功能的（改 QSS 就行）

| 改动 | 文件 | 效果 |
|------|------|------|
| 圆角 16px → 22px | `template.py` 中 `#modeBtn` | 更柔和 |
| 边框透明度提高（`#252550` → `rgba(255,255,255,0.06)`） | `template.py` | 更精致 |
| 卡片背景加微弱的对角线渐变（用 `background-color` + 扁平纯色模拟） | `template.py` | 打破纯色单调 |
| hover 时边框染上 accent 色（已有雏形，需加强对比度） | `template.py` | 反馈更强 |

### 4.2 需要加少量 Python 代码的

| 改动 | 实现位置 | 效果 |
|------|---------|------|
| 卡片顶部内高光线（1px） | 自定义 `CardWidget.paintEvent()` 或嵌入 QFrame | 玻璃边缘感 |
| 卡片悬浮上浮 3px | `eventFilter` + `QPropertyAnimation` | 物理反馈 |
| 封面图微旋转 3° | `_platform_card()` 中预旋转 pixmap | 打破数字感 |
| `CardTone` 数据类 + 按平台自动选色调 | `src/theme/card_tone.py` | 每张卡片独立配色 |
| `QGraphicsDropShadowEffect` | 在 `_platform_card()` 中给 btn 设置 | 阴影景深 |

### 4.3 较复杂但值得做的

| 改动 | 实现位置 | 效果 |
|------|---------|------|
| 空闲呼吸动画（窗口空闲 5s 后卡片微微浮动） | ModePage 中 QTimer + QPropertyAnimation | 活的感觉 |
| 装饰 overlay（对角线渐变层） | 自定义 `GradientOverlay` widget 叠在卡片上 | 材质感 |
| 切换卡片时的涟漪动画 | `QPropertyAnimation` + `QGraphicsOpacityEffect` | 过渡品质感 |

---

## 5. 对 Origami 当前页面的具体改造建议

### 5.1 平台卡片 (`mode_page.py` — `_platform_card()`)

**现状**：
```python
btn.setStyleSheet("""
    QPushButton#modeBtn {
        background-color: #12122A;
        border: 2px solid #252550;
        border-radius: 16px;
    }
""")
```

**改造后**（伪代码，展示方向）：
```python
card_tone = TONES[platform_id]  # 抖音→暖红, B站→蓝粉

btn.setStyleSheet(f"""
    QPushButton#modeBtn {{
        background-color: rgba({card_tone.bg_rgb}, 0.75);
        border: 1px solid rgba(255,255,255, 0.06);
        border-radius: 22px;
        padding: 18px;
    }}
    QPushButton#modeBtn:hover {{
        background-color: rgba({card_tone.hover_rgb}, 0.85);
        border-color: rgba({card_tone.accent_rgb}, 0.42);
        /* 注：上浮 + 阴影由 eventFilter + QGraphicsDropShadowEffect 处理 */
    }}
""")
```

### 5.2 列表卡片 (`batch_page.py` / `single_page.py`)

Mineradio 的 `.pl-card` 模式：
- 左侧 44×44 缩略图（圆角 8px）
- 右侧标题 + 副标题
- hover: 背景微亮 + 边框微亮
- 间距 7px

Origami 的视频列表项完全可以直接套用这个布局。

### 5.3 设置页面的预设主题卡片

当前 [[theme-design]] 中计划的预设卡片网格（2列），和 Mineradio 的 `.preset-card` 几乎一样：
- 2 列网格 `grid-template-columns: repeat(2, 1fr)`
- `border-radius: 11px`，hover 边框变亮
- 选中态：边框变 accent 色 + 内发光

这个可以直接在 Origami 的主题选择器里实现。

---

## 6. 与现有主题系统的整合

[[theme-design]] 已规划了 28 个 Design Token + 7 套预设主题。Mineradio 的卡片设计在主题系统上的扩展：

```
现有 Token (28个):
  bg_window, bg_card, bg_input, bg_hover, bg_selected,
  text_primary, text_secondary, text_disabled, text_on_accent,
  accent, accent_hover, accent_pressed,
  border_default, border_focus, divider,
  success, warning, error, info,
  card_border, bg_raised,
  scrollbar_bg, scrollbar_handle, scrollbar_hover,
  danger, danger_hover, disabled_bg, link

新增 Token (6个，可选):
  card_glass_bg        — 卡片玻璃背景色 (rgba)
  card_glass_border    — 卡片玻璃边框色 (rgba, 极淡)
  card_inner_glow      — 卡片顶部高光线颜色 (rgba 白)
  card_shadow_color    — 卡片阴影颜色 (rgba 黑)
  card_tone_a          — 卡片色调 A (用于渐变装饰)
  card_tone_b          — 卡片色调 B (用于渐变装饰)
```

前 4 个对所有卡片生效（全局玻璃效果），后 2 个按平台/页面动态注入。

---

## 7. 实现优先级

```
P0（改 QSS，30 分钟）:
  ├─ 圆角 16px → 22px
  ├─ 边框透明度降低（淡到几乎看不见）
  └─ hover 边框染 accent 色增强

P1（加少量代码，2-3 小时）:
  ├─ CardTone 数据类 + 按平台配色
  ├─ QGraphicsDropShadowEffect 阴影
  ├─ eventFilter + QPropertyAnimation 悬浮上浮
  └─ 封面图预旋转 3°

P2（品质提升，4-6 小时）:
  ├─ 卡片顶部高光线（自定义 paintEvent）
  ├─ 对角线渐变 overlay
  └─ 空闲呼吸动画

P3（锦上添花，视情况）:
  ├─ QGraphicsBlurEffect 真·玻璃效果
  └─ 卡片切换涟漪动画
```

---

## 8. 关键数值速查表

| 设计参数 | Mineradio 值 | Origami 建议值 | 说明 |
|---------|-------------|---------------|------|
| 卡片圆角 | 22px | 20-22px (font_scale) | 大圆角 → 柔和 |
| 卡片边框色 | `rgba(255,255,255, 0.085)` | `rgba(255,255,255, 0.06)` | 极淡 |
| hover 边框色 | `color-mix(tone-a 42%, 白18%)` | `rgba(accent_r, accent_g, accent_b, 0.42)` | 染色调 |
| 内高光 | `inset 0 1px 0 rgba(白,6%)` | `rgba(255,255,255, 0.06)` 顶部 1px | 玻璃边缘 |
| 悬浮上浮 | `translateY(-3px)` | 动画位移 -3px (逻辑像素) | 物理反馈 |
| 阴影偏移 | `0 20px 64px` | `QGraphicsDropShadowEffect(blurRadius=24, offset=0,6)` | 浮动感 |
| 缓动曲线 | `cubic-bezier(.16, 1, .3, 1)` | `QEasingCurve.OutBack` (近似) | 弹性不夸张 |
| 封面旋转 | `rotate(3deg)` | `QPainter::rotate(3)` | 打破对齐 |
| 空闲浮动周期 | 7.4s, 振幅 2px | 同 | 呼吸感 |
| 过渡时长 | 220ms | 220ms (QPropertyAnimation duration) | 快速不拖沓 |

---

*分析完毕 · 2026-06-24 · Gali*
