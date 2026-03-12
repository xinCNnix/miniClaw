---
name: get_weather
description: 获取指定城市的实时天气信息
version: 1.0.0
author: miniClaw
tags: [weather, api, utility]
---

# Get Weather Skill

## 功能描述
获取指定城市的实时天气信息，包括温度、天气描述、风速、湿度等。

## 使用步骤

### 步骤 1: 使用 fetch_url 获取天气数据

推荐使用 wttr.in API（无需 API Key）：

```
fetch_url(url="https://wttr.in/{城市英文名}?format=j1")
```

**城市名称映射**：
- 北京 → Beijing
- 上海 → Shanghai
- 广州 → Guangzhou
- 深圳 → Shenzhen
- 成都 → Chengdu
- 杭州 → Hangzhou

### 步骤 2: 解析返回的 JSON

wttr.in 返回的 JSON 结构（简化）：
```json
{
  "current": [
    {
      "temp_C": "15",
      "weatherDesc": [{"value": "多云"}],
      "windspeedKmph": "10.5",
      "humidity": "65"
    }
  ]
}
```

### 步骤 3: 友好地返回结果

将天气信息整理成易读的格式返回给用户。

## 示例

**用户输入**: "北京天气怎么样？"

**执行过程**:
1. 使用 `fetch_url` 访问: `https://wttr.in/Beijing?format=j1`
2. 从 JSON 中提取：temp_C, weatherDesc, windspeedKmph, humidity
3. 返回格式化的结果

**预期输出**:
```
北京当前天气：

🌡️ 温度: 15°C
☁️ 天气: 多云
💨 风速: 10.5 km/h
💧 湿度: 65%
```

## 注意事项

1. 城市名称必须使用英文
2. 如果 API 请求失败，告知用户并建议稍后重试
3. 如果城市名称无效，API 会返回错误信息
