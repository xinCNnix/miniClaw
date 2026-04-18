---
name: diagram-plotter
description: "Create architecture diagrams, flowcharts, mind maps, UML diagrams, and network topology graphs from text descriptions. Use when user asks to: (1) 画架构图、画流程图、绘制拓扑图; (2) 思维导图、脑图; (3) UML类图、时序图; (4) 系统架构、微服务架构、网络拓扑; (5) specify nodes and edges relationships."
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

## 功能描述

使用 Graphviz DOT 语言从文本描述生成专业图表，适用于系统架构、网络拓扑、流程图和思维导图。

### 支持的图表类型
- **层次结构图 (hierarchy)**: 组织架构、系统架构、分类树
- **流程图 (flow)**: 业务流程、算法流程、工作流
- **网络拓扑图 (network)**: 网络架构、服务依赖、ER图
- **思维导图 (mindmap)**: 头脑风暴、知识梳理、概念图
- **UML (类图/时序图)**: 类设计、API设计、数据模型

## 输入

- 图表类型: `hierarchy`, `flow`, `network`, `mindmap`, `uml`
- 节点和边关系: 简单箭头格式文本（见下方格式说明）
- 可选: 标题、样式、布局引擎

## 输出

所有输出文件自动保存到 `outputs/` 目录。

- `outputs/<name>.svg`: **SVG 矢量图**（默认，推荐 — 无限缩放不失真）
- `outputs/<name>.png`: 栅格图 (300 DPI)
- `outputs/<name>.dot`: DOT 源文件（可供手动编辑）
- `outputs/<name>.pdf`: 矢量图（按需生成）

⚠️ **注意**: 输出路径无需手动指定 `outputs/` 前缀，脚本会自动将文件放入 `outputs/` 目录。

## 调用方式

本 skill 通过 `terminal` 工具调用脚本执行。**调用时必须提供 command 参数：**

**参数格式（JSON）：**
```json
{
  "command": "python data/skills/diagram-plotter/scripts/diagram_plotter.py --type <类型> --content \"<节点关系>\" --title \"<标题>\" --format svg --output <文件名>.svg"
}
```

脚本路径: `data/skills/diagram-plotter/scripts/diagram_plotter.py`

⚠️ **不要**自己用 python_repl 写代码来生成图表，必须通过 terminal 工具调用，且 command 参数不能为空。脚本已内置中文字体检测、路径管理和格式输出。

## Example Interactions

### User: "画一个微服务架构图"

**Agent action:**
```bash
python data/skills/diagram-plotter/scripts/diagram_plotter.py \
  --type hierarchy \
  --content "客户端 -> API网关 -> 认证服务, 业务服务A, 业务服务B; 业务服务A -> 数据库; 业务服务B -> 缓存; 认证服务 -> 用户库" \
  --title "微服务架构" \
  --direction LR \
  --shape box \
  --color lightblue \
  --format svg \
  --output microservices.svg
```

### User: "画一个登录流程图"

**Agent action:**
```bash
python data/skills/diagram-plotter/scripts/diagram_plotter.py \
  --type flow \
  --content "开始 -> 登录 -> 验证 -> 成功, 验证 -> 失败 -> 返回登录" \
  --title "登录流程" \
  --format svg \
  --output login_flow.svg
```

### User: "画一个思维导图，主题是项目管理"

**Agent action:**
```bash
python data/skills/diagram-plotter/scripts/diagram_plotter.py \
  --type mindmap \
  --content "项目管理 -> 进度, 成本, 质量; 进度 -> 计划, 执行, 监控" \
  --title "项目管理思维导图" \
  --format svg \
  --output mindmap.svg
```

### User: "画一个网络拓扑图"

**Agent action:**
```bash
python data/skills/diagram-plotter/scripts/diagram_plotter.py \
  --type network \
  --content "服务器A <-> 负载均衡 <-> 服务器B; 服务器A <-> 数据库" \
  --title "网络拓扑" \
  --format svg \
  --output network.svg
```

### User: "画一个 CI/CD 流程图"

**Agent action:**
```bash
python data/skills/diagram-plotter/scripts/diagram_plotter.py \
  --type flow \
  --content "代码提交 -> 构建检查 -> 单元测试 -> 部署开发环境 -> 集成测试 -> 部署生产环境" \
  --title "CI/CD 流程" \
  --format svg \
  --output cicd.svg
```

### User: "画一个数据模型ER图"

**Agent action:**
```bash
python data/skills/diagram-plotter/scripts/diagram_plotter.py \
  --type network \
  --content "用户 <-[1:N]-> 订单; 订单 <-[1:N]-> 商品; 订单 <-[1:1]-> 支付" \
  --title "数据模型" \
  --format svg \
  --output datamodel.svg
```

## 文本格式

### 简单箭头格式
```
A -> B -> C
A -> D
B -> E
```

### 分号分隔
```
用户 -> API网关; API网关 -> 服务A; API网关 -> 服务B
```

### 双向箭头
```
服务器A <-> 负载均衡 <-> 服务器B
```

### 带标签的边
```
A -[请求]-> B
B -[响应]-> A
```

### 多目标（逗号分隔）
```
用户 -> 服务A, 服务B, 服务C
```

## 脚本参数

| 参数 | 短选项 | 说明 | 示例 |
|------|--------|------|------|
| `--type` | | 图表类型: hierarchy, flow, network, mindmap, uml | `hierarchy` |
| `--content` | | 文本描述（节点和边关系） | `"A -> B -> C"` |
| `--title` | | 图表标题 | `"系统架构"` |
| `--output` | | 输出文件名 | `architecture.svg` |
| `--format` | | 输出格式: svg, png, pdf | `svg` |
| `--shape` | | 节点形状: box, ellipse, diamond, circle, record | `box` |
| `--color` | | 节点颜色 | `lightblue` |
| `--direction` | | 方向: TB, LR, BT, RL | `TB` |
| `--layout` | | 覆盖布局引擎 | `fdp` |
| `--input` | | 输入 DOT 文件（替代 --content） | `diagram.dot` |

## 布局引擎

| 引擎 | 适用场景 | 说明 |
|------|----------|------|
| `dot` | 层次结构 | 自上而下有向图 |
| `neato` | 网络 | 弹簧模型（无向） |
| `fdp` | 大型网络 | 力导向（可扩展） |
| `circo` | 思维导图 | 环形布局 |
| `twopi` | 径向树 | 以根为中心 |

## Error Handling

- **Graphviz binaries not found**: 系统未安装 Graphviz。脚本会回退到仅生成 DOT 文件，提示用户手动安装。Agent 应告知用户安装 Graphviz 并重试。
- **No edges found in content**: 内容格式不正确，无法解析出节点关系。Agent 应将用户描述转换为正确的箭头格式重新调用。
- **Error rendering diagram**: Graphviz 渲染失败。脚本会保存 DOT 文件供手动渲染。Agent 可尝试简化图表内容后重试。

## 注意事项

- 系统需要 Graphviz 二进制文件（dot, circo 等），首次使用可能需要安装
- 自动检测系统中文字体（SimHei, Microsoft YaHei 等）
- 默认输出 SVG 矢量图（无限缩放不失真）
- 复杂图表可能需要几秒钟渲染
