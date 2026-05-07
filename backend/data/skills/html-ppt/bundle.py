#!/usr/bin/env python3
"""
html-ppt bundle script — 将 deck HTML 打包为单文件自包含 HTML。
把所有本地 CSS/JS 内联进 HTML，主题切换改为内联 <style> 切换，
生成的文件可复制到任何位置直接打开。

Usage:
    python data/skills/html-ppt/scripts/bundle.py <input.html> [output.html]
"""
import sys
import os
import re


def resolve_path(href: str, base_dir: str) -> str | None:
    """将相对路径解析为绝对路径，仅处理本地文件。"""
    if href.startswith(("http://", "https://", "data:", "//", "#")):
        return None
    abs_path = os.path.normpath(os.path.join(base_dir, href))
    return abs_path if os.path.isfile(abs_path) else None


def read_file(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def collect_themes(html: str, base_dir: str) -> list[tuple[str, str]]:
    """从 data-themes 属性收集所有主题名和对应 CSS 内容。"""
    m = re.search(r'data-themes="([^"]+)"', html)
    if not m:
        return []
    theme_names = [t.strip() for t in m.group(1).split(",") if t.strip()]

    # 解析 data-theme-base 路径
    m2 = re.search(r'data-theme-base="([^"]+)"', html)
    theme_base = m2.group(1) if m2 else "assets/themes/"

    themes = []
    for name in theme_names:
        path = resolve_path(theme_base + name + ".css", base_dir)
        if path:
            themes.append((name, read_file(path)))
    return themes


def get_active_theme(html: str) -> str:
    """从 <link id="theme-link"> 或 data-theme 获取当前激活主题。"""
    m = re.search(r'data-theme="([^"]+)"', html)
    if m:
        return m.group(1)
    m = re.search(r'id="theme-link"[^>]*href="([^"]+)"', html)
    if m:
        return os.path.splitext(os.path.basename(m.group(1)))[0]
    return "minimal-white"


def patch_runtime_js(js: str) -> str:
    """修改 runtime.js 中的 cycleTheme 函数，使用内联 style 切换代替外部 CSS 加载。"""
    # 替换 cycleTheme 函数中的主题切换逻辑
    old_cycle = """function cycleTheme(){
      if (!themes.length) return;
      themeIdx = (themeIdx+1) % themes.length;
      const name = themes[themeIdx];
      let link = document.getElementById('theme-link');
      if (!link) {
        link = document.createElement('link');
        link.rel = 'stylesheet';
        link.id = 'theme-link';
        document.head.appendChild(link);
      }
      // resolve relative to runtime's location
      const themePath = (root.getAttribute('data-theme-base') || 'assets/themes/') + name + '.css';
      link.href = themePath;
      root.setAttribute('data-theme', name);
      const ind = document.querySelector('.theme-indicator');
      if (ind) ind.textContent = name;
    }"""

    new_cycle = """function cycleTheme(){
      if (!themes.length) return;
      themeIdx = (themeIdx+1) % themes.length;
      const name = themes[themeIdx];
      // 切换内联主题 style（bundle 模式）
      document.querySelectorAll('style[data-inline-theme]').forEach(function(s){
        s.disabled = s.getAttribute('data-inline-theme') !== name;
      });
      root.setAttribute('data-theme', name);
      const ind = document.querySelector('.theme-indicator');
      if (ind) ind.textContent = name;
    }"""

    if old_cycle in js:
        return js.replace(old_cycle, new_cycle)
    # fallback: 用正则替换
    return re.sub(
        r"function cycleTheme\(\)\{.*?const ind = document\.querySelector\('\.theme-indicator'\);\s*if \(ind\) ind\.textContent = name;\s*\}",
        new_cycle,
        js,
        flags=re.DOTALL,
    )


def bundle(input_path: str, output_path: str | None = None) -> str:
    """将 deck HTML 打包为自包含单文件。"""
    input_path = os.path.abspath(input_path)
    base_dir = os.path.dirname(input_path)

    if output_path is None:
        name, ext = os.path.splitext(input_path)
        output_path = name + "-bundled" + ext

    html = read_file(input_path)
    active_theme = get_active_theme(html)
    themes = collect_themes(html, base_dir)

    # 1. 内联 fonts.css 中的 @import 为 <link> 标签（CDN 资源保留）
    fonts_match = re.search(r'<link[^>]*href="([^"]*fonts\.css)"[^>]*/?\s*>', html)
    fonts_imports = []
    if fonts_match:
        fonts_path = resolve_path(fonts_match.group(1), base_dir)
        if fonts_path:
            fonts_css = read_file(fonts_path)
            for url_m in re.finditer(r"@import\s+url\('([^']+)'\)\s*;", fonts_css):
                fonts_imports.append(url_m.group(1))
            # 移除 fonts.css link
            html = html.replace(fonts_match.group(0), "")

    # 2. 收集并内联所有本地 <link rel="stylesheet">
    css_blocks = []

    def inline_css(match):
        full_tag = match.group(0)
        href_m = re.search(r'href="([^"]+)"', full_tag)
        if not href_m:
            return full_tag
        resolved = resolve_path(href_m.group(1), base_dir)
        if not resolved:
            return full_tag  # 非本地文件，保留
        css = read_file(resolved)
        fname = os.path.basename(resolved)
        css_blocks.append(f"/* === {fname} === */\n{css}")
        return ""  # 移除原始 link 标签

    html = re.sub(
        r'<link\s+[^>]*rel="stylesheet"[^>]*/?\s*>',
        inline_css,
        html,
    )
    # 也匹配 href 在前的情况
    html = re.sub(
        r'<link\s+[^>]*href="[^"]*"[^>]*rel="stylesheet"[^>]*/?\s*>',
        lambda m: "",
        html,
    )

    # 3. 内联 <script src="...">
    def inline_js(match):
        full_tag = match.group(0)
        src_m = re.search(r'src="([^"]+)"', full_tag)
        if not src_m:
            return full_tag
        resolved = resolve_path(src_m.group(1), base_dir)
        if not resolved:
            return full_tag
        js = read_file(resolved)
        fname = os.path.basename(resolved)
        # 如果是 runtime.js，patch 主题切换逻辑
        if "runtime.js" in src_m.group(1) and themes:
            js = patch_runtime_js(js)
        return f"<script>\n/* === {fname} === */\n{js}\n</script>"

    html = re.sub(r'<script\s+src="[^"]*"[^>]*>\s*</script>', inline_js, html)

    # 4. 生成内联主题 style 标签
    theme_styles = []
    for name, css in themes:
        disabled = "" if name == active_theme else " disabled"
        theme_styles.append(
            f'<style data-inline-theme="{name}"{disabled}>\n/* === theme: {name} === */\n{css}\n</style>'
        )

    # 5. 组装最终 HTML
    # 在 </head> 前插入所有内容
    head_inject = ""

    # Google Fonts
    for url in fonts_imports:
        head_inject += f'<link rel="stylesheet" href="{url}">\n'

    # 合并的非主题 CSS
    if css_blocks:
        head_inject += "<style>\n" + "\n".join(css_blocks) + "\n</style>\n"

    # 主题 CSS（内联切换）
    for ts in theme_styles:
        head_inject += ts + "\n"

    html = html.replace("</head>", head_inject + "</head>")

    # 清理：移除 data-theme-base 属性（bundle 后不再需要）
    html = re.sub(r'\s*data-theme-base="[^"]*"', "", html)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    size_kb = os.path.getsize(output_path) / 1024
    return output_path, size_kb


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python bundle.py <input.html> [output.html]")
        sys.exit(1)

    inp = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else None

    result, size = bundle(inp, out)
    print(f"Bundled: {result} ({size:.1f} KB)")
