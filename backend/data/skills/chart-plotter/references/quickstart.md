# 🚀 Chart Plotter 快速上手指南（Windows 用户）

> 💡 提示：本指南专为 Windows 系统设计，所有路径、命令、截图均基于 CMD 环境验证。

---

## ✅ 第一步：准备你的数据文件

### 推荐格式：CSV（最简单）
1. 用 **记事本** 或 **VS Code** 新建文件 → 保存为 `data.csv`（**务必选择 `UTF-8` 编码！**）
2. 内容格式（第一列为 X 轴，其余为 Y 轴系列）：
   ```csv
   月份,销售额,成本
   1月,12000,8500
   2月,13500,9200
   3月,14800,9800
   ```
   > ⚠️ 注意：**不要用 Excel 直接「另存为 CSV」** —— 它默认用 `ANSI` 编码，会导致中文乱码！

### 备选格式：Excel（`.xlsx`）
- 直接保存为 `.xlsx` 即可（Excel 自动 UTF-8 兼容）

---

## ✅ 第二步：在 CMD 中运行绘图命令

打开 **CMD**（开始菜单 → 输入 `cmd` → 回车），然后依次执行：

```cmd
# 1. 进入项目根目录（确保你在 miniclaw/ 下）
cd /d "F:\vllm\.conda\envs\mini_openclaw\miniclaw"

# 2. 运行绘图脚本（以 line chart 为例）
python data\skills\chart-plotter\scripts\plot.py --input data.csv --type line --title "2024年销售趋势"
```

✅ 成功后你会看到：
- `output.png` 生成在当前目录（DPI=300，高清）
- CMD 输出：`✅ Chart saved to output.png` 和 `📊 Data shape: (3, 3)`

---

## ❓ 常见问题与解决

| 现象 | 原因 | 解决方案 |
|------|------|-----------|
| `❌ Error: Input file data.csv not found.` | `data.csv` 不在当前目录 | 把 `data.csv` 拖到 CMD 打开的窗口里，看路径是否正确 |
| `⚠️ Warning: No Chinese font detected.` | Windows 字体路径未扫描到 | 手动确认 `C:\Windows\Fonts\simhei.ttf` 存在；或重装 SimHei 字体 |
| 图表中文字显示为方块 □□ | matplotlib 未加载中文字体 | 在 `plot.py` 开头添加 `plt.rcParams['font.sans-serif'] = ['SimHei']`（已内置） |
| `UnicodeDecodeError: 'gbk' codec...` | CSV 用 ANSI 编码保存 | 用记事本 →「另存为」→ 编码选 `UTF-8` → 重试 |

---

## 📎 附：支持的图表类型速查

| 类型 | 命令 `--type` | 适用场景 |
|------|----------------|------------|
| 折线图 | `line` | 时间序列趋势（如：月度销售额） |
| 柱状图 | `bar` | 分类对比（如：各产品销量） |
| 散点图 | `scatter` | 相关性分析（如：广告费 vs 销售额） |
| 饼图 | `pie` | 占比分布（如：市场份额） |
| 直方图 | `histogram` | 数据分布（如：客户年龄分布） |
