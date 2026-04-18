---
name: chart-plotter
description: "Create, customize, and export publication-ready charts (line, bar, scatter, pie, histogram) from CSV/Excel data with full Chinese font support, responsive layout, and Windows-compatible rendering. Use when user asks to: (1) 画图表、绘图、数据可视化; (2) 折线图、柱状图、散点图、饼图、直方图; (3) CSV/Excel 数据绘制; (4) mention chart type ('line chart', 'bar plot'); (5) 中文标签、标题、字体."
dependencies:
  python:
    - "matplotlib>=3.7.0"
    - "numpy>=1.24.0"
    - "pandas>=2.0.0"
---

# Chart Plotter Skill

## 功能描述

从结构化数据生成高质量图表，支持 CSV/Excel 输入，保证 Windows/macOS/Linux 上的中文渲染。

### 支持的图表类型
- **折线图 (line)**: 趋势分析、时间序列、多系列对比
- **柱状图 (bar)**: 分类比较、排名、分组数据
- **散点图 (scatter)**: 相关性分析、分布展示
- **饼图 (pie)**: 占比分析、构成展示
- **直方图 (histogram)**: 频率分布、数据分布

## 输入

- 数据源: CSV 文件、Excel 文件或内联表格
- 图表类型: `line`, `bar`, `scatter`, `pie`, `histogram`
- 可选: 标题、X/Y 轴标签、输出格式

## 输出

所有输出文件自动保存到 `outputs/` 目录。

- `outputs/<name>.svg`: **SVG 矢量图**（默认，推荐 — 无限缩放不失真）
- `outputs/<name>.png`: 栅格图 (300 DPI)
- `outputs/<name>.pdf`: 矢量图（按需生成）

⚠️ **注意**: 输出路径无需手动指定 `outputs/` 前缀，脚本会自动将文件放入 `outputs/` 目录。

## 调用方式

本 skill 通过 `terminal` 工具调用脚本执行。**调用时必须提供 command 参数：**

**参数格式（JSON）：**
```json
{
  "command": "python data/skills/chart-plotter/scripts/plot.py --input <数据文件> --type <图表类型> --title \"<标题>\" --output-svg <文件名>.svg"
}
```

脚本路径: `data/skills/chart-plotter/scripts/plot.py`

⚠️ **不要**自己用 python_repl 写 matplotlib 代码来画图表，必须通过 terminal 工具调用，且 command 参数不能为空。脚本已内置中文字体检测、高 DPI 输出和格式管理。

如果用户没有提供数据文件，Agent 应先通过 `write_file` 创建 CSV 文件，再调用脚本绘图。

## Example Interactions

### User: "帮我画一个柱状图，这是销售数据 [表格]"

**Agent action:**
1. 先用 `write_file` 将数据保存为 CSV 文件
2. 调用脚本:
```bash
python data/skills/chart-plotter/scripts/plot.py \
  --input data/sales.csv \
  --type bar \
  --title "2026年第一季度销售数据" \
  --output-svg sales_chart.svg
```

### User: "画一个折线图，X轴是月份，Y轴是收入"

**Agent action:**
1. 先用 `write_file` 将数据保存为 CSV（第一列月份，第二列收入）
2. 调用脚本:
```bash
python data/skills/chart-plotter/scripts/plot.py \
  --input data/revenue.csv \
  --type line \
  --title "月度收入趋势" \
  --xlabel "月份" \
  --ylabel "收入(万元)" \
  --output-svg revenue.svg
```

### User: "画一个饼图展示各产品占比"

**Agent action:**
1. 先用 `write_file` 将数据保存为 CSV（第一列产品名，第二列占比）
2. 调用脚本:
```bash
python data/skills/chart-plotter/scripts/plot.py \
  --input data/products.csv \
  --type pie \
  --title "产品占比" \
  --output-svg products.svg
```

### User: "画一个散点图分析身高和体重的关系"

**Agent action:**
1. 先用 `write_file` 将数据保存为 CSV（第一列身高，第二列体重）
2. 调用脚本:
```bash
python data/skills/chart-plotter/scripts/plot.py \
  --input data/body_data.csv \
  --type scatter \
  --title "身高与体重关系" \
  --xlabel "身高(cm)" \
  --ylabel "体重(kg)" \
  --output-svg scatter.svg
```

### User: "画一个正弦函数图像"

**Agent action:**
注意：函数图像属于 geometry-plotter 的范围，不是 chart-plotter。Agent 应使用 geometry-plotter skill。

### User: "从 CSV 文件 data.csv 画一个直方图"

**Agent action:**
```bash
python data/skills/chart-plotter/scripts/plot.py \
  --input data/data.csv \
  --type histogram \
  --title "数据分布" \
  --output-svg histogram.svg
```

## 脚本参数

| 参数 | 说明 | 示例 |
|------|------|------|
| `--input` | 输入文件路径（CSV/Excel）| `data/sales.csv` |
| `--type` | 图表类型: line, bar, scatter, pie, histogram | `bar` |
| `--title` | 图表标题（支持中文）| `"销售趋势"` |
| `--xlabel` | X 轴标签 | `"月份"` |
| `--ylabel` | Y 轴标签 | `"收入"` |
| `--output-svg` | SVG 输出文件名 | `chart.svg` |
| `--output-png` | PNG 输出文件名 | `chart.png` |
| `--output-pdf` | PDF 输出文件名（可选）| `chart.pdf` |

## 数据文件格式

CSV 文件第一行是列名，第一列默认作为 X 轴：

```csv
月份,收入,支出
1月,120,80
2月,150,90
3月,180,85
```

- **折线图**: 第一列为 X 轴，其余列各画一条线
- **柱状图**: 第一列为分类，第二列为数值
- **散点图**: 第一列为 X 值，第二列为 Y 值
- **饼图**: 第一列为标签，第二列为数值
- **直方图**: 第一列为数据值

## Error Handling

- **Input file not found**: 数据文件不存在。Agent 应先检查路径或先用 `write_file` 创建数据文件。
- **Unsupported file format**: 只支持 `.csv` 和 `.xlsx`。如果是其他格式，Agent 应先转换为 CSV。
- **No Chinese font detected**: 系统缺少中文字体。图表仍会生成，但中文可能显示为方块。Agent 应提示用户安装中文字体。

## 注意事项

- 系统依赖 matplotlib、numpy、pandas
- 自动检测中文字体（Windows: SimHei/Microsoft YaHei，macOS: PingFang，Linux: Noto Sans CJK）
- 默认同时输出 SVG 和 PNG 格式
- 图表分辨率 300 DPI，适合打印和演示
- 函数图像（sin, cos, relu 等）属于 geometry-plotter 范围，不是本 skill
