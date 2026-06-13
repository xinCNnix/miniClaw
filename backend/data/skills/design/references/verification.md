# 验证 — 检查制品确实能工作

没有在真实浏览器中加载 HTML 就声称"完成"是猜测，不是交付。

## 验证循环

对每个设计制品，声明完成前：

1. **在真实浏览器中打开 HTML。** 在 Claude Code 中使用 `/browse` — 不用原始 `mcp__claude-in-chrome__*` 或 `mcp__computer-use__*`
2. **读浏览器控制台。** 任何 404、JS 错误、React 挂载警告都意味着有问题。修复。重新验证。
3. **测试缩放。** 固定尺寸内容调整预览窗口/视口到多个尺寸。内容应 letterbox 干净，控件保持可用。
4. **至少点击一个流程。** 交互原型点击主路径。
5. **检查字体加载。** CDN web 字体可能默默 404。

## "控制台干净"意味着

- 无 `Failed to load resource: 404`
- 无红色 `Uncaught …` 错误
- 无 React "Warning: Each child in a list should have a unique key" 警告
- 无 CORS 或 CSP 错误
- 无混合内容警告

黄色开发警告（弃用 API 等）如果实际不影响行为可以接受。**任何红色错误必须修复。**

## 格式特定检查

### Slide decks

- [ ] prev/next 箭头和键盘导航都工作
- [ ] slide 计数器随导航更新
- [ ] slide index 在 localStorage 持久化（刷新 → 同一 slide）
- [ ] 在窄于 1920px 的视口上缩放 letterbox 干净
- [ ] 正文 ≥ 24px / 标题 ≥ 64px
- [ ] 每 slide 有 `data-screen-label`

### 交互原型

- [ ] 主流程端到端推进无控制台错误
- [ ] 表单输入接受文本并可见更新状态
- [ ] hover/focus/active 状态已定义
- [ ] 代码库中无 `scrollIntoView`
- [ ] 设备框架（如果用）匹配平台

### 时间线动画

- [ ] scrubber 在全程平滑移动
- [ ] play/pause 切换播放
- [ ] scrubber 位置在 localStorage 持久化
- [ ] 无可见丢帧
- [ ] 动画在结尾循环或保持最终帧

### Design canvas

- [ ] 所有 cell 有标签描述在探索什么
- [ ] cell 尺寸一致
- [ ] canvas 背景不干扰变体颜色
- [ ] cell 内无裁剪内容的溢出

## 验证失败时

根因修复。不要：
- 用 `display: none` 隐藏坏元素
- 用 try/catch 吞掉 JS 错误
- 因为字体 404 就移除字体导入
- 跳过失败的点击断言

## 不要过度验证

不要随意截图。不要在用户要求修复一个 CSS 值时点击每个屏幕。验证匹配变更：
- 局部 CSS 编辑 → 局部视觉检查
- 新交互流程 → 完整点击通过
- 新 deck 骨架 → 完整检查
