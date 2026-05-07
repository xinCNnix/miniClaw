"""SkillMatcher — 基于关键词的技能匹配器，用于元策略 baseline 阶段。"""

from typing import Dict, Optional, Set
import re
import logging

logger = logging.getLogger(__name__)

# 简单任务模式（不需要工具/技能）
_SIMPLE_TASK_PATTERNS = re.compile(
    r'^(what is|what are|who is|who are|define|explain|tell me about|'
    r'[\d+\-*/().\s]+$|'  # 纯数学表达式
    r'^(yes|no|ok|sure|thanks|thank you|好的|是|否|谢))',
    re.IGNORECASE
)


class SkillMatcher:
    """基于关键词的技能匹配器。

    在元策略 baseline 阶段，通过关键词匹配判断用户查询应使用哪个技能。
    """

    def __init__(self, skills_snapshot: Dict[str, str]):
        """初始化技能匹配器。

        Args:
            skills_snapshot: 技能名称到描述的映射，例如:
                {"arxiv-search": "Search academic papers from arXiv", ...}
        """
        self._skills_snapshot = skills_snapshot
        self._keyword_index = self._build_keyword_index(skills_snapshot)

    def _build_keyword_index(self, skills_snapshot: Dict[str, str]) -> Dict[str, Set[str]]:
        """构建关键词到技能名称的倒排索引。

        Returns:
            {keyword_lower: {skill_name1, skill_name2, ...}}
        """
        index: Dict[str, Set[str]] = {}

        # 技能专用关键词映射
        skill_keywords = {
            "arxiv-search": {
                "arxiv", "paper", "论文", "学术", "academic", "research paper",
                "论文搜索", "学术论文", "文献", "literature",
            },
            "conference-paper": {
                "conference", "iclr", "neurips", "icml", "ijcai", "cvpr",
                "iccv", "acl", "会议论文", "顶会", "conference paper",
                "proceedings", "openreview",
                "顶会论文", "iclr 20", "neurips 20", "icml 20",
            },
            "agent-papers": {
                "agent论文", "agent research", "多智能体", "agent survey",
                "agent综述", "agent记忆", "agent规划", "agent工具",
                "awesome agents", "agent research papers", "ai agent研究",
                "agent papers", "agent paper",
            },
            "find-skill": {
                "find skill", "install skill", "搜索技能", "安装技能",
                "skill search", "技能搜索", "download skill",
            },
            "github": {
                "github", "pr", "pull request", "issue", "code review",
                "ci", "commit", "branch", "merge", "repo",
            },
            "research_report_writer": {
                "report", "报告", "write report", "写报告", "research report",
                "研究报告", "调研报告",
            },
            "cluster_reduce_synthesis": {
                "cluster", "synthesis", "聚类", "合并", "consensus",
                "摘要综合", "多源", "聚类合并",
            },
            "diagram-plotter": {
                "diagram", "architecture", "flowchart", "mind map",
                "架构图", "流程图", "思维导图", "时序图", "uml",
            },
            "arxiv-download-paper": {
                "download paper", "pdf", "下载论文", "full text",
                "论文下载", "全文",
            },
            "baidu-search": {
                "百度", "baidu", "搜索", "search", "查找", "资讯",
                "新闻", "实时搜索", "中文搜索",
            },
            "deep_source_extractor": {
                "extract", "提取", "结构化", "structured", "深层次",
                "信息提取", "extraction",
            },
            "doc-creator": {
                "document", "docx", "word", "office", "文档",
                "创建文档", "word文档", "报告文档",
            },
            "chart-plotter": {
                "chart", "plot", "graph", "可视化", "数据图",
                "折线图", "柱状图", "饼图", "散点图", "统计图",
                "matplotlib", "visualization",
            },
            "skill_validator": {
                "validate skill", "验证技能", "检查技能",
            },
            "skill-creator": {
                "create skill", "创建技能", "新建技能", "make skill",
            },
            "get_weather": {
                "weather", "天气", "气温", "温度", "forecast",
                "天气预报",
            },
        }

        for skill_name, keywords in skill_keywords.items():
            if skill_name not in skills_snapshot:
                continue
            for kw in keywords:
                kw_lower = kw.lower()
                if kw_lower not in index:
                    index[kw_lower] = set()
                index[kw_lower].add(skill_name)

        return index

    def match_skill(self, query: str) -> Optional[str]:
        """根据查询匹配最相关的技能。

        对每个 skill 取其所有命中关键词中最长的作为该 skill 的得分，
        再比较各 skill 得分，取最高分的 skill。

        Args:
            query: 用户查询文本

        Returns:
            匹配的技能名称，或 None（无匹配）
        """
        query_lower = query.lower()
        best_skill: Optional[str] = None
        best_score = 0

        for keyword, skills in self._keyword_index.items():
            if keyword in query_lower:
                score = len(keyword)
                for skill in skills:
                    if skill in self._skills_snapshot and score > best_score:
                        best_score = score
                        best_skill = skill

        return best_skill

    def is_simple_task(self, query: str) -> bool:
        """判断是否为简单任务（不需要工具或技能）。

        简单任务包括：
        - 简单问答（what is, who is 等）
        - 纯数学表达式
        - 短确认语（yes, no, ok 等）
        - 非常短的查询（< 5 字符）
        """
        stripped = query.strip()
        if len(stripped) < 5:
            return True
        if _SIMPLE_TASK_PATTERNS.match(stripped):
            return True
        return False

    @property
    def available_skills(self) -> Set[str]:
        """当前可用的技能名称集合。"""
        return set(self._skills_snapshot.keys())
