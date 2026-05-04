"""
Skills Management API

Provides endpoints for managing skills including installation,
removal, and listing with refined descriptions.
"""

from fastapi import APIRouter, HTTPException, status, BackgroundTasks
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from pathlib import Path
import sys

from app.core.skills_registry import get_skills_registry
from app.core.description_refiner import get_description_refiner
from app.skills.loader import get_skill_loader
from app.config import get_settings

# Add skills directory to path for importing skill scripts
import os
skills_scripts_dir = Path(os.path.join(os.path.dirname(__file__), "../../data/skills/find-skill/scripts"))
if skills_scripts_dir.exists():
    sys.path.insert(0, str(skills_scripts_dir))


router = APIRouter(tags=["skills"])


class SkillMetadata(BaseModel):
    """Skill metadata model."""
    name: str = Field(..., description="Skill name")
    description: str = Field(..., description="Refined Chinese description")
    description_en: Optional[str] = Field(None, description="Refined English description (auto-fallback to description if missing)")
    enabled: bool = Field(True, description="Whether skill is enabled")
    version: str = Field("1.0.0", description="Skill version")
    author: str = Field("", description="Skill author")
    tags: List[str] = Field(default_factory=list, description="Skill tags")
    installed_at: Optional[str] = Field(None, description="Installation timestamp")

    @classmethod
    def from_registry_data(cls, data: Dict[str, Any]) -> "SkillMetadata":
        """
        Create SkillMetadata from registry data with fallback for missing description_en.

        Args:
            data: Raw skill data from registry

        Returns:
            SkillMetadata instance
        """
        # Fallback: if description_en is missing, use description
        description_en = data.get("description_en") or data.get("description", "")
        return cls(
            name=data.get("name", ""),
            description=data.get("description", ""),
            description_en=description_en,
            enabled=data.get("enabled", True),
            version=data.get("version", "1.0.0"),
            author=data.get("author", ""),
            tags=data.get("tags", []),
            installed_at=data.get("installed_at"),
        )


class ListSkillsResponse(BaseModel):
    """Response model for listing skills."""
    skills: List[SkillMetadata]


class InstallSkillRequest(BaseModel):
    """Request model for installing a skill."""
    name: str = Field(..., description="Skill name to install")


class CreateSkillRequest(BaseModel):
    """Request model for creating a new skill."""
    name: str = Field(..., description="Skill name (alphanumeric, underscores only)")
    description: str = Field(..., description="Detailed skill description")
    author: str = Field(default="", description="Skill author")
    tags: List[str] = Field(default_factory=list, description="Skill tags")
    version: str = Field(default="1.0.0", description="Skill version")


class ToggleSkillRequest(BaseModel):
    """Request model for toggling skill enabled state."""
    enabled: bool = Field(..., description="New enabled state")


@router.get("/list", response_model=ListSkillsResponse)
async def list_skills():
    """
    List all installed skills.

    Returns a list of all skills with their metadata including
    refined descriptions suitable for UI display.

    ## Response Example
    ```json
    {
      "skills": [
        {
          "name": "get_weather",
          "description": "获取城市天气信息",
          "description_en": "Get city weather info",
          "enabled": true,
          "version": "1.0.0",
          "author": "miniClaw",
          "tags": ["weather", "api"],
          "installed_at": "2025-01-15T10:30:00Z"
        }
      ]
    }
    ```
    """
    try:
        registry = get_skills_registry()

        # Sync with filesystem (remove skills that no longer exist)
        settings = get_settings()
        skills_dir = Path(settings.skills_dir)
        registry.scan_and_sync(skills_dir)

        # Auto-discover unregistered skills from disk
        registered = set(registry.list_skills().keys())
        for skill_dir in skills_dir.iterdir():
            if not skill_dir.is_dir():
                continue
            skill_file = skill_dir / "SKILL.md"
            if not skill_file.exists():
                continue
            skill_name = skill_dir.name
            if skill_name in registered:
                continue

            # Read frontmatter to register without LLM
            try:
                import yaml
                content = skill_file.read_text(encoding="utf-8")
                frontmatter = {}
                if content.startswith("---"):
                    parts = content.split("---", 2)
                    if len(parts) >= 2:
                        frontmatter = yaml.safe_load(parts[1]) or {}

                desc = frontmatter.get("description", "")
                desc_en = frontmatter.get("description_en", "") or desc
                registry.add_skill(
                    name=skill_name,
                    description=desc,
                    description_en=desc_en,
                    enabled=True,
                    version=frontmatter.get("version", "1.0.0"),
                    author=frontmatter.get("author", ""),
                    tags=frontmatter.get("tags", []),
                )
            except Exception:
                pass

        # List all skills
        skills_dict = registry.list_skills()
        skills = [
            SkillMetadata.from_registry_data(skill_data)
            for skill_data in skills_dict.values()
        ]

        return ListSkillsResponse(skills=skills)

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list skills: {str(e)}",
        )


