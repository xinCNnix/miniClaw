---
name: chart-plotter
description: "Create, customize, and export publication-ready charts (line, bar, scatter, pie) from CSV/Excel data with full Chinese font support, responsive layout, and Windows-compatible rendering. Use when user asks to: (1) 'plot a chart', 'draw a graph', 'make a visualization'; (2) specify chart type ('line chart', 'bar plot'); (3) mention Chinese labels, titles, or fonts; (4) request PNG/PDF export; (5) provide tabular data (CSV, Excel) or column names in Chinese."
---

# Chart Plotter Skill

## Purpose
Generate high-fidelity, publication-ready charts from structured data, with guaranteed Chinese text rendering on Windows/macOS/Linux.

## Required Inputs
- Data source: `data.csv`, `data.xlsx`, or inline table (pasted as markdown/table)
- Chart type: `line`, `bar`, `scatter`, `pie`, `histogram`
- Optional: title, xlabel, ylabel, Chinese font path (auto-detected if omitted)

## Output
所有输出文件自动保存到 `downloads/` 目录。

- `downloads/output.svg`: **Vector graphics** (default, recommended - infinite resolution)
- `downloads/output.pdf`: **Vector graphics** (print-ready, if requested)
- `downloads/output.png`: Raster image (300 DPI, always generated)
- Console summary: dimensions, data shape, encoding info

⚠️ **注意**: 输出路径无需手动指定 `downloads/` 前缀，脚本会自动将文件放入 `downloads/` 目录。

## How to Use
1. Place your data file in `./data/` or provide inline table
2. Run `python scripts/plot.py --input data.csv --type bar --title "销售趋势"`
3. View `output.svg` — **Vector graphics, infinite resolution, Chinese labels work perfectly**

**Example:**
```bash
python scripts/plot.py \
  --input data.csv \
  --type bar \
  --title "2026年第一季度销售数据" \
  --output-svg sales_chart.svg
```
