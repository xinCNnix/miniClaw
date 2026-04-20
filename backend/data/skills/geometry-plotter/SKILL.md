---
name: geometry-plotter
description: "绘制2D/3D数学图形：函数图像、几何证明示意图、3D曲面等。输出 SVG 矢量图。Use when user asks to: (1) 画图、绘图、绘制图形; (2) 函数图像 (sin, cos, relu, sigmoid 等); (3) 几何证明示意图; (4) 数学定理可视化; (5) 坐标系、函数曲线、3D曲面."
dependencies:
  python:
    - "matplotlib>=3.7.0"
    - "numpy>=1.24.0"
---

# Geometry Plotter

## 功能

绘制 2D/3D 数学图形，输出 SVG 矢量图。

- 函数图像（sin, cos, relu, sigmoid 等）
- 几何证明示意图（点坐标、线段、多边形、角度标注、弧线）
- 3D 曲面和立体图形

## 重要：调用方式

**必须使用 `python_repl` 工具执行以下代码。禁止用 `read_file` 读取 handler.py。**

## 两种调用模式

### 模式 1：函数图像 — `draw()`

适合有明确函数表达式的场景。Agent 从用户需求提取函数式、范围等参数。

```python
import sys; sys.path.insert(0, 'data/skills/geometry-plotter/scripts')
from handler import draw
result = draw(
    expr="<函数表达式>",
    x_range=(-3, 3),
    title="<标题>",
    latex_label=r"$<LaTeX公式>$"
)
print(result)
```

**参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `expr` | str 或 list | 是 | Python 表达式，使用 `x` 和 `np`，如 `"np.sin(x)"`。多条曲线传列表 |
| `x_range` | tuple | 否 | x 轴范围，默认 `(-5, 5)` |
| `y_range` | tuple | 否 | y 轴范围，默认自动 |
| `title` | str | 否 | 图表标题 |
| `latex_label` | str 或 list | 否 | 图例 LaTeX，如 `r"$\\sin(x)$"`，多条曲线传列表 |
| `xlabel` | str | 否 | x 轴标签 |
| `ylabel` | str | 否 | y 轴标签 |
| `save_name` | str | 否 | 文件名（不含扩展名），默认自动 |

**示例 — 单函数：**

用户: "画一个 ReLU 函数图像"

```python
from handler import draw
result = draw(
    expr="np.maximum(0, x)",
    x_range=(-3, 3),
    title="ReLU Function",
    latex_label=r"$f(x) = \max(0, x)$"
)
print(result)
```

**示例 — 多函数：**

用户: "画出 sin 和 cos 的图像"

```python
from handler import draw
result = draw(
    expr=["np.sin(x)", "np.cos(x)"],
    x_range=(0, 2*3.14159),
    latex_label=[r"$\sin(x)$", r"$\cos(x)$"],
    title="sin and cos"
)
print(result)
```

### 模式 2：自由绘图 — `draw_code()`

适合几何图形、证明示意图、3D 曲面等**无法用单个表达式描述**的场景。Agent 编写完整 matplotlib 代码，handler 提供执行环境和文件保存。

```python
import sys; sys.path.insert(0, 'data/skills/geometry-plotter/scripts')
from handler import draw_code
code = """
<matplotlib 代码>
"""
result = draw_code(code)
print(result)
```

**代码中可直接使用：** `plt`, `np`, `mpatches`, `SAVE_PATH`（输出文件路径）, `pi`, `e`

**代码规则：**
- 必须以 `plt.savefig(SAVE_PATH)` 结尾
- 禁止 `plt.show()`
- 禁止使用 `os`, `subprocess`, `open`, `exec`, `eval`, `__import__`
- 数学公式用 `r"$...$"` (matplotlib mathtext 语法)
- 中文字体用 `'SimHei'` 或 `'Microsoft YaHei'`
- 禁止 `\begin{cases}`, `\boxed`, `\text{}` 等 LaTeX 环境命令

