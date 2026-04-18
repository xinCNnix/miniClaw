---
name: doc-creator
description: "Create professional DOCX/XLSX/PPTX documents with embedded images, tables, and formatted text. Use when user asks to: (1) 'create a Word/Excel/PowerPoint document'; (2) 'generate a report with charts'; (3) 'export data to Office format'; (4) 'make a presentation with slides'; (5) insert charts/images into documents."
dependencies:
  python:
    - "python-docx>=1.0.0"
    - "openpyxl>=3.1.0"
    - "python-pptx>=0.6.0"
---

# Doc Creator Skill

## Purpose
Generate professional Microsoft Office documents (Word, Excel, PowerPoint) with support for:
- Embedded images (charts from chart-plotter)
- Formatted text (headings, bold, colors)
- Tables and data
- Multiple slides (PPTX)

## Required Inputs
- Document type: `docx`, `xlsx`, `pptx`
- Content: text, tables, or data
- Optional: image paths, title, styling

## Output
- `output.docx`: Word document
- `output.xlsx`: Excel workbook
- `output.pptx`: PowerPoint presentation

## CRITICAL: Mandatory Execution Steps

创建文档时必须完成以下两步：
1. 使用 `write_file` 编写 Python 脚本
2. 使用 `terminal` 执行脚本来生成最终文档

**重要**: 仅编写脚本是不够的，必须用 `terminal` 工具执行脚本，
用户需要的是输出文档，而不是脚本文件。

## How to Use

### Step 1: Generate Content (Optional)
```bash
# First generate charts with chart-plotter
python ../chart-plotter/scripts/plot.py --input data.csv --type line --title "Sales Trend"
```

### Step 2: Create Document

#### Word Document (DOCX)
```bash
python scripts/doc_creator.py \
  --type docx \
  --title "Quarterly Report" \
  --content "Executive Summary..." \
  --image output.png \
  --output report.docx
```

#### Excel Spreadsheet (XLSX)
```bash
python scripts/doc_creator.py \
  --type xlsx \
  --data data.csv \
  --sheet-name "Sales Data" \
  --output report.xlsx
```

#### PowerPoint Presentation (PPTX)
```bash
python scripts/doc_creator.py \
  --type pptx \
  --title "Q4 Review" \
  --content "Key metrics..." \
  --image output.png \
  --output presentation.pptx
```

### Step 3: Save with write_file
```python
# Use write_file to save the output
write_file: path="docs/report.docx", content="<base64_data>", mode="base64", mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
```

## Features

### DOCX Features
- Headings (H1-H6)
- Paragraphs with formatting
- Embedded images (resizable)
- Bullet lists
- Tables
- Page breaks

### XLSX Features
- Multiple sheets
- Data from CSV/arrays
- Auto column width
- Number formatting
- Charts (basic)

### PPTX Features
- Title slides
- Content slides
- Image slides
- Bullet points
- Custom layouts

## Examples

### Sales Report with Chart
```bash
# 1. Generate chart
python ../chart-plotter/scripts/plot.py \
  --input sales_data.csv \
  --type bar \
  --title "Monthly Sales"

# 2. Create Word report
python scripts/doc_creator.py \
  --type docx \
  --title "Q1 2026 Sales Report" \
  --content "Sales increased by 25% compared to Q4 2025." \
  --image ../chart-plotter/output.png \
  --output sales_report.docx
```

### Data Export to Excel
```bash
python scripts/doc_creator.py \
  --type xlsx \
  --csv data/sales_q1_2026.csv \
  --sheet-name "Q1 Sales" \
  --output sales_data.xlsx
```

### Presentation with Slides
```bash
python scripts/doc_creator.py \
  --type pptx \
  --title "Business Review" \
  --slides 5 \
  --content "Agenda, Financials, Growth, Challenges, Next Steps" \
  --image ../chart-plotter/output.png \
  --output review.pptx
```

## Notes
- Images are automatically resized to fit document width
- CSV files should have headers in the first row
- Chinese text is supported (uses system fonts)
- Output files are created in the current directory
