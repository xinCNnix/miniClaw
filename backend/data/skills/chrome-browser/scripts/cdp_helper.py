"""
Chrome DevTools Protocol (CDP) 辅助脚本

通过 WebSocket 连接到 Chrome CDP 端口 9222，执行浏览器操作。
用法: python cdp_helper.py '<JSON>'

操作类型:
  - navigate:    导航到 URL
  - click:       点击 CSS 选择器匹配的元素
  - type:        在元素中输入文字
  - screenshot:  截图并保存为文件
  - evaluate:    执行 JavaScript 表达式
  - wait_for:    等待元素出现
  - get_cookies: 获取当前页面 cookies
  - scroll:      滚动页面
  - get_html:    获取页面完整 HTML
"""

import json
import sys
import time
import base64
import os

import requests
import websocket


CDP_HOST = os.environ.get("CDP_HOST", "localhost")
CDP_PORT = int(os.environ.get("CDP_PORT", "9222"))
CDP_BASE_URL = f"http://{CDP_HOST}:{CDP_PORT}"


class CDPClient:
    """Chrome DevTools Protocol 客户端"""

    def __init__(self, target_index: int = 0):
        self.ws_url = self._get_ws_url(target_index)
        self._msg_id = 0

    def _get_ws_url(self, index: int) -> str:
        """获取指定标签页的 WebSocket 调试地址"""
        try:
            resp = requests.get(f"{CDP_BASE_URL}/json", timeout=5)
            resp.raise_for_status()
            pages = resp.json()
        except requests.ConnectionError:
            raise ConnectionError(
                f"无法连接 Chrome CDP ({CDP_BASE_URL})。"
                "请确认 Chrome 已以 --remote-debugging-port=9222 启动。"
            )
        if not pages:
            raise ValueError("Chrome 没有打开的标签页")
        # 优先选择 type=page 的标签
        page_tabs = [p for p in pages if p.get("type") == "page"]
        tabs = page_tabs if page_tabs else pages
        if index >= len(tabs):
            raise IndexError(f"标签页索引 {index} 超出范围（共 {len(tabs)} 个）")
        return tabs[index]["webSocketDebuggerUrl"]

    def send(self, method: str, params: dict | None = None) -> dict:
        """发送 CDP 命令并返回响应"""
        self._msg_id += 1
        msg = {"id": self._msg_id, "method": method}
        if params:
            msg["params"] = params

        ws = websocket.create_connection(self.ws_url, timeout=30, suppress_origin=True)
        try:
            ws.send(json.dumps(msg))
            result = json.loads(ws.recv())
        finally:
            ws.close()

        if "error" in result:
            raise RuntimeError(f"CDP 错误: {result['error']}")
        return result.get("result", {})

    def evaluate(self, expression: str) -> any:
        """执行 JavaScript 表达式并返回值"""
        result = self.send("Runtime.evaluate", {
            "expression": expression,
            "returnByValue": True,
        })
        value_info = result.get("result", {})
        if value_info.get("type") == "object" and value_info.get("subtype") == "error":
            raise RuntimeError(f"JS 执行错误: {value_info.get('description', 'unknown')}")
        return value_info.get("value")

    def navigate(self, url: str) -> dict:
        """导航到指定 URL"""
        self.send("Page.enable")
        result = self.send("Page.navigate", {"url": url})
        time.sleep(1)  # 等待页面开始加载
        return result

    def click(self, selector: str) -> dict:
        """点击 CSS 选择器匹配的元素"""
        # 获取元素位置
        js = f"""
        (function() {{
            var el = document.querySelector({json.dumps(selector)});
            if (!el) return {{ error: '元素未找到: {selector}' }};
            var rect = el.getBoundingClientRect();
            el.scrollIntoView({{ behavior: 'instant', block: 'center' }});
            return {{
                x: rect.x + rect.width / 2,
                y: rect.y + rect.height / 2,
                width: rect.width,
                height: rect.height
            }};
        }})()
        """
        rect = self.evaluate(js)
        if isinstance(rect, dict) and "error" in rect:
            raise ValueError(rect["error"])

        x, y = rect["x"], rect["y"]
        # 模拟鼠标按下和释放
        for event_type in ["mousePressed", "mouseReleased"]:
            self.send("Input.dispatchMouseEvent", {
                "type": event_type,
                "x": x, "y": y,
                "button": "left",
                "clickCount": 1,
            })
        time.sleep(0.3)
        return {"clicked": selector, "position": rect}

    def type_text(self, selector: str, text: str) -> dict:
        """在元素中输入文字（先聚焦，再输入）"""
        # 聚焦元素
        self.evaluate(
            f"document.querySelector({json.dumps(selector)})?.focus()"
        )
        time.sleep(0.2)
        # 逐字符输入以触发键盘事件
        for char in text:
            self.send("Input.dispatchKeyEvent", {
                "type": "char",
                "text": char,
            })
        return {"typed": text, "selector": selector}

    def screenshot(self, path: str = "outputs/screenshot.png", fmt: str = "png") -> dict:
        """截取页面截图"""
        result = self.send("Page.captureScreenshot", {"format": fmt})
        img_data = base64.b64decode(result["data"])

        os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)
        with open(path, "wb") as f:
            f.write(img_data)
        return {"saved": path, "size_bytes": len(img_data)}

    def wait_for(self, selector: str, timeout: int = 5000) -> dict:
        """等待元素出现在 DOM 中"""
        interval = 0.2
        elapsed = 0.0
        while elapsed < timeout / 1000.0:
            found = self.evaluate(
                f"document.querySelector({json.dumps(selector)}) !== null"
            )
            if found:
                return {"found": selector, "waited_ms": int(elapsed * 1000)}
            time.sleep(interval)
            elapsed += interval
        raise TimeoutError(f"等待元素超时 ({timeout}ms): {selector}")

    def get_cookies(self) -> list:
        """获取当前页面的 cookies"""
        result = self.send("Network.getCookies")
        return result.get("cookies", [])

    def scroll(self, x: int = 0, y: int = 0, selector: str | None = None) -> dict:
        """滚动页面或指定元素"""
        if selector:
            js = f"document.querySelector({json.dumps(selector)}).scrollBy({x}, {y})"
        else:
            js = f"window.scrollBy({x}, {y})"
        self.evaluate(js)
        return {"scrolled": {"x": x, "y": y}, "selector": selector}

    def get_html(self) -> str:
        """获取页面完整 HTML"""
        return self.evaluate("document.documentElement.outerHTML")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    try:
        args = json.loads(sys.argv[1])
    except json.JSONDecodeError as e:
        print(f"JSON 解析错误: {e}", file=sys.stderr)
        sys.exit(1)

    action = args.get("action")
    if not action:
        print("缺少 action 参数", file=sys.stderr)
        sys.exit(1)

    # 各操作必需参数定义
    required_params = {
        "navigate": ["url"],
        "click": ["selector"],
        "type": ["selector", "text"],
        "evaluate": ["expression"],
        "wait_for": ["selector"],
    }

    if action not in required_params and action not in ("screenshot", "get_cookies", "scroll", "get_html"):
        print(f"未知操作: {action}。支持: {', '.join(sorted(required_params.keys()) + ['screenshot', 'get_cookies', 'scroll', 'get_html'])}", file=sys.stderr)
        sys.exit(1)

    # 校验必需参数
    missing = [p for p in required_params.get(action, []) if p not in args]
    if missing:
        print(f"缺少必需参数: {', '.join(missing)}", file=sys.stderr)
        sys.exit(1)

    client = CDPClient(target_index=args.get("tab_index", 0))

    handlers = {
        "navigate": lambda: client.navigate(args["url"]),
        "click": lambda: client.click(args["selector"]),
        "type": lambda: client.type_text(args["selector"], args["text"]),
        "screenshot": lambda: client.screenshot(
            args.get("path", "outputs/screenshot.png"),
            args.get("format", "png"),
        ),
        "evaluate": lambda: {"result": client.evaluate(args["expression"])},
        "wait_for": lambda: client.wait_for(
            args["selector"], args.get("timeout", 5000),
        ),
        "get_cookies": lambda: {"cookies": client.get_cookies()},
        "scroll": lambda: client.scroll(
            args.get("x", 0), args.get("y", 0), args.get("selector"),
        ),
        "get_html": lambda: {"html": client.get_html()},
    }

    try:
        result = handlers[action]()
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (ConnectionError, ValueError, TimeoutError, RuntimeError) as e:
        print(json.dumps({"error": str(e)}, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
