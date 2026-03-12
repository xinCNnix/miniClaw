# 知识库功能实现文档

## 实现概述

本文档记录了 miniClaw 知识库功能的完整实现。该功能允许用户上传文档到知识库，Agent 可以通过 RAG（检索增强生成）技术基于文档内容回答问题。

**实现日期**: 2026-03-07
**状态**: 代码完成，待测试

---

## 核心功能

### 1. 文档管理
- 上传文档（支持 txt, md, pdf, docx 格式）
- 查看文档列表（显示文件名、大小、上传时间、分块数量）
- 删除文档
- 文件大小限制：10MB

### 2. RAG 检索
- 智能嵌入模型检测（自动跟随用户配置的 LLM 提供商）
- 混合搜索（BM25 + 向量相似度）
- Chroma 持久化向量存储
- 自动降级机制（Claude 等不支持 embedding 的提供商降级到 sentence-transformers）

### 3. 前端界面
- 右侧面板标签页切换（Editor / Knowledge Base）
- 拖拽上传文档
- 实时上传进度显示
- 文档列表展示
- 删除确认对话框
- 友好的错误提示

---

## 技术架构

### 后端架构

```
backend/app/
├── core/
│   └── rag_engine.py           # RAG 引擎核心（320+ 行）
├── models/
│   └── knowledge_base.py        # Pydantic 数据模型
├── api/
│   └── knowledge_base.py        # 知识库 API 路由
├── tools/
│   └── search_kb.py             # 知识库搜索工具（已更新）
├── config.py                    # 配置（已更新）
└── main.py                      # 主应用（已注册路由）
```

#### RAG 引擎 (`rag_engine.py`)

**核心类**: `RAGEngine`

**关键方法**:
- `_get_embedding_model()`: 智能检测并创建嵌入模型
- `_try_provider_embedding()`: 尝试使用 LLM 提供商的嵌入服务
- `_infer_llm_config()`: 从 LLM 配置推断嵌入配置
- `_get_fallback_embedding()`: 降级到 sentence-transformers
- `upload_document()`: 上传并索引文档
- `delete_document()`: 删除文档
- `list_documents()`: 列出所有文档
- `search()`: 混合搜索
- `get_stats()`: 获取统计信息

**嵌入模型适配逻辑**:

| LLM 提供商 | 嵌入模型 | 说明 |
|-----------|---------|------|
| OpenAI | text-embedding-3-large | 直接使用 |
| DeepSeek | deepseek-embedding | 自动推断 |
| Qwen | text-embedding-v3 | 自动推断 |
| Gemini | embedding-001 | 直接使用 |
| Ollama | nomic-embed-text | 本地模型 |
| Claude | sentence-transformers | 自动降级 |
| Custom | 自动推断 | 从 base_url 推断 |

#### API 端点 (`knowledge_base.py`)

| 端点 | 方法 | 功能 |
|------|------|------|
| `/api/kb/upload` | POST | 上传文档 |
| `/api/kb/documents` | GET | 获取文档列表 |
| `/api/kb/documents/{doc_id}` | DELETE | 删除文档 |
| `/api/kb/stats` | GET | 获取统计信息 |

#### 数据模型 (`knowledge_base.py`)

```python
class KBDocument(BaseModel):
    id: str
    filename: str
    file_type: str
    size: int
    upload_date: str
    chunk_count: int

class KBUploadResponse(BaseModel):
    success: bool
    document: KBDocument
    message: str

class KBDocumentListResponse(BaseModel):
    documents: List[KBDocument]
    total: int

class KBStats(BaseModel):
    total_documents: int
    total_chunks: int
    total_size: int
    last_updated: Optional[str]
```

### 前端架构

```
frontend/
├── types/
│   └── knowledge-base.ts       # TypeScript 类型定义
├── components/
│   ├── knowledge-base/
│   │   └── knowledge-base-panel.component.tsx  # 知识库面板
│   ├── layout/
│   │   └── tabbed-panel.component.tsx          # 标签页面板
│   └── ui/
│       └── tabs.tsx              # Tabs UI 组件
├── lib/
│   └── api.ts                    # API 客户端（已扩展）
└── app/
    └── chat/
        └── page.tsx              # 聊天页面（已更新）
```

