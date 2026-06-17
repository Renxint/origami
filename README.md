<div align="center">

<a href="https://github.com/Renxint/origami">
  <img src="https://capsule-render.vercel.app/api?type=waving&color=timeAuto&height=160&section=header&text=Origami%20%C2%B7%20%E6%8A%98%E4%BD%A0%E6%89%80%E7%88%B1&fontSize=45&fontAlignY=35" width="100%" alt="Origami">
</a>

<p align="center">
  <a href="https://github.com/Renxint/origami">
    <img src="https://readme-typing-svg.demolab.com?font=JetBrains+Mono&weight=600&size=18&duration=3500&pause=1000&color=38BDF8&center=true&vCenter=true&width=500&lines=%E6%8F%92%E4%BB%B6%E5%BC%8F%E6%9E%B6%E6%9E%84+%C2%B7+%E7%BA%AF%E6%9C%AC%E5%9C%B0%E8%BF%90%E8%A1%8C;PyQt6+%2B+Puppeteer+%2B+Node.js;%E6%96%B0%E5%B9%B3%E5%8F%B0%E4%B8%89%E6%AD%A5%E5%85%A5%E9%A9%BB" alt="Typing SVG">
  </a>
</p>

<img src="logo.png" alt="Origami" width="140">

![visitors](https://count.getloli.com/get/@origami?theme=booru-lewd)

</div>

<p align="center">
  <img src="https://img.shields.io/badge/platform-Windows-blue?logo=windows" alt="Platform">
  <img src="https://img.shields.io/badge/python-3.12+-green?logo=python" alt="Python">
  <img src="https://img.shields.io/badge/license-MIT-red" alt="License">
  <img src="https://img.shields.io/badge/version-0.6.0-E11D48" alt="Version">
  <img src="https://img.shields.io/github/stars/Renxint/origami?style=flat" alt="Stars">
  <img src="https://img.shields.io/github/downloads/Renxint/origami/total" alt="Downloads">
  <img src="https://img.shields.io/github/repo-size/Renxint/origami" alt="Repo Size">
  <img src="https://img.shields.io/github/last-commit/Renxint/origami" alt="Last Commit">
</p>

<p align="center">
  <a href="https://github.com/Renxint/origami">
    <img src="https://skillicons.dev/icons?i=py,qt,nodejs,js,html,css,bash,git,github,githubactions" alt="Tech Stack">
  </a>
</p>

<div align="center">
  <img src="https://raw.githubusercontent.com/Renxint/origami/main/docs/demo.gif" alt="Origami Demo" width="700">
</div>

<div align="center">

👏 使用中遇到问题？欢迎提交 [Issue](https://github.com/Renxint/origami/issues)

</div>

---

## ✨ 亮点

| 🧩 插件式架构 | 🎨 原生桌面体验 | 🛡️ 纯本地 · 无数据收集 |
|:---:|:---:|:---:|
| PlatformAdapter 设计模式 | PyQt6 深色/亮色主题 | 所有数据留在你的电脑上 |
| 新平台三步入驻 | 托盘运行 · 快捷键 · 单实例 | SignPath 代码签名 · MIT 开源 |

> 💡 Origami 是一个**多平台内容管理桌面应用**，采用插件式架构。当前支持多个内容平台的内容获取与本地归档。本项目也是 Python 桌面应用开发与网络协议逆向的**学习实践**。

---

## 🏗️ 技术架构

```
src/platforms/          ← 插件式平台适配器（策略模式 + 注册表）
  ├── base.py           ← PlatformAdapter 抽象基类（接口契约）
  ├── douyin.py         ← 平台适配器实现
  └── __init__.py       ← 全局注册表，新平台一行 import 即可接入

sign-server/            ← Node.js 签名与反爬服务（独立进程）
src/gui/                ← PyQt6 原生桌面界面
src/webview_api.py      ← Puppeteer 自动化引擎
```

**核心技术栈：** Python 3.12 · PyQt6 · Node.js · Puppeteer · requests

**工程化：** Inno Setup 安装器 · SignPath 代码签名 · 单实例检测 · 自动更新

---

## 📥 安装

| 方式 | 链接 |
|------|------|
| **安装包（推荐）** | [📦 下载 Origami_v0.6.0_setup.exe](https://github.com/Renxint/origami/releases/latest) |
| **免安装版** | [📁 下载便携版](https://github.com/Renxint/origami/releases) |

---

## 📖 使用指南

### 安装

1. 下载 `Origami_v0.6.0_setup.exe`，双击安装
2. 或在 [Releases](https://github.com/Renxint/origami/releases) 下载免安装版

### 登录

1. 启动后点击首页平台卡片
2. 点击右上角「点击登录 →」
3. 在弹出的浏览器中扫码登录
4. 登录成功后自动返回，显示头像和昵称

### 单个作品

1. 首页 → 选择平台 → 单个作品
2. 粘贴分享链接或口令
3. 点击「开始」
4. 图集作品可选择要保存的图片
5. 完成后可打开所在文件夹

### 批量归档

1. 首页 → 选择平台 → 批量
2. 粘贴主页链接
3. 选择数量，点击「开始」
4. 支持暂停 / 取消

### 个人主页

1. 批量页 → 切换到「自己」标签
2. 登录后自动加载账号信息和作品统计
3. 点击「查看列表」→ 勾选 → 开始

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
- Node.js（用于签名服务）

### 启动

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

## 🔌 新增平台

三步接入新平台：

1. 创建 `src/platforms/newplatform.py`
2. 继承 `PlatformAdapter`，实现 `resolve_url` / `fetch_media` / `fetch_author` / `fetch_posts`
3. 在文件末尾调用 `register_platform(NewPlatformAdapter)`

GUI 自动识别所有已注册平台，无需修改界面代码。

---

## 📁 项目结构

```
Origami/
├── main.py              # 入口
├── src/
│   ├── environ.py       # 环境路径
│   ├── config.py        # 全局配置
│   ├── api.py           # HTTP API 客户端
│   ├── cookie.py        # Cookie 管理
│   ├── downloader.py    # 通用下载引擎
│   ├── utils.py         # 工具函数
│   ├── webview_api.py   # Puppeteer 自动化
│   ├── settings/        # 配置管理
│   ├── platforms/       # 平台适配器（插件式架构）
│   └── gui/             # PyQt6 界面
├── sign-server/         # Node.js 签名服务
├── translations/        # Qt 中文翻译
└── src/gui/assets/      # 图标 / 字体
```

---

## 🙏 致谢

- 代码签名由 [SignPath.io](https://signpath.io) 免费提供，证书由 [SignPath Foundation](https://signpath.org/) 颁发

---

## ⚠️ 声明

本项目为 Python 桌面应用开发与网络协议学习的**实践项目**，源代码仅用于个人研究。

请遵守各平台服务条款，在授权范围内使用。使用者自行承担所有责任。

---

## 👥 贡献者

<a href="https://github.com/Renxint/origami/graphs/contributors">
  <img src="https://contrib.rocks/image?repo=Renxint/origami" />
</a>

---

## 📊 项目活跃度

<p align="center">
  <a href="https://github.com/Renxint/origami">
    <img src="https://github-readme-activity-graph.vercel.app/graph?username=Renxint&repo=origami&theme=react-dark&hide_border=true" alt="Activity Graph" width="100%">
  </a>
</p>

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

<img src="https://capsule-render.vercel.app/api?type=waving&color=timeAuto&height=100&section=footer&text=&fontSize=0" width="100%">

Made with ❤️ by [Renxint](https://github.com/Renxint)

</div>
