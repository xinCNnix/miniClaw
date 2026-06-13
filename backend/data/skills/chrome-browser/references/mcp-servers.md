# MCP Server 对比参考

## 方案对比

| 特性 | Chrome DevTools MCP | Playwright MCP | mcp_server_browser_use |
|------|-------------------|----------------|----------------------|
| 连接已有 Chrome 9222 | 原生支持 `--browser-url` | `--cdp-endpoint` | `CHROME_CDP` 环境变量 |
| 工具数量 | 44 | 60+ | ~10 |
| 语言 | Node.js/TS | Node.js/TS | Python |
| 维护方 | Google Chrome 团队 | Microsoft | 社区 |
| 成熟度 | Public Preview (2025.09) | 非常成熟 (65+ releases) | 早期 (v0.1.5) |
| Node.js 要求 | v20.19+ | v18+ | 不需要 |

## Chrome DevTools MCP（推荐）

Google 官方维护，专为 CDP 设计，工具覆盖最全面。

### 安装配置
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

### 连接方式
1. `--browser-url=http://127.0.0.1:9222` — 最常用，直接连接
2. `--ws-endpoint=ws://127.0.0.1:9222/devtools/browser/<id>` — WebSocket 直连
3. `--autoConnect` — Chrome 144+ 自动发现，无需指定端口

### 工具分类（44 个）

**输入自动化（10）**: click, drag, fill, fill_form, handle_dialog, hover, press_key, type_text, upload_file, click_at

**导航（6）**: close_page, list_pages, navigate_page, new_page, select_page, wait_for

**调试（8）**: evaluate_script, get_console_message, lighthouse_audit, list_console_messages, take_screenshot, take_snapshot, screencast_start, screencast_stop

**性能（3）**: performance_analyze_insight, performance_start_trace, performance_stop_trace

**网络（2）**: get_network_request, list_network_requests

**内存（4）**: take_memory_snapshot, get_memory_snapshot_details, get_nodes_by_class, load_memory_snapshot

**模拟（2）**: emulate, resize_page

**扩展（5）**: install_extension, list_extensions, reload_extension, trigger_extension_action, uninstall_extension

**WebMCP（4）**: execute_3p_developer_tool, list_3p_developer_tools, execute_webmcp_tool, list_webmcp_tools

### 常用选项
- `--slim` — 轻量模式，仅 3 个工具（navigate, execute, screenshot）
- `--headless` — 无头模式
- `--isolated` — 临时配置文件
- `--viewport=1280x720` — 设置视口大小
- `--no-usage-statistics` — 关闭 Google 遥测

## Playwright MCP（替代方案）

Microsoft 维护，工具最多，生态最成熟。

### 安装配置
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

### 工具分类（60+）

**核心（22）**: browser_click, browser_close, browser_console_messages, browser_drag, browser_drop, browser_evaluate, browser_file_upload, browser_fill_form, browser_handle_dialog, browser_hover, browser_navigate, browser_navigate_back, browser_network_request, browser_network_requests, browser_press_key, browser_resize, browser_run_code_unsafe, browser_select_option, browser_snapshot, browser_take_screenshot, browser_type, browser_wait_for

**标签页（1）**: browser_tabs

**存储（16，需 --caps=storage）**: cookie 和 storage 操作

**网络（4，需 --caps=network）**: 路由和网络状态控制

**DevTools（9，需 --caps=devtools）**: 追踪、视频录制、标注

**视觉/坐标（6，需 --caps=vision）**: 基于坐标的鼠标操作

**PDF（1，需 --caps=pdf）**: browser_pdf_save

**测试（5，需 --caps=testing）**: 验证和定位器生成

### 常用选项
- `--caps=vision,pdf,devtools,storage,network,testing` — 启用额外功能组
- `--headless` — 无头模式
- `--browser=chrome|firefox|webkit|msedge` — 多浏览器支持
- `--codegen=typescript` — 生成 Playwright 测试代码

## mcp_server_browser_use（Python 方案）

适合 Python 环境要求严格的场景。

### 安装配置
```json
{
  "mcpServers": {
    "browser-use": {
      "command": "python",
      "args": ["-m", "mcp_server_browser_use"],
      "env": {
        "MCP_USE_OWN_BROWSER": "true",
        "CHROME_CDP": "http://localhost:9222"
      }
    }
  }
}
```

注意：此方案早期阶段，文档有限，不建议生产使用。
