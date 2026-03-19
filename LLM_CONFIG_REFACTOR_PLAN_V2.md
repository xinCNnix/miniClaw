# LLM 配置系统重构方案 V2.0

## 核心需求

1. **前端所见即所得**：前端显示的提供商 = 后端实际使用的提供商
2. **支持多个 LLM 配置**：
   - 可以保存多个 custom LLM
   - 同一提供商的不同模型视为独立 LLM
   - 例如：`custom:gpt-4` 和 `custom:gpt-3.5-turbo` 是两个独立配置
3. **前端完整显示**：模型名称、URL、API Key 全部可见
4. **多 custom LLM 支持**：允许同时配置多个自定义后端

## 新的配置模型

### credentials.encrypted 结构
```json
{
  "current_llm_id": "openrouter-hunter-alpha",
  "llms": {
    "qwen-default": {
      "id": "qwen-default",
      "provider": "qwen",
      "name": "通义千问",
      "api_key": "v1:obfuscated...",
      "model": "qwen-plus",
      "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1"
    },
    "openrouter-hunter": {
      "id": "openrouter-hunter",
      "provider": "custom",
      "name": "OpenRouter Hunter Alpha",
      "api_key": "v1:obfuscated...",
      "model": "openrouter/hunter-alpha",
      "base_url": "https://openrouter.ai/api/v1/chat/completions"
    },
    "openrouter-gpt4": {
      "id": "openrouter-gpt4",
      "provider": "custom",
      "name": "GPT-4 via OpenRouter",
      "api_key": "v1:obfuscated...",
      "model": "openai/gpt-4-turbo",
      "base_url": "https://openrouter.ai/api/v1/chat/completions"
    }
  }
}
```

### LLM ID 规则

每个 LLM 配置有唯一 ID，格式：`{provider}-{model-slug}`

- `qwen-default`: 通义千问默认配置
- `qwen-turbo`: 通义千问 turbo 模型
- `custom-openrouter-hunter`: OpenRouter 的 Hunter 模型
- `custom-local-ollama`: 本地 Ollama

## 修改文件清单

### 1. 后端修改

#### backend/app/config.py
**新增**：
```python
@dataclass
class LLMConfig:
    """单个 LLM 配置"""
    id: str
    provider: str
    name: str
    api_key: str
    model: str
    base_url: str

class Settings(BaseSettings):
    # 移除旧的配置方式
    # llm_provider: Literal[...] = Field(default="qwen")
    # qwen_api_key: str = Field(default="")
    # custom_api_key: str = Field(default="")

    # 新增：当前 LLM ID
    current_llm_id: str = Field(default="qwen-default")

    # 保留环境变量支持（兼容性）
    LLM_PROVIDER: str = Field(default="qwen")
    QWEN_API_KEY: str = Field(default="")
    CUSTOM_API_KEY: str = Field(default="")

    @property
    def current_llm(self) -> LLMConfig:
        """获取当前 LLM 配置"""
        return load_llm_config(self.current_llm_id)
```

#### backend/app/core/llm.py
**修改**：
```python
def create_llm(llm_config: LLMConfig) -> BaseChatModel:
    """从 LLMConfig 创建 LLM 实例"""
    return ChatOpenAI(
        base_url=llm_config.base_url,
        api_key=llm_config.api_key,
        model=llm_config.model,
        temperature=0.1,
        streaming=True,
    )
```

