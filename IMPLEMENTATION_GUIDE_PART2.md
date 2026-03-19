# Implementation Guide - Additional Content

## 测试用例

### E2E 测试示例

```typescript
// frontend/e2e/llm-config.spec.ts
import { test, expect } from '@playwright/test'

test.describe('LLM Configuration', () => {
  test('should add new LLM', async ({ page }) => {
    await page.goto('http://localhost:3000')
    await page.click('[data-testid="settings-button"]')
    await page.click('text=添加 LLM')

    await page.fill('[name="name"]', 'Test LLM')
    await page.selectOption('[name="provider"]', 'custom')
    await page.fill('[name="model"]', 'test-model')
    await page.fill('[name="base_url"]', 'https://api.test.com/v1')
    await page.fill('[name="api_key"]', 'sk-test-key-12345')
    await page.click('button:has-text("保存")')

    await expect(page.locator('text=保存成功')).toBeVisible()
  })

  test('should not expose API key in UI', async ({ page }) => {
    await page.click('[data-testid="settings-button"]')

    const cardText = await page.locator('.llm-card').first().textContent()
    expect(cardText).not.toMatch(/sk-[a-zA-Z0-9]{32,}/)
    expect(cardText).toMatch(/✓ API Key 已配置/)
  })
})
```

## 迁移脚本

### backend/scripts/migrate_config.py

```python
#!/usr/bin/env python3
"""Migration script for LLM configuration."""

import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.obfuscation import KeyObfuscator
from app.core.llm_config import migrate_old_config_to_new

def backup_credentials():
    """Backup existing credentials."""
    creds_file = Path("data/credentials.encrypted")
    backup_file = Path("data/credentials.backup")

    if creds_file.exists():
        import shutil
        shutil.copy(creds_file, backup_file)
        print(f"✓ Backed up to {backup_file}")
        return True
    return False

def migrate(dry_run=False):
    """Run migration."""
    try:
        credentials = KeyObfuscator.load_credentials()

        if "llms" in credentials:
            print("✓ Already using new format")
            return True

        print("Detected old format, migrating...")

        if not dry_run:
            if not backup_credentials():
                return False

            migrate_old_config_to_new(credentials)
            print("✓ Migration complete")
        else:
            print("[DRY RUN] Would migrate now")

        return True
    except Exception as e:
        print(f"✗ Error: {e}")
        return False

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    success = migrate(dry_run=args.dry_run)
    sys.exit(0 if success else 1)
```

## 实施步骤

### Day 1: 准备
```bash
git checkout -b feature/multi-llm-config
python backend/scripts/migrate_config.py --dry-run
```

### Day 2-3: 后端
```bash
# 创建新文件
touch backend/app/core/llm_config.py

# 修改文件
# - config.py (完整替换)
# - api/config.py (完整替换)
# - api/chat.py (修改)

# 测试
pytest backend/tests/test_llm_config.py -v
```

### Day 3-4: 前端
```bash
# 创建新文件
touch frontend/types/config.ts

# 修改文件
# - lib/api.ts (添加方法)
# - SettingsDialog.tsx (重写)

# 测试
npm run lint
npx playwright test
```

### Day 5: 联调
```bash
# 启动完整系统测试
# - 添加 LLM
# - 切换 LLM
# - 编辑 LLM
# - 删除 LLM
# - 验证安全性
```

### Day 6: 发布
```bash
git add .
git commit -m "feat: multi-LLM configuration"
git checkout main
git merge feature/multi-llm-config
git push
```

## 回滚方案

### Git 回滚
```bash
git revert <commit-hash>
# 或
git reset --hard <commit-before-migration>
```

### 恢复备份
```bash
cp backend/data/credentials.backup backend/data/credentials.encrypted
```

## 安全验证清单

- [ ] 前端不显示明文 API key
- [ ] API 响应不包含明文
- [ ] 编辑时不回填已有 key
- [ ] HTTPS 传输
- [ ] 加密存储
- [ ] 日志脱敏

## 总结

**修改文件**：12 个（后端5，前端3，测试3，脚本1）

**关键改进**：
- ✅ 多 LLM 支持
- ✅ 前端所见即所得
- ✅ API Key 安全
- ✅ 热切换

**预期影响**：
- 性能：<5ms/请求
- 安全性：显著提升
- 用户体验：大幅改善
