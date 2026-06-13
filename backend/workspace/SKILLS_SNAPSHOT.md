# Available Skills
This document lists all available skills that the Agent can use.
**Total Skills**: 40
---

### agent-papers
**Description**: 搜索和浏览 AI Agent 研究论文库 (基于 Awesome-AI-Agents-Live 数据集，8800+ 篇论文)。Use when: (1) user asks about AI agent research papers, (2) user wants to find papers on specific agent topics (memory, planning, tools, collaboration, etc.), (3) user asks about trends or state-of-the-art in AI agents, (4) user needs paper recommendations by category/difficulty/score. NOT for: general academic search outside AI agents (use arxiv-search), non-research questions.
**Location**: `data/skills/agent-papers`
**Version**: 1.0.0
**Author**: miniClaw
**Tags**: ai-agents, research, papers, literature-search, knowledge-base

### arxiv-download-paper
**Description**: Download academic papers from arXiv.org in PDF format. Use when user asks to download research papers, save academic papers locally, or get PDF versions of arXiv papers. Supports downloading by arXiv ID, title search, author search, or keyword query. Papers are saved with sanitized titles as filenames to the downloads directory. Optionally adds papers to knowledge base.
**Location**: `data/skills/arxiv-download-paper`
**Version**: 1.0.0
**Author**: miniClaw
**Tags**: arxiv, download, pdf, academic, research, papers

### arxiv-search
**Description**: Search academic papers from arXiv, OpenAlex, and Semantic Scholar. Use when user asks to find research papers, search academic literature, get paper information, or verify citations.
**Location**: `data/skills/arxiv-search`
**Version**: 2.0.0
**Author**: miniClaw
**Tags**: arxiv, openalex, semantic-scholar, academic, research, papers, literature-search

### baidu-search
**Description**: Search the web using Baidu AI Search Engine (BDSE). Use for live information, documentation, or research topics.
**Location**: `data/skills/baidu-search`
**Version**: 1.0.0

### chart-plotter
**Description**: Create, customize, and export publication-ready charts (line, bar, scatter, pie, histogram) from CSV/Excel data with full Chinese font support, responsive layout, and Windows-compatible rendering. Use when user asks to: (1) 画图表、绘图、数据可视化; (2) 折线图、柱状图、散点图、饼图、直方图; (3) CSV/Excel 数据绘制; (4) mention chart type ('line chart', 'bar plot'); (5) 中文标签、标题、字体.
**Location**: `data/skills/chart-plotter`
**Version**: 1.0.0

### chrome-browser
**Description**: Use when user needs to: (1) control Chrome browser, web automation, web scraping; (2) 控制浏览器、网页自动化、网页抓取; (3) screenshot, form filling, page navigation, execute JS in browser; (4) 截图、填表、页面导航、执行JS; (5) interact with existing Chrome session. Triggers: browser, chrome, CDP, puppeteer, selenium, playwright, 浏览器, 网页自动化, 截图, 爬虫, 网页操作.
**Location**: `data/skills/chrome-browser`
**Version**: 1.0.0

### cluster_reduce_synthesis
**Description**: 将多个源的结构化提取结果，进行聚类合并压缩。
输出 cluster summaries + contradictions + consensus。

**Location**: `data/skills/cluster_reduce_synthesis`
**Version**: 1.0

### conference-paper
**Description**: Search and retrieve papers from top AI conferences (ICLR, NeurIPS, ICML, IJCAI, CVPR, ICCV, ACL). Use when: (1) user asks about papers from specific AI conferences, (2) user wants to find papers presented at ICLR/NeurIPS/ICML etc., (3) user needs to browse conference proceedings by year/topic, (4) user wants to download PDFs of conference papers. NOT for: general arXiv search (use arxiv-search), AI Agent specific papers (use agent-papers).
**Location**: `data/skills/conference-paper`
**Version**: 1.0.0
**Author**: miniClaw
**Tags**: conference, academic, research, papers, AI, ICLR, NeurIPS, ICML, CVPR, ACL

### deep_source_extractor
**Description**: 对单个来源全文进行深层结构化信息提取，输出详细结构化 JSON。
适用于论文、网页、PDF 转文本等长文档的研究信息提取。