#### backend/app/api/config.py
**新增接口**：
```python
@router.get("/llms")
async def list_llms():
    """列出所有已配置的 LLM（不返回 API key 明文）"""
    llms = load_all_llm_configs()
    return {
        "current_llm_id": get_current_llm_id(),
        "llms": [
            {
                "id": llm.id,
                "provider": llm.provider,
                "name": llm.name,
                "model": llm.model,
                "base_url": llm.base_url,
                "has_api_key": bool(llm.api_key),  # ✅ 只返回是否有 key，不返回明文
                "api_key_preview": f"{llm.api_key[:10]}***" if llm.api_key else "",  # ✅ 脱敏预览
                "is_current": llm.id == get_current_llm_id()
            }
            for llm in llms
        ]
    }

@router.post("/llms")
async def save_llm(request: SaveLLMRequest):
    """
    保存或更新 LLM 配置

    如果 ID 已存在则更新，否则创建新配置
    """
    llm_config = LLMConfig(
        id=request.id or generate_llm_id(request.provider, request.model),
        provider=request.provider,
        name=request.name,
        api_key=request.api_key,
        model=request.model,
        base_url=request.base_url
    )
    save_llm_config(llm_config)
    return {"success": True, "llm_id": llm_config.id}

@router.post("/llms/{llm_id}/switch")
async def switch_llm(llm_id: str):
    """切换到指定 LLM"""
    if not llm_exists(llm_id):
        raise HTTPException(404, f"LLM {llm_id} not found")

    set_current_llm_id(llm_id)
    reset_agent_manager()  # 强制重载 Agent
    return {"success": True, "current_llm_id": llm_id}

@router.delete("/llms/{llm_id}")
async def delete_llm(llm_id: str):
    """删除 LLM 配置"""
    if llm_id == get_current_llm_id():
        raise HTTPException(400, "Cannot delete current LLM")
    delete_llm_config(llm_id)
    return {"success": True}
```

### 2. 前端修改

#### frontend/components/layout/SettingsDialog.tsx
**界面改造**：
```tsx
// 新的 LLM 配置界面
<div className="llm-config-panel">
  {/* 当前 LLM 显示 */}
  <div className="current-llm">
    <h3>当前 LLM</h3>
    <LLMCard llm={currentLLM} isCurrent={true} />
  </div>

  {/* 已配置的 LLM 列表 */}
  <div className="llm-list">
    <h3>已配置的 LLM ({llms.length})</h3>
    {llms.map(llm => (
      <LLMCard
        key={llm.id}
        llm={llm}
        isCurrent={llm.id === currentLLM?.id}
        onSwitch={() => handleSwitchLLM(llm.id)}
        onEdit={() => handleEditLLM(llm)}
        onDelete={() => handleDeleteLLM(llm.id)}
      />
    ))}
  </div>

  {/* 添加新 LLM 按钮 */}
  <Button onClick={() => setShowAddLLMDialog(true)}>
    <Plus /> 添加 LLM
  </Button>
</div>

// LLM 卡片组件
function LLMCard({ llm, isCurrent, onSwitch, onEdit, onDelete }) {
  return (
    <div className={`llm-card ${isCurrent ? 'current' : ''}`}>
      <div className="llm-info">
        <h4>{llm.name}</h4>
        <div className="llm-details">
          <span>提供商: {llm.provider}</span>
          <span>模型: {llm.model}</span>
          <span>URL: {llm.base_url}</span>
          <span>API Key: {llm.api_key?.slice(0, 10)}***</span>
        </div>
      </div>
      <div className="llm-actions">
        {isCurrent ? (
          <Badge>当前使用</Badge>
        ) : (
          <Button onClick={onSwitch}>切换</Button>
        )}
        <Button onClick={onEdit}>编辑</Button>
        <Button onClick={onDelete} variant="destructive">删除</Button>
      </div>
    </div>
  )
}
```

#### frontend/lib/api.ts
**新增方法**：
```typescript
interface LLMConfig {
  id: string;
  provider: string;
  name: string;
  model: string;
  base_url: string;
  has_api_key: boolean;        // ✅ 只返回是否配置
  api_key_preview: string;     // ✅ 脱敏预览（sk-***）
  is_current?: boolean;
  // ❌ 移除 api_key 字段
}

interface SaveLLMRequest {
  id?: string;
  provider: string;
  name: string;
  model: string;
  base_url: string;
  api_key?: string;  // 可选，编辑时如果不修改则不传
}

class APIClient {
  /**
   * 获取所有已配置的 LLM（不包含明文 API key）
   */
  async listLLMs(): Promise<{
    current_llm_id: string;
    llms: LLMConfig[];
  }> {
    const response = await fetch(`${this.baseUrl}/api/config/llms`);
    const data = await response.json();
    // ✅ 后端不返回 api_key，前端也无法获取
    return data;
  }

  /**
   * 保存或更新 LLM 配置
   *
   * api_key 是可选的：
   * - 新增时：必须提供 api_key
   * - 编辑时：如果不修改 api_key 则不传此字段
   */
  async saveLLM(request: SaveLLMRequest): Promise<{ success: true; llm_id: string }> {
    const response = await fetch(`${this.baseUrl}/api/config/llms`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      // ✅ api_key 通过 HTTPS 加密传输
      body: JSON.stringify(request),
    });
    return response.json();
  }

  /**
   * 切换到指定 LLM
   */
  async switchLLM(llmId: string): Promise<{ success: true; current_llm_id: string }> {
    const response = await fetch(`${this.baseUrl}/api/config/llms/${llmId}/switch`, {
      method: 'POST',
    });
    return response.json();
  }

  /**
   * 删除 LLM 配置
   */
  async deleteLLM(llmId: string): Promise<{ success: true }> {
    const response = await fetch(`${this.baseUrl}/api/config/llms/${llmId}`, {
      method: 'DELETE',
    });
    return response.json();
  }
}
```

