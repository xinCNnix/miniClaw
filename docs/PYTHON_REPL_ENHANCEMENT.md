# Python REPL 工具增强说明

## 更新概述

Python REPL 工具已大幅增强，现在支持：
- ✅ 在受控目录读写文件
- ✅ 三种执行模式（safe/standard/free）
- ✅ 动态内存限制（基于可用内存）
- ✅ 操作计数（防止死循环）
- ✅ 实时监控和用户可中断

---

## 新功能详解

### 1. 文件 I/O 能力

**现在可以在 Python 代码中直接读写文件：**

```python
# 写入文件
with open("data/output.txt", "w") as f:
    f.write("Hello World")

# 读取文件
with open("data/input.txt", "r") as f:
    content = f.read()
```

**允许的目录：**
- ✅ 项目根目录（默认）
- ✅ 用户配置的额外目录（通过 `ALLOWED_WRITE_DIRS` 配置）

**安全保护：**
- ❌ 无法访问敏感文件（.env、credentials.encrypted 等）
- ❌ 无法访问项目目录外的文件
- ❌ 无法路径遍历（../../etc/passwd）

---

### 2. 三种执行模式

#### safe 模式（保守保护）
```
超时: 60秒
内存: 20% 可用内存
操作限制: 100万次
```

**适用场景：**
- 测试不确定的代码
- 学习和探索
- 早期开发阶段

#### standard 模式（标准保护，默认）
```
超时: 5分钟
内存: 50% 可用内存
操作限制: 1000万次
```

**适用场景：**
- 日常使用
- 中等规模数据处理
- 常规文件生成

#### free 模式（自由模式）
```
超时: 30分钟
内存: 80% 可用内存
操作限制: 无限制
```

**适用场景：**
- 大型数据处理
- 生成大文件（Excel、PPT、PDF）
- 复杂计算任务

---

### 3. 动态内存限制

**内存限制根据可用内存自动计算：**

```
系统可用内存: 8GB
→ safe 模式: 1.6GB (20%)
→ standard 模式: 4GB (50%)
→ free 模式: 6.4GB (80%)

系统可用内存: 32GB
→ safe 模式: 6.4GB (20%)
→ standard 模式: 16GB (50%)
→ free 模式: 25.6GB (80%)
```

**优点：**
- 自适应不同机器配置
- 16GB 和 64GB 内存机器都能合理利用
- 不会因为硬限制导致合法任务失败

---

### 4. 操作计数（防止死循环）

**通过 sys.settrace 计数每行代码执行次数：**

```python
# 死循环示例
while True:
    pass  # ← 每次循环都计数，超过限制会被中断
```

**模式对比：**
- safe: 100万次操作后中断
- standard: 1000万次操作后中断
- free: 无限制

---

### 5. 实时监控

**监控线程定期检查：**
- 执行时间是否超时
- 内存使用是否超限
- 用户是否请求停止

**超过警告阈值（70%）时显示：**
```
[WARNING] Memory usage: 3.5GB / 4.1GB (88%)
```

---

## 使用示例

### 示例 1：生成 Excel 文件

```python
# Agent 执行（使用 free 模式）
python_repl: mode=free, code="""
import pandas as pd

# 生成数据
data = {
    'Name': ['Alice', 'Bob', 'Charlie'],
    'Age': [25, 30, 35],
    'City': ['New York', 'London', 'Tokyo']
}

df = pd.DataFrame(data)
df.to_excel('report.xlsx', index=False)

print('Excel file generated: report.xlsx')
"""
```

**执行过程：**
```
[INFO] 启动 python_repl（free 模式）
[INFO] 可用内存: 8.2GB，限制: 6.6GB (80%)

[进度] 执行中... (5秒)
[INFO] 内存: 256MB / 6.6GB (4%)

[进度] 执行中... (15秒)
[DONE] Excel file generated: report.xlsx
```

---

### 示例 2：生成 PPT 演示文稿

```python
python_repl: mode=free, code="""
from pptx import Presentation

prs = Presentation()
title_slide = prs.slides.add_slide(prs.slide_layouts[0])
title = title_slide.shapes.title
title.text = "Project Summary"

# 添加内容幻灯片
bullet_slide = prs.slides.add_slide(prs.slide_layouts[1])
text_box = bullet_slide.shapes.placeholders[1]
text_frame = text_box.text_frame
text_frame.text = "Key Points:\\n- Point 1\\n- Point 2\\n- Point 3"

prs.save('presentation.pptx')
print('PPT generated: presentation.pptx')
"""
```

---

### 示例 3：数据处理并保存

