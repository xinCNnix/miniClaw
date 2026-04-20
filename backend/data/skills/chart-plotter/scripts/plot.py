# -*- coding: utf-8 -*-
"""
Chart Plotter for Windows/macOS/Linux
- Auto-detects Chinese fonts on Windows (C:/Windows/Fonts/)
- Supports CSV/Excel input, multiple chart types
- Outputs high-res PNG + optional PDF
- UTF-8 safe, no encoding errors
"""

import os
import sys
import argparse
import pandas as pd
import matplotlib
matplotlib.use('Agg')  # Non-interactive backend
import matplotlib.pyplot as plt
import numpy as np
from pathlib import Path

# Script: backend/data/skills/chart-plotter/scripts/plot.py
# backend/ root is 5 levels up: scripts/ → chart-plotter/ → skills/ → data/ → backend/
_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
_PROJECT_ROOT = _BACKEND_ROOT.parent  # project root (miniclaw/)


def _resolve_output_path(output_path: str) -> str:
    """Resolve output path: absolute as-is, relative against project_root/outputs/."""
    p = Path(output_path)
    if p.is_absolute():
        return str(p)
    # Always place output in outputs/ unless path already includes it
    if not output_path.startswith("outputs" + os.sep) and not output_path.startswith("outputs/"):
        output_path = f"outputs{os.sep}{output_path}"
    return str(_PROJECT_ROOT / output_path)

# --- Font Setup for Chinese Support ---
def get_chinese_font():
    """Auto-detect Chinese font on Windows/macOS/Linux"""
    # Windows common paths (support both C:/ and /c/ formats)
    win_fonts = [
        r'C:/Windows/Fonts/simhei.ttf',      # SimHei
        r'C:/Windows/Fonts/msyh.ttc',        # Microsoft YaHei
        r'C:/Windows/Fonts/msyhbd.ttc',      # Microsoft YaHei Bold
        r'C:/Windows/Fonts/NotoSansSC-VF.ttf',  # Noto Sans SC
        r'C:/Windows/Fonts/NotoSerifSC-VF.ttf', # Noto Serif SC
        # Git Bash format on Windows
        '/c/Windows/Fonts/simhei.ttf',
        '/c/Windows/Fonts/msyh.ttc',
        '/c/Windows/Fonts/msyhbd.ttc',
        '/c/Windows/Fonts/NotoSansSC-VF.ttf',
        '/c/Windows/Fonts/NotoSerifSC-VF.ttf',
    ]

    # macOS & Linux fallbacks
    unix_fonts = [
        '/System/Library/Fonts/PingFang.ttc',  # macOS
        '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
        '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
        '/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf',
    ]

    for f in win_fonts + unix_fonts:
        if os.path.exists(f):
            return f

    # Final fallback: matplotlib's default (may not render Chinese)
    return None