#### frontend/types/config.ts
**新增类型**：
```typescript
// ✅ 正确的类型定义：不包含明文 api_key
interface LLMConfig {
  id: string;
  provider: string;
  name: string;
  model: string;
  base_url: string;
  has_api_key: boolean;      // 是否已配置 API Key
  api_key_preview: string;   // 脱敏预览（如 "sk-1234567890***"）
  is_current?: boolean;
  // ❌ 不要添加 api_key 字段
}

// 保存请求类型
interface SaveLLMRequest {
  id?: string;
  provider: string;
  name: string;
  model: string;
  base_url: string;
  api_key?: string;  // 可选，编辑时不修改则不传
}
```

## 迁移脚本

### 从旧配置迁移
```python
# backend/app/config.py

def migrate_old_config():
    """迁移旧的 credentials 格式到新格式"""
    try:
        # 读取旧格式
        old_creds = KeyObfuscator.load_credentials()
        if "llms" in old_creds:
            # 已经是新格式，无需迁移
            return

        llms = {}
        current_llm_id = old_creds.get("_current_provider", "qwen") + "-default"

        # 迁移每个提供商
        for provider, config in old_creds.items():
            if provider.startswith("_"):
                continue

            llm_id = f"{provider}-default"
            llms[llm_id] = {
                "id": llm_id,
                "provider": provider,
                "name": get_provider_display_name(provider),
                "api_key": config["api_key"],
                "model": config.get("model", get_default_model(provider)),
                "base_url": config.get("base_url", get_default_base_url(provider))
            }

        # 保存新格式
        new_creds = {
            "current_llm_id": current_llm_id,
            "llms": llms
        }
        KeyObfuscator.save_credentials(new_creds)

        logger.info(f"Migrated {len(llms)} LLM configs to new format")

    except Exception as e:
        logger.error(f"Migration failed: {e}")
```

## 测试用例

### 单元测试
```python
def test_multiple_custom_llms():
    # 保存多个 custom LLM
    save_llm_config(LLMConfig(
        id="custom-openrouter-hunter",
        provider="custom",
        name="OpenRouter Hunter",
        api_key="sk-xxx",
        model="openrouter/hunter-alpha",
        base_url="https://openrouter.ai/api/v1"
    ))

    save_llm_config(LLMConfig(
        id="custom-openrouter-gpt4",
        provider="custom",
        name="GPT-4",
        api_key="sk-yyy",
        model="openai/gpt-4",
        base_url="https://openrouter.ai/api/v1"
    ))

    # 验证可以列出所有 LLM
    llms = load_all_llm_configs()
    assert len(llms) == 2

    # 验证切换
    set_current_llm_id("custom-openrouter-gpt4")
    current = load_llm_config(get_current_llm_id())
    assert current.model == "openai/gpt-4"
```

