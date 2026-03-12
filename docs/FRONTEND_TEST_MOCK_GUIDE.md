# Frontend Test Mock Guide

## 概述

本文档说明如何使用前端测试 Mock 来编写单元测试和组件测试。

## Mock 组件

### 1. FileTree Mock

FileTree 组件的 Mock 实现，用于测试文件树相关功能。

**位置**: `frontend/components/editor/__mocks__/FileTree.mock.tsx`

**使用示例**:

```typescript
import { renderWithProviders, createMockFile } from "@/tests/utils/test-utils"
import { FileTree } from "@/components/editor/FileTree"

describe("FileTree", () => {
  it("renders files", () => {
    const mockFiles = [
      createMockFile("test.ts"),
      createMockFile("src/app.ts"),
    ]

    renderWithProviders(
      <FileTree files={mockFiles} onSelectFile={vi.fn()} />
    )

    expect(screen.getByTestId("file-test.ts")).toBeInTheDocument()
  })
})
```

### 2. MonacoWrapper Mock

Monaco 编辑器的 Mock 实现，用于测试代码编辑器相关功能。

**位置**: `frontend/components/editor/__mocks__/MonacoWrapper.mock.tsx`

**使用示例**:

```typescript
import { renderWithProviders } from "@/tests/utils/test-utils"
import { MonacoWrapper } from "@/components/editor/MonacoWrapper"

describe("MonacoWrapper", () => {
  it("renders editor", () => {
    renderWithProviders(
      <MonacoWrapper content="test code" />
    )

    const textarea = screen.getByTestId("monaco-textarea")
    expect(textarea).toHaveValue("test code")
  })
})
```

## 测试工具

### renderWithProviders

封装了所有必要的 Context Provider 的渲染函数。

**位置**: `frontend/tests/utils/test-utils.tsx`

**特性**:
- 自动注入 AppContext
- 提供 mock 的 chat 和 editor 状态
- 简化组件测试设置

**使用示例**:

```typescript
import { renderWithProviders } from "@/tests/utils/test-utils"

test("my component", () => {
  renderWithProviders(<MyComponent />)
  // 组件已包含所有必要的 providers
})
```

### createMockFile

创建 mock 文件对象。

**参数**:
- `path`: 文件路径
- `type`: 文件类型 ("file" | "directory")

**示例**:

```typescript
const mockFile = createMockFile("src/app.ts", "file")
```

### createMockSession

创建 mock 会话对象。

**参数**:
- `id`: 会话 ID
- `title`: 会话标题

**示例**:

```typescript
const mockSession = createMockSession("session-1", "Test Chat")
```

## 配置文件

### vitest.config.ts

Vitest 配置文件，包含：

- 测试环境设置 (jsdom)
- 路径别名配置
- 覆盖率配置

### vitest.setup.ts

全局测试设置文件，包括：

- Monaco Editor mock
- Next.js router mock
- IntersectionObserver mock
- ResizeObserver mock

## 运行测试

### 运行所有测试

```bash
cd frontend
npm test
```

### 运行特定测试文件

```bash
npm test FileTree.test.tsx
```

### 运行测试并生成覆盖率报告

```bash
npm test -- --coverage
```

### 监听模式

```bash
npm test -- --watch
```

## 最佳实践

### 1. 使用 renderWithProviders

始终使用 `renderWithProviders` 而不是直接使用 `render`，以确保组件有正确的 Context。

```typescript
// ✅ 推荐
renderWithProviders(<MyComponent />)

// ❌ 不推荐
render(<MyComponent />)
```

### 2. 使用测试工具函数

使用提供的工具函数来创建 mock 数据。

```typescript
// ✅ 推荐
const mockFile = createMockFile("test.ts")

// ❌ 不推荐
const mockFile = {
  path: "test.ts",
  name: "test.ts",
  type: "file",
  size: 1024,
  modified_at: new Date().toISOString(),
}
```

### 3. 清理副作用

使用 `vi.fn()` 创建 mock 函数，并在需要时进行清理。

```typescript
 afterEach(() => {
   vi.clearAllMocks()
 })
```

### 4. 异步测试

使用 `waitFor` 或 `waitForAsync` 处理异步操作。

```typescript
import { waitFor } from "@testing-library/react"

test("async operation", async () => {
  // 触发异步操作
  fireEvent.click(button)

  // 等待结果
  await waitFor(() => {
    expect(screen.getByText("Success")).toBeInTheDocument()
  })
})
```

## 常见问题

### Q: 如何测试用户交互？

A: 使用 `fireEvent` 或 `@testing-library/user-event`。

```typescript
import { fireEvent } from "@testing-library/react"

fireEvent.click(button)
fireEvent.change(input, { target: { value: "new value" } })
```

### Q: 如何 Mock API 调用？

A: 使用 `vi.fn()` 或 `fetch-mock`。

```typescript
global.fetch = vi.fn(() =>
  Promise.resolve({
    ok: true,
    json: () => Promise.resolve({ data: "mock" }),
  })
)
```

### Q: 如何测试 Context 消费？

A: `renderWithProviders` 已经包含了必要的 Context，可以直接使用。

```typescript
const { chat } = useApp()
// chat 已经是 mock 对象
```

## 相关文档

- [Vitest 文档](https://vitest.dev/)
- [Testing Library 文档](https://testing-library.com/)
- [React Testing Library 文档](https://testing-library.com/react)
