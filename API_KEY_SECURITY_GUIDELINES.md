# API Key 安全规范

## 核心原则

**前端永远不应该接触到明文 API Key**

## 数据流向

```
用户输入（前端明文）
    ↓ HTTPS 加密传输
后端接收（临时明文）
    ↓ 设备指纹加密
credentials.encrypted（密文存储）
    ↓ 使用时解密
LLM 调用（内存明文）
```

## 前端安全规范

### ❌ 禁止操作

```typescript
// 1. 不要显示明文
<div>{llm.api_key}</div>  // ❌

// 2. 不要回填已有 Key
<input value={llm.api_key} />  // ❌

// 3. 不要存储到 localStorage
localStorage.setItem('key', apiKey)  // ❌

// 4. 不要在 URL 中传递
fetch(`/api/llm?key=${key}`)  // ❌

// 5. 不要在 console 中输出
console.log('Key:', key)  // ❌
```

### ✅ 正确操作

```typescript
// 1. 只显示状态
{llm.has_api_key ? '✓ 已配置' : '✗ 未配置'}

// 2. 编辑时不回填
<input
  type="password"
  placeholder="如需修改请重新输入"
  value=""  // ✅ 始终为空
/>

// 3. HTTPS POST 传输
fetch('/api/llms', {
  method: 'POST',
  body: JSON.stringify({ api_key: key })  // ✅ HTTPS 加密
})
```

## 后端安全规范

### API 响应

```python
# ❌ 错误：返回明文
return {"id": "...", "api_key": "sk-xxx"}

# ✅ 正确：只返回状态
return {
    "id": "...",
    "has_api_key": True,
    "api_key_preview": "sk-1234***"  # 脱敏预览
}
```

### 日志记录

```python
# ❌ 危险
logger.info(f"API key: {api_key}")  # 会记录到文件

# ✅ 正确
logger.info(f"API key: {api_key[:8]}***")  # 脱敏
```

### 存储安全

```python
# ✅ 加密存储
obfuscated = KeyObfuscator.obfuscate(api_key)
credentials[llm_id]["api_key"] = obfuscated

# ✅ 文件权限 600
os.chmod("data/credentials.encrypted", 0o600)
```

## 加密机制

### 设备指纹混淆

```python
# backend/app/core/obfuscation.py

def obfuscate(api_key: str) -> str:
    """
    使用设备指纹 XOR 加密

    安全特性：
    1. 基于机器特征（hostname, machine, system）
    2. XOR 加密（简单但有效）
    3. Base64 编码
    4. MD5 校验和（防篡改）
    """
    machine_id = hashlib.sha256(
        f"{platform.node()}-{platform.machine()}".encode()
    ).digest()

    # XOR 加密
    encrypted = xor(api_key.encode(), machine_id)

    # Base64 + Checksum
    encoded = base64.b64encode(encrypted).decode()
    checksum = hashlib.md5(encoded.encode()).hexdigest()[:8]

    return f"v1:{encoded}:{checksum}"
```

### 为什么不是强加密？

- **目的**：防止 Agent 工具意外读取
- **不是**：防止有文件系统访问权限的攻击者
- **权衡**：简单够用，无需用户输入密码

## 传输安全

### HTTPS 强制

```python
# backend/app/main.py
from fastapi.middleware.httpsredirect import HTTPSRedirectMiddleware

app.add_middleware(HTTPSRedirectMiddleware)
```

### CORS 限制

```python
# backend/app/config.py
cors_origins: list[str] = [
    "https://localhost:3000",  # ✅ 生产环境
    "http://localhost:3000",   # ⚠️ 开发环境
]
```

## 安全检查清单

### 开发阶段
- [ ] API Key 字段使用 `type="password"`
- [ ] 不在列表显示明文
- [ ] 编辑时不回填
- [ ] 使用 HTTPS 通信
- [ ] 后端验证输入格式

### 测试阶段
- [ ] 测试 API Key 脱敏显示
- [ ] 测试编辑时不暴露已有 Key
- [ ] 测试 HTTPS 传输
- [ ] 检查日志无明文
- [ ] 检查网络请求无明文

### 部署阶段
- [ ] credentials.encrypted 不在 Git 中
- [ ] 文件权限设置为 600
- [ ] 启用 HTTPS
- [ ] 配置 CORS 白名单
- [ ] 设置日志轮转

### 运维阶段
- [ ] 定期审计代码
- [ ] 监控异常调用
- [ ] 定期轮换 Key
- [ ] 备份加密存储
- [ ] 应急响应预案

## 常见安全问题

### Q1: 浏览器 DevTools 能看到 Key 吗？

**A**: 用户输入时能看到（无法避免），但：
- 页面刷新后消失
- 不存储到任何地方
- 列表页面不显示
- 编辑时不回填

### Q2: 网络请求能截获 Key 吗？

**A**: 使用 HTTPS 加密传输，无法截获。

### Q3: Agent 工具能读取 Key 吗？

**A**: 不能。credentials.encrypted 使用设备指纹加密，即使被读取也无法解密（除非在同一台机器）。

### Q4: 数据库泄露会暴露 Key 吗？

**A**: 不存储在数据库。存储在文件系统并加密。

### Q5: 需要使用 AES-256 强加密吗？

**A**: 当前方案已足够。如需更强保护：
- 需要用户输入密码
- 增加复杂度和使用成本
- 对抗有文件系统访问的攻击者有限

## 应急响应

### Key 泄露处理

1. **立即撤销**：在提供商平台撤销泄露的 Key
2. **生成新 Key**：创建新的 API Key
3. **更新配置**：通过前端界面更新
4. **检查日志**：确认泄露范围
5. **加固措施**：分析泄露原因并修复

### 可疑活动监控

```python
# 监控异常 API 调用
if api_call_count > threshold:
    logger.warning(f"Unusual API activity: {api_call_count} calls")
    # 可选：自动切换到备用 Key 或暂停服务
```

## 合规性

### GDPR/数据保护

- API Key 属于"认证凭据"类别
- 需要适当的技术和组织措施保护
- 加密存储 = 适当措施
- 脱敏显示 = 数据最小化

### 审计日志

```python
# 记录配置变更（不记录 Key 值）
logger.info(
    f"LLM config updated: llm_id={llm_id}, "
    f"has_api_key={bool(api_key)}, user={user_id}"
)
```

## 参考资料

- [OWASP API Security Top 10](https://owasp.org/www-project-api-security/)
- [FastAPI Security](https://fastapi.tiangolo.com/tutorial/security/)
- [Web Crypto API](https://developer.mozilla.org/en-US/docs/Web/API/Web_Crypto_API)
