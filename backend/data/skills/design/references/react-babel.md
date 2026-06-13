# React + Babel 设置（inline JSX 原型）

用 inline JSX 构建 React 原型时，有四个会默默搞崩东西的陷阱。

## 固定版本 + integrity hash（不可协商）

```html
<script
  src="https://unpkg.com/react@18.3.1/umd/react.development.js"
  integrity="sha384-hD6/rw4ppMLGNu3tX5cjIb+uRZ7UkRJ6BPkLpg4hAu/6onKUg4lLsHAs9EBPT82L"
  crossorigin="anonymous"
></script>
<script
  src="https://unpkg.com/react-dom@18.3.1/umd/react-dom.development.js"
  integrity="sha384-u6aeetuaXnQ38mYT8rp6sbXaQe3NL9t+IBXmnYxwkUI2Hw4bsp2Wvmx4yRQF1uAm"
  crossorigin="anonymous"
></script>
<script
  src="https://unpkg.com/@babel/standalone@7.29.0/babel.min.js"
  integrity="sha384-m08KidiNqLdpJqLq95G/LEi8Qvjl/xUYll3QILypMoQ65QorJ9Lvtp2RXYGBFj1y"
  crossorigin="anonymous"
></script>
```

Babel 在 React 和 ReactDOM 之后加载。

## 陷阱 1：样式对象命名冲突

每个 `<script type="text/babel">` 在**相同全局作用域**中转译和求值。两个文件都定义 `const styles = { ... }` 会导致第二个默默覆盖第一个。

**修复：** 给每个样式对象绑定组件的唯一名称：

```jsx
// terminal.jsx
const terminalStyles = {
  root: { fontFamily: 'monospace', background: '#111' },
};

const Terminal = () => <div style={terminalStyles.root}>...</div>;
```

```jsx
// sidebar.jsx
const sidebarStyles = {
  root: { width: 240, background: '#1a1a1a' },
};

const Sidebar = () => <div style={sidebarStyles.root}>...</div>;
```

## 陷阱 2：Babel 脚本不共享作用域

`components.jsx` 中定义的组件不会自动对 `app.jsx` 可用。

**修复：** 显式导出到 `window`：

```jsx
// components.jsx
const Terminal = (props) => { /* ... */ };
const Line = (props) => { /* ... */ };

Object.assign(window, { Terminal, Line });
```

```jsx
// app.jsx
const { Terminal, Line } = window;

const App = () => (
  <Terminal>
    <Line>$ hello</Line>
  </Terminal>
);

ReactDOM.render(<App/>, document.getElementById('root'));
```

## 陷阱 3：scrollIntoView 破坏嵌入预览

`element.scrollIntoView()` 可以滚动整个嵌入应用（不只是 iframe），导致预览容器跳动。

**修复：** 用 `element.scrollTop = n` 或 `element.scrollTo(...)` 操作特定滚动容器。

## 陷阱 4：integrity hash 必须精确匹配

拼错 integrity 属性 → 浏览器默默拒绝加载脚本 → React is undefined。错误信息误导你以为 JSX 有问题。

**修复：** 上面的 hash 逐字节复制。用不同版本时从 unpkg 获取正确的 integrity hash。

## 原型项目结构

```
prototype/
├── index.html       # 固定版本 React/Babel + script 标签
├── components.jsx   # 小可复用组件
├── app.jsx          # 屏幕和顶层布局
├── styles.css       # CSS reset + 字体导入 + 全局样式
└── assets/
    ├── logo.svg
    └── hero-placeholder.svg
```

超 ~1000 行的文件难以可靠编辑。跨阈值时按领域拆分。

## 有用的 CDN 导入

```html
<!-- Tailwind via CDN -->
<script src="https://cdn.tailwindcss.com"></script>

<!-- 动画 -->
<script src="https://unpkg.com/popmotion@11.0.5/dist/popmotion.min.js"></script>

<!-- 图标 (lucide) -->
<script src="https://unpkg.com/lucide@latest"></script>
```

Tailwind CDN 用法：自定义主题放在 CDN 脚本之前的 `<script>` 块中：

```html
<script>
  tailwind.config = {
    theme: { extend: {
      colors: { brand: { 500: '#D97757' } },
      fontFamily: { display: ['Söhne', 'sans-serif'] },
    }},
  };
</script>
<script src="https://cdn.tailwindcss.com"></script>
```

## 检查清单

- [ ] 固定版本 + integrity hash（React, ReactDOM, Babel）
- [ ] Babel 在 React 之后加载
- [ ] 每个样式对象有唯一名称（或用 inline 样式）
- [ ] 共享组件通过 `Object.assign(window, {...})` 导出
- [ ] Babel script 标签不用 `type="module"`
- [ ] 组件代码中无 `scrollIntoView`