**示例 — 几何证明：**

用户: "画一个直角三角形，标注三边长度 3, 4, 5"

```python
from handler import draw_code
code = '''
fig, ax = plt.subplots(figsize=(6, 6))

# 直角三角形顶点
A = np.array([0, 0])
B = np.array([3, 0])
C = np.array([0, 4])

triangle = plt.Polygon([A, B, C], fill=False, edgecolor='black', linewidth=2)
ax.add_patch(triangle)

# 标注边长
ax.annotate(r"$3$", xy=(1.5, -0.3), fontsize=14, ha='center')
ax.annotate(r"$4$", xy=(-0.5, 2), fontsize=14, ha='center')
ax.annotate(r"$5$", xy=(1.8, 2.2), fontsize=14, ha='center')

# 直角标记
right_angle = mpatches.Arc((0, 0), 0.6, 0.6, angle=0, theta1=0, theta2=90, color='gray')
ax.add_patch(right_angle)

ax.set_xlim(-1, 4)
ax.set_ylim(-1, 5)
ax.set_aspect('equal')
ax.grid(True, alpha=0.3)
ax.set_title(r"Right Triangle: $3^2 + 4^2 = 5^2$", fontsize=14)

plt.savefig(SAVE_PATH)
'''
result = draw_code(code)
print(result)
```

**示例 — 3D 曲面：**

用户: "画一个 z=x²+y² 的 3D 曲面图"

```python
from handler import draw_code
code = '''
fig = plt.figure(figsize=(8, 6))
ax = fig.add_subplot(111, projection='3d')

x = np.linspace(-3, 3, 100)
y = np.linspace(-3, 3, 100)
X, Y = np.meshgrid(x, y)
Z = X**2 + Y**2

ax.plot_surface(X, Y, Z, cmap='viridis', alpha=0.8)
ax.set_xlabel('X')
ax.set_ylabel('Y')
ax.set_zlabel(r'$z = x^2 + y^2$')
ax.set_title(r"$z = x^2 + y^2$", fontsize=14)

plt.savefig(SAVE_PATH)
'''
result = draw_code(code)
print(result)
```

## 格式规范

- 数学公式统一使用 `r"$...$"` 格式
- **必须使用 matplotlib mathtext 语法**（`usetex=False`），不使用外部 LaTeX 引擎
- mathtext 支持的语法：`\alpha`, `\beta`, `\sin`, `\cos`, `\sqrt{}`, `\frac{}{}`, `^{}`, `_{}`, `\int`, `\sum`, `\pi`, `\infty`, `\neq`, `\leq`, `\geq` 等
- mathtext 不支持的语法（禁止使用）：`\begin{cases}`, `\boxed`, `\text{}`, `\begin{align}`, `\begin{equation}`, `\mathrm{}` 等完整 LaTeX 环境命令
- 禁止在公式内嵌中文，中文标注写在 `r"$...$"` 外面，如 `title="正弦函数 " + r"$y = \sin(x)$"`
- 中文字体：`'SimHei'` 或 `'Microsoft YaHei'`
- 几何图形坐标轴等比例：`ax.set_aspect('equal')`

## 如何选择模式

| 场景 | 模式 | 说明 |
|------|------|------|
| 函数图像 (sin, relu, 自定义) | `draw()` | 有明确表达式 |
| 多函数对比 | `draw()` | expr 传列表 |
| 几何证明（点、线、多边形、角度） | `draw_code()` | Agent 编写坐标和绘图代码 |
| 3D 曲面/立体 | `draw_code()` | 需要 3D axes |
| 任意复杂图形 | `draw_code()` | Agent 自由控制 |

## 错误处理

- `expr` 无法执行 → 返回 `{"status": "error", ...}`
- `draw_code` 代码报错 → 返回错误类型和信息
- 代码执行但未生成文件 → 提示检查 `SAVE_PATH`
