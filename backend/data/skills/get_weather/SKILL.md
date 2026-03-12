---
name: get_weather
description: "Get current weather and forecasts via wttr.in. Use when: user asks about weather, temperature, or forecasts for any location. Returns current conditions, temperature, humidity, wind, and forecasts. No API key needed."
homepage: https://wttr.in/:help
metadata: { "miniclaw": { "emoji": "🌤️", "requires": { "bins": ["curl"] } } }
---

# Get Weather Skill

Get current weather conditions and forecasts for any city worldwide.

## ⚠️ MANDATORY EXECUTION STEPS

**You MUST execute these steps in order. DO NOT STOP after reading this file.**

1. **STEP 1** (DONE): You are reading this file
2. **STEP 2** (DO NOW): IMMEDIATELY call terminal tool with curl command
3. **STEP 3**: Parse the JSON response
4. **STEP 4**: Present formatted weather to user

**IF YOU ONLY READ THIS FILE AND STOP, YOU HAVE FAILED.**

## When to Use

✅ **USE this skill when:**

- "What's the weather?"
- "Weather in [city]"
- "Temperature in [location]"
- "Will it rain today/tomorrow?"
- Travel planning weather checks
- "北京天气怎么样？"
- "上海热不热？"

## When NOT to Use

❌ **DON'T use this skill when:**

- Historical weather data → use weather archives/APIs
- Climate analysis or trends → use specialized data sources
- Severe weather alerts → check official weather services

## Location Format

- `Beijing` - 北京
- `Shanghai` - 上海
- `New+York` - Multi-word cities (use + for spaces)
- `Xingtai` - 邢台 (use Pinyin for Chinese cities)
- `ORD` - Airport codes supported

## Commands

### Current Weather (One-line)

```bash
curl -s "wttr.in/{city}?format=%l:+%c+%t+(feels+like+%f),+%w+wind,+%h+humidity"
```

### Current Weather (JSON)

```bash
curl -s "wttr.in/{city}?format=j1"
```

Returns JSON with:
- `current_condition[0]` - Current weather
- `weather` - Array of forecasts (today, tomorrow, day after)

### 3-Day Forecast

```bash
curl -s "wttr.in/{city}"
```

## Example Execution

**User:** "北京天气怎么样？"

**Agent steps:**
1. Use terminal tool with curl:
   ```bash
   curl -s "wttr.in/Beijing?format=j1"
   ```
2. Parse JSON response
3. Format output for user:
   ```
   北京当前天气：

   🌡️ 温度: 15°C
   ☁️ 天气: 晴朗
   💨 风速: 10.5 km/h
   💧 湿度: 65%
   ```

**User:** "上海会下雨吗？"

**Agent steps:**
1. Use terminal tool:
   ```bash
   curl -s "wttr.in/Shanghai?format=j1"
   ```
2. Check weatherDesc and precipitation fields
3. Report if rain is expected

**User:** "邢台天气怎么样？"

**Agent steps:**
1. Recognize "邢台" is a Chinese city
2. Use Pinyin "Xingtai" for the API call:
   ```bash
   curl -s "wttr.in/Xingtai?format=j1"
   ```
3. Parse and format the response

## CRITICAL: Execution Requirements

**MANDATORY STEPS - Do NOT skip any:**

1. ✅ First: Read this SKILL.md file (you just did this)
2. ✅ Second: IMMEDIATELY call the terminal tool with curl command
3. ✅ Third: Parse the JSON response
4. ✅ Fourth: Present formatted weather data to user

**WARNING:** Reading SKILL.md is ONLY step 1. You MUST continue to step 2 (execute curl).

**The correct flow is:**
```
User: "北京天气"
Agent:
  Step 1: read_file(".../SKILL.md") ← You are here
  Step 2: terminal("curl -s 'wttr.in/Beijing?format=j1'") ← DO THIS NEXT
  Step 3: Parse and format response
```

**Common Mistake:** Stopping after reading SKILL.md. This is WRONG. You MUST execute the curl command.

## Common City Names

| 中文 | 英文 |
|------|------|
| 北京 | Beijing |
| 上海 | Shanghai |
| 广州 | Guangzhou |
| 深圳 | Shenzhen |
| 成都 | Chengdu |
| 杭州 | Hangzhou |
| 西安 | Xi'an |
| 南京 | Nanjing |
| 邢台 | Xingtai |
| 武汉 | Wuhan |
| 重庆 | Chongqing |
| 天津 | Tianjin |

## Output Parsing

When using `format=j1`, parse JSON:

**Current weather:**
```json
{
  "current_condition": [{
    "temp_C": "25",
    "FeelsLikeC": "24",
    "humidity": "65",
    "weatherDesc": [{"value": "Partly cloudy"}],
    "windspeedKmph": "15",
    "winddir16Point": "NW"
  }]
}
```

**Key Fields:**
- `temp_C` - Temperature (Celsius)
- `FeelsLikeC` - Feels like temperature
- `weatherDesc[0].value` - Weather condition
- `windspeedKmph` - Wind speed
- `humidity` - Humidity percentage
- `pressure` - Atmospheric pressure

## Notes

- No API key needed (uses wttr.in)
- Rate limited; don't spam requests
- Works for most global cities
- JSON format (`j1`) provides structured data for parsing
- Use `+` for spaces in multi-word city names
- If city not found, API returns error
- For Chinese cities not in the list, use Pinyin (e.g., 邢台 → Xingtai)
