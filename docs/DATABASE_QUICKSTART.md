# SQLite 双存储架构 - 快速开始

## 📖 简介

miniClaw 现在支持 **SQLite 数据库 + Markdown 文件** 的双存储架构：

- **SQLite 数据库**: 存储所有数据，供程序快速查询
- **Markdown 文件**: 人类可读的精选记忆摘要

## ✨ 核心特性

### 1. 数据库存储（程序用）
- ✅ 会话和消息存储
- ✅ 记忆提取和索引
- ✅ 高效查询（10-100x 速度提升）
- ✅ 事务保证数据安全

### 2. Markdown 文件（人类读）
- ✅ USER.md: 用户偏好摘要（最近30天，30条）
- ✅ MEMORY.md: 长期记忆摘要（最近90天，每分类50条）
- ✅ 按时间和置信度自动筛选
- ✅ 可读性强，支持版本控制

## 🚀 快速开始

### 1. 自动初始化

数据库会在首次使用时自动创建，无需手动操作。

### 2. 配置（可选）

在 `.env` 文件中添加：

```bash
# 启用数据库（默认已启用）
USE_SQLITE=true

# Markdown 配置
MD_USER_INCLUDE_DAYS=30        # USER.md 包含最近30天
MD_MEMORY_INCLUDE_DAYS=90      # MEMORY.md 包含最近90天
MD_MIN_CONFIDENCE=0.7          # 最低置信度
```

### 3. 使用方式

#### 方式一：默认使用（推荐）

无需修改代码，自动使用数据库：

```python
from app.memory.database_session import get_session_manager
from app.memory.database_memory import get_memory_manager

# 会话管理
session_mgr = get_session_manager()
session = session_mgr.create_session()

# 记忆管理
memory_mgr = get_memory_manager()
await memory_mgr.extract_and_store("session-id")
```

#### 方式二：降级到 JSON

如果想继续使用 JSON 文件：

```python
# 在 .env 中设置
USE_SQLITE=false
```

#### 方式三：双写模式（过渡期）

同时写数据库和 JSON：

```python
# 在 .env 中设置
DUAL_WRITE_MODE=true
```

### 4. 查看生成的 MD 文件

MD 文件会自动生成在 `workspace/` 目录：

```
workspace/
├── USER.md      # 用户偏好摘要
└── MEMORY.md    # 长期记忆摘要
```

文件内容示例：

```markdown
---
generated_at: 2025-03-09T15:30:00
data_range: 2025-02-07 to 2025-03-09
total_memories: 15
min_confidence: 0.7
---

# User Context

> Last updated: 2025-03-09 15:30:00
> Data range: Recent 30 days

## Communication Style
- 用户喜欢简洁明了的沟通方式
- 偏好直接的表达，不喜欢过多客套话

## Technical Preferences
- 用户偏好使用 Python 进行开发
...
```

## 📊 迁移旧数据

如果你之前使用 JSON 文件存储，可以迁移到数据库：

### 方法一：运行脚本（推荐）

```bash
python -m backend.scripts.migrate_to_database
```

### 方法二：通过 API

```bash
# 启动后端
cd backend && uvicorn app.main:app --port 8002

# 触发迁移
curl -X POST http://localhost:8002/api/memory/migrate
```

## 🔧 手动操作

### 触发 MD 文件同步

```bash
# API 方式
curl -X POST http://localhost:8002/api/memory/sync

# Python 方式
from app.memory.database_memory import get_memory_manager
mgr = get_memory_manager()
await mgr.sync_markdown_files()
```

### 查看数据库统计

```bash
curl http://localhost:8002/api/memory/stats
```

返回示例：

```json
{
  "database_exists": true,
  "size_bytes": 24576,
  "tables": {
    "sessions": 15,
    "messages": 342,
    "memories": 87,
    "user_profile": 12,
    "memory_metadata": 3
  }
}
```

## 📈 性能提升

| 操作 | 之前（JSON） | 现在（SQLite） | 提升 |
|------|-------------|---------------|------|
| 加载会话 | ~10ms | ~1ms | 10x |
| 列出会话 | ~50ms | ~2ms | 25x |
| 筛选记忆 | ~100ms | ~1ms | 100x |

## 📂 文件位置

### 数据库文件

```
backend/data/
├── memory.db          # SQLite 数据库
└── memory.db.backup   # 自动备份
```

### Markdown 文件

```
workspace/
├── USER.md           # 用户偏好（最近30天）
└── MEMORY.md         # 长期记忆（最近90天）
```

### JSON 文件（仍然保留）

```
backend/data/
├── sessions/         # 会话 JSON 文件
│   └── *.json
└── memory_metadata.json  # 记忆元数据
```

## ⚙️ 配置参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `use_sqlite` | true | 是否使用数据库 |
| `md_user_include_days` | 30 | USER.md 包含天数 |
| `md_memory_include_days` | 90 | MEMORY.md 包含天数 |
| `md_min_confidence` | 0.7 | MD 文件最低置信度 |
| `md_sync_interval` | 10 | 自动同步间隔（次记忆写入） |
| `md_auto_sync` | true | 是否自动同步 MD 文件 |

## ❓ 常见问题

### Q: 数据库在哪里？
A: `backend/data/memory.db`

### Q: 如何查看数据库内容？
A: 使用 [DB Browser for SQLite](https://sqlitebrowser.org/)

### Q: MD 文件太大怎么办？
A: 减少配置中的天数或条目数：
- `MD_USER_INCLUDE_DAYS=15`（更少天数）
- `MD_MEMORY_MAX_ITEMS=25`（更少条目）

### Q: 如何禁用数据库？
A: 在 `.env` 中设置 `USE_SQLITE=false`

### Q: 数据会丢失吗？
A: 不会！数据库使用事务保证安全，且 JSON 文件仍然保留

### Q: 可以同时用数据库和 JSON 吗？
A: 可以！设置 `DUAL_WRITE_MODE=true`

## 📚 更多文档

- **详细指南**: `docs/DATABASE_STORAGE_GUIDE.md`
- **实施总结**: `docs/DATABASE_IMPLEMENTATION_SUMMARY.md`
- **测试报告**: 运行 `pytest tests/database/ tests/generators/ -v`

## 🎉 开始使用

1. **无需任何操作**，数据库已自动启用
2. **查看生成的 MD 文件**：`workspace/USER.md` 和 `workspace/MEMORY.md`
3. **享受 10-100x 的性能提升**！

---

**如有问题**，请参考 `docs/DATABASE_STORAGE_GUIDE.md` 或提交 Issue。
