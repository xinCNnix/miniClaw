---
name: diagram-plotter
description: "Create architecture diagrams, flowcharts, mind maps, UML diagrams, and network topology graphs from text descriptions. Use when user asks to: (1) 'draw an architecture diagram', 'create a flowchart'; (2) 'generate a mind map'; (3) 'visualize system topology'; (4) 'draw UML/class diagrams'; (5) specify nodes and edges relationships."
dependencies:
  python:
    - "graphviz>=0.20.0"
  system:
    - name: graphviz
      bins: [dot, circo, neato, fdp]
      install:
        - kind: winget
          label: "winget install Graphviz.Graphviz"
        - kind: brew
          formula: graphviz
          label: "brew install graphviz"
        - kind: apt
          package: graphviz
          label: "sudo apt install graphviz"
---

# Diagram Plotter Skill

## Purpose
Generate professional diagrams from text descriptions using Graphviz DOT language. Perfect for system architecture, network topology, process flows, and mind maps.

## Required Inputs
- Diagram type: `hierarchy`, `flow`, `network`, `mindmap`, `uml`
- Nodes and edges: Text description or DOT format
- Optional: title, style, layout engine

## Output
所有输出文件自动保存到 `downloads/` 目录。

- `downloads/output.svg`: **Vector graphics** (default, recommended - infinite resolution)
- `downloads/output.pdf`: **Vector graphics** (print-ready)
- `downloads/output.png`: Raster image (300 DPI, fallback)
- `downloads/output.dot`: DOT source file (for editing)
- Console summary: nodes, edges, layout info

⚠️ **注意**: 输出路径无需手动指定 `downloads/` 前缀，脚本会自动将文件放入 `downloads/` 目录。

## How to Use

### Step 1: Describe Your Diagram

**Architecture Diagram (Hierarchy) - Vector Output**
```bash
python scripts/diagram_plotter.py \
  --type hierarchy \
  --content "用户 -> API网关 -> 服务A, 服务B" \
  --title "系统架构" \
  --format svg \
  --output architecture.svg
```

**Architecture Diagram - PDF Output**
```bash
python scripts/diagram_plotter.py \
  --type hierarchy \
  --content "用户 -> API网关 -> 服务A, 服务B" \
  --title "系统架构" \
  --format pdf \
  --output architecture.pdf
```

**Flowchart**
```bash
python scripts/diagram_plotter.py \
  --type flow \
  --content "开始 -> 登录 -> 验证 -> 成功, 验证 -> 失败" \
  --title "登录流程" \
  --output login_flow.png
```

**Mind Map**
```bash
python scripts/diagram_plotter.py \
  --type mindmap \
  --content "项目管理 -> 进度, 成本, 质量; 进度 -> 计划, 执行, 监控" \
  --title "项目管理思维导图" \
  --output mindmap.png
```

**Network Topology**
```bash
python scripts/diagram_plotter.py \
  --type network \
  --content "服务器A <-> 负载均衡 <-> 服务器B; 服务器A <-> 数据库" \
  --title "网络拓扑" \
  --output network.png
```

### Step 2: Advanced Usage

**Custom DOT File**
```bash
python scripts/diagram_plotter.py \
  --input diagram.dot \
  --output custom.png
```

**Custom Layout Engine**
```bash
python scripts/diagram_plotter.py \
  --type hierarchy \
  --content "A -> B; A -> C" \
  --layout fdp \
  --output diagram.png
```

**Style Options**
```bash
python scripts/diagram_plotter.py \
  --type flow \
  --content "A -> B -> C" \
  --shape box \
  --color lightblue \
  --output styled.png
```

## Diagram Types

### Hierarchy (层次结构图)
- Use for: 组织架构、系统架构、分类树
- Layout: `dot` (top-down)
- Nodes: Rectangular boxes
- Edges: Directed arrows

### Flow (流程图)
- Use for: 业务流程、算法流程、工作流
- Layout: `dot` (top-down)
- Shapes: Boxes, diamonds (decisions), rounded rectangles
- Supports: Decision branches, loops

### Network (网络拓扑图)
- Use for: 网络架构、服务依赖、ER图
- Layout: `fdp` or `neato` (force-directed)
- Edges: Bidirectional arrows
- Style: Modern, clean

### Mind Map (思维导图)
- Use for: 头脑风暴、知识梳理、概念图
- Layout: `circo` (circular)
- Nodes: Central topic with branches
- Style: Colorful, organic

### UML (类图/时序图)
- Use for: 类设计、API设计、数据模型
- Layout: `dot`
- Elements: Classes, interfaces, relationships

## Text Format

### Simple Arrow Format
```
A -> B -> C
A -> D
B -> E
```

### Semicolon Separator
```
用户 -> API网关; API网关 -> 服务A; API网关 -> 服务B
```

### Bidirectional
```
服务器A <-> 负载均衡 <-> 服务器B
```

### Labels on Edges
```
A -[请求]-> B
B -[响应]-> A
```

### Grouping (Clusters)
```
{
  前端组 -> Web服务器
  Web服务器 -> 应用服务器
}
应用服务器 -> 数据库
```

## Layout Engines

| Engine | Best For | Description |
|--------|----------|-------------|
| `dot` | Hierarchies | Top-down directed graphs |
| `neato` | Networks | Spring model (undirected) |
| `fdp` | Large networks | Force-directed (scalable) |
| `circo` | Mind maps | Circular layout |
| `twopi` | Radial trees | Root-centered |
| `osage` | Clusters | Partition-based |

## Style Options

### Shapes
- `box` - Rectangle
- `ellipse` - Oval (default)
- `diamond` - Decision
- `circle` - Circle
- `none` - Invisible (text only)

### Colors
- `lightblue`, `lightgreen`, `lightyellow`
- `lightcoral`, `lightpink`
- Or any CSS color name

### Direction
- `TB` - Top to Bottom (default)
- `LR` - Left to Right
- `BT` - Bottom to Top
- `RL` - Right to Left

## Examples

### Microservices Architecture
```bash
python scripts/diagram_plotter.py \
  --type hierarchy \
  --content "客户端 -> API网关 -> 认证服务, 业务服务A, 业务服务B; 业务服务A -> 数据库; 业务服务B -> 缓存; 认证服务 -> 用户库" \
  --title "微服务架构" \
  --direction LR \
  --shape box \
  --color lightblue \
  --output microservices.png
```

### CI/CD Pipeline
```bash
python scripts/diagram_plotter.py \
  --type flow \
  --content "代码提交 -> 构建检查 -> 单元测试 -> 部署开发环境 -> 集成测试 -> 部署生产环境" \
  --title "CI/CD 流程" \
  --output cicd.png
```

### Data Model
```bash
python scripts/diagram_plotter.py \
  --type network \
  --content "用户 <-[1:N]-> 订单; 订单 <-[1:N]-> 商品; 订单 <-[1:1]-> 支付" \
  --title "数据模型" \
  --output datamodel.png
```

## Tips

- **Use Chinese**: Graphviz supports UTF-8, use Chinese labels freely
- **Keep it simple**: Start with simple arrow format, advance to DOT if needed
- **Auto-layout**: Let Graphviz handle positioning, don't manually set coordinates
- **Iterate**: Generate, review, adjust text, regenerate
- **Export DOT**: Save .dot file for manual editing in Graphviz GUI tools

## Notes
- System requires Graphviz binaries (dot, circo, etc.)
- First run may auto-install system dependencies
- Output images are high-resolution (300 DPI)
- Complex diagrams may take a few seconds to render