```python
python_repl: mode=standard, code="""
import json
import requests

# 获取数据
response = requests.get('https://api.example.com/data')
data = response.json()

# 处理数据
processed = []
for item in data['items']:
    processed.append({
        'id': item['id'],
        'name': item['name'].upper(),
        'value': item['value'] * 2
    })

# 保存结果
with open('output/processed.json', 'w') as f:
    json.dump(processed, f, indent=2)

print(f'Processed {len(processed)} items')
print('Saved to output/processed.json')
"""
```

---

## API 端点

### 停止执行
```
POST /api/python_repl/stop
```

### 查询执行状态
```
GET /api/python_repl/status
```

响应：
```json
{
  "is_running": false,
  "operations": 15234,
  "elapsed": 12.5,
  "mode": "standard"
}
```

### 查询系统资源
```
GET /api/python_repl/resources
```

响应：
```json
{
  "total_memory_mb": 16384.0,
  "available_memory_mb": 8192.0,
  "used_memory_mb": 8192.0,
  "memory_usage_percent": 50.0,
  "cpu_percent": 15.2
}
```

### 查询配置
```
GET /api/python_repl/config
```

响应：
```json
{
  "mode": "standard",
  "timeout": 300,
  "memory_limit_mb": 4096,
  "max_operations": 10000000,
  "allowed_dirs": ["I:/code/miniclaw", "C:/Users/YourName/Documents"]
}
```

### 更新允许的目录
```
POST /api/python_repl/update_dirs
```

请求：
```json
{
  "dirs": ["C:/Users/YourName/Documents", "D:/Workspace"]
}
```

---

## 配置说明

### .env 文件配置

```bash
# 执行模式
PYTHON_EXECUTION_MODE=standard  # safe | standard | free

# 超时配置（秒）
PYTHON_SAFE_TIMEOUT=60
PYTHON_STANDARD_TIMEOUT=300
PYTHON_FREE_TIMEOUT=1800

# 内存比例
PYTHON_SAFE_MEMORY_RATIO=0.2
PYTHON_STANDARD_MEMORY_RATIO=0.5
PYTHON_FREE_MEMORY_RATIO=0.8

# 操作计数
PYTHON_SAFE_MAX_OPERATIONS=1000000
PYTHON_STANDARD_MAX_OPERATIONS=10000000
PYTHON_FREE_MAX_OPERATIONS=0

# 监控配置
PYTHON_MONITOR_INTERVAL=5
PYTHON_WARNING_THRESHOLD=0.7

# 额外的允许目录
ALLOWED_WRITE_DIRS=["C:/Users/YourName/Documents", "D:/Workspace"]
```

---

## 安全机制

### 多层防护

| 保护机制 | safe | standard | free | 说明 |
|---------|------|----------|------|------|
| 超时限制 | ✅ 60秒 | ✅ 5分钟 | ✅ 30分钟 | 所有模式 |
| 内存限制 | ✅ 20% | ✅ 50% | ✅ 80% | 动态计算 |
| 操作计数 | ✅ 100万 | ✅ 1000万 | ❌ 无限 | 防止死循环 |
| 路径限制 | ✅ | ✅ | ✅ | 项目目录 |
| 敏感文件保护 | ✅ | ✅ | ✅ | .env 等 |
| 用户可中断 | ✅ | ✅ | ✅ | 随时停止 |

---

## Skills 应用场景

现在 Skills 可以利用增强的 python_repl 做更多事情：

### Skill: generate_report
```markdown
## 功能
生成包含数据和图表的 Excel 报告

## 使用步骤
1. 使用 python_repl（free 模式）：
```python
import pandas as pd
import matplotlib.pyplot as plt

# 生成数据
data = pd.read_csv('input.csv')
summary = data.describe()

# 保存摘要
summary.to_excel('report_summary.xlsx')

# 生成图表
plt.figure(figsize=(10, 6))
plt.plot(data['value'])
plt.savefig('chart.png')

print('Report generated!')
```

2. 返回文件路径
```

### Skill: batch_process
```markdown
## 功能
批量处理大量文件

## 使用步骤
1. 使用 python_repl（free 模式）
2. 遍历目录，处理每个文件
3. 生成结果文件

注意：使用 free 模式，可能需要较长时间
```

---

## 总结

**核心改进：**
```
✅ Tools 不增加（还是 6 个）
✅ python_repl 变得非常强大
✅ 支持文件 I/O（受控目录）
✅ 三种执行模式适应不同场景
✅ 动态内存限制适配不同机器
✅ 多层防护防止死循环和资源耗尽
✅ 用户可随时中断执行
```

**现在 Agent 可以：**
- 生成任意格式的文件（PPT、Excel、PDF、图片等）
- 处理大数据集
- 执行长时间任务
- 安装并使用任意 Python 库
- 在受控目录保存结果

**Tools 职责：提供原子能力**
**Skills 职责：提供业务逻辑**

完美的架构！🎉
