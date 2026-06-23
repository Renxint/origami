# Origami 项目美化方案

## Context

Origami 是一个功能完善的抖音下载工具（Python 3.12 + PyQt6 + Node.js），目前 GitHub README 和项目展示比较朴素。参考 Catime（2.7k+ stars 的优秀开源项目）的美化实践，对 Origami 进行全面视觉和社区美化，提升项目吸引力和用户信任度。

---

## Catime vs Origami 对比分析

| 维度 | Catime ✅ | Origami 现状 ❌ |
|------|----------|---------------|
| 项目 Logo | 精美大图居中 | 无（只有一个 ico 文件） |
| 演示视频 | 有 GIF 动图 | 无 |
| Badge 矩阵 | HelloGitHub + Trendshift + ProductHunt | 只有平台/语言/许可证 |
| 访问计数 | count.getloli.com 计数器 | 无 |
| 社区链接 | Discord + QQ 群 | 无 |
| Star History | star-history.com 图表 | 无 |
| 贡献者墙 | 头像 + 名字列表 | 无 |
| Sponsors | 赞助商展示区 | 无 |
| 专属域名 | catime.vladelaina.com | 无 |
| 独立网站 | 作者个人站 + 项目站 | 无 |
| 包管理器 | winget 可安装 | 无 |
| 代码签名 | SignPath（已配置） | SignPath（配置中） |
| 记忆点 | "Only 995KB" / "pure C" | 无突出卖点 |
| Repobeats | repobeats 分析图 | 无 |

---

## 美化方案（按优先级排序）

### 🌟 第一优先级：README 大改造（影响最大、成本最低）

**1.1 顶部品牌区**
- 居中放置项目 Logo（用现有 `app.ico` 转 PNG 作为临时方案，后续找设计师画一个）
- 副标题：`Origami · 折你所爱，存你所想`
- 一句话介绍：`Windows 端抖音/B站/微博多平台内容下载工具 · 纯 Python 打造 · 界面优雅`

**1.2 演示 GIF**
- 录制软件核心操作流程（录屏 → 转 GIF）
- 建议录制：登录 → 粘贴链接 → 下载 → 查看结果 的完整流程

**1.3 Badge 矩阵升级**
加入：
- HelloGitHub 推荐 badge（需去 hellogithub.com 提交）
- 下载计数 badge（GitHub release assets 统计）
- `platform-windows` → 加 `stars`、`license-MIT`（已有）、`python-3.12+`
- 可选：Trendshift 提交

**1.4 访问计数器**
- 用 `count.getloli.com` 或 `moe-counter.glitch.me`
- 一行 markdown 图片即可

**1.5 核心卖点提炼**
当前无记忆点。建议提炼：
- `仅 132MB 安装包`（你 commit 里提过）
- `支持三大平台：抖音 · B站 · 微博`
- `Puppeteer 智能反爬 · 无需手动操作`

**1.6 贡献者墙**
- 用 `contrib.rocks` 自动生成
- 一行 URL：`https://contrib.rocks/image?repo=Renxint/origami`

**1.7 Star History**
- 用 `star-history.com` 自动生成图表
- 一行 markdown 图片

**1.8 Repobeats 分析图**
- 用 `repobeats.axiom.co` 嵌入
- 展示 commit 活跃度

**1.9 下载引导更醒目**
- 仿 Catime 样式：居中大号按钮 + Winget 命令
- 添加 `winget` 包（需提交 manifest 到 winget-pkgs）

---

### 🌟 第二优先级：独立项目网站

参考 Catime 的 `catime.vladelaina.com`，为 Origami 建一个简洁的项目站：

**方案 A（推荐）：GitHub Pages + 单页 HTML**
- 免费托管在 `renxint.github.io/origami`
- 纯静态 HTML/CSS，参考 vladelaina.com 的风格
- 包含：下载按钮、功能介绍、使用教程、FAQ

**方案 B：购买域名**
- 可选 `origami.app` 或类似域名
- 指向 GitHub Pages

---

### 🌟 第三优先级：社区建设

- **QQ 群**：创建 Origami 用户群（放 README 醒目位置）
- **Discord**（可选）：如果面向海外用户
- **HelloGitHub 投稿**：国内最大的开源推荐平台，能带大量曝光
- **少数派/小众软件 投稿**：国产软件推荐渠道

---

### 🌟 第四优先级：包管理器分发

- **Winget**：仿 Catime `winget install --id VladElaina.Catime`
  - 需提交 manifest PR 到 https://github.com/microsoft/winget-pkgs
- **Chocolatey**（可选）

---

## 需修改的文件

| 文件 | 改动内容 |
|------|---------|
| `README.md` | 全面改造：品牌区、GIF、badge、计数器、卖点、贡献者墙、star history、下载引导 |
| `C:\Users\lenovo\Desktop\` | 新增录屏 GIF 文件，放入仓库 |
| `docs/index.html`（新建） | GitHub Pages 项目站 |
| winget manifest（新建） | 提交到 winget-pkgs 仓库（PR） |

---

## 执行步骤

1. 先录一个 15-30 秒的操作演示 GIF
2. 改造 README.md（品牌区 + badge + 卖点 + 计数器 + 贡献者墙）
3. 提交 HelloGitHub 投稿
4. 创建项目 GitHub Pages
5. 提交 winget manifest PR

---

---

## 📚 相关文档

- [[注意事项]] — 合规约束（美化不能触碰的红线）
- [[同类项目对比分析]] — 竞品展示方式参考

---

## 验证方式

- 打开 GitHub 仓库页面，确认 README 渲染效果
- 在移动端查看 README，确认响应式
- 各 badge 链接可点击跳转正确
- GitHub Pages 网站可访问