@router.post("/install")
async def install_skill(request: InstallSkillRequest):
    """
    Install a skill and generate refined descriptions.

    This endpoint:
    1. Reads the SKILL.md file
    2. Uses LLM to generate refined descriptions
    3. Adds the skill to the registry

    ## Request Example
    ```json
    {
      "name": "get_weather"
    }
    ```

    ## Response Example
    ```json
    {
      "success": true,
      "message": "Skill 'get_weather' installed successfully",
      "skill": {
        "name": "get_weather",
        "description": "获取城市天气信息",
        "description_en": "Get city weather info"
      }
    }
    ```
    """
    try:
        # Get skill loader
        skill_loader = get_skill_loader()
        skill_path = skill_loader.get_skill_path(request.name)

        if not skill_path:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Skill '{request.name}' not found",
            )

        # Read skill content
        skill_content = skill_loader.load_skill_from_file(skill_path)
        if not skill_content:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to read skill file for '{request.name}'",
            )

        # Parse frontmatter for metadata
        import yaml
        frontmatter = {}
        if skill_content.startswith("---"):
            parts = skill_content.split("---", 2)
            if len(parts) >= 2:
                try:
                    frontmatter = yaml.safe_load(parts[1])
                except:
                    pass

        # Extract metadata
        version = frontmatter.get("version", "1.0.0")
        author = frontmatter.get("author", "")
        tags = frontmatter.get("tags", [])

        # Refine description using LLM
        refiner = get_description_refiner()
        description, description_en = await refiner.refine_description(skill_content)

        # Add to registry
        registry = get_skills_registry()
        skill_data = registry.add_skill(
            name=request.name,
            description=description,
            description_en=description_en,
            enabled=True,
            version=version,
            author=author,
            tags=tags,
        )

        return {
            "success": True,
            "message": f"Skill '{request.name}' installed successfully",
            "skill": SkillMetadata.from_registry_data(skill_data),
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to install skill: {str(e)}",
        )


