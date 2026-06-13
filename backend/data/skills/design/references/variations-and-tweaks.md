# 变体与 Tweaks — 给用户可混搭的选项

设计很少是"这是答案" — 而是"这里有几个方向，我们一起找到正确的"。你的工作是让比较有效率。

## 变体组合

好的变体集跨越空间。不要交付同一想法的三个小偏差 — 交付真正不同方向的探索。

变化轴：
- **布局** — 层次、节奏、密度、网格结构
- **排版** — 字体搭配、尺度、粗细对比、大小写处理
- **颜色** — 主色板、背景逻辑、点缀位置
- **图像** — 摄影vs 插画 vs 无；全出血 vs 包含
- **交互** — hover 模式、微文案、状态反馈
- **隐喻** — 如何框定产品（终端/文档/工作室/助手）
- **高级 CSS** — 纹理、混合模式、clip paths、滚动驱动动效

## 展示变体

| 在变化的... | 展示为... |
|-------------|-----------|
| 一个静态元素的 ≥3 处理 | **Design canvas** — 标记 cell 网格 |
| 有小变体的原型（暗色模式、文案、布局模式） | **Tweaks 面板** — 单个原型，可切换 |
| 不同叙事（不同 deck 大纲、不同演讲角度） | Deck 内的 **Sections** |
| UX 流程的重大偏差 | **独立 HTML 文件**，互链 |

**不要**在一个文件带 Tweaks 就行时产生 N 个独立 HTML 文件。

## Tweaks 协议

Tweaks 是制品内 UI，让用户实时切换设计方面：颜色、排版、文案、布局变体、feature flags。

### 主机集成（当可用时）

1. **先注册 listener，再宣布可用性：**

```javascript
window.addEventListener('message', (e) => {
  if (e.data?.type === '__activate_edit_mode') showTweaksPanel();
  if (e.data?.type === '__deactivate_edit_mode') hideTweaksPanel();
});

window.parent.postMessage({ type: '__edit_mode_available' }, '*');
```

2. **用 `__edit_mode_set_keys` 持久化变更回文件：**

```javascript
function onTweakChange(key, value) {
  applyLive(key, value);
  window.parent.postMessage({
    type: '__edit_mode_set_keys',
    edits: { [key]: value }
  }, '*');
}
```

3. **用 edit-mode 标记包裹默认值：**

```javascript
const TWEAK_DEFAULTS = /*EDITMODE-BEGIN*/{
  "primaryColor": "#D97757",
  "fontSize": 16,
  "dark": false,
  "variant": "A"
}/*EDITMODE-END*/;
```

标记规则：
- 块必须是**有效 JSON**：双引号键、双引号字符串
- 根 HTML 文件中**恰好一个**这样的块
- 必须在 inline `<script>` 内（不是外部文件）

### 独立 Tweaks（无主机集成）

```javascript
const TWEAKS = loadTweaksFromStorage() ?? {
  primaryColor: '#D97757',
  fontSize: 16,
  dark: false,
  variant: 'A',
};

function onTweakChange(key, value) {
  TWEAKS[key] = value;
  applyLive(key, value);
  localStorage.setItem('tweaks', JSON.stringify(TWEAKS));
}
```

### Tweaks UI 模式

- **右下角浮动面板** — 标题 "Tweaks"，可折叠，可拖拽
- **hover 时内联手柄** — 小齿轮图标在控制的元素旁边
- **顶部工具栏** — 仅当有很多 tweaks 时使用

规则：
- Tweaks 关闭时面板完全隐藏。设计应看起来完成
- 不要过度构建面板本身 — 无深层嵌套、无标签页、无滚动
- 分组相关 tweaks（所有色板在一起，所有字体控制在一起）

### 默认暴露什么

用户没指定时：3-5 个打开有趣设计空间的 tweaks：
- 主色（颜色选择器或色板集）
- 排版（字体搭配选择器或标题字体切换）
- 密度（紧凑/舒适/宽敞）
- 变体切换（A/B/C — 循环主要布局）
- 文案语调（专业/休闲/有力）

### 循环变体

常见模式：用户要求单个元素在更大设计中的多个变体。添加一个 tweak 循环该元素：

```javascript
const [heroVariant, setHeroVariant] = useState(TWEAKS.variant);
// 渲染中：
{heroVariant === 'A' && <HeroEditorial/>}
{heroVariant === 'B' && <HeroProduct/>}
{heroVariant === 'C' && <HeroRemix/>}
```

## 不确定变体数量时

问。变体是用户最常想要不同数量的东西。默认 3 个，跨越保守→激进。
