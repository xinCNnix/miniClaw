# LLM 配置系统重构方案

## 问题总结

### 核心问题
1. **LRU Cache 导致配置不同步**
   - `get_settings()` 使用 `@lru_cache` 装饰器
   - 第一次调用后永久缓存，环境变量更新无效
   - 修改 credentials 文件不会触发重新加载

2. **时序问题**
   - Settings 实例在第一次调用时创建
   - 此时 credentials 文件可能还不存在或未加载
   - 之后无论如何修改，Settings 不会更新

3. **三层缓存混乱**
   - 环境变量（os.environ）
   - lru_cache（函数级缓存）
   - Settings 对象（pydantic 内部缓存）

### 问题复现
```python
# 第一次调用：credentials 不存在
settings = get_settings()
# → _load_obfuscated_config() 失败（文件不存在）
# → Settings() 使用默认值（qwen_api_key=""）
# → 缓存这个空的 Settings 实例

# 用户通过前端配置 custom 提供商
# → credentials.encrypted 文件创建
# → 环境变量设置 CUSTOM_API_KEY

# 第二次调用：期望使用新配置
settings = get_settings()
# → 返回缓存的旧实例（qwen_api_key=""）
# → 完全忽略新的 credentials 文件
```

## 解决方案

### 方案 1：移除 LRU Cache（推荐）✅

**优点**：
- 简单直接，一次性解决所有问题
- 每次调用都重新加载，确保最新配置
- 无需修改调用方代码

**缺点**：
- 性能开销（每次都创建 Settings 实例）
- 需要优化 credentials 加载（文件 I/O）

**实现**：
```python
# 移除 @lru_cache 装饰器
def get_settings() -> Settings:
    """Get settings instance (always fresh)."""
    _load_obfuscated_config()
    return Settings()

# 移除 clear_settings_cache()（不再需要）
```

### 方案 2：单例模式 + 版本控制

**优点**：
- 性能好（只加载一次）
- 支持显式 reload
- 版本号检测，只在文件变化时重新加载

**缺点**：
- 实现复杂
- 需要修改所有调用方代码
- 文件监控增加复杂度

**实现**：
```python
class SettingsManager:
    _instance = None
    _version = 0

    @classmethod
    def get_settings(cls) -> Settings:
        if cls._instance is None or cls._should_reload():
            cls._reload()
        return cls._instance

    @classmethod
    def _should_reload(cls) -> bool:
        """Check if credentials file changed."""
        # 监控文件修改时间或版本号
        pass

    @classmethod
    def reload(cls) -> None:
        """Force reload configuration."""
        cls._reload()
```

### 方案 3：延迟加载 + 信号量

**优点**：
- 兼顾性能和灵活性
- 支持热重载
- 清晰的生命周期管理

**缺点**：
- 需要引入信号量机制
- 增加系统复杂度

## 推荐实现：方案 1（移除 LRU Cache）

### 修改文件清单

1. **backend/app/config.py**
   - 移除 `@lru_cache` 装饰器
   - 移除 `clear_settings_cache()` 函数
   - 简化 `get_settings()` 函数

2. **backend/app/api/config.py**
   - 移除所有 `clear_settings_cache()` 调用
   - 简化配置更新逻辑

3. **backend/app/api/chat.py**
   - 移除 `get_settings.cache_clear()` 调用

### 代码差异

#### config.py
```diff
- from functools import lru_cache

- @lru_cache
  def get_settings() -> Settings:
      """Get settings instance."""
      _load_obfuscated_config()
      return Settings()

- def clear_settings_cache() -> None:
-     """Clear the cached Settings instance."""
-     get_settings.cache_clear()

- def get_settings_uncached() -> Settings:
-     """Get a fresh Settings instance without using cache."""
-     _load_obfuscated_config()
-     return Settings()
```

#### api/config.py
```diff
- from app.config import get_settings, get_available_providers, clear_settings_cache, get_settings_uncached
+ from app.config import get_settings, get_available_providers

  async def save_llm_config(request: SaveLLMConfigRequest):
      ...
-     clear_settings_cache()
      _load_obfuscated_config()

-     from app.api.chat import reset_agent_manager
      reset_agent_manager()

  async def switch_provider(request: SwitchProviderRequest):
      ...
-     clear_settings_cache()

      os.environ['LLM_PROVIDER'] = request.provider
      ...

-     clear_settings_cache()

      reset_agent_manager()
      agent = get_agent_manager()

  async def get_current_provider():
      ...
-     settings = get_settings_uncached()
+     settings = get_settings()
```

#### api/chat.py
```diff
  def get_agent_manager() -> AgentManager:
      ...
-     get_settings.cache_clear()
      settings = get_settings()
```

### 性能优化建议

虽然移除了 cache，但可以通过以下方式优化性能：

1. **缓存 credentials 解密结果**
```python
_credentials_cache: dict = None
_credentials_mtime: float = 0

def _load_obfuscated_config() -> dict:
    global _credentials_cache, _credentials_mtime

    # 检查文件修改时间
    mtime = os.path.getmtime(KeyObfuscator.CREDENTIALS_FILE)
    if _credentials_cache and mtime == _credentials_mtime:
        return _credentials_cache

    # 重新加载
    credentials = KeyObfuscator.load_credentials()
    _credentials_cache = credentials
    _credentials_mtime = mtime

    # 设置环境变量...
```

2. **使用 weakref 避免重复实例化**
```python
from weakref import WeakValueDictionary
_settings_cache = WeakValueDictionary()

def get_settings() -> Settings:
    key = (id(os.environ.get('LLM_PROVIDER')), ...)
    if key in _settings_cache:
        return _settings_cache[key]

    settings = Settings()
    _settings_cache[key] = settings
    return settings
```

3. **只在需要时加载**
```python
# 对于非 LLM 配置（如路径、端口），不需要频繁重载
# 可以将 Settings 拆分为 StaticSettings 和 DynamicLLMSettings
```

## 测试计划

### 单元测试
```python
def test_settings_reload():
    # 初始状态
    s1 = get_settings()
    assert s1.custom_api_key == ""

    # 修改 credentials
    KeyObfuscator.save_credentials({
        "custom": {"api_key": "test-key", "model": "test-model"}
    })

    # 重新加载（自动）
    s2 = get_settings()
    assert s2.custom_api_key == "test-key"
```

### 集成测试
```python
async def test_switch_provider():
    # 保存 custom 配置
    await api_client.save_llm_config({...})

    # 切换到 custom
    result = await api_client.switch_provider("custom")

    # 验证后端使用新配置
    agent = get_agent_manager()
    assert agent.llm_provider == "custom"
```

### E2E 测试
1. 前端配置 custom 提供商
2. 发送聊天请求
3. 验证后端调用 custom API（而非 qwen）

## 迁移步骤

1. **Phase 1：修改 config.py**
   - 移除 lru_cache
   - 运行单元测试验证

2. **Phase 2：修改 api 层**
   - 移除 clear_settings_cache 调用
   - 运行集成测试

3. **Phase 3：性能优化**
   - 添加 credentials 文件监控
   - 添加性能测试

4. **Phase 4：文档更新**
   - 更新 CLAUDE.md
   - 添加配置热重载说明

## 风险评估

- **低风险**：移除 cache 不会破坏现有功能
- **性能影响**：每次创建 Settings 实例有轻微开销（<1ms）
- **兼容性**：无需修改调用方代码（除了移除 clear_settings_cache）

## 回滚方案

如果新方案有问题，可以快速回滚：
```bash
git revert <commit-hash>
```

所有改动都集中在 config.py 和 api/*.py，影响范围可控。