@router.post("/create")
async def create_skill(request: CreateSkillRequest):
    """
    Create a new skill from user input.

    This endpoint:
    1. Validates skill name (alphanumeric, underscores only)
    2. Creates skill directory and SKILL.md file
    3. Generates refined descriptions using LLM
    4. Adds skill to registry

    ## Request Example
    ```json
    {
      "name": "file_manager",
      "description": "管理本地文件系统，支持文件读写、目录浏览",
      "author": "Your Name",
      "tags": ["files", "utility"],
      "version": "1.0.0"
    }
    ```

    ## Response Example
    ```json
    {
      "success": true,
      "message": "Skill 'file_manager' created successfully",
      "skill": {
        "name": "file_manager",
        "description": "管理本地文件系统",
        "description_en": "Manage local file system",
        "enabled": true
      }
    }
    ```
    """
    try:
        import re
        import yaml

        # Validate skill name
        if not re.match(r'^[a-zA-Z][a-zA-Z0-9_]*$', request.name):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Skill name must start with a letter and contain only letters, numbers, and underscores",
            )

        # Check if skill already exists
        settings = get_settings()
        skills_dir = Path(settings.skills_dir)
        skill_path = skills_dir / request.name

        if skill_path.exists():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Skill '{request.name}' already exists",
            )

        # Create skill directory
        skill_path.mkdir(parents=True, exist_ok=True)

        # Generate SKILL.md content
        skill_md_content = f"""---
name: {request.name}
description: {request.description}
version: {request.version}
author: {request.author}
tags: {yaml.dump(request.tags, default_flow_style=False, allow_unicode=True)}
---

# {request.name.replace('_', ' ').title()} Skill

## 功能描述

{request.description}

## 使用步骤

当用户需要使用此技能时，按照以下步骤操作：

### 步骤 1: 分析用户需求

理解用户的具体需求，确定如何使用此技能来解决问题。

### 步骤 2: 执行相应操作

使用核心工具完成用户的需求。

## 示例

### 示例 1: 基础用法

**用户输入**: （待补充）

**执行过程**:
1. 理解用户意图
2. 执行相应操作
3. 返回结果给用户

**预期输出**:
```
（待补充）
```

## 注意事项

1. 确保操作的安全性
2. 处理可能的错误情况
3. 向用户提供清晰的反馈

## 进阶用法

可以根据实际需求扩展此技能的功能。
"""

        # Write SKILL.md
        skill_file = skill_path / "SKILL.md"
        skill_file.write_text(skill_md_content, encoding="utf-8")

        # Refine description using LLM
        refiner = get_description_refiner()
        refined_desc, refined_desc_en = await refiner.refine_description(skill_md_content)

        # Add to registry
        registry = get_skills_registry()
        skill_data = registry.add_skill(
            name=request.name,
            description=refined_desc,
            description_en=refined_desc_en,
            enabled=True,
            version=request.version,
            author=request.author,
            tags=request.tags,
        )

        return {
            "success": True,
            "message": f"Skill '{request.name}' created successfully",
            "skill": SkillMetadata.from_registry_data(skill_data),
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create skill: {str(e)}",
        )


@router.delete("/{skill_name}")
async def delete_skill(skill_name: str):
    """
    Delete a skill from the registry.

    Note: This only removes the skill from the registry.
    The SKILL.md file must be deleted manually.

    Args:
        skill_name: Name of the skill to delete

    ## Response Example
    ```json
    {
      "success": true,
      "message": "Skill 'get_weather' deleted successfully"
    }
    ```
    """
    try:
        registry = get_skills_registry()

        if not registry.get_skill(skill_name):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Skill '{skill_name}' not found in registry",
            )

        registry.remove_skill(skill_name)

        return {
            "success": True,
            "message": f"Skill '{skill_name}' deleted successfully",
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete skill: {str(e)}",
        )


@router.post("/{skill_name}/toggle", response_model=SkillMetadata)
async def toggle_skill(skill_name: str, request: ToggleSkillRequest):
    """
    Enable or disable a skill.

    Args:
        skill_name: Name of the skill
        request: Toggle request with new enabled state

    ## Response Example
    ```json
    {
      "name": "get_weather",
      "description": "获取城市天气信息",
      "enabled": false
    }
    ```
    """
    try:
        registry = get_skills_registry()

        if not registry.get_skill(skill_name):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Skill '{skill_name}' not found",
            )

        registry.toggle_skill(skill_name, request.enabled)

        # Return updated skill data
        skill_data = registry.get_skill(skill_name)
        return SkillMetadata.from_registry_data(skill_data)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to toggle skill: {str(e)}",
        )