# --- Main Plotting Logic ---
def main():
    parser = argparse.ArgumentParser(description='Plot charts from CSV/Excel with Chinese support')
    parser.add_argument('--input', required=True, help='Input file: data.csv or data.xlsx')
    parser.add_argument('--type', required=True, choices=['line', 'bar', 'scatter', 'pie', 'histogram'],
                        help='Chart type')
    parser.add_argument('--title', default='', help='Chart title (supports Chinese)')
    parser.add_argument('--xlabel', default='', help='X-axis label')
    parser.add_argument('--ylabel', default='', help='Y-axis label')
    parser.add_argument('--output-png', default='output.png', help='Output PNG filename (raster)')
    parser.add_argument('--output-svg', default='output.svg', help='Output SVG filename (vector, recommended)')
    parser.add_argument('--output-pdf', default='', help='Optional output PDF filename (vector)')

    args = parser.parse_args()
    
    # Load data
    input_path = Path(args.input)
    if not input_path.exists():
        print(f'[ERROR] Input file {args.input} not found.')
        sys.exit(1)

    try:
        if input_path.suffix.lower() == '.csv':
            df = pd.read_csv(input_path, encoding='utf-8')
        elif input_path.suffix.lower() in ['.xlsx', '.xls']:
            df = pd.read_excel(input_path)
        else:
            print(f'[ERROR] Unsupported file format. Use .csv or .xlsx')
            sys.exit(1)
    except Exception as e:
        print(f'[ERROR] Error loading data: {e}')
        sys.exit(1)
    
    # Set font
    font_path = get_chinese_font()
    if font_path:
        # Use FontManager for better font loading
        from matplotlib.font_manager import FontProperties
        try:
            font_prop = FontProperties(fname=font_path)
            plt.rcParams['font.family'] = font_prop.get_name()
            plt.rcParams['axes.unicode_minus'] = False  # Fix minus sign
            print(f'[OK] Using font: {font_prop.get_name()} from {font_path}')
        except Exception as e:
            print(f'[WARN] Could not load font {font_path}: {e}')
            print('Trying fallback method...')
            # Fallback: direct font file path
            try:
                import matplotlib.font_manager as fm
                fm.fontManager.addfont(font_path)
                plt.rcParams['font.family'] = 'sans-serif'
                plt.rcParams['font.sans-serif'] = [Path(font_path).stem]
                plt.rcParams['axes.unicode_minus'] = False
                print(f'[OK] Using fallback font configuration')
            except Exception as e2:
                print(f'[WARN] Fallback also failed: {e2}')
    else:
        print('[WARN] No Chinese font detected. Using default (may not render Chinese correctly).')
    
    # Plot
    plt.figure(figsize=(10, 6), dpi=300)
    
    if args.type == 'line':
        for col in df.columns[1:]:  # Skip first column as x-axis
            plt.plot(df.iloc[:, 0], df[col], marker='o', label=col)
        plt.xlabel(df.columns[0])
        plt.ylabel('Value')
        
    elif args.type == 'bar':
        if len(df.columns) >= 2:
            plt.bar(df.iloc[:, 0], df.iloc[:, 1], color='skyblue')
            plt.xlabel(df.columns[0])
            plt.ylabel(df.columns[1])
        else:
            plt.bar(range(len(df)), df.iloc[:, 0], color='skyblue')
            plt.xlabel('Index')
            plt.ylabel(df.columns[0])
            
    elif args.type == 'scatter':
        if len(df.columns) >= 2:
            plt.scatter(df.iloc[:, 0], df.iloc[:, 1], alpha=0.7)
            plt.xlabel(df.columns[0])
            plt.ylabel(df.columns[1])
        
    elif args.type == 'pie':
        if len(df.columns) >= 2:
            plt.pie(df.iloc[:, 1], labels=df.iloc[:, 0], autopct='%1.1f%%')
        
    elif args.type == 'histogram':
        if len(df.columns) >= 1:
            plt.hist(df.iloc[:, 0], bins=20, edgecolor='black')
            plt.xlabel(df.columns[0])
            plt.ylabel('Frequency')
    
    if args.title:
        plt.title(args.title, fontsize=14)
    if args.xlabel:
        plt.xlabel(args.xlabel)
    if args.ylabel:
        plt.ylabel(args.ylabel)
    
    plt.tight_layout()

    # Resolve output paths (auto-add outputs/ prefix)
    png_path = _resolve_output_path(args.output_png)
    svg_path = _resolve_output_path(args.output_svg)
    pdf_path = _resolve_output_path(args.output_pdf) if args.output_pdf else None

    # Ensure output directory exists
    Path(png_path).parent.mkdir(parents=True, exist_ok=True)

    # Save PNG (raster, lower quality)
    plt.savefig(png_path, bbox_inches='tight', dpi=300)
    print(f'[OK] Chart saved to {png_path} (PNG, 300 DPI)')

    # Save SVG (vector, infinite resolution)
    plt.savefig(svg_path, bbox_inches='tight', format='svg')
    print(f'[OK] Chart saved to {svg_path} (SVG, vector graphics)')

    if pdf_path:
        plt.savefig(pdf_path, bbox_inches='tight', format='pdf')
        print(f'[OK] PDF saved to {pdf_path} (PDF, vector graphics)')

    plt.close()

    # Summary
    print(f'[INFO] Data shape: {df.shape}')
    print(f'[INFO] Chart type: {args.type}')
    print(f'[INFO] Font used: {font_path or "default"}')
    print(f'[INFO] Output formats: PNG (raster), SVG (vector - recommended)')
    print(f'[INFO] Vector graphics (SVG/PDF) can be scaled infinitely without quality loss')

if __name__ == '__main__':
    main()