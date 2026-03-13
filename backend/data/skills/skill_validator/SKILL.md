---
name: skill_validator
description: "Validate skill files before use. Use when: loading new skills, verifying skill integrity, checking skill metadata. Checks for: required fields, valid syntax, security issues."
metadata: { "miniclaw": { "emoji": "🔒", "requires": { "bins": ["python"] } } }
---

# Skill Validator

Validate skill files for integrity and security before use.

## When to Use

✅ **USE this skill when:**

- Loading a new skill from disk
- Verifying skill integrity after modification
- Checking skill metadata completeness
- Validating skill syntax before deployment

## When NOT to Use

❌ **DON'T use this skill when:**

- Validating core system files (use backend tests)
- Checking non-skill files
- Runtime validation errors (handle in code)

## Validation Checklist

### Required Frontmatter Fields

Every SKILL.md must have:

```yaml
---
name: skill_name
description: "Clear description of when to use this skill"
homepage: https://optional-documentation-url
metadata:
  miniclaw:
    emoji: "🔧"
    requires:
      bins: ["required_binary"]
---
```

### Required Sections

1. **When to Use** - Clear use cases
2. **When NOT to Use** - Boundary conditions
3. **Commands** - Executable examples
4. **Notes** - Limitations and requirements

### Security Checks

- ❌ No hardcoded API keys or secrets
- ❌ No shell injection vulnerabilities
- ❌ No unsafe file operations
- ✅ Input validation for user data
- ✅ Safe command execution

## Commands

### Validate Single Skill

```bash
# Read and validate skill
python -c "
import yaml
import re
from pathlib import Path

skill_file = Path('backend/data/skills/{skill_name}/SKILL.md')
content = skill_file.read_text()

# Check frontmatter
match = re.match(r'^---\n(.*?)\n---', content, re.DOTALL)
if not match:
    print('❌ Missing frontmatter')
    exit(1)

frontmatter = yaml.safe_load(match.group(1))

# Check required fields
required = ['name', 'description']
for field in required:
    if field not in frontmatter:
        print(f'❌ Missing required field: {field}')
        exit(1)

print('✅ Skill validation passed')
"
```

### List All Skills

```bash
find backend/data/skills -name "SKILL.md" -type f | sort
```

### Check for Common Issues

```bash
# Check for hardcoded secrets
grep -r "api_key\|secret\|password" backend/data/skills/*/SKILL.md

# Check for unsafe commands
grep -r "rm -rf\|format\|shutdown" backend/data/skills/*/SKILL.md
```

## Validation Output

**Valid skill example:**
```
✅ Frontmatter: Complete
✅ Required sections: Present
✅ Security check: Passed
✅ Syntax: Valid
```

**Invalid skill example:**
```
❌ Missing required field: description
❌ Missing section: When NOT to Use
⚠️  Warning: Contains 'rm -rf' command
```

## Manual Validation Checklist

Before loading a skill, verify:

- [ ] Frontmatter exists and is valid YAML
- [ ] `name` field is present and unique
- [ ] `description` explains when to use the skill
- [ ] `When to Use` section is clear
- [ ] `When NOT to Use` section defines boundaries
- [ ] Command examples are executable
- [ ] No hardcoded credentials
- [ ] File paths are relative or safe
- [ ] Error handling is documented

## Notes

- Skills in `backend/data/skills/` are auto-loaded on startup
- Invalid skills are skipped with warnings
- This validator uses Python and PyYAML
- For production, implement validation in `skills_bootstrap.py`
