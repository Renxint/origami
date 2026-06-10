# 测试项目总结

## 单视频 / 用户信息

| 脚本 | 功能 | 方法 | 结论 |
|------|------|------|------|
| `test_single_info.py` | 单视频统计信息（点赞/评论/分享/收藏） | HTTP 直连 | ✅ `statistics` 字段齐全 |
| `test_profile.py` | 获取自己 sec_uid + 头像 + 喜欢总数 | HTTP + Puppeteer | ✅ 可用 |

## 实况检测

| 脚本 | 功能 | 方法 | 结论 |
|------|------|------|------|
| `test_live_photo.py` | 检测主页作品的实况识别 | HTTP 直连 | `is_live_photo` 不可靠 |
| `test_live3.py` | 单个实况作品的完整视频数据 | HTTP + sign-server | 每张图片自带 video |
| `test_compare.py` | 对比图集 vs 实况的字段差异 | HTTP 直连 | **`media_type=2` 图集，`=42` 实况** |

## 评论区

| 脚本 | 功能 | 方法 | 结论 |
|------|------|------|------|
| `test_comment.py` | 评论区内容 + 表情包下载 | HTTP ❌ → Puppeteer ✅ | 评论/回复/表情包均可获取，带完整指纹参数 |

输出文件：
- `tests/data/comments_raw.json` — 评论原始 JSON
- `tests/data/comments_img_raw.json` — 含表情包标记的评论
- `tests/data/comments.md` — 格式化 Markdown
- `tests/data/comment_images/` — 下载的表情包图片

## 合集 / 短剧

| 脚本 | 功能 | 方法 | 结论 |
|------|------|------|------|
| `test_mix_video.py` | 合集内作品列表 | HTTP + Puppeteer + SDK | ❌ Janus 网关拒绝 |
| `mix-test.js` | 合集页请求拦截分析 | Puppeteer 完整 SDK | ❌ 所有 mix API 返回 "Unsupported path" |
| `test_mix_alt.py` | 合集内容替代方案 | 作品列表 `mix_info` 过滤 | ✅ **可行** |

### 合集内容获取方案（已验证）

合集 API 被封，但每个作品的 `aweme.mix_info` 字段自带合集归属：

```json
"mix_info": {
  "mix_id": "7514361363695683611",
  "mix_name": "砚底鸣蝶",
  "cover_url": {...}
}
```

**流程**：翻页拉用户全部作品 → 按 `mix_info.mix_id` 过滤 → 得到合集内作品 → 正常下载。

已用煎饼果仔（126 作品，7 页）验证，筛出「砚底鸣蝶」3 个视频。用户作品数越多越慢，但可接受。短剧系列同理（`mix_info.mix_id` 关联到系列）。

## 喜欢列表

| 测试 | 功能 | 方法 | 结论 |
|------|------|------|------|
| `test_comment.py` 内嵌测试 | 自己的喜欢列表翻页 | Puppeteer `_call_api` | ✅ 翻页正常（58+条） |
| — | 他人的喜欢列表 | — | 取决于 `show_favorite_list` 隐私设置 |

## 文章（长文）

`media_type=43`, `aweme_type=163`，抖音长文章类型。

| 字段 | 示例 |
|------|------|
| `article_info.article_title` | 我复读一年的意义是什么? |
| `article_info.article_content` → `long_article_abstract` | 正文 451 字 |
| `article_info.read_time` | 2 分钟 |
| `article_info.fe_data` → `head_poster_list` | 头图 URL |
| `article_info.fe_data` → `article_num` | 第 1062 篇 |
| `statistics` | 点赞/评论/分享/收藏 |
| `author` | 昵称、粉丝数 |

正文解析：`json.loads(article_info.article_content)['long_article_abstract']`

- 纯文字，无图片/视频
- HTTP 直连可获取全部内容

---

## 其他

| 脚本 | 功能 |
|------|------|
| `test_close.py` | 关闭/托盘逻辑测试 |
