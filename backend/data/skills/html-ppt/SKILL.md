---
name: html-ppt
description: "HTML PPT Studio — 创建专业级静态 HTML 演示文稿/PPT/幻灯片。Use when user asks for: (1) presentation, PPT, slides, deck, keynote, slideshow; (2) 幻灯片、演讲稿、做 PPT、做 slides; (3) 小红书图文; (4) reveal-style HTML deck; (5) any multi-slide pitch/report/sharing document. Triggers: presentation, ppt, slides, deck, keynote, reveal, slideshow, 幻灯片, 演讲稿, 分享稿, 小红书图文, pitch deck, tech sharing, technical presentation."
---

# html-ppt — HTML PPT Studio

创建专业 HTML 演示文稿。36 个主题、31 种布局、27 个动画，全部 token 化设计系统。

## 前置确认

开始前向用户确认：1) 内容与受众 2) 风格偏好（推荐 2-3 个主题）3) 是否使用完整 deck 模板。

主题快速推荐：技术→`tokyo-night`/`dracula`/`cyberpunk-neon`；小红书→`xiaohongshu-white`/`soft-pastel`；商务→`pitch-deck-vc`/`corporate-clean`；学术→`academic-paper`/`editorial-serif`。

## 工作流程（三步）

### Step 1: 读取模板

用 `read_file` 读取最接近的布局文件，理解 HTML 结构。布局在 `data/skills/html-ppt/assets/templates/single-page/<layout>.html`。常用布局：`cover`（封面）、`toc`（目录）、`section-divider`（章节分隔）、`bullets`（要点）、`two-column`（双栏）、`stat-highlight`（数据）、`kpi-grid`（KPI）、`code`（代码）、`timeline`（时间线）、`thanks`（结束）。完整列表见 `references/layouts.md`。

也支持 14 个完整 deck 模板：`data/skills/html-ppt/assets/templates/full-decks/<name>/`（pitch-deck / tech-sharing / weekly-report / xhs-post 等）。详见 `references/full-decks.md`。

### Step 2: 生成草稿 HTML

用 `write_file` 在 `data/skills/html-ppt/assets/` 下创建草稿（此目录下 `assets/` 相对路径才可用）。HTML 模板结构：

```html
<!DOCTYPE html>
<html lang="zh-CN" data-theme="主题名">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>标题</title>
  <link rel="stylesheet" href="fonts.css">
  <link rel="stylesheet" href="base.css">
  <link rel="stylesheet" id="theme-link" href="themes/主题名.css">
  <link rel="stylesheet" href="animations/animations.css">
</head>
<body data-themes="主题1,主题2,主题3" data-theme-base="themes/">
<div class="deck">
  <section class="slide" data-title="页面标题">...</section>
</div>
<script src="runtime.js"></script>
</body></html>
```

关键规则：
- 每页一个 `<section class="slide" data-title="...">`
- 所有颜色用 CSS 变量（`var(--text-1)`, `var(--accent)` 等），不要用字面颜色
- 始终从模板复制 slide 结构，替换内容
- Speaker notes 放 `<div class="notes">…</div>`（display:none，按 S 查看）
- 常用动画：封面用 `rise-in`/`blur-in`，内容用 `fade-up`，列表用 `stagger-list`，数字用 `counter-up`，章节用 `perspective-zoom`，结尾用 `confetti-burst`

### Step 3: 打包为自包含 HTML（必做）

草稿依赖外部文件，不可移植。用 `terminal` 调用打包脚本：

```bash
python data/skills/html-ppt/bundle.py <草稿路径> <输出路径>
```

示例：
```bash
python data/skills/html-ppt/bundle.py data/skills/html-ppt/assets/my-deck.html outputs/my-deck.html
```

脚本将所有 CSS/JS 内联，主题切换改为内联切换，生成 ~40KB 单文件。输出到 `outputs/` 目录。

**打包后删除草稿文件。最终交付 `outputs/` 下的文件。**

## 键盘操作

`← →` 翻页 · `T` 切主题 · `F` 全屏 · `O` 概览 · `S` 备注

## 参考资料（按需读取）

- `references/themes.md` — 36 个主题详细说明
- `references/layouts.md` — 31 种布局类型
- `references/animations.md` — 27 个 CSS + 20 个 Canvas 动画
- `references/full-decks.md` — 14 个完整 deck 模板
- `references/authoring-guide.md` — 完整创作流程