@router.post("/refresh")
async def refresh_skills():
    """
    Refresh skills from filesystem.

    Scans the skills directory and:
    - Removes registry entries for deleted skills
    - Optionally adds new skills (if LLM is configured)

    ## Response Example
    ```json
    {
      "success": true,
      "message": "Skills refreshed. 2 skills found.",
      "removed": ["old_skill"],
      "added": ["new_skill"]
    }
    ```
    """
    try:
        registry = get_skills_registry()
        settings = get_settings()
        skills_dir = Path(settings.skills_dir)
        skill_loader = get_skill_loader()

        # Remove deleted skills
        removed = registry.scan_and_sync(skills_dir)

        # Scan for new skills
        current_skills = set(registry.list_skills().keys())
        filesystem_skills = set()

        for skill_dir in skills_dir.iterdir():
            if not skill_dir.is_dir():
                continue

            skill_file = skill_dir / "SKILL.md"
            if not skill_file.exists():
                continue

            filesystem_skills.add(skill_dir.name)

        # Find new skills
        new_skills = filesystem_skills - current_skills
        added = []

        # Auto-install new skills (optional - requires LLM)
        for skill_name in new_skills:
            try:
                # Read skill content
                skill_path = skill_loader.get_skill_path(skill_name)
                skill_content = skill_loader.load_skill_from_file(skill_path)

                if skill_content:
                    # Parse frontmatter
                    import yaml
                    frontmatter = {}
                    if skill_content.startswith("---"):
                        parts = skill_content.split("---", 2)
                        if len(parts) >= 2:
                            try:
                                frontmatter = yaml.safe_load(parts[1])
                            except:
                                pass

                    # Refine description
                    refiner = get_description_refiner()
                    description, description_en = await refiner.refine_description(skill_content)

                    # Add to registry
                    registry.add_skill(
                        name=skill_name,
                        description=description,
                        description_en=description_en,
                        enabled=True,
                        version=frontmatter.get("version", "1.0.0"),
                        author=frontmatter.get("author", ""),
                        tags=frontmatter.get("tags", []),
                    )

                    added.append(skill_name)

            except Exception as e:
                print(f"Failed to auto-install skill '{skill_name}': {e}")
                continue

        return {
            "success": True,
            "message": f"Skills refreshed. {len(filesystem_skills)} skills found.",
            "removed": removed,
            "added": added,
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to refresh skills: {str(e)}",
        )


# ========== Skill Search and Installation APIs ==========


class SearchSkillsRequest(BaseModel):
    """Request model for searching skills."""
    source: str = Field("github", description="Source to search (github, clawhub)")
    query: str = Field(..., description="Search query")
    max_results: int = Field(10, description="Maximum number of results", ge=1, le=100)
    sort: str = Field("stars", description="Sort order (stars, forks, updated)")
    language: Optional[str] = Field(None, description="Filter by programming language")


class SearchSkillsResult(BaseModel):
    """Single search result."""
    name: str
    full_name: str
    description: str
    url: str
    clone_url: str
    stars: int
    forks: int
    updated: str
    language: Optional[str]


class SearchSkillsResponse(BaseModel):
    """Response model for skill search."""
    source: str
    query: str
    total_count: int
    returned: int
    results: List[SearchSkillsResult]


@router.post("/search", response_model=SearchSkillsResponse)
async def search_skills(request: SearchSkillsRequest):
    """
    Search for skills from external sources (GitHub, clawhub).

    ## Request Example
    ```json
    {
      "source": "github",
      "query": "weather",
      "max_results": 10,
      "sort": "stars"
    }
    ```

    ## Response Example
    ```json
    {
      "source": "github",
      "query": "weather",
      "total_count": 1523,
      "returned": 10,
      "results": [
        {
          "name": "weather-skill",
          "full_name": "user/weather-skill",
          "description": "Get weather information",
          "url": "https://github.com/user/weather-skill",
          "clone_url": "https://github.com/user/weather-skill.git",
          "stars": 45,
          "forks": 12,
          "updated": "2024-03-15",
          "language": "Python"
        }
      ]
    }
    ```
    """
    try:
        # Import search functions from find-skill scripts
        try:
            from search_skills import search_github, search_clawhub
        except ImportError as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Search module not available: {str(e)}",
            )

        # Perform search
        if request.source == "github":
            result = search_github(
                query=request.query,
                max_results=request.max_results,
                sort=request.sort,
                language=request.language,
            )
        elif request.source == "clawhub":
            result = search_clawhub(
                query=request.query,
                max_results=request.max_results,
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unknown source: {request.source}",
            )

        # Check for errors
        if "error" in result:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=result["error"],
            )

        # Convert to response model
        results = [SearchSkillsResult(**r) for r in result.get("results", [])]

        return SearchSkillsResponse(
            source=result["source"],
            query=result["query"],
            total_count=result.get("total_count", 0),
            returned=result.get("returned", 0),
            results=results,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to search skills: {str(e)}",
        )


