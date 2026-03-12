# E2E Testing Quick Start

快速上手指南：如何运行和编写 E2E 测试。

## 前置要求

1. **安装依赖**
   ```bash
   cd frontend
   npm install
   ```

2. **安装 Playwright 浏览器**
   ```bash
   npx playwright install
   ```

3. **启动服务**

   **方式 1：使用启动脚本（推荐）**
   ```bash
   # Windows
   start.bat

   # Linux/Mac
   ./start.sh
   ```

   **方式 2：手动启动**
   ```bash
   # 终端 1：启动后端
   cd backend
   uvicorn app.main:app --port 8002 --reload

   # 终端 2：启动前端
   cd frontend
   npm run dev
   ```

## 运行测试

### 运行所有测试
```bash
cd frontend
npm run test:e2e
```

### 运行特定测试文件
```bash
npx playwright test tool-calling
npx playwright test basic-chat
npx playwright test session-management
```

### 调试模式（推荐新手）
```bash
npx playwright test --debug
```
这会打开浏览器，让你逐步查看测试执行过程。

### 查看测试报告
```bash
npx playwright show-report
```

## 编写测试

### 基本结构

```typescript
import { test, expect } from '../fixtures/test-server'

test.describe('My Feature', () => {
  test.beforeEach(async ({ page, serverUrl }) => {
    await page.goto(serverUrl.replace('8002', '3000') + '/chat')
  })

  test('should do something', async ({ page }) => {
    // 测试逻辑
  })
})
```

### 常用操作

**发送消息：**
```typescript
import { sendChatMessage } from '../utils/helpers'

await sendChatMessage(page, '你好')
```

**等待响应：**
```typescript
import { waitForAgentReady } from '../utils/helpers'

await waitForAgentReady(page)
```

**验证工具调用：**
```typescript
import { expectToolCalled } from '../utils/assertions'

await expectToolCalled(page, 'read_file', {
  withArgs: true,
})
```

## 测试最佳实践

1. **每个测试独立** - 不依赖其他测试的状态
2. **清理资源** - 测试结束后删除创建的数据
3. **真实场景** - 测试真实用户流程，不只是组件渲染
4. **等待策略** - 使用合理的等待超时

## 常见问题

**Q: 测试失败，提示 "Backend not responding"**
A: 确保后端正在运行：`curl http://localhost:8002/health`

**Q: 测试超时**
A: 某些测试需要较长时间（涉及 LLM），可以在测试中增加超时：
```typescript
test.setTimeout(60000)  // 60 秒
```

**Q: 如何查看失败时的截图？**
A: 失败的测试会自动保存在 `test-results/` 目录。

## 更多信息

详细文档请参阅：[tests/README.md](./README.md)
