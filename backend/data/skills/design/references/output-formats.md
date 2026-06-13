# 输出格式 — 选择和构建每种类型

格式是探索的函数。先使用决策树，然后从匹配的骨架构建。

## 决策树

```
探索主要是视觉的（颜色、字体、静态布局）？
├─ 是，并排展示选项 → DESIGN CANVAS
└─ 否 ↓

这是叙事序列（故事、演讲、教程）？
├─ 是 → SLIDE DECK
└─ 否 ↓

有交互/流程/多选项？
├─ 是，高保真 → INTERACTIVE PROTOTYPE（带 Tweaks）
└─ 否 ↓

关于动效/时间/视频？
├─ 是 → TIMELINE ANIMATION
└─ 否 ↓

大量粗略想法，探索早期？
└─ 是 → WIREFRAMES / STORYBOARD
```

## 1. Design canvas — 多个静态选项并排

**何时：** 纯视觉探索，用户想一目了然比较变体。

```html
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>Hero — variations</title>
  <style>
    body { margin: 0; font-family: 'Söhne', sans-serif; background: #f4f1ec; }
    .canvas { display: grid; grid-template-columns: repeat(2, 1fr); gap: 48px; padding: 48px; }
    .cell { background: white; border-radius: 8px; overflow: hidden; }
    .cell-label { padding: 16px 20px; border-bottom: 1px solid #eee; }
    .cell-label h3 { margin: 0; font-size: 13px; letter-spacing: 0.04em; text-transform: uppercase; color: #666; }
    .cell-label p { margin: 4px 0 0; font-size: 14px; color: #999; }
    .cell-body { padding: 0; }
  </style>
</head>
<body>
  <main class="canvas">
    <section class="cell">
      <header class="cell-label">
        <h3>Variant A · Editorial</h3>
        <p>Serif headline, generous negative space</p>
      </header>
      <div class="cell-body"><!-- hero A --></div>
    </section>
    <section class="cell">
      <header class="cell-label">
        <h3>Variant B · Product-forward</h3>
        <p>Mono headline, product screenshot</p>
      </header>
      <div class="cell-body"><!-- hero B --></div>
    </section>
  </main>
</body>
</html>
```

**注意：**
- 每个 cell 标签描述在探索什么
- cell 尺寸一致
- 画布背景中性无观点（cream/浅灰）
- 2-3 列通常合适；4+ 变体每行变得太小

## 2. Slide deck — 分页叙事

**何时：** 演讲、报告、教程。任何顺序场景。

**骨架：** 固定尺寸画布（默认 1920×1080，16:9）包在缩放 stage 中。

```html
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>Deck — Project Aurora</title>
</head>
<body>
  <deck-stage width="1920" height="1080">
    <section data-screen-label="01 Title">...</section>
    <section data-screen-label="02 Problem">...</section>
    <section data-screen-label="03 Solution">...</section>
  </deck-stage>

  <script type="application/json" id="speaker-notes">
    ["Slide 1 notes...", "Slide 2 notes...", ""]
  </script>
</body>
</html>
```

**必须有的行为：**
- 缩放：`transform: scale()` 适配任意视口；黑底 letterbox
- 导航：方向键 + 可见 prev/next 控件。控件在缩放元素外部
- 计数器：`{current}/{total}` 叠加。1-indexed
- 持久化：`localStorage` 存储 slide index
- 屏幕标签：每 slide `data-screen-label` 如 "01 Title"
- 打印：`@page size: 1920px 1080px` + `break-after: page`

**Slide 字号下限：**
- 正文 ≥ 24px（强调 32-48px）
- 标题 ≥ 64px
- 超 ~40 词正文就拆分或移到 speaker notes

## 3. 交互原型 — 可点击高保真

**何时：** 用户需要感受交互，不只是看布局。

**骨架：** React（inline JSX + Babel）用于有状态组件。

```html
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>Onboarding — prototype</title>
  <script src="https://unpkg.com/react@18.3.1/umd/react.development.js" integrity="sha384-hD6/rw4ppMLGNu3tX5cjIb+uRZ7UkRJ6BPkLpg4hAu/6onKUg4lLsHAs9EBPT82L" crossorigin="anonymous"></script>
  <script src="https://unpkg.com/react-dom@18.3.1/umd/react-dom.development.js" integrity="sha384-u6aeetuaXnQ38mYT8rp6sbXaQe3NL9t+IBXmnYxwkUI2Hw4bsp2Wvmx4yRQF1uAm" crossorigin="anonymous"></script>
  <script src="https://unpkg.com/@babel/standalone@7.29.0/babel.min.js" integrity="sha384-m08KidiNqLdpJqLq95G/LEi8Qvjl/xUYll3QILypMoQ65QorJ9Lvtp2RXYGBFj1y" crossorigin="anonymous"></script>
</head>
<body>
  <div id="root"></div>
  <script type="text/babel" src="components.jsx"></script>
  <script type="text/babel" src="app.jsx"></script>
</body>
</html>
```

**规则：**
- 原型居中在视口，直接进入产品
- 移动 UI 包在设备框架中
- 真实状态，不用 `window.alert`
- Mock 后端 inline
- 永不用 `scrollIntoView`

## 4. 时间线动画 — 动效设计

**何时：** 概念动画、交互演示、短视频风格制品。

**骨架：** Stage 组件 + scrubber/play/pause + Sprite 组件带 start/end 关键帧。

```jsx
const { useTime } = window.AnimationStage;

const Intro = () => {
  const t = useTime();
  const opacity = interpolate(t, [0, 0.5], [0, 1], Easing.outCubic);
  return <div style={{ opacity }}>Hello</div>;
};

ReactDOM.render(
  <Stage duration={6.0}>
    <Sprite start={0} end={2}><Intro/></Sprite>
    <Sprite start={1.5} end={4}><Middle/></Sprite>
    <Sprite start={3.5} end={6}><Outro/></Sprite>
  </Stage>,
  document.getElementById('root')
);
```

**规则：**
- 一个动态语言（相同缓动曲线、一致持续时间范围）
- 无交互时自动循环
- scrubber 位置持久化到 localStorage

## 5. 线框图/故事板

**何时：** 广度优先于精度。早期探索，大量廉价想法。

```html
<main style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 24px; padding: 48px;">
  <figure class="wire">
    <h3>01 · Landing</h3>
    <div class="wire-frame">
      <div class="wire-nav"></div>
      <div class="wire-hero">[hero image]</div>
      <div class="wire-cta">Sign up</div>
    </div>
    <figcaption>用户着陆，看到价值主张，点击注册</figcaption>
  </figure>
</main>
```

**规则：**
- 保持真正低保真。发现自己加颜色/阴影/排版 — 你在做中保真
- 每帧编号、标题、一行说明
- 6-12 帧合适

## 固定尺寸内容的缩放

任何固定画布尺寸的制品（decks、动画、海报）必须缩放适配任意视口。

模式：
1. 固定尺寸内部元素（如 1920×1080）
2. 外部 stage 填充视口并黑底 letterbox
3. JS 计算视口，`scale = min(vw/1920, vh/1080)`，应用 `transform: scale()`
4. 控件在缩放元素外部，保持一致大小