#### 知识库面板组件 (`knowledge-base-panel.component.tsx`)

**功能**:
- 文档列表展示
- 拖拽上传区域
- 点击上传（input file）
- 上传进度显示
- 删除确认对话框
- 空状态提示
- 错误消息显示

**状态管理**:
```typescript
interface KBUploadStatus {
  isUploading: boolean
  progress: number
  currentFile: string | null
  error: string | null
}
```

#### 标签页面板组件 (`tabbed-panel.component.tsx`)

**功能**:
- 标签页切换（Editor / Knowledge Base）
- 传递 props 到对应面板
- 标签样式状态管理

#### API 客户端扩展 (`api.ts`)

**新增方法**:
```typescript
async uploadKBDocument(
  file: File,
  onProgress?: (progress: number) => void
): Promise<KBUploadResponse>

async listKBDocuments(): Promise<KBDocumentListResponse>

async deleteKBDocument(docId: string): Promise<KBDeleteResponse>

async getKBStats(): Promise<KBStats>
```

---

## 配置更新

### 后端配置 (`config.py`)

新增配置项：
```python
# RAG / Knowledge Base
chunk_size: int = 512
chunk_overlap: int = 50
max_file_size: int = 10 * 1024 * 1024  # 10MB
allowed_file_types: list[str] = ['.txt', '.md', '.pdf', '.docx']
embedding_fallback: Literal["ollama", "sentence-transformers", "disable"] = "sentence-transformers"
```

### 后端依赖 (`requirements.txt`)

新增依赖：
```txt
# Document Processing
pypdf>=3.0.0
python-docx>=1.0.0
sentence-transformers>=2.2.0

# LlamaIndex Embeddings
llama-index-embeddings-huggingface>=0.1.0
llama-index-embeddings-gemini>=0.1.0
```

---

## 数据流

### 文档上传流程

```
用户选择文件
  ↓
前端验证（类型、大小）
  ↓
创建 FormData
  ↓
POST /api/kb/upload
  ↓
后端保存到 knowledge_base_dir
  ↓
RAGEngine.upload_document()
  ↓
加载文档（SimpleDirectoryReader）
  ↓
文本分块（SentenceSplitter, chunk_size=512, overlap=50）
  ↓
生成嵌入向量
  ↓
存储到 Chroma 向量数据库
  ↓
更新 BM25 索引
  ↓
保存文档元数据（.metadata.json）
  ↓
返回 KBUploadResponse
  ↓
前端刷新文档列表
```

### 知识检索流程

```
Agent 接收用户查询
  ↓
调用 search_kb 工具
  ↓
RAGEngine.search(query, top_k=5)
  ↓
混合检索：
  - 向量相似度搜索（Chroma）
  - BM25 关键词搜索
  ↓
QueryFusionRetriever 融合结果
  ↓
返回 top_k 个相关段落
  ↓
格式化为上下文
  ↓
Agent 使用上下文回答
```

---

## 关键特性

### 1. 智能嵌入模型适配

**自动检测流程**:
1. 读取用户配置的 `llm_provider`
2. 尝试使用同提供商的 embedding API
3. 如果不支持，自动降级到 sentence-transformers
4. 无需用户额外配置

**支持的提供商**:
- ✅ OpenAI（text-embedding-3-large）
- ✅ DeepSeek（自动推断）
- ✅ Qwen（text-embedding-v3）
- ✅ Gemini（embedding-001）
- ✅ Ollama（nomic-embed-text）
- ✅ 自定义 OpenAI 兼容 API
- ⚠️ Claude（降级到 sentence-transformers）

### 2. 混合搜索

结合两种检索方式：
- **向量相似度搜索**: 语义理解，找到概念相关的内容
- **BM25 关键词搜索**: 精确匹配，找到包含特定关键词的内容

使用 `QueryFusionRetriever` 融合两种结果，提升检索质量。

### 3. 持久化存储

- **向量存储**: Chroma 持久化到 `data/vector_store/`
- **文档元数据**: JSON 文件存储到 `data/knowledge_base/.metadata.json`
- **源文件**: 保存到 `data/knowledge_base/`

### 4. 文本分块策略

- **chunk_size**: 512 tokens
- **chunk_overlap**: 50 tokens
- **目的**: 在保持上下文的同时，确保检索精度

---

