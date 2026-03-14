# API Key 混淆加密方案

## 方案概述

本方案使用**设备指纹混淆加密**来保护 API key，防止 Agent 工具（如 `read_file`、`terminal`）通过提示词注入等方式泄露用户的 API 密钥。

### 核心特性

- ✅ **无需用户密码**：使用设备特征自动生成混淆密钥
- ✅ **防止 Agent 泄露**：Agent 工具无法读取明文 key
- ✅ **域名白名单**：预置可信 LLM 服务商，非白名单需用户确认
- ✅ **简单易用**：用户无感知，自动加密/解密
- ✅ **换电脑自动失效**：设备指纹变化后需要重新配置

---

## 实现细节

### 1. 混淆算法

**位置：** `backend/app/core/obfuscation.py`

```python
# 设备指纹生成
machine_id = sha256(platform.node() + platform.machine() + platform.system())

# XOR 混淆
obfuscated = xor(api_key_bytes, machine_id)

# Base64 编码
encoded = base64.b64encode(obfuscated)

# 存储格式：v1:encoded_data:checksum
```

**安全性：**
- 防止：Agent 工具读取、随意查看
- 不防：能运行程序的攻击者（可以调用同样的代码）

### 2. 工具权限限制

**`backend/app/tools/read_file.py`**
- 阻止读取：`credentials.encrypted`、`.env`、`.env.local` 等

**`backend/app/tools/terminal.py`**
- 阻止命令：`cat credentials.encrypted`、`cat .env` 等

### 3. 域名白名单

**位置：** `backend/app/core/trusted_domains.py`

**预置可信域名：**
- `api.openai.com` - OpenAI
- `dashscope.aliyuncs.com` - 通义千问
- `api.deepseek.com` - DeepSeek
- `api.anthropic.com` - Anthropic Claude
- `generativelanguage.googleapis.com` - Google Gemini
- `localhost` - 本地开发

**非白名单域名：**
- 需要用户在设置界面确认
- 确认后标记为 `user_confirmed: true`

---

## 文件结构

### 新增文件

```
backend/
├── app/
│   ├── core/
│   │   ├── obfuscation.py          # 混淆加密核心模块
│   │   └── trusted_domains.py      # 域名白名单
│   └── api/
│       └── config.py               # 配置管理 API

frontend/
└── lib/
    └── api.ts                      # 新增配置 API 调用
```

### 修改文件

```
backend/
├── app/
│   ├── config.py                   # 支持从加密文件加载
│   ├── tools/
│   │   ├── read_file.py            # 阻止访问敏感文件
│   │   └── terminal.py             # 阻止访问敏感文件
│   └── main.py                     # 注册配置 API

.gitignore                           # 添加加密文件规则
```

---

## API 端点

### 保存配置

```
POST /api/config/save
Content-Type: application/json

{
  "provider": "qwen",
  "api_key": "sk-xxxxx",
  "model": "qwen-turbo",
  "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
  "user_confirmed": false
}

Response:
{
  "success": true,
  "message": "Configuration saved for qwen"
}

非白名单域名响应:
{
  "success": false,
  "requires_confirmation": true,
  "message": "⚠️ 域名 xxx 不在预置的可信服务商列表中...",
  "domain": "xxx"
}
```

### 查看状态

```
GET /api/config/status

Response:
{
  "has_credentials": true,
  "providers": ["qwen", "openai"]
}
```

### 删除配置

```
DELETE /api/config/{provider}

Response:
{
  "success": true,
  "message": "Configuration deleted for qwen"
}
```

### 检查域名

```
POST /api/config/check-domain
Content-Type: application/json

{
  "domain": "api.example.com"
}

Response:
{
  "trusted": false,
  "domain": "api.example.com"
}
```

---

## 存储格式

### 加密文件示例

**`data/credentials.encrypted`**
```json
{
  "qwen": {
    "api_key": "v1:9bJPPi57CmqplFtVe4W9ymMaiJK1G2p5gbiqLJ3rBv/3qxE+Pn4JI+Ld:95ce1e61",
    "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "model": "qwen-turbo"
  },
  "openai": {
    "api_key": "v1:abc123...:checksum",
    "model": "gpt-4"
  }
}
```

### .gitignore 规则

```gitignore
# 敏感配置文件
.env
.env.local
.env.*.local

# 加密凭证文件
data/credentials.encrypted
data/credentials.json
*.key
```

---

## 使用流程

### 用户首次使用

1. 打开应用设置页面
2. 选择 LLM 提供商（如"通义千问"）
3. 输入 API key
4. 点击保存
   - 自动使用设备指纹混淆加密
   - 存储到 `data/credentials.encrypted`
   - 后续自动加载，无需用户操作

### 日常使用

- 启动应用 → 自动从加密文件加载 → 内存中解密
- 调用 LLM → 使用内存中的明文 key
- Agent 工具 → 只能看到混淆后的密文

### 更换电脑

1. 打开应用
2. 检测到设备变化，提示重新配置
3. 重新输入 API key
4. 新电脑自动生成新的设备指纹

---

## 测试

运行测试验证功能：

```bash
cd backend
python tests/test_obfuscation.py
```

测试覆盖：
- ✅ 混淆/解密算法
- ✅ 保存/加载凭证
- ✅ 获取指定提供商的 key

---

## 安全性总结

| 威胁场景 | 防护效果 | 说明 |
|---------|---------|------|
| Agent read_file 读取配置 | ✅ 已防护 | 工具级别阻止访问敏感文件 |
| Agent terminal cat .env | ✅ 已防护 | 命令级别阻止访问敏感文件 |
| 提示词注入读取 key | ✅ 已防护 | 存储文件为混淆密文 |
| 病毒批量扫描 | ✅ 已防护 | 不同电脑密钥不同 |
| 用户随意查看 | ✅ 已防护 | 看到的是混淆密文 |
| 攻击者控制你的电脑 | ❌ 无法防护 | 可以运行同样代码解密 |

---

## 未来改进方向

1. **前端设置界面**
   - 集成到现有的 SettingsDialog
   - 支持保存、删除、查看状态

2. **迁移工具**
   - 从 .env 迁移到加密存储
   - 清理明文 key

3. **多设备支持**
   - 提供导出/导入功能
   - 用户手动迁移加密配置

4. **更强的混淆**
   - 可选的密码保护
   - 多轮混淆增强安全性

---

## 总结

本方案在**用户体验**和**安全性**之间取得了良好平衡：

- ✅ 用户无感知，自动加密
- ✅ 有效防范 Agent 泄露
- ✅ 域名白名单防止劫持
- ✅ 实现简单，易于维护
- ✅ 适合个人用户本地部署

**核心原则：混淆加密 + 工具限制 + 域名白名单 = 足够安全**
