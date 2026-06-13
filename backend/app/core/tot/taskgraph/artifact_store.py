"""
ArtifactStore — 任务产出物注册与持久化。

注册时:
- path 模式: 源文件复制到 base_dir
- content 模式: 内容写入 base_dir

查询: by_id / by_task / by_type / list_all
"""
from __future__ import annotations

import hashlib
import logging
import os
import shutil
import time
from typing import Dict, List, Optional

from app.core.tot.taskgraph.models import Artifact, ArtifactType

logger = logging.getLogger(__name__)


class ArtifactStore:
    """任务产出物注册与查询"""

    def __init__(self, base_dir: str = "data/artifacts"):
        self.base_dir = base_dir
        self._artifacts: Dict[str, Artifact] = {}
        self._task_index: Dict[str, List[str]] = {}

    def register(
        self,
        name: str,
        artifact_type: ArtifactType,
        path: Optional[str] = None,
        content: Optional[str] = None,
        task_id: str = "",
        **kwargs,
    ) -> Artifact:
        """注册一个产出物"""
        os.makedirs(self.base_dir, exist_ok=True)

        art_id = f"art_{len(self._artifacts) + 1}_{int(time.time())}"
        dest_path: Optional[str] = None
        size_bytes = 0
        checksum = ""

        if path and os.path.exists(path):
            dest_path = os.path.join(self.base_dir, name)
            if os.path.exists(dest_path) and dest_path != path:
                base, ext = os.path.splitext(name)
                dest_path = os.path.join(self.base_dir, f"{base}_{art_id}{ext}")
            shutil.copy2(path, dest_path)
            size_bytes = os.path.getsize(dest_path)
            with open(dest_path, "rb") as f:
                checksum = hashlib.md5(f.read()).hexdigest()

        elif content is not None:
            dest_path = os.path.join(self.base_dir, name)
            if os.path.exists(dest_path):
                base, ext = os.path.splitext(name)
                dest_path = os.path.join(self.base_dir, f"{base}_{art_id}{ext}")
            with open(dest_path, "w", encoding="utf-8") as f:
                f.write(content)
            size_bytes = os.path.getsize(dest_path)
            checksum = hashlib.md5(content.encode()).hexdigest()

        artifact = Artifact(
            id=art_id,
            name=name,
            artifact_type=artifact_type,
            path=dest_path,
            created_by_task=task_id,
            created_at=time.time(),
            size_bytes=size_bytes,
            checksum=checksum,
            **kwargs,
        )

        self._artifacts[art_id] = artifact
        if task_id:
            self._task_index.setdefault(task_id, []).append(art_id)

        logger.debug("Artifact registered: %s (%s) from task %s", art_id, name, task_id)
        return artifact

    def get(self, artifact_id: str) -> Optional[Artifact]:
        """按 ID 获取产出物"""
        return self._artifacts.get(artifact_id)

    def get_by_task(self, task_id: str) -> List[Artifact]:
        """获取任务的所有产出物"""
        ids = self._task_index.get(task_id, [])
        return [self._artifacts[i] for i in ids if i in self._artifacts]

    def get_by_type(self, artifact_type: ArtifactType) -> List[Artifact]:
        """按类型筛选产出物"""
        return [a for a in self._artifacts.values() if a.artifact_type == artifact_type]

    def read_content(self, artifact_id: str) -> Optional[str]:
        """读取产出物内容"""
        art = self._artifacts.get(artifact_id)
        if art is None or art.path is None:
            return None
        if not os.path.exists(art.path):
            return None
        with open(art.path, "r", encoding="utf-8") as f:
            return f.read()

    def list_all(self) -> List[Artifact]:
        """列出所有产出物"""
        return list(self._artifacts.values())

    def summary_json(self) -> str:
        """返回产出物摘要 JSON（用于 checkpoint）"""
        import json
        summary = []
        for art in self._artifacts.values():
            summary.append({
                "id": art.id,
                "name": art.name,
                "type": art.artifact_type.value,
                "size_bytes": art.size_bytes,
                "created_by_task": art.created_by_task,
            })
        return json.dumps(summary, ensure_ascii=False)