## 安全考虑

### 文件上传验证

1. **文件类型白名单**: 只允许 `.txt`, `.md`, `.pdf`, `.docx`
2. **文件大小限制**: 最大 10MB
3. **文件名处理**: 自动处理重复文件名（添加后缀 _1, _2...）
4. **路径安全**: 使用 `Path` 对象，防止路径遍历

### API 错误处理

- 400 Bad Request: 不支持的文件类型
- 413 Payload Too Large: 文件过大
- 404 Not Found: 文档不存在
- 500 Internal Server Error: 服务器错误（如索引失败）

---

## 性能优化

### 异步处理

- 文档上传立即返回响应
- 后台处理分块和嵌入
- TODO: 添加进度查询接口

### 缓存策略

- 嵌入模型单例缓存
- 向量存储连接池
- 文档列表可添加缓存（60秒）

### 分块策略

- 自适应分块大小（可根据文档类型调整）
- 重叠区域保持上下文连续性

---

## 已完成工作清单

### 后端（✅ 100%）

- [x] 创建 RAG 引擎核心模块
- [x] 实现智能嵌入模型检测
- [x] 实现文档上传和索引
- [x] 实现文档删除
- [x] 实现混合搜索
- [x] 创建知识库 API 端点
- [x] 创建 Pydantic 数据模型
- [x] 更新 search_kb 工具
- [x] 注册路由
- [x] 更新配置文件
- [x] 更新依赖文件
- [x] 安装所有依赖包
- [x] 验证代码导入成功

### 前端（✅ 100%）

- [x] 创建 TypeScript 类型定义
- [x] 扩展 API 客户端方法
- [x] 创建知识库面板组件
- [x] 创建标签页面板组件
- [x] 创建 Tabs UI 组件
- [x] 更新聊天页面
- [x] 实现拖拽上传
- [x] 实现文档列表展示
- [x] 实现删除功能
- [x] 实现错误提示

---

## 文件清单

### 新建文件（9 个）

**后端（3 个）**:
1. `backend/app/core/rag_engine.py`
2. `backend/app/models/knowledge_base.py`
3. `backend/app/api/knowledge_base.py`

**前端（6 个）**:
1. `frontend/types/knowledge-base.ts`
2. `frontend/components/knowledge-base/knowledge-base-panel.component.tsx`
3. `frontend/components/layout/tabbed-panel.component.tsx`
4. `frontend/components/ui/tabs.tsx`
5. `docs/KNOWLEDGE_BASE_IMPLEMENTATION.md`（本文档）
6. `docs/KNOWLEDGE_BASE_TEST_PLAN.md`（测试计划）

### 修改文件（6 个）

**后端（5 个）**:
1. `backend/app/tools/search_kb.py`
2. `backend/app/main.py`
3. `backend/app/api/__init__.py`
4. `backend/app/config.py`
5. `backend/requirements.txt`

**前端（2 个）**:
1. `frontend/lib/api.ts`
2. `frontend/app/chat/page.tsx`

---

## 下一步

所有代码已完成，下一步是测试验证。详细测试计划请参考 `docs/KNOWLEDGE_BASE_TEST_PLAN.md`。

测试内容包括：
1. 后端 API 单元测试
2. 前端组件测试
3. E2E 功能测试
4. 性能测试

---

## 技术债务

### 当前限制

1. **Chroma 删除限制**: 当前版本 Chroma 不支持按 doc_id 删除向量，需要重建索引
2. **进度查询**: 文档上传后无法查询处理进度
3. **并发上传**: 未实现并发上传控制

### 未来改进

1. 添加文档上传进度查询接口
2. 支持并发上传多个文档
3. 支持文档更新（替换已有文档）
4. 支持文档标签和分类
5. 支持高级搜索（按日期、类型、标签过滤）
6. 优化向量删除逻辑（避免重建整个索引）
7. 添加文档预览功能

---

## 参考资料

- LlamaIndex 文档: https://docs.llamaindex.ai/
- Chroma 文档: https://docs.trychroma.com/
- FastAPI 文档: https://fastapi.tiangolo.com/
- Shadcn/UI 文档: https://ui.shadcn.com/

---

**实现者**: Claude (Sonnet 4.5)
**完成日期**: 2026-03-07
**文档版本**: 1.0
