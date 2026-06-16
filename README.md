<div align="center">

<img src="logo.png" alt="Origami" width="128">

# Origami · 折你所爱，存你所想

**Windows 端多平台内容下载工具 · 纯 Python 打造 · 界面优雅**

抖音单视频 / 图集 / 实况照片 / 主页批量下载 · 即将支持 B站、微博

![visitors](https://count.getloli.com/get/@origami?theme=rule34)

</div>

<p align="center">
  <img src="https://img.shields.io/badge/platform-Windows-blue?logo=windows" alt="Platform">
  <img src="https://img.shields.io/badge/python-3.12+-green?logo=python" alt="Python">
  <img src="https://img.shields.io/badge/license-MIT-red" alt="License">
  <img src="https://img.shields.io/badge/version-0.6.0-E11D48" alt="Version">
  <img src="https://img.shields.io/github/stars/Renxint/origami?style=flat" alt="Stars">
  <img src="https://img.shields.io/github/downloads/Renxint/origami/total" alt="Downloads">
</p>

<!-- TODO: 替换为实际演示 GIF -->
<div align="center">
  <img src="https://raw.githubusercontent.com/Renxint/origami/main/docs/demo.gif" alt="Origami Demo" width="700">
</div>

<div align="center">

👏 使用中遇到问题？欢迎提交 [Issue](https://github.com/Renxint/origami/issues)

</div>

---

## ✨ 为什么选择 Origami？

| 🚀 极速下载 | 🎨 优雅界面 | 🛡️ 安全可靠 |
|:---:|:---:|:---:|
| Puppeteer 智能反爬 | PyQt6 现代 UI | MIT 开源 |
| 支持多任务并发 | 托盘最小化 | 无数据收集 · 本地运行 |
| 仅 132MB 安装包 | 暗色/亮色主题 | SignPath 代码签名 |

> 💡 不需要在手机上操作，不需要抓包，登录后粘贴链接即可下载。支持抖音视频、图集、实况照片，正在扩展 B站和微博。

---

## 📥 下载安装

| 方式 | 命令 / 链接 |
|------|------------|
| **安装包（推荐）** | [📦 下载 Origami_v0.6.0_setup.exe](https://github.com/Renxint/origami/releases/latest) |
| **免安装版** | [📁 下载便携版](https://github.com/Renxint/origami/releases) |

---

## 📖 使用指南

### 安装

1. 下载 `Origami_v0.6.0_setup.exe`，双击安装
2. 或在 [Releases](https://github.com/Renxint/origami/releases) 下载免安装版

### 登录

1. 启动后点击首页「抖音」卡片
2. 点击右上角「点击登录 →」
3. 在弹出的浏览器中扫码登录抖音
4. 登录成功后自动返回，右上角显示头像和昵称

### 单个作品下载

1. 首页 → 抖音 → 单个作品下载
2. 粘贴抖音分享链接或口令
3. 点击「开始下载」
4. 图集作品会弹出选择框，可勾选要下载的图片
5. 下载完成后右键列表可打开文件夹

### 批量下载他人主页

1. 首页 → 抖音 → 批量作品下载
2. 切换到「下载他人」标签
3. 粘贴用户主页链接
4. 选择数量，点击「开始下载」
5. 支持暂停 / 取消

### 下载自己主页

1. 批量作品下载页 → 切换到「自己」标签
2. 登录后自动加载账号信息和作品统计
3. 点击「查看列表」→ 勾选要下载的作品 → 开始下载

---

## ⌨️ 快捷键

| 快捷键 | 功能 |
|--------|------|
| `Ctrl + H` | 回到首页 |
| `Ctrl + ,` | 打开设置 |
| `Ctrl + Q` | 退出 |
| `Esc` | 最小化到托盘 |

---

## 🛠️ 从源码运行

### 环境要求

- Python 3.12+
- Node.js（用于 Puppeteer API 代理）

### 安装运行

```bash
git clone https://github.com/Renxint/origami.git
cd origami

# 安装 Python 依赖
pip install -r requirements.txt

# 安装 Node.js 依赖
cd sign-server && npm install && cd ..

# 启动
python main.py
```

---

## 📁 项目结构

```
Origami/
├── main.py              # 入口
├── src/
│   ├── environ.py       # 环境路径
│   ├── config.py        # 全局配置
│   ├── api.py           # 抖音 HTTP API
│   ├── cookie.py        # Cookie 管理
│   ├── downloader.py    # 通用下载器
│   ├── utils.py         # 工具函数
│   ├── webview_api.py   # Puppeteer API 代理
│   ├── settings/        # 配置管理
│   ├── platforms/       # 平台适配器
│   └── gui/             # PyQt6 界面
├── sign-server/         # Node.js 服务
├── translations/        # Qt 中文翻译
└── src/gui/assets/      # 图标 / 字体
```

---

## 🔌 新增平台

三步接入新平台：

1. 创建 `src/platforms/bilibili.py`
2. 继承 `PlatformAdapter`，实现 `resolve_url` / `fetch_media` / `fetch_author` / `fetch_posts`
3. 末尾调用 `register_platform(BilibiliAdapter)`

---

## 🧰 技术栈

Python 3.12 · PyQt6 · Node.js · Puppeteer · requests

---

## 🙏 致谢

- 代码签名由 [SignPath.io](https://signpath.io) 免费提供，证书由 [SignPath Foundation](https://signpath.org/) 颁发

---

## 👥 贡献者

<a href="https://github.com/Renxint/origami/graphs/contributors">
  <img src="https://contrib.rocks/image?repo=Renxint/origami" />
</a>

---

## ⭐ Star History

<a href="https://www.star-history.com/#Renxint/origami&Date">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/svg?repos=Renxint/origami&type=Date&theme=dark" />
    <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/svg?repos=Renxint/origami&type=Date" />
    <img alt="Star History Chart" src="https://api.star-history.com/svg?repos=Renxint/origami&type=Date" />
  </picture>
</a>

---

## 📄 许可证

MIT License — © 2026 Renxint

---

<div align="center">

Made with ❤️ by [Renxint](https://github.com/Renxint)

</div>
