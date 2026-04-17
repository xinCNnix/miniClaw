# Doc Creator Quick Start

## Installation

Install dependencies:
```bash
cd backend
pip install python-pptx>=0.6.0
```

## Basic Usage

### 1. Create a Word Document with Chart

```bash
cd backend/data/skills/doc-creator

# First, create a sample chart (using chart-plotter)
python ../chart-plotter/scripts/plot.py \
  --input ../../../data/test-sales-q1-2026.csv \
  --type bar \
  --title "Q1 Sales"

# Create Word document with embedded chart
python scripts/doc_creator.py \
  --type docx \
  --title "Q1 2026 Sales Report" \
  --content "Sales showed strong growth in Q1 2026.\n\nKey highlights:\n- January: $120K\n- February: $150K\n- March: $180K" \
  --image ../chart-plotter/output.png \
  --output sales_report.docx
```

### 2. Create an Excel Spreadsheet

```bash
# Export CSV data to Excel
python scripts/doc_creator.py \
  --type xlsx \
  --data ../../../data/test-sales-q1-2026.csv \
  --sheet-name "Q1 Sales" \
  --title "Q1 2026 Sales Data" \
  --output sales_data.xlsx
```

### 3. Create a PowerPoint Presentation

```bash
# Create presentation with multiple slides
python scripts/doc_creator.py \
  --type pptx \
  --title "Q1 Business Review" \
  --content "Executive Summary,Financial Performance,Growth Analysis,Next Steps" \
  --image ../chart-plotter/output.png \
  --slides 5 \
  --output presentation.pptx
```

## Agent Usage Pattern

When an Agent needs to create a document:

1. **Read the skill definition**
   ```
   read_file: path="backend/data/skills/doc-creator/SKILL.md"
   ```

2. **Generate charts (if needed)**
   ```
   Use chart-plotter skill to create visualizations
   ```

3. **Create the document**
   ```
   python_repl: Execute doc_creator.py with appropriate parameters
   ```

4. **Save the output**
   ```
   write_file: path="docs/report.docx", mode="base64", ...
   ```

## Supported Formats

| Format | Extension | Features |
|--------|-----------|----------|
| Word   | .docx     | Text, images, tables, formatting |
| Excel  | .xlsx     | Multiple sheets, data import, formulas |
| PowerPoint | .pptx | Slides, images, layouts |

## Notes

- Images are automatically resized to fit document width
- Chinese text is supported (uses system fonts)
- CSV files should have headers in the first row
- Output files are created in the current directory
