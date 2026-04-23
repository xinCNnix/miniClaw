"""
Geometry Plotter Skill Handler

两种模式：
1. draw()     — 函数图像，Agent 传入结构化参数（expr, x_range 等）
2. draw_code() — 自由绘图，Agent 传入完整 matplotlib 代码

均不依赖 LLM，由 Agent 解析用户需求后组装输入直接调用。
输出 SVG 矢量图。
"""

import hashlib
import logging
import re
import traceback
from pathlib import Path
from typing import Optional, Union

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np

# ── 中文字体配置 ──────────────────────────────────────────────
plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False  # 解决负号显示问题

# ── 渲染配置 ────────────────────────────────────────────────
# 使用 matplotlib 内置 mathtext 渲染数学公式（$...$ 语法）
# 不使用外部 LaTeX（usetex=True），避免 MiKTeX 不支持中文 Unicode 的问题
plt.rcParams['text.usetex'] = False

logger = logging.getLogger(__name__)

# 项目路径
_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
_PROJECT_ROOT = _BACKEND_ROOT.parent
_OUTPUT_DIR = _PROJECT_ROOT / "outputs"
_DATA_OUTPUT_DIR = _BACKEND_ROOT / "data" / "outputs"

_COLORS = ['#2196F3', '#F44336', '#4CAF50', '#FF9800', '#9C27B0', '#00BCD4']


def _safe_text(text: str) -> str:
    """安全化 mathtext：如果 mathtext 无法解析，剥离 $...$ 回退为纯文本。

    mathtext 不支持 \\text{}, \\mathrm{}, \\begin{} 等 LaTeX 命令，
    遇到这些会抛 ValueError。此函数先试探渲染，失败则把 $...$ 内容
    剥离为可读的纯文本。
    """
    if not text or '$' not in text:
        return text

    # 试探 mathtext 能否解析
    try:
        from matplotlib.mathtext import MathTextParser
        _parser = MathTextParser('Agg')
        _parser.parse(text)
        return text
    except Exception:
        logger.warning(f"[geometry-plotter] mathtext 不支持，回退纯文本: {text}")

    # 剥离 $...$ 中的 LaTeX 命令，保留可读内容
    def _strip_latex(match):
        inner = match.group(1)
        # 移除常见 LaTeX 命令前缀，保留核心内容
        inner = re.sub(r'\\(?:mathrm|text|textrm|mathbf|mathit|mathsf)\{([^}]*)\}', r'\1', inner)
        inner = re.sub(r'\\(?:frac)\{([^}]*)\}\{([^}]*)\}', r'\1/\2', inner)
        inner = re.sub(r'\\(?:sqrt)\{([^}]*)\}', r'sqrt(\1)', inner)
        inner = re.sub(r'\\(?:alpha|beta|gamma|delta|epsilon|theta|lambda|mu|sigma|omega|pi|phi|psi)\b',
                        lambda m: m.group(0)[1:], inner)
        inner = re.sub(r'\\(?:sin|cos|tan|log|ln|exp|sqrt|sum|int|prod|lim|infty)\b',
                        lambda m: m.group(0)[1:], inner)
        inner = re.sub(r'\\[a-zA-Z]+', '', inner)
        inner = re.sub(r'[{}]', '', inner)
        inner = re.sub(r'\^(\w)', r'^\1', inner)
        inner = re.sub(r'_(\w)', r'_\1', inner)
        return inner.strip()

    result = re.sub(r'\$([^$]+)\$', _strip_latex, text)
    return result


# ── 工具函数 ──────────────────────────────────────────────────

def _ensure_dirs():
    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    _DATA_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def _save_fig(fig, save_name: Optional[str] = None, name_seed: str = "") -> dict:
    """保存图表到 SVG，双写到 data/outputs，返回结果 dict。"""
    if not save_name:
        content_hash = hashlib.md5(name_seed.encode()).hexdigest()[:8]
        save_name = f"geometry_{content_hash}"

    output_path = _OUTPUT_DIR / f"{save_name}.svg"
    fig.savefig(output_path, format='svg', bbox_inches='tight')
    plt.close(fig)

    # 双写到 data/outputs
    data_output_path = _DATA_OUTPUT_DIR / output_path.name
    try:
        import shutil
        shutil.copy2(output_path, data_output_path)
    except Exception:
        pass

    logger.info(f"[geometry-plotter] 成功: {output_path}")

    return {
        "status": "success",
        "image_path": str(data_output_path),
        "image_format": "svg",
    }