**Location**: `data/skills/deep_source_extractor`
**Version**: 1.0

### design
**Description**: 综合设计技能：HTML 设计稿、演示文稿、交互原型、动画、线框图、Mondo 风格海报/书籍封面/专辑封面。 触发词：设计、design、mockup、prototype、landing page、deck、PPT、海报、poster、 书籍封面、book cover、专辑封面、album art、wireframe、故事板、storyboard、 可视化、visualize、Mondo、公众号封面、小红书配图、文章配图。 支持事实核验、品牌资产协议、10 种设计哲学方向、20+ 传奇艺术家风格、 多平台比例(21:9/16:9/3:4/1:1/9:16)、反 AI 烂设计规则、React+Babel 技术规范。
**Location**: `data/skills/design`
**Version**: 1.0.0

### diagram-plotter
**Description**: Create architecture diagrams, flowcharts, mind maps, UML diagrams, and network topology graphs from text descriptions. Use when user asks to: (1) 画架构图、画流程图、绘制拓扑图; (2) 思维导图、脑图; (3) UML类图、时序图; (4) 系统架构、微服务架构、网络拓扑; (5) specify nodes and edges relationships.
**Location**: `data/skills/diagram-plotter`
**Version**: 1.0.0

### distill-persona
**Description**: 从人物样本中蒸馏可复用的 Agent 技能 profile。当需要：(1) 从一组问答样本提取某人的决策风格和表达习惯， (2) 生成可执行的 skill profile (profile.json + skill.md + skill.py)，(3) 自动评判和修复 profile 质量， (4) 批量蒸馏多个 persona 为独立 skill 时使用。输入为人物名称 + 样本列表，输出为完整 skill 包。

**Location**: `data/skills/distill-persona`
**Version**: 1.0.0

### doc-creator
**Description**: Create professional DOCX/XLSX/PPTX documents with embedded images, tables, and formatted text. Use when user asks to: (1) 'create a Word/Excel/PowerPoint document'; (2) 'generate a report with charts'; (3) 'export data to Office format'; (4) 'make a presentation with slides'; (5) insert charts/images into documents.
**Location**: `data/skills/doc-creator`
**Version**: 1.0.0

### find-skill
**Description**: Search and install skills from external sources like GitHub, clawhub, and other skill repositories. Use when user asks to find, download, or install new skills from the internet.
**Location**: `data/skills/find-skill`
**Version**: 1.0.0
**Author**: miniClaw
**Tags**: skills, search, install, github, repository

### geometry-plotter
**Description**: 绘制2D/3D数学图形：函数图像、几何证明示意图、3D曲面等。输出 SVG 矢量图。Use when user asks to: (1) 画图、绘图、绘制图形; (2) 函数图像 (sin, cos, relu, sigmoid 等); (3) 几何证明示意图; (4) 数学定理可视化; (5) 坐标系、函数曲线、3D曲面.
**Location**: `data/skills/geometry-plotter`
**Version**: 1.0.0

### get_weather
**Description**: Get current weather and forecasts via wttr.in. Use when: user asks about weather, temperature, or forecasts for any location. Returns current conditions, temperature, humidity, wind, and forecasts. No API key needed.
**Location**: `data/skills/get_weather`
**Version**: 1.0.0

### github
**Description**: GitHub operations via `gh` CLI: issues, PRs, CI runs, code review, API queries. Use when: (1) checking PR status or CI, (2) creating/commenting on issues, (3) listing/filtering PRs or issues, (4) viewing run logs. NOT for: complex web UI interactions requiring manual browser flows (use browser tooling when available), bulk operations across many repos (script with gh api), or when gh auth is not configured.
**Location**: `data/skills/github`
**Version**: 1.0.0

### html-ppt
**Description**: HTML PPT Studio — 创建专业级静态 HTML 演示文稿/PPT/幻灯片。Use when user asks for: (1) presentation, PPT, slides, deck, keynote, slideshow; (2) 幻灯片、演讲稿、做 PPT、做 slides; (3) 小红书图文; (4) reveal-style HTML deck; (5) any multi-slide pitch/report/sharing document. Triggers: presentation, ppt, slides, deck, keynote, reveal, slideshow, 幻灯片, 演讲稿, 分享稿, 小红书图文, pitch deck, tech sharing, technical presentation.
**Location**: `data/skills/html-ppt`
**Version**: 1.0.0

