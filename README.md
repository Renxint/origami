# Origami · 多功能内容下载工具

> 抖音单视频 / 图集 / 实况照片 / 主页批量下载 · 后续支持 B站、微博、YouTube

![Platform](https://img.shields.io/badge/platform-Windows-blue) ![Python](https://img.shields.io/badge/python-3.12+-green) ![License](https://img.shields.io/badge/license-MIT-red)

---

## 功能

- **单视频下载** — 粘贴分享链接，下载无水印视频、图集、实况照片
- **主页批量下载** — 输入用户主页链接，自动翻页下载全部公开作品
- **分享口令解析** — 直接粘贴"长按复制此条消息..."自动识别
- **剪贴板监听** — 复制抖音链接自动弹窗询问是否下载
- **扫码登录** — 内嵌浏览器打开抖音网页，扫码后自动保存登录状态
- **反爬代理** — Node.js Puppeteer 代跑 API，绕过 a_bogus / msToken 签名

---

## 快速开始

### 环境要求
- Python 3.12+
- Node.js（用于 Puppeteer API 代理）
- Chrome 或 Edge 浏览器

### 安装运行

```bash
# 1. 克隆
git clone https://gitee.com/Renxint/origami.git
cd origami

# 2. 安装依赖
pip install -r requirements.txt
cd sign-server && npm install && cd ..

# 3. 启动
python main.py
```

### 首次使用

1. 启动后点击首页「抖音」卡片
2. 点击底部「未登录」→ 在弹出的浏览器中扫码登录抖音
3. 登录成功后即可下载

---

## 项目结构

```
Origami/
├── main.py                     # 入口
├── src/
│   ├── environ.py              # 环境路径解析
│   ├── config.py               # 全局配置
│   ├── api.py                  # 抖音 HTTP API（requests 直连）
│   ├── cookie.py               # Cookie 管理（base64 + browser-cookie3 + WebView 登录）
│   ├── downloader.py           # 通用下载器
│   ├── utils.py                # 工具函数
│   ├── webview_api.py          # Puppeteer API 代理
│   ├── fonts.py                # 字体大小缩放工具
│   ├── stylesheet.py           # 暗色 QSS 样式表
│   ├── settings/               # 配置管理
│   │   ├── schema.py           # Schema + 默认值 + 校验
│   │   └── store.py            # 线程安全持久化
│   ├── platforms/              # 平台适配器
│   │   ├── base.py             # 抽象基类（MediaItem, AuthorInfo）
│   │   └── douyin.py           # 抖音适配器
│   └── gui/                    # PyQt6 用户界面
│       ├── main_window.py      # 主窗口（导航 / 托盘 / 剪贴板监听）
│       ├── pages/              # 页面模块
│       │   ├── mode_page.py    # 首页（平台选择）
│       │   ├── douyin_page.py  # 抖音功能页
│       │   ├── single_page.py  # 单视频下载
│       │   ├── homepage_page.py# 主页批量下载
│       │   ├── settings_page.py# 设置（侧边栏布局）
│       │   └── update_page.py  # 版本更新
│       ├── dialogs/            # 对话框
│       └── widgets/            # 可复用控件
├── sign-server/                # Node.js 服务
│   ├── bootstrap.js            # 视频签名服务
│   └── api-call.js             # API 代理（Puppeteer）
├── translations/               # Qt 中文翻译
└── src/gui/assets/icons/       # 平台图标
```

---

## 新增平台

三步接入新平台：

1. 创建 `src/platforms/bilibili.py`
2. 继承 `PlatformAdapter`，实现 `resolve_url` / `fetch_media` / `fetch_author` / `fetch_posts`
3. 末尾调用 `register_platform(BilibiliAdapter)`

GUI 自动识别新平台，无需改动页面代码。

---

## 快捷键

| 快捷键 | 功能 |
|--------|------|
| `Ctrl + H` | 回到首页 |
| `Ctrl + ,` | 打开设置 |
| `Ctrl + Q` | 退出 |
| `Esc` | 最小化到托盘 |

---

## 技术栈

Python 3.12 · PyQt6 · Node.js · Puppeteer · requests · browser-cookie3

---

## 许可证

MIT License — © 2026 Renxint
