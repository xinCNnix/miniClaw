"""
同步脚本：将修改的文件同步到 Git 本地仓库和 F 盘

同步规则：
- ✓ 同步源代码、配置、文档、技能定义
- ✗ 不同步测试文件、临时文档、数据库、敏感数据
"""

import os
import shutil
from pathlib import Path
from datetime import datetime

# 源目录（工作目录）
SOURCE_DIR = Path(r"I:\code\miniclaw")

# 目标目录
GIT_REPO_DIR = Path(r"I:\miniclaw-git")
F_DRIVE_DIR = Path(r"F:\vllm\.conda\envs\mini_openclaw\miniclaw")

# 不应该同步的文件/目录模式
EXCLUDE_PATTERNS = [
    # 测试相关
    r"tests/",
    r"test_",
    r"_test.",
    r".test.",
    r".spec.",
    r"e2e/",
    r"test_output.txt",

    # 临时文档（非生产文档）
    r"API_KEY_SECURITY_GUIDELINES.md",
    r"COMPLETION_SUMMARY.md",
    r"IMPLEMENTATION_GUIDE.md",
    r"IMPLEMENTATION_GUIDE_PART2.md",
    r"LLM_CONFIG_REFACTOR_PLAN.md",
    r"LLM_CONFIG_REFACTOR_PLAN_V2.md",
    r"PERFORMANCE_TEST_REPORT.md",
    r"network_requests.txt",

    # 敏感数据和数据库
    r"credentials.encrypted",
    r".env",
    r"*.sqlite3",
    r"*.db",

    # 生成文件和临时文件
    r"__pycache__/",
    r"node_modules/",
    r".next/",
    r"*.pyc",
    r"*.tmp",
    r"*.bak",
    r"*.log",

    # 临时图片
    r"settings-dialog-full.png",
    r"settings-llm-provider.png",
    r"test_qwen.json",

    # 后端临时文件
    r"backend/=0.8",  # 这个奇怪的文件

    # 文档（中文文档根据内容决定）
    # r"docs/Agent主动性和响应模式增强计划.md",  # 临时分析文档
]

# 只同步这些目录/文件类型
SYNC_PATTERNS = [
    r"backend/app/",
    r"backend/data/skills/",
    r"backend/workspace/",
    r"backend/pyproject.toml",
    r"backend/requirements.txt",
    r"frontend/app/",
    r"frontend/components/",
    r"frontend/hooks/",
    r"frontend/lib/",
    r"frontend/types/",
    r"frontend/package.json",
    r"frontend/package-lock.json",
    r"frontend/postcss.config.mjs",
    r"frontend/playwright.config.ts",
    r".gitignore",
    r"README.md",
    r"CHANGELOG.md",
    r"CLAUDE.md",
    r"QUICKSTART.md",
    r"CONTRIBUTING.md",
    r"CONTRIBUTORS.md",
    r"LICENSE",
    r"NOTICE.md",
    r"start.bat",
    r"start.sh",
    r"docs/DEPLOYMENT.md",
    r"TOT_SKILLS_SUPPORT_REPORT.md",
]

def should_sync(file_path: Path, relative_path: str) -> bool:
    """判断文件是否应该同步"""
    path_str = str(relative_path).replace("\\", "/")

    # 检查是否在同步列表中
    in_sync_list = any(
        path_str.startswith(pattern.rstrip("/")) or
        path_str == pattern.rstrip("/")
        for pattern in SYNC_PATTERNS
    )

    if not in_sync_list:
        return False

    # 检查是否在排除列表中
    for pattern in EXCLUDE_PATTERNS:
        if pattern.endswith("/"):
            # 目录排除
            if path_str.startswith(pattern.rstrip("/")):
                return False
        else:
            # 文件/模式排除
            if pattern in path_str or path_str.endswith(pattern.replace("*", "")):
                return False

    return True

def get_files_to_sync():
    """获取需要同步的文件列表"""
    files_to_sync = []

    # 获取 git 状态中的修改文件
    import subprocess
    result = subprocess.run(
        ["git", "status", "--short"],
        cwd=SOURCE_DIR,
        capture_output=True,
        text=True
    )

    for line in result.stdout.split("\n"):
        if not line.strip():
            continue

        # 解析 git status 输出
        # 格式: XY filename
        parts = line.strip().split(maxsplit=1)
        if len(parts) < 2:
            continue

        file_path = parts[1]
        status = parts[0]

        # 只处理修改（M）、新增（A）、删除（D）的文件
        if status.startswith("??"):
            # 未跟踪文件
            file_rel = Path(file_path)
        else:
            file_rel = Path(file_path)

        full_path = SOURCE_DIR / file_rel

        # 检查是否应该同步
        if should_sync(full_path, file_rel):
            files_to_sync.append((file_rel, status))

    return files_to_sync

def copy_file_to_targets(source_path: Path, relative_path: Path, status: str):
    """复制文件或目录到目标位置"""
    for target_dir in [GIT_REPO_DIR, F_DRIVE_DIR]:
        target_path = target_dir / relative_path

        if status.startswith("D"):
            # 删除文件或目录
            if target_path.exists():
                if target_path.is_file():
                    target_path.unlink()
                elif target_path.is_dir():
                    shutil.rmtree(target_path)
                print(f"  [DELETE] {relative_path}")
        else:
            # 复制文件或目录
            if source_path.exists():
                if source_path.is_file():
                    # 复制文件
                    target_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source_path, target_path)
                    print(f"  [COPY] {relative_path}")
                elif source_path.is_dir():
                    # 复制整个目录
                    if target_path.exists():
                        shutil.rmtree(target_path)
                    shutil.copytree(source_path, target_path, dirs_exist_ok=True)
                    print(f"  [COPY DIR] {relative_path}")

def main():
    """主函数"""
    print("=" * 60)
    print("同步脚本：Git 本地仓库 + F 盘")
    print("=" * 60)
    print(f"源目录: {SOURCE_DIR}")
    print(f"Git 仓库: {GIT_REPO_DIR}")
    print(f"F 盘:    {F_DRIVE_DIR}")
    print("=" * 60)

    # 获取需要同步的文件
    files_to_sync = get_files_to_sync()

    print(f"\n找到 {len(files_to_sync)} 个需要同步的文件\n")

    # 同步文件
    for relative_path, status in files_to_sync:
        source_path = SOURCE_DIR / relative_path

        print(f"\n处理: {relative_path} ({status})")

        if status.startswith("D"):
            print(f"  [DELETE] {relative_path}")
            # 删除目标文件
            for target_dir in [GIT_REPO_DIR, F_DRIVE_DIR]:
                target_path = target_dir / relative_path
                if target_path.exists():
                    if target_path.is_file():
                        target_path.unlink()
                    elif target_path.is_dir():
                        shutil.rmtree(target_path)
        else:
            copy_file_to_targets(source_path, relative_path, status)

    print("\n" + "=" * 60)
    print("同步完成！")
    print("=" * 60)

    # 统计信息
    print(f"\n同步统计:")
    print(f"  处理文件数: {len(files_to_sync)}")
    print(f"  目标位置: 2 (Git 仓库 + F 盘)")

if __name__ == "__main__":
    main()
