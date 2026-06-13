---
name: chrome-browser
description: "Use when user needs to: (1) control Chrome browser, web automation, web scraping; (2) 控制浏览器、网页自动化、网页抓取; (3) screenshot, form filling, page navigation, execute JS in browser; (4) 截图、填表、页面导航、执行JS; (5) interact with existing Chrome session. Triggers: browser, chrome, CDP, puppeteer, selenium, playwright, 浏览器, 网页自动化, 截图, 爬虫, 网页操作."
metadata: { "openclaw": { "emoji": "🌐", "requires": { "bins": ["python"], "env": [] } } }
---

# Chrome 浏览器控制

通过 Chrome DevTools Protocol (CDP) 在端口 9222 上控制 Chrome 浏览器。支持导航、点击、输入、截图、执行 JavaScript 等全量浏览器操作。

## 前置条件

### 1. 启动 Chrome 远程调试模式

用 `terminal` 工具启动 Chrome，必须带 `--remote-debugging-port=9222` 参数：

```bash
# Windows
start "" "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --remote-allow-origins=* --user-data-dir=%TEMP%\chrome-debug

# macOS
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --remote-debugging-port=9222 --remote-allow-origins=* --user-data-dir=/tmp/chrome-debug &

# Linux
google-chrome --remote-debugging-port=9222 --remote-allow-origins=* --user-data-dir=/tmp/chrome-debug &
```

**注意：** 如果 Chrome 已在运行，需要先关闭所有 Chrome 窗口，再以调试模式重启。端口 9222 被占用时会失败。

### 2. 验证连接

```bash
curl -s http://127.0.0.1:9222/json/version
```

返回 JSON 表示 CDP 可用。

## 控制方式

### 方式一：辅助脚本（推荐）

用 `terminal` 调用辅助脚本，所有操作通过 JSON 参数控制：

```bash
python data/skills/chrome-browser/scripts/cdp_helper.py '<JSON>'
```

脚本自动管理 WebSocket 连接，适合单次操作。

### 方式二：python_repl 直接调用

在 `python_repl` 中使用 CDP 协议直接操作，适合需要多步交互的复杂场景：

```python
import requests, json, websocket

# 获取 WebSocket 地址
pages = requests.get("http://127.0.0.1:9222/json").json()
ws_url = pages[0]["webSocketDebuggerUrl"]

def cdp(method, params=None, msg_id=1):
    """发送 CDP 命令"""
    ws = websocket.create_connection(ws_url)
    msg = {"id": msg_id, "method": method}
    if params: msg["params"] = params
    ws.send(json.dumps(msg))
    result = json.loads(ws.recv())
    ws.close()
    return result
```

## 常用操作速查

### 导航到页面
```bash
python scripts/cdp_helper.py '{"action":"navigate","url":"https://example.com"}'
```

### 获取页面标题和 URL
```bash
python scripts/cdp_helper.py '{"action":"evaluate","expression":"JSON.stringify({title:document.title,url:location.href})"}'
```

### 截图
```bash
python scripts/cdp_helper.py '{"action":"screenshot","path":"outputs/screenshot.png"}'
```

### 点击元素
```bash
python scripts/cdp_helper.py '{"action":"click","selector":"#submit-btn"}'
```

### 输入文字
```bash
python scripts/cdp_helper.py '{"action":"type","selector":"#search-input","text":"人工智能"}'
```

### 获取页面文本内容
```bash
python scripts/cdp_helper.py '{"action":"evaluate","expression":"document.body.innerText"}'
```

### 等待元素出现
```bash
python scripts/cdp_helper.py '{"action":"wait_for","selector":".result-item","timeout":5000}'
```

### 获取页面 HTML
```bash
python scripts/cdp_helper.py '{"action":"evaluate","expression":"document.documentElement.outerHTML"}'
```

## 操作参数参考

| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| action | string | 是 | 操作类型：navigate/click/type/screenshot/evaluate/wait_for/get_cookies/scroll |
| url | string | 条件 | navigate 操作的目标 URL |
| selector | string | 条件 | click/type/wait_for 操作的 CSS 选择器 |
| text | string | 条件 | type 操作的输入文本 |
| expression | string | 条件 | evaluate 操作的 JS 表达式 |
| path | string | 否 | screenshot 保存路径（默认 outputs/screenshot.png） |
| timeout | int | 否 | wait_for 超时毫秒数（默认 5000） |
| format | string | 否 | screenshot 格式：png/jpeg（默认 png） |

## MCP Server 配置（Claude Code）

在 Claude Code 中使用 MCP 工具控制 Chrome，需配置 `.claude/settings.json`。

### Chrome DevTools MCP（Google 官方，44 个工具）
```json
{
  "mcpServers": {
    "chrome-devtools": {
      "command": "npx",
      "args": ["-y", "chrome-devtools-mcp@latest",
        "--browser-url=http://127.0.0.1:9222",
        "--no-usage-statistics"]
    }
  }
}
```

### Playwright MCP（Microsoft，60+ 工具，需 Node.js 18+）
```json
{
  "mcpServers": {
    "playwright": {
      "command": "npx",
      "args": ["@playwright/mcp@latest",
        "--cdp-endpoint=http://localhost:9222/"]
    }
  }
}
```

MCP Server 详细对比见 [references/mcp-servers.md](references/mcp-servers.md)。

## 故障排除

| 问题 | 原因 | 解决方案 |
|------|------|---------|
| Connection refused | Chrome 未以调试模式启动 | 关闭所有 Chrome 窗口，用 `--remote-debugging-port=9222` 重启 |
| 端口被占用 | 已有 Chrome 实例占用 9222 | `taskkill /F /IM chrome.exe`（Windows）后重启 |
| WebSocket 连接失败 | 页面标签已关闭 | 重新获取 `webSocketDebuggerUrl` |
| 元素找不到 | 页面未加载完成 | 先用 `wait_for` 等待元素出现 |
| 截图空白 | 页面仍在渲染 | 等待 1-2 秒后再截图 |

## 依赖

```yaml
dependencies:
  python:
    - "websocket-client>=1.6.0"
    - "requests>=2.31.0"
```
