# Origami — 项目 CLAUDE.md

## 项目概述

**Origami** — 多平台个人内容备份工具（Personal Content Archive）。支持抖音/B站/微博/快手/小红书的内容下载与管理。

- 当前版本: V2 开发中
- 技术栈: Python 3.12 / aiohttp / HTML+CSS+JS
- 分支: `v2`
- 定位: 个人备份库，简洁工具型 UI（Obsidian 风格）

## 文档指引

| 目录/文件 | 说明 |
|-----------|------|
| `docs/README.md` | 文档索引 |
| `docs/requirements.md` | 产品需求规格说明书 |
| `docs/architecture.md` | 技术架构文档 |
| `docs/design-spec.md` | UI 设计规范（布局/主题/交互） |
| `docs/dev-guide.md` | 开发执行指南（编码规范/命令/测试） |
| `docs/roadmap.md` | 产品路线图 |
| `docs/api-reference.md` | API 参考 |
| `dev-logs/YYYY-MM-DD.md` | 每日开发日志 |
| `同类项目对比分析.md` | 竞品分析 |
| `注意事项.md` | 合规策略 |
| `DEVELOPMENT.md` | V2 开发记录（历史） |

## 关键文件

| 文件 | 用途 |
|------|------|
| `src/main.py` | CLI 入口 (~950行，7种下载模式) |
| `src/server.py` | V2 Web UI 后端 (aiohttp) |
| `src/platforms/douyin.py` | 抖音 API 适配器 |
| `src/platforms/base.py` | PlatformAdapter 基类 + MediaItem/AuthorInfo |
| `src/api.py` | DouyinAPI 纯 HTTP 客户端 |
| `src/downloader.py` | 文件下载器 |
| `src/signer.py` | Playwright 签名（保留，未使用） |
| `src/webview_api.py` | 登录桥接（已简化为 no-op） |
| `ui/pages/splash.html` | 启动页 |
| `ui/pages/home.html` | 首页 |
| `ui/pages/login.html` | 登录页 |
| `ui/js/api.js` | 前端 API 桥接 |
| `ui/css/themes.css` | 主题系统 |

## 开发工作流

1. **修改前**: 阅读 `docs/` 中对应的规范文件
2. **修改后**: `python -c "from src.main import main"` 验证编译
3. **每日结束**: 更新 `dev-logs/YYYY-MM-DD.md`（已完成/待办/问题/commit 统计）
4. **提交**: 每个功能点单独 commit，不跨功能混合提交
5. **不推远端**: 当前版本未完善，只在本地 git 管理

## CLI 命令

```bash
python -m src.main cli <链接>                        # 自动识别
python -m src.main cli single|batch|like|collection|mix|music|live <链接>
python -m src.main login                              # 扫码登录
python -m src.main server --port 8765                 # 启动 Web UI
```

可选参数: `--count N` `--dir PATH` `--image-format webp|jpeg|jpg` `--threads 30` `--include-long` `--duration 60`

## 设计原则

- **统一输入框**: 一个输入框自动检测所有平台链接，路由到对应 adapter
- **左侧边栏**: 首页 / 订阅 / 主页(喜欢收藏音乐) / 直播(订阅+手动) / 设置 / 更多
- **主题系统**: CSS 变量驱动，可 DIY 切换
- **跨平台 Adapter**: PlatformAdapter 基类 → DouyinAdapter / BilibiliAdapter / ...
- **增量同步**: 订阅作者 → 自动检测新作品 → 弹窗提醒 → 选择下载

## 当前进度

CLI 7 种模式全通。下一步: V2 UI MVP（统一输入框首页 + 侧边栏 + 订阅管理）。