### E2E 测试
```typescript
test('multiple custom LLMs', async ({ page }) => {
  // 1. 打开设置页面
  await page.goto('http://localhost:3000')
  await page.click('[data-testid="settings-button"]')

  // 2. 添加第一个 custom LLM
  await page.click('text=添加 LLM')
  await page.fill('[name="name"]', 'OpenRouter Hunter')
  await page.fill('[name="model"]', 'openrouter/hunter-alpha')
  await page.fill('[name="base_url"]', 'https://openrouter.ai/api/v1')
  await page.fill('[name="api_key"]', 'sk-test-xxx')
  await page.click('text=保存')

  // 3. 添加第二个 custom LLM
  await page.click('text=添加 LLM')
  await page.fill('[name="name"]', 'GPT-4')
  await page.fill('[name="model"]', 'openai/gpt-4')
  await page.fill('[name="base_url"]', 'https://openrouter.ai/api/v1')
  await page.fill('[name="api_key"]', 'sk-test-yyy')
  await page.click('text=保存')

  // 4. 验证列表显示两个 LLM
  await expect(page.locator('.llm-card')).toHaveCount(2)

  // 5. 切换到第二个 LLM
  await page.click('text=GPT-4')
  await page.click('text=切换')

  // 6. 发送聊天请求，验证使用正确的 LLM
  await page.fill('[data-testid="chat-input"]', 'Hello')
  await page.click('text=发送')

  // 验证后端日志显示调用 GPT-4
  // (需要检查后端日志或 mock API)
})
```

## 安全性设计

### 🔐 API Key 安全原则

**核心原则**：前端永远不应该接触到明文 API Key

### 数据流向

```
用户输入（前端）
    ↓ HTTPS 加密传输
后端 API（解密）
    ↓ 使用设备指纹加密
存储到 credentials.encrypted
    ↓ 读取时解密
LLM 调用（仅在内存中）
```

### 前端安全规范

#### ❌ 禁止操作
```typescript
// 1. 永远不要在界面显示明文 API key
<span>API Key: {llm.api_key}</span>  // ❌ 危险

// 2. 永远不要在 URL/Query 中传递 API key
fetch(`/api/llm?key=${apiKey}`)  // ❌ 会记录到日志

// 3. 永远不要在 localStorage/sessionStorage 存储
localStorage.setItem('api_key', key)  // ❌ 可被 XSS 读取

// 4. 永远不要在 console.log 中输出
console.log('API Key:', apiKey)  // ❌ 会记录到浏览器控制台
```

#### ✅ 正确操作
```typescript
// 1. 只显示脱敏预览
<span>
  {llm.has_api_key ? '✓ API Key 已配置' : '✗ 未配置'}
</span>

// 2. 编辑时不回填已有 key
<input
  type="password"
  placeholder="如需修改请重新输入，否则留空"
  value=""  // ✅ 始终为空
/>

// 3. 使用 HTTPS POST 传输
fetch('/api/config/llms', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ api_key: userKey })  // ✅ HTTPS 加密
})

// 4. 后端验证并加密存储
// backend/app/api/config.py
@router.post("/llms")
async def save_llm(request: SaveLLMRequest):
    # ✅ 收到后立即加密存储
    obfuscated_key = KeyObfuscator.obfuscate(request.api_key)
    credentials[llm_id]["api_key"] = obfuscated_key
```

### 后端安全规范

#### API 响应安全
```python
# ✅ 正确：不返回明文
@router.get("/llms")
async def list_llms():
    llms = load_all_llm_configs()
    return {
        "llms": [
            {
                "id": llm.id,
                "name": llm.name,
                "has_api_key": bool(llm.api_key),      # ✅ 只返回布尔值
                "api_key_preview": f"{llm.api_key[:8]}***",  # ✅ 脱敏预览
                # ❌ 不要返回 "api_key": llm.api_key
            }
        ]
    }
```

#### 日志安全
```python
# ❌ 危险：日志中记录明文
logger.info(f"Saving API key: {api_key}")  # 会记录到文件

# ✅ 正确：只记录脱敏信息
logger.info(f"Saving API key: {api_key[:8]}***")
```

#### 内存安全
```python
# ✅ LLM 调用时才解密，使用完立即释放
def create_llm(llm_config: LLMConfig):
    # 此时 api_key 在内存中是明文（不可避免）
    llm = ChatOpenAI(api_key=llm_config.api_key)

    # LLM 调用完成后，Python GC 会自动回收内存
    return llm
```

### 加密存储细节

#### 设备指纹加密
```python
# backend/app/core/obfuscation.py

class KeyObfuscator:
    @classmethod
    def obfuscate(cls, api_key: str) -> str:
        """
        使用设备指纹 XOR 加密

        流程：
        1. 生成机器 ID（基于 hostname, machine, system）
        2. XOR 加密 API key
        3. Base64 编码
        4. MD5 校验和
        5. 格式：v1:encoded:checksum
        """
        machine_id = cls._get_machine_id()
        obfuscated = xor(api_key, machine_id)
        encoded = base64.b64encode(obfuscated)
        checksum = md5(encoded).hexdigest()[:8]
        return f"v1:{encoded}:{checksum}"
```