### research_report_writer
**Description**: 基于综合后的 reduced_json 撰写研究报告，
强制使用引用标注 [S1][S2]。

**Location**: `data/skills/research_report_writer`
**Version**: 1.0

### scale_down_analyze_python
**Description**: No description
**Location**: `data/skills/scale_down_analyze_python`
**Version**: 1.0.0

### scale_down_fix_bug
**Description**: No description
**Location**: `data/skills/scale_down_fix_bug`
**Version**: 1.0.0

### scale_down_refactor_module
**Description**: No description
**Location**: `data/skills/scale_down_refactor_module`
**Version**: 1.0.0

### skill-creator
**Description**: Create or update skills. Use when designing, structuring, validating, or packaging skills with scripts, references, and assets.
**Location**: `data/skills/skill-creator`
**Version**: 1.0.0

### skill_validator
**Description**: Validate skill files before use. Use when: loading new skills, verifying skill integrity, checking skill metadata. Checks for: required fields, valid syntax, security issues.
**Location**: `data/skills/skill_validator`
**Version**: 1.0.0

### tool_restricted_analyze_python
**Description**: No description
**Location**: `data/skills/tool_restricted_analyze_python`
**Version**: 1.0.0

### tool_restricted_fix_bug
**Description**: No description
**Location**: `data/skills/tool_restricted_fix_bug`
**Version**: 1.0.0

### animejs
**Description**: Anime.js adapter patterns for HyperFrames. Use when writing Anime.js animations or timelines inside HyperFrames compositions, registering animations on window.__hfAnime, making Anime.js seek-driven and deterministic, or translating Anime.js examples into render-safe HyperFrames HTML.
**Location**: `data/skills/hyperframes/skills/animejs`
**Version**: 1.0.0

### contribute-catalog
**Description**: Author a new HyperFrames registry block (caption style, VFX block, transition, lower third) or component (text effect, overlay, snippet) and ship it as an upstream PR to the hyperframes repo. Use ONLY when the user wants to CONTRIBUTE to the public catalog — for in-project caption/transition authoring use the `hyperframes` skill, for installing existing registry items use the `hyperframes-registry` skill.
**Location**: `data/skills/hyperframes/skills/contribute-catalog`
**Version**: 1.0.0

### css-animations
**Description**: CSS animation adapter patterns for HyperFrames. Use when authoring CSS keyframes, animation-delay based timing, animation-fill-mode, animation-play-state, or CSS-only motion that HyperFrames must seek deterministically during preview and rendering.
**Location**: `data/skills/hyperframes/skills/css-animations`
**Version**: 1.0.0

### gsap
**Description**: GSAP animation reference for HyperFrames. Covers gsap.to(), from(), fromTo(), easing, stagger, defaults, timelines (gsap.timeline(), position parameter, labels, nesting, playback), and performance (transforms, will-change, quickTo). Use when writing GSAP animations in HyperFrames compositions.
**Location**: `data/skills/hyperframes/skills/gsap`
**Version**: 1.0.0

### hyperframes
**Description**: Create video compositions, animations, title cards, overlays, captions, voiceovers, audio-reactive visuals, and scene transitions in HyperFrames HTML. Use when asked to build any HTML-based video content, add captions or subtitles synced to audio, generate text-to-speech narration, create audio-reactive animation (beat sync, glow, pulse driven by music), add animated text highlighting (marker sweeps, hand-drawn circles, burst lines, scribble, sketchout), or add transitions between scenes (crossfades, wipes, reveals, shader transitions). Covers composition authoring, timing, media, and the full video production workflow. For dev-loop CLI commands (init, lint, inspect, preview, render) see the hyperframes-cli skill; for asset preprocessing commands (tts, transcribe, remove-background) see the hyperframes-media skill.
**Location**: `data/skills/hyperframes/skills/hyperframes`
**Version**: 1.0.0

