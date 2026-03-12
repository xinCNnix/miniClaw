# Find Skill

## Description
帮助用户查找可用的 Skills。

## Parameters
- **keyword** (string, optional): 搜索关键词，用于过滤 skills

## Instructions
1. 使用 read_file 工具读取 backend/data/skills 目录
2. 列出所有可用的 skills
3. 如果提供了 keyword，过滤匹配的 skills
4. 对于每个 skill，读取其 SKILL.md 文件
5. 返回 skill 的简要描述

## Example
User: 有什么可用的 skills？
Agent 执行:
1. 列出所有 skills 目录
2. 读取每个 skill 的 SKILL.md
3. 返回可用 skills 列表及描述

## Output Format
返回格式化的 skills 列表，包括：
- Skill 名称
- 简要描述
- 如何使用