#### 为什么是混淆而非强加密？
- **目的**：防止 Agent 工具（read_file, terminal）意外读取
- **不是**：防止有权限访问文件系统的攻击者
- **如果需要强加密**：可以使用 AES-256，但需要用户输入密码

### 前端输入安全

#### 输入验证
```typescript
// 前端：验证输入格式
function validateApiKey(key: string): boolean {
  // 基本格式检查
  if (!key || key.length < 20) return false

  // 检查是否包含可疑字符（防止注入）
  if (/[<>\"'\\\\]/.test(key)) return false

  return true
}
```

#### 后端验证
```python
# 后端：验证并清洗
def validate_api_key(key: str) -> bool:
    # 长度检查
    if not key or len(key) < 20:
        raise ValueError("API key too short")

    # 格式检查（常见前缀）
    valid_prefixes = ["sk-", "v1:", "sess-"]
    if not any(key.startswith(p) for p in valid_prefixes):
        logger.warning(f"Unusual API key format: {key[:8]}***")

    return True
```

### HTTPS 传输

#### 强制 HTTPS
```python
# backend/app/main.py
from fastapi.middleware.httpsredirect import HTTPSRedirectMiddleware

app.add_middleware(HTTPSRedirectMiddleware)
# 所有 HTTP 请求自动重定向到 HTTPS
```

#### CORS 配置
```python
# backend/app/config.py
cors_origins: list[str] = [
    "https://localhost:3000",   # ✅ 只允许 HTTPS
    "http://localhost:3000",    # ⚠️ 开发环境允许 HTTP
    # ❌ 不要使用 "http://*" 或 "*"
]
```

### 安全检查清单

#### 前端
- [ ] API Key 字段使用 `type="password"`
- [ ] 列表页面不显示明文 Key
- [ ] 编辑时不回填已有 Key
- [ ] 删除时确认对话框
- [ ] 使用 HTTPS 通信

#### 后端
- [ ] API 响应不包含明文 Key
- [ ] 日志中不记录明文 Key
- [ ] 加密存储到文件系统
- [ ] 文件权限设置为 600（仅所有者读写）
- [ ] 定期审计代码中的 Key 处理

#### 运维
- [ ] credentials.encrypted 不提交到 Git
- [ ] 添加到 .gitignore
- [ ] 使用环境变量覆盖（生产环境）
- [ ] 定期轮换 API Key
- [ ] 监控异常 API 调用

## 配置验证
- ✅ 每次打开设置界面，调用 `/api/config/llms` 获取最新列表
- ✅ 切换 LLM 后，立即刷新当前 LLM 显示
- ✅ 保存/编辑/删除后，自动刷新列表

### 后端验证
- ✅ `get_agent_manager()` 每次都读取 `current_llm_id`
- ✅ 切换 LLM 时强制重置 Agent
- ✅ 不使用 lru_cache，确保配置实时性

## 实施步骤

### Phase 1：后端重构（2天）
1. 修改 `config.py` - 新配置模型
2. 修改 `llm.py` - LLMConfig 支持
3. 修改 `api/config.py` - 新 API 端点
4. 添加迁移脚本
5. 单元测试

### Phase 2：前端重构（2天）
1. 修改 `SettingsDialog.tsx` - 新界面
2. 修改 `api.ts` - 新 API 方法
3. 添加 `LLMCard` 组件
4. 添加 `AddLLMDialog` 组件
5. E2E 测试

### Phase 3：联调测试（1天）
1. 前后端集成测试
2. 性能测试
3. 用户体验优化

### Phase 4：文档和发布（1天）
1. 更新 CLAUDE.md
2. 更新用户手册
3. 发布说明

## 风险评估

- **兼容性风险**：需要迁移脚本支持旧配置
- **性能风险**：每次都重新加载配置，需要优化
- **复杂度风险**：新模型增加了代码复杂度

**总体评估**：风险可控，收益明显（解决所见即所得问题）