def _eval_expr(expr: str, x: np.ndarray) -> np.ndarray:
    """安全求值数学表达式。"""
    safe_globals = {
        "__builtins__": {
            "abs": abs, "min": min, "max": max, "float": float, "int": int,
            "True": True, "False": False, "None": None,
        },
        "np": np,
        "x": x,
        "pi": np.pi,
        "e": np.e,
    }
    return eval(expr, safe_globals)  # noqa: S307


# ── 模式 1: 函数图像（结构化参数）──────────────────────────────

def draw(
    expr: Union[str, list[str]],
    x_range: tuple[float, float] = (-5, 5),
    y_range: Optional[tuple[float, float]] = None,
    title: Optional[str] = None,
    latex_label: Optional[Union[str, list[str]]] = None,
    xlabel: Optional[str] = None,
    ylabel: Optional[str] = None,
    save_name: Optional[str] = None,
    num_points: int = 500,
) -> dict:
    """绘制函数图像。

    Args:
        expr: Python 表达式，使用变量 x 和 np。
              单条: "np.sin(x)"  多条: ["np.sin(x)", "np.cos(x)"]
        x_range: x 轴范围，默认 (-5, 5)
        y_range: y 轴范围，None 则自动
        title: 图表标题
        latex_label: 图例 LaTeX 标签，如 r"$\\sin(x)$"
        xlabel: x 轴标签
        ylabel: y 轴标签
        save_name: 输出文件名（不含扩展名）
        num_points: 采样点数

    Returns:
        {"status": "success/error", "image_path": ..., "svg_content": ...}
    """
    try:
        _ensure_dirs()

        exprs = [expr] if isinstance(expr, str) else list(expr)
        labels = [latex_label] if isinstance(latex_label, str) else (
            list(latex_label) if latex_label else [None] * len(exprs)
        )

        x = np.linspace(x_range[0], x_range[1], num_points)
        fig, ax = plt.subplots(figsize=(8, 6))

        for i, (e, label) in enumerate(zip(exprs, labels)):
            y = _eval_expr(e, x)
            ax.plot(x, y, color=_COLORS[i % len(_COLORS)], linewidth=2, label=label)

        _setup_axes(ax, x_range, y_range, title, xlabel, ylabel)
        if any(l is not None for l in labels):
            ax.legend(fontsize=12)

        return _save_fig(fig, save_name, "+".join(exprs) + str(x_range))

    except Exception as e:
        logger.error(f"[geometry-plotter] draw 失败: {e}\n{traceback.format_exc()}")
        plt.close('all')
        return {"status": "error", "result": f"{type(e).__name__}: {e}"}


# ── 模式 2: 自由绘图（Agent 提供 matplotlib 代码）──────────────

