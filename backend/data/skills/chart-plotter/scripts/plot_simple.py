# -*- coding: utf-8 -*-
"""
Minimal Chinese-Safe Chart Plotter
- Reads UTF-8 CSV with Chinese headers
- Auto-detects Chinese font on the system
- Saves PNG without console output
"""
import sys
import os
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def _detect_chinese_font() -> str | None:
    """Detect an available Chinese font file and register it with matplotlib."""
    import matplotlib.font_manager as fm

    known_fonts = [
        "msyh.ttc", "simhei.ttf", "simsun.ttc", "simkai.ttf",
        "STZHONGS.TTF", "STKAITI.TTF", "NotoSansCJK-Regular.ttc",
    ]
    font_dirs = []
    if sys.platform == "win32":
        windir = os.environ.get("WINDIR", r"C:\Windows")
        font_dirs.append(os.path.join(windir, "Fonts"))
        local = os.environ.get("LOCALAPPDATA", "")
        if local:
            font_dirs.append(os.path.join(local, "Microsoft", "Windows", "Fonts"))
    else:
        font_dirs.extend([
            "/usr/share/fonts",
            "/usr/local/share/fonts",
            "/System/Library/Fonts",
            os.path.expanduser("~/.fonts"),
            os.path.expanduser("~/.local/share/fonts"),
        ])

    for d in font_dirs:
        if not os.path.isdir(d):
            continue
        for fname in known_fonts:
            fpath = os.path.join(d, fname)
            if os.path.exists(fpath):
                try:
                    fm.fontManager.addfont(fpath)
                    return os.path.splitext(fname)[0]
                except Exception:
                    continue
    return None


_font_name = _detect_chinese_font()
if _font_name:
    plt.rcParams["font.sans-serif"] = [_font_name, "DejaVu Sans", "sans-serif"]
else:
    plt.rcParams["font.sans-serif"] = ["DejaVu Sans", "sans-serif"]
plt.rcParams["axes.unicode_minus"] = False

if len(sys.argv) < 2:
    print('Usage: python plot_simple.py <input.csv> <output.png>')
    sys.exit(1)

input_csv = sys.argv[1]
output_png = sys.argv[2]

df = pd.read_csv(input_csv, encoding='utf-8')

# Assume first column is x, second is y
x_col = df.columns[0]
y_col = df.columns[1]

plt.figure(figsize=(8, 6))
plt.bar(df[x_col], df[y_col], color=['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728'])
plt.title('2026年Q1销售额对比', fontsize=14)
plt.xlabel(x_col, fontsize=12)
plt.ylabel(y_col, fontsize=12)
plt.grid(True, alpha=0.3)

# Add value labels on bars
for i, v in enumerate(df[y_col]):
    plt.text(i, v + 1, str(v), ha='center', va='bottom')

plt.tight_layout()
plt.savefig(output_png, dpi=300, bbox_inches='tight')
# No print() — silent & robust