### hyperframes-cli
**Description**: HyperFrames CLI dev loop — `npx hyperframes` for scaffolding (init), validation (lint, inspect), preview, render, and environment troubleshooting (doctor, browser, info, upgrade). Use when running any of these commands or troubleshooting the HyperFrames build/render environment. For asset preprocessing commands (`tts`, `transcribe`, `remove-background`), invoke the `hyperframes-media` skill instead.
**Location**: `data/skills/hyperframes/skills/hyperframes-cli`
**Version**: 1.0.0

### hyperframes-media
**Description**: Asset preprocessing for HyperFrames compositions — text-to-speech narration (Kokoro), audio/video transcription (Whisper), and background removal for transparent overlays (u2net). Use when generating voiceover from text, transcribing speech for captions, removing the background from a video or image to use as a transparent overlay, choosing a TTS voice or whisper model, or chaining these (TTS → transcribe → captions). Each command downloads its own model on first run.
**Location**: `data/skills/hyperframes/skills/hyperframes-media`
**Version**: 1.0.0

### hyperframes-registry
**Description**: Install and wire registry blocks and components into HyperFrames compositions. Use when running hyperframes add, installing a block or component, wiring an installed item into index.html, or working with hyperframes.json. Covers the add command, install locations, block sub-composition wiring, component snippet merging, and registry discovery.
**Location**: `data/skills/hyperframes/skills/hyperframes-registry`
**Version**: 1.0.0

### lottie
**Description**: Lottie and dotLottie adapter patterns for HyperFrames. Use when embedding lottie-web JSON animations, .lottie files, @lottiefiles/dotlottie-web players, registering instances on window.__hfLottie, or making After Effects exports deterministic in HyperFrames.
**Location**: `data/skills/hyperframes/skills/lottie`
**Version**: 1.0.0

### remotion-to-hyperframes
**Description**: Translate an existing Remotion (React-based) video composition into a HyperFrames HTML composition. Use ONLY when the user explicitly asks to port, convert, migrate, translate, or rewrite a Remotion composition as HyperFrames (e.g. "port my Remotion project to HyperFrames"). Do NOT use when (a) authoring a NEW HyperFrames composition (even if A/B-testing a Remotion video); (b) Remotion is mentioned in passing; (c) Remotion code is shared as reference, not for translation; (d) the user wants "the same video as my Remotion one" without explicitly asking to migrate the source — treat as a fresh HyperFrames build. When in doubt, default to the `hyperframes` skill. Detects unsupported patterns (useState, useEffect side effects, async calculateMetadata, third-party React component libraries, `@remotion/lambda`) and recommends the runtime interop escape hatch instead of a lossy translation.
**Location**: `data/skills/hyperframes/skills/remotion-to-hyperframes`
**Version**: 1.0.0

### tailwind
**Description**: Tailwind CSS v4.2 browser-runtime patterns for HyperFrames compositions. Use when scaffolding or editing projects created with `hyperframes init --tailwind`, writing Tailwind utility classes in composition HTML, adding CSS-first Tailwind v4 theme tokens, debugging v3 vs v4 syntax, or deciding when to compile Tailwind to CSS instead of using the browser runtime.
**Location**: `data/skills/hyperframes/skills/tailwind`
**Version**: 1.0.0

### three
**Description**: Three.js and WebGL adapter patterns for HyperFrames. Use when creating deterministic Three.js scenes, WebGL canvas layers, AnimationMixer timelines, camera motion, shader-driven visuals, or canvas renders that respond to HyperFrames hf-seek events.
**Location**: `data/skills/hyperframes/skills/three`
**Version**: 1.0.0

### waapi
**Description**: Web Animations API adapter patterns for HyperFrames. Use when authoring element.animate() motion, Animation currentTime seeking, document.getAnimations(), KeyframeEffect timing, fill modes, or native browser animations that must render deterministically in HyperFrames.
**Location**: `data/skills/hyperframes/skills/waapi`
**Version**: 1.0.0

### website-to-hyperframes
**Description**: Capture a website and create a HyperFrames video from it. Use when: (1) a user provides a URL and wants a video, (2) someone says "capture this site", "turn this into a video", "make a promo from my site", (3) the user wants a social ad, product tour, or any video based on an existing website, (4) the user shares a link and asks for any kind of video content. Even if the user just pastes a URL — this is the skill to use.

**Location**: `data/skills/hyperframes/skills/website-to-hyperframes`
**Version**: 1.0.0

