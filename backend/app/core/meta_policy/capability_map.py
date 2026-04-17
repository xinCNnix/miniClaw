"""能力映射管理模块。

管理工具/技能名称到网络槽位的双向映射，支持动态扩展。
用于元策略网络中将离散的能力标识符映射为连续的向量索引。
"""

from typing import Dict, Optional


class CapabilityMap:
    """管理工具/技能名称到网络槽位的双向映射，支持动态扩展。"""

    def __init__(self, max_tool_slots: int = 20, max_skill_slots: int = 30):
        self._max_tool_slots = max_tool_slots
        self._max_skill_slots = max_skill_slots
        self._tool_map: Dict[str, int] = {}    # tool_name -> slot_index
        self._tool_rmap: Dict[int, str] = {}   # slot_index -> tool_name
        self._skill_map: Dict[str, int] = {}
        self._skill_rmap: Dict[int, str] = {}

    def register_tool(self, name: str, slot: int) -> None:
        """注册工具到指定槽位。

        如果该槽位已被占用或该工具已注册到其他槽位，会先移除旧映射。

        Args:
            name: 工具名称。
            slot: 目标槽位索引。

        Raises:
            ValueError: 槽位索引超出有效范围。
        """
        if slot < 0 or slot >= self._max_tool_slots:
            raise ValueError(f"Tool slot {slot} out of range [0, {self._max_tool_slots})")
        # 如果该槽位已被占用，先移除旧映射
        if slot in self._tool_rmap:
            old_name = self._tool_rmap[slot]
            self._tool_map.pop(old_name, None)
        # 如果该工具已注册到其他槽位，先移除旧映射
        if name in self._tool_map:
            old_slot = self._tool_map[name]
            self._tool_rmap.pop(old_slot, None)
        self._tool_map[name] = slot
        self._tool_rmap[slot] = name

    def register_skill(self, name: str, slot: int) -> None:
        """注册技能到指定槽位。

        如果该槽位已被占用或该技能已注册到其他槽位，会先移除旧映射。

        Args:
            name: 技能名称。
            slot: 目标槽位索引。

        Raises:
            ValueError: 槽位索引超出有效范围。
        """
        if slot < 0 or slot >= self._max_skill_slots:
            raise ValueError(f"Skill slot {slot} out of range [0, {self._max_skill_slots})")
        if slot in self._skill_rmap:
            old_name = self._skill_rmap[slot]
            self._skill_map.pop(old_name, None)
        if name in self._skill_map:
            old_slot = self._skill_map[name]
            self._skill_rmap.pop(old_slot, None)
        self._skill_map[name] = slot
        self._skill_rmap[slot] = name

    def unregister_tool(self, name: str) -> None:
        """注销工具，slot 号保留但标记为空。

        Args:
            name: 要注销的工具名称。
        """
        if name in self._tool_map:
            slot = self._tool_map.pop(name)
            self._tool_rmap.pop(slot, None)

    def unregister_skill(self, name: str) -> None:
        """注销技能，slot 号保留但标记为空。

        Args:
            name: 要注销的技能名称。
        """
        if name in self._skill_map:
            slot = self._skill_map.pop(name)
            self._skill_rmap.pop(slot, None)

    def get_tool_slot(self, name: str) -> Optional[int]:
        """获取工具的槽位索引。

        Args:
            name: 工具名称。

        Returns:
            槽位索引，未注册则返回 None。
        """
        return self._tool_map.get(name)

    def get_skill_slot(self, name: str) -> Optional[int]:
        """获取技能的槽位索引。

        Args:
            name: 技能名称。

        Returns:
            槽位索引，未注册则返回 None。
        """
        return self._skill_map.get(name)

    def get_tool_name(self, slot: int) -> Optional[str]:
        """通过槽位索引获取工具名称。

        Args:
            slot: 槽位索引。

        Returns:
            工具名称，槽位未占用则返回 None。
        """
        return self._tool_rmap.get(slot)

    def get_skill_name(self, slot: int) -> Optional[str]:
        """通过槽位索引获取技能名称。

        Args:
            slot: 槽位索引。

        Returns:
            技能名称，槽位未占用则返回 None。
        """
        return self._skill_rmap.get(slot)

    def get_active_tool_slots(self) -> Dict[int, str]:
        """获取所有已注册的工具槽位映射。

        Returns:
            槽位索引到工具名称的字典副本。
        """
        return dict(self._tool_rmap)

    def get_active_skill_slots(self) -> Dict[int, str]:
        """获取所有已注册的技能槽位映射。

        Returns:
            槽位索引到技能名称的字典副本。
        """
        return dict(self._skill_rmap)

    def get_next_available_tool_slot(self) -> Optional[int]:
        """获取下一个可用的工具槽位。

        Returns:
            最小的未占用槽位索引，无可用槽位则返回 None。
        """
        for i in range(self._max_tool_slots):
            if i not in self._tool_rmap:
                return i
        return None

    def get_next_available_skill_slot(self) -> Optional[int]:
        """获取下一个可用的技能槽位。

        Returns:
            最小的未占用槽位索引，无可用槽位则返回 None。
        """
        for i in range(self._max_skill_slots):
            if i not in self._skill_rmap:
                return i
        return None

    @property
    def tool_count(self) -> int:
        """当前已注册的工具数量。"""
        return len(self._tool_map)

    @property
    def skill_count(self) -> int:
        """当前已注册的技能数量。"""
        return len(self._skill_map)

    def auto_register_tool(self, name: str) -> int:
        """自动注册工具到下一个可用槽位。

        如果工具已注册，返回已有的槽位索引。

        Args:
            name: 工具名称。

        Returns:
            分配的槽位索引。

        Raises:
            ValueError: 无可用槽位。
        """
        slot = self.get_tool_slot(name)
        if slot is not None:
            return slot
        slot = self.get_next_available_tool_slot()
        if slot is None:
            raise ValueError(f"No available tool slots (max={self._max_tool_slots})")
        self.register_tool(name, slot)
        return slot

    def auto_register_skill(self, name: str) -> int:
        """自动注册技能到下一个可用槽位。

        如果技能已注册，返回已有的槽位索引。

        Args:
            name: 技能名称。

        Returns:
            分配的槽位索引。

        Raises:
            ValueError: 无可用槽位。
        """
        slot = self.get_skill_slot(name)
        if slot is not None:
            return slot
        slot = self.get_next_available_skill_slot()
        if slot is None:
            raise ValueError(f"No available skill slots (max={self._max_skill_slots})")
        self.register_skill(name, slot)
        return slot

    @classmethod
    def from_core_tools(
        cls,
        max_tool_slots: int = 20,
        max_skill_slots: int = 30,
    ) -> "CapabilityMap":
        """创建并自动注册核心工具和技能。

        Returns:
            已注册核心工具的 CapabilityMap 实例
        """
        cap_map = cls(max_tool_slots, max_skill_slots)

        # 注册核心工具
        try:
            from app.tools import CORE_TOOLS
            for i, tool in enumerate(CORE_TOOLS):
                if i < max_tool_slots:
                    cap_map.register_tool(tool.name, i)
        except Exception:
            pass

        # 注册技能
        try:
            from app.skills.bootstrap import SkillsBootstrap
            bootstrap = SkillsBootstrap()
            skills = bootstrap.scan_skills()
            for i, skill in enumerate(skills):
                if i < max_skill_slots:
                    cap_map.register_skill(skill.name, i)
        except Exception:
            pass

        return cap_map
