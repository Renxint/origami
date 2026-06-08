# Origami

多功能内容下载工具 — 支持抖音单视频/图集/实况照片/主页批量下载。

**平台支持：** 抖音 | 即将支持：B站 · 微博 · YouTube

## 快速开始

```bash
pip install -r requirements.txt
python main.py
```

## 项目结构

```
Origami/
├── main.py                 # 入口
├── src/
│   ├── environ.py          # 路径解析
│   ├── config.py           # 全局配置
│   ├── api.py              # 抖音 API
│   ├── downloader.py       # 通用下载器
│   ├── utils.py            # 工具函数
│   ├── theme/              # 主题系统
│   │   ├── colors.py       # 色板 token
│   │   └── stylesheet.py   # QSS 生成器
│   ├── settings/           # 配置管理
│   │   ├── schema.py       # Schema + 校验
│   │   └── store.py        # 持久化
│   ├── platforms/          # 平台适配器
│   │   ├── base.py         # 抽象基类
│   │   └── douyin.py       # 抖音适配器
│   └── gui/                # 用户界面
│       ├── main_window.py  # 主窗口
│       ├── pages/          # 页面模块
│       ├── dialogs/        # 对话框
│       └── widgets/        # 可复用控件
├── sign-server/            # Node.js 签名服务
├── translations/           # Qt 中文翻译
└── tests/                  # 测试
```

## 新增平台

1. 创建 `src/platforms/newplatform.py`
2. 继承 `PlatformAdapter`，实现抽象方法
3. 末尾调用 `register_platform(NewPlatform)`
4. GUI 自动识别

## 许可证

MIT License — (c) 2026 Renxint