class InstallSkillFromUrlRequest(BaseModel):
    """Request model for installing a skill from URL."""
    url: str = Field(..., description="Git repository URL")
    name: Optional[str] = Field(None, description="Skill/directory name (default: derived from URL)")
    branch: Optional[str] = Field(None, description="Git branch to checkout")
    tag: Optional[str] = Field(None, description="Git tag to checkout")
    subdir: Optional[str] = Field(None, description="Subdirectory in repo containing the skill")


class InstallSkillFromUrlResponse(BaseModel):
    """Response model for skill installation."""
    success: bool
    message: str
    skill_name: Optional[str] = None
    path: Optional[str] = None


@router.post("/install-from-url", response_model=InstallSkillFromUrlResponse)
async def install_skill_from_url(request: InstallSkillFromUrlRequest, background_tasks: BackgroundTasks):
    """
    Install a skill from a Git repository URL.

    This endpoint:
    1. Clones the Git repository
    2. Validates the skill structure (SKILL.md must exist)
    3. Copies to the skills directory
    4. Registers the skill

    ## Request Example
    ```json
    {
      "url": "https://github.com/user/weather-skill",
      "name": "weather",
      "branch": "main"
    }
    ```

    ## Response Example
    ```json
    {
      "success": true,
      "message": "Skill 'weather' installed successfully",
      "skill_name": "weather",
      "path": "./data/skills/weather"
    }
    ```
    """
    try:
        # Import install function from find-skill scripts
        try:
            from install_skill import install_skill
        except ImportError as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Install module not available: {str(e)}",
            )

        settings = get_settings()
        target_dir = Path(settings.skills_dir).resolve()

        # Perform installation
        result = install_skill(
            url=request.url,
            name=request.name,
            target=str(target_dir),
            branch=request.branch,
            tag=request.tag,
            subdir=request.subdir,
        )

        # Check for errors
        if "error" in result:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result["error"],
            )

        # Schedule background refresh of skills registry
        async def refresh_registry():
            try:
                registry = get_skills_registry()
                skill_loader = get_skill_loader()

                skill_name = result.get("name")
                skill_path = Path(result.get("path"))

                # Read skill content
                skill_content = skill_loader.load_skill_from_file(skill_path / "SKILL.md")

                if skill_content:
                    # Parse frontmatter
                    import yaml
                    frontmatter = {}
                    if skill_content.startswith("---"):
                        parts = skill_content.split("---", 2)
                        if len(parts) >= 2:
                            try:
                                frontmatter = yaml.safe_load(parts[1])
                            except:
                                pass

                    # Refine description
                    refiner = get_description_refiner()
                    description, description_en = await refiner.refine_description(skill_content)

                    # Add to registry
                    registry.add_skill(
                        name=skill_name,
                        description=description,
                        description_en=description_en,
                        enabled=True,
                        version=frontmatter.get("version", "1.0.0"),
                        author=frontmatter.get("author", ""),
                        tags=frontmatter.get("tags", []),
                    )
            except Exception as e:
                print(f"Failed to refresh registry after installation: {e}")

        background_tasks.add_task(refresh_registry)

        return InstallSkillFromUrlResponse(
            success=True,
            message=result.get("message", "Skill installed successfully"),
            skill_name=result.get("name"),
            path=result.get("path"),
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to install skill: {str(e)}",
        )
