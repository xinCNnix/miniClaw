---
name: find-skill
description: Search and install skills from external sources like GitHub, clawhub, and other skill repositories. Use when user asks to find, download, or install new skills from the internet.
version: 1.0.0
author: miniClaw
tags: [skills, search, install, github, repository]
---

# Find and Install Skills

Search for and install skills from external repositories like GitHub, clawhub, and other skill sharing platforms.

## Overview

This skill enables discovering and installing new skills from external sources, extending the Agent's capabilities beyond the built-in skill set.

## Agent Usage Workflow

When a user asks to find or install a skill, follow this automated workflow:

### Step 1: Try ClawHub CLI First (Preferred)

**ClawHub is the official skill repository with vetted, quality-assured skills.**

Always try ClawHub CLI first:

```bash
# Search for skills
clawhub search "user query here" --limit 10

# If found, install the best match
clawhub install <skill-slug>

# Optional: Install specific version
clawhub install <skill-slug> --version 1.2.3
```

**Advantages of ClawHub:**
- ✅ Official repository - vetted skills
- ✅ Version management - install specific versions
- ✅ Hash-based updates - only changed files
- ✅ Community ratings and reviews
- ✅ Centralized quality control

**If ClawHub succeeds:** Skip to Step 4 (Verify)

**If ClawHub fails** (not found, rate limit, server down): Continue to Step 2

---

### Step 2: Search GitHub (Fallback)

Use the `search_and_install.py` script to search GitHub:

```bash
python data/skills/find-skill/scripts/search_and_install.py --query "user query here" --max-results 5
```

**Examples:**
- User: "Find a weather skill" → `--query "weather"`
- User: "I need PDF processing" → `--query "pdf processing"`
- User: "Search for arxiv skills" → `--query "arxiv"`

The script will return a list of matching repositories with:
- Repository name and description
- Star count (quality indicator)
- Clone URL

**Decision Criteria:**
- Stars > 10: Generally good quality
- Description matches user need: Consider installing
- Recent updates: More likely to be maintained



### Step 3: Install the Skill

**From ClawHub:**
```bash
clawhub install <skill-slug>
# Or specific version:
clawhub install <skill-slug> --version 1.2.3
```

**From GitHub:**
```bash
python data/skills/find-skill/scripts/install_skill.py --url <repository-url>
```

The installation will:
1. Clone/download the skill
2. Validate skill structure (SKILL.md must exist)
3. Install to `data/skills/`
4. Return installation status

---

### Step 4: Verify and Inform User

```bash
# Validate the installed skill
python data/skills/skill-creator/scripts/quick_validate.py "data/skills/skill-name"

# Refresh skills registry (if needed)
python data/skills/skill-creator/scripts/refresh_skills.py
```

**Response to User:**
```
✓ Found and installed skill: [skill-name]
  Description: [brief description]
  Stars: [number]
  Location: data/skills/[skill-name]

The skill is now ready to use. Would you like me to test it?
```

### Step 5: Handle Errors

If installation fails:
1. Explain the error to the user
2. Suggest alternatives:
   - Try a different search query
   - Manually specify a repository URL
   - Create the skill using skill-creator

## Quick Start

### Search GitHub for Skills

```bash
python data/skills/find-skill/scripts/search_skills.py --source github --query "weather"
```

### Search clawhub for Skills

```bash
python data/skills/find-skill/scripts/search_skills.py --source clawhub --query "pdf"
```

### Install a Skill

```bash
python data/skills/find-skill/scripts/install_skill.py --url "https://github.com/user/repo" --name "skill-name"
```

## Supported Sources

### GitHub

Search for skill repositories on GitHub:

```bash
# Search by topic
python data/skills/find-skill/scripts/search_skills.py --source github --query "topic:agent-skill"

# Search by keyword in repository name
python data/skills/find-skill/scripts/search_skills.py --source github --query "arxiv"

# Search by keyword in description
python data/skills/find-skill/scripts/search_skills.py --source github --query "weather in:description"
```

**GitHub Search Query Syntax:**
- `topic:agent-skill` - Repositories with the agent-skill topic
- `stars:>10` - Repositories with more than 10 stars
- `language:python` - Python repositories
- `pushed:>2024-01-01` - Repositories updated after a date

### clawhub

Search clawhub for curated skills:

```bash
python data/skills/find-skill/scripts/search_skills.py --source clawhub --query "document processing"
```

**Note:** clawhub is a curated collection of Agent skills. It provides:
- Quality-vetted skills
- Standardized skill structure
- Compatibility information
- Usage examples

### Direct URL

Install a skill from a direct GitHub or Git URL:

```bash
python data/skills/find-skill/scripts/install_skill.py --url "https://github.com/username/skills-repo"
```

## Search Parameters

| Parameter | Short | Description | Example |
|-----------|-------|-------------|---------|
| `--source` | `-s` | Source to search (github, clawhub) | `github` |
| `--query` | `-q` | Search query | `"weather api"` |
| `--max-results` | `-m` | Maximum results (default: 10) | `20` |
| `--language` | `-l` | Programming language filter | `python` |
| `--sort` | `-o` | Sort order (stars, forks, updated) | `stars` |

