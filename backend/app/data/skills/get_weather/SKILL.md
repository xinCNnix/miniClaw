# Get Weather Skill

## Description
获取指定城市的天气信息。

## Parameters
- **city** (string): 城市名称，例如 "Beijing", "Shanghai", "New York"

## Instructions
1. 使用 fetch_url 工具获取天气信息
2. URL 格式: https://wttr.in/{city}?format=j1
3. 解析返回的 JSON 数据
4. 返回当前天气、温度等信息

## Example
User: 北京的天气怎么样？
Agent 执行:
1. 使用 fetch_url 工具访问 https://wttr.in/Beijing?format=j1
2. 解析天气数据
3. 用友好的格式返回天气信息

## Output Format
返回格式化的天气信息，包括：
- 当前温度
- 天气状况
- 湿度
- 风速
