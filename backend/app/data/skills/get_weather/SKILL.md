---
name: get_weather
description: "Get current weather and forecasts via wttr.in JSON API. Use when: user asks about weather, temperature, or forecasts for any location. Returns structured weather data including current conditions, temperature, humidity, wind, and forecasts."
homepage: https://wttr.in/:help
metadata: { "miniclaw": { "emoji": "🌤️", "requires": { "bins": ["curl"] } } }
---

# Get Weather Skill

Get current weather conditions and forecasts for any city worldwide.

## When to Use

✅ **USE this skill when:**

- "What's the weather?"
- "Weather in [city]"
- "Temperature in [location]"
- "Will it rain today/tomorrow?"
- Travel planning weather checks

## When NOT to Use

❌ **DON'T use this skill when:**

- Historical weather data → use weather archives/APIs
- Climate analysis or trends → use specialized data sources
- Severe weather alerts → check official weather services

## Location Format

Use city names directly:
- `Beijing` - Chinese cities
- `New+York` - Multi-word cities (use + for spaces)
- `Tokyo` - International cities
- `ORD` - Airport codes supported

## Commands

### Current Weather (JSON)

```bash
# Current weather with detailed data
curl -s "wttr.in/{city}?format=j1"
```

Returns JSON with:
- `current_condition[0]` - Current weather
- `weather` - Array of forecasts (today, tomorrow, day after)

### Quick One-Liner

```bash
# Simple summary
curl -s "wttr.in/{city}?format=%l:+%c+%t+(feels+like+%f),+%w+wind,+%h+humidity"
```

### Forecast

```bash
# 3-day forecast (default)
curl -s "wttr.in/{city}"

# Specific day (0=today, 1=tomorrow, 2=day after)
curl -s "wttr.in/{city}?1"
```

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

**Forecast:**
```json
{
  "weather": [
    {
      "date": "2025-03-12",
      "maxtempC": "28",
      "mintempC": "18",
      "avgtempC": "23"
    }
  ]
}
```

## Example Execution

**User:** "北京天气怎么样？"

**Agent steps:**
1. Use Terminal tool with curl:
   ```bash
   curl -s "wttr.in/Beijing?format=j1"
   ```
2. Parse JSON response
3. Format output for user:
   - Location: Beijing
   - Temperature: 25°C (feels like 24°C)
   - Condition: Partly cloudy
   - Humidity: 65%
   - Wind: 15 km/h NW

## Quick Response Templates

**"What's the weather?"**
```bash
curl -s "wttr.in/{city}?format=j1"
```

**"Will it rain?"**
```bash
curl -s "wttr.in/{city}?format=j1" | grep -o '"maxtempC":"[^"]*"'
```

**"Temperature only"**
```bash
curl -s "wttr.in/{city}?format=%c+%t"
```

## Notes

- No API key needed (uses wttr.in)
- Rate limited; don't spam requests
- Works for most global cities
- JSON format (`j1`) provides structured data for parsing
- Use `+` for spaces in multi-word city names
