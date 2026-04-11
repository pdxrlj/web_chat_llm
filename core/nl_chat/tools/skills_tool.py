"""技能工具：基于 langchain-skills-adapters 的 SkillsTool 封装

使用 SkillsTool 而非 SkillMiddleware 的原因：
- SkillMiddleware 的 system_prompt 属性不会被 create_agent 自动注入到 ModelRequest 中
- SkillsTool 将技能目录嵌入工具的 description，模型通过工具列表即可看到技能信息
- 模型调用 activate_skill(name="xxx") 获取完整技能指令，路径由 SkillsLoader 自动管理
"""

from pathlib import Path

from langchain_skills_adapters.tools import SkillsTool as _SkillsTool

# 导出便于使用的工厂函数
__all__ = ["create_skills_tool"]


def create_skills_tool(skills_dir: str | Path) -> _SkillsTool:
    """创建技能工具实例

    Args:
        skills_dir: skills 目录路径

    Returns:
        SkillsTool 实例（工具名: activate_skill）
    """
    skills_path = Path(skills_dir)
    return _SkillsTool(skills_path=skills_path)