def draw_code(code: str, save_name: Optional[str] = None) -> dict:
    """执行 Agent 提供的 matplotlib 代码，保存输出为 SVG。

    Agent 负责编写代码，handler 提供执行环境和文件保存。
    代码中可直接使用: plt, np, mpatches (matplotlib.patches)
    必须以 plt.savefig(SAVE_PATH) 结尾（或用 SAVE_PATH 变量保存）。

    Args:
        code: 完整的 matplotlib 绘图代码
        save_name: 输出文件名（不含扩展名）

    Returns:
        {"status": "success/error", "image_path": ..., "svg_content": ...}
    """
    try:
        _ensure_dirs()

        if not save_name:
            save_name = f"geometry_{hashlib.md5(code.encode()).hexdigest()[:8]}"

        output_path = _OUTPUT_DIR / f"{save_name}.svg"

        # 预检：检测被禁止的 import 语句，给出友好提示
        import re

        # 白名单：这些库已被预注入 exec_globals，允许 import（不会加载新模块）
        _IMPORT_WHITELIST = {
            "matplotlib", "matplotlib.pyplot", "matplotlib.patches",
            "numpy",
            "mpl_toolkits", "mpl_toolkits.mplot3d",
        }

        # Strip whitelisted import lines (modules already pre-injected)
        # Block non-whitelisted imports
        clean_lines = []
        for line in code.split('\n'):
            stripped = line.strip()
            if re.match(r'^(import |from \S+ import )', stripped):
                mod_match = re.match(r'^(?:from\s+(\S+)\s+import|import\s+(\S+))', stripped)
                if mod_match:
                    full_mod = mod_match.group(1) or mod_match.group(2)
                    base_mod = full_mod.split('.')[0]
                    if full_mod in _IMPORT_WHITELIST or base_mod in _IMPORT_WHITELIST:
                        continue  # Skip whitelisted import (already pre-injected)
                return {
                    "status": "error",
                    "result": (
                        f"draw_code 沙箱禁止 import 语句。"
                        f"可用对象: plt, np, mpatches, matplotlib, Axes3D, SAVE_PATH, pi, e。"
                        f"问题行: {stripped}"
                    ),
                }
            clean_lines.append(line)
        code = '\n'.join(clean_lines)

        # 构建安全执行环境
        exec_globals = {
            "__builtins__": {
                "abs": abs, "min": min, "max": max, "len": len,
                "range": range, "enumerate": enumerate, "zip": zip,
                "int": int, "float": float, "str": str, "bool": bool,
                "list": list, "tuple": tuple, "dict": dict, "set": set,
                "True": True, "False": False, "None": None,
                "print": print, "round": round, "sum": sum,
                "sorted": sorted, "reversed": reversed,
                "isinstance": isinstance, "type": type,
            },
            "plt": plt,
            "np": np,
            "mpatches": mpatches,
            "matplotlib": matplotlib,
            "SAVE_PATH": str(output_path),
            "pi": np.pi,
            "e": np.e,
        }

        # 预导入 3D 支持
        try:
            from mpl_toolkits.mplot3d import Axes3D  # noqa: F401
            exec_globals["Axes3D"] = Axes3D
        except ImportError:
            pass

        exec(code, exec_globals)  # noqa: S102
        plt.close('all')

        if not output_path.exists():
            return {"status": "error", "result": "代码执行成功但未生成输出文件，请确保使用 SAVE_PATH 保存"}

        # 双写到 data/outputs
        data_output_path = _DATA_OUTPUT_DIR / output_path.name
        try:
            import shutil
            shutil.copy2(output_path, data_output_path)
        except Exception:
            pass

        logger.info(f"[geometry-plotter] draw_code 成功: {output_path}")

        return {
            "status": "success",
            "image_path": str(data_output_path),
            "image_format": "svg",
        }

    except Exception as e:
        logger.error(f"[geometry-plotter] draw_code 失败: {e}\n{traceback.format_exc()}")
        plt.close('all')
        return {"status": "error", "result": f"{type(e).__name__}: {e}"}


# ── 通用图表配置 ──────────────────────────────────────────────

def _setup_axes(ax, x_range=None, y_range=None, title=None, xlabel=None, ylabel=None):
    """配置坐标轴样式，标题/标签使用 _safe_text 防止 mathtext 崩溃。"""
    if x_range:
        ax.set_xlim(x_range)
    if y_range:
        ax.set_ylim(y_range)
    ax.axhline(y=0, color='gray', linewidth=0.5, linestyle='-')
    ax.axvline(x=0, color='gray', linewidth=0.5, linestyle='-')
    ax.grid(True, alpha=0.3)
    ax.spines['right'].set_visible(False)
    ax.spines['top'].set_visible(False)
    if title:
        ax.set_title(_safe_text(title), fontsize=14)
    if xlabel:
        ax.set_xlabel(_safe_text(xlabel), fontsize=12)
    if ylabel:
        ax.set_ylabel(_safe_text(ylabel), fontsize=12)