## Installation Workflow

### Step 1: Search for Skills

```bash
# Example: Find weather-related skills
python data/skills/find-skill/scripts/search_skills.py --source github --query "weather agent-skill"
```

**Output:**
```
Found 5 repositories:

[1] username/weather-skill
    Description: Get weather information from wttr.in API
    Stars: 45 | Updated: 2024-03-15
    URL: https://github.com/username/weather-skill

[2] org/forecast-skill
    Description: Advanced weather forecasting with multiple data sources
    Stars: 23 | Updated: 2024-02-28
    URL: https://github.com/org/forecast-skill
...
```

### Step 2: Review the Skill

Before installing, review the skill's documentation:

```bash
# Clone to temporary location to inspect
git clone https://github.com/username/weather-skill /tmp/weather-skill-review

# Read the SKILL.md
cat /tmp/weather-skill-review/SKILL.md
```

### Step 3: Install the Skill

```bash
python data/skills/find-skill/scripts/install_skill.py \
  --url "https://github.com/username/weather-skill" \
  --name "weather" \
  --target "./data/skills"
```

The installer will:
1. Clone the repository
2. Validate the skill structure (SKILL.md must exist)
3. Copy to the skills directory
4. Update the skills registry
5. Run validation checks

### Step 4: Verify Installation

```bash
# Validate the installed skill
python data/skills/skill-creator/scripts/quick_validate.py "./data/skills/weather"
```

## Installation Options

| Parameter | Description | Example |
|-----------|-------------|---------|
| `--url` | Repository URL (GitHub, GitLab, etc.) | `https://github.com/user/repo` |
| `--name` | Skill/directory name | `my-skill` |
| `--target` | Installation directory | `./data/skills` |
| `--branch` | Git branch to checkout | `main` |
| `--tag` | Specific Git tag | `v1.0.0` |

## Example Workflows

### Workflow 1: Find and Install a Weather Skill

```bash
# Search
python data/skills/find-skill/scripts/search_skills.py --source github --query "weather agent-skill"

# Install
python data/skills/find-skill/scripts/install_skill.py \
  --url "https://github.com/username/weather-skill" \
  --name "weather"

# Verify
python data/skills/skill-creator/scripts/quick_validate.py "./data/skills/weather"
```

### Workflow 2: Install from clawhub

```bash
# Search clawhub
python data/skills/find-skill/scripts/search_skills.py --source clawhub --query "pdf processing"

# Install with specific version
python data/skills/find-skill/scripts/install_skill.py \
  --url "https://clawhub.example.com/pdf-processor" \
  --name "pdf-processor" \
  --tag "v2.1.0"
```

### Workflow 3: Bulk Install Multiple Skills

```bash
# Install from a list of repositories
cat skills.txt | while read url; do
  python data/skills/find-skill/scripts/install_skill.py --url "$url"
done
```

## Skill Structure Requirements

For a skill to be installable, it must have:

```
skill-name/
├── SKILL.md (required)
│   ├── YAML frontmatter with name and description
│   └── Markdown content with usage instructions
└── scripts/ (optional)
    └── executable scripts
```

**Validation checks:**
- SKILL.md must exist
- YAML frontmatter must be valid
- `name` and `description` fields are required
- No symlinks allowed (security)

## Security Considerations

1. **Review before installing**: Always inspect the skill code before installation
2. **Validate structure**: The installer runs validation checks
3. **Sandbox execution**: Scripts run in restricted environments
4. **No symlinks**: Symlinks are rejected during installation
5. **Known sources**: Prefer installing from reputable sources

## Troubleshooting

### "SKILL.md not found"
The repository doesn't have a valid skill structure. Ensure:
- The repository has a SKILL.md file in the root
- Or specify the subdirectory: `--url "https://github.com/user/repo" --subdir "skills/weather"`

### "Validation failed"
The skill failed validation checks:
```bash
# Run validator manually to see errors
python data/skills/skill-creator/scripts/quick_validate.py "./data/skills/skill-name"
```

### "Git clone failed"
Network or repository access issues:
- Check the URL is correct
- Ensure you have network access
- For private repos, configure SSH keys

## Tips for Effective Searching

1. **Use specific topics**: `topic:agent-skill weather` instead of just `weather`
2. **Check quality filters**: `stars:>10` finds more popular/reliable skills
3. **Sort by relevance`: Use `--sort stars` for quality, `--sort updated` for recent
4. **Search clawhub first**: clawhub has curated, vetted skills
5. **Read descriptions**: Look for skills with clear, detailed descriptions

## Resources

### scripts/search_skills.py

Search for skills across GitHub and clawhub. Supports various search parameters and formats.

### scripts/install_skill.py

Install skills from Git repositories. Handles cloning, validation, and integration with the local skills directory.

## Notes

- Skills are installed to `data/skills/` by default
- The skills registry (`skills_registry.json`) is automatically updated
- Installed skills become immediately available to the Agent
- You can manage skills manually using git commands if needed
