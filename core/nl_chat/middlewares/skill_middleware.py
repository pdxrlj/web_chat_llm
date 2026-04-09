"""Skill 中间件

在系统提示中注入可用技能列表，让 Agent 知道有哪些技能可用
"""

import logging
from dataclasses import replace
from typing import Any, Callable

from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import ModelRequest

logger = logging.getLogger(__name__)


class SkillMiddleware(AgentMiddleware):
    """Skill 中间件

    功能：
    - 在系统提示中注入可用技能列表
    - 让 Agent 自动知道有哪些技能可用
    - 不需要手动调用 list_skills

    使用示例:
        from .skill_loader import SkillLoader
        from .skill_middleware import SkillMiddleware

        loader = SkillLoader("./skills")
        middleware = SkillMiddleware(loader)

        agent = create_agent(
            model=llm,
            tools=[...],
            middleware=[middleware],
        )
    """

    def __init__(self, skill_loader):
        """
        初始化 Skill 中间件

        Args:
            skill_loader: SkillLoader 实例
        """
        self.skill_loader = skill_loader
        self._skills_prompt = self._build_skills_prompt()

    def _build_skills_prompt(self) -> str:
        """构建技能列表提示"""
        skills = self.skill_loader.list_skills()

        if not skills:
            return ""

        lines = ["\n\n## 可用技能\n"]
        lines.append("你可以使用以下专业技能来处理特定类型的问题：\n")

        for skill in skills:
            tags_str = ", ".join(skill.get("tags", []))
            has_tools = "✓ 包含工具" if skill.get("has_tools") else "仅指导"
            lines.append(
                f"- **{skill['name']}**: {skill['description']}\n"
                f"  （标签: {tags_str} | {has_tools}）"
            )
            
            # 如果技能包含工具，明确说明如何调用
            if skill.get("has_tools"):
                lines.append(f"  💡 使用方式: invoke_skill_tool(skill_name='{skill['name']}', tool_name='<工具名>', **参数)")

        lines.append(
            "\n### 工具使用指南\n"
            "1. **list_skills**: 列出所有可用技能\n"
            "2. **load_skill(skill_name)**: 加载技能的详细指导内容\n"
            "3. **invoke_skill_tool(skill_name, tool_name, parameters)**: 调用技能工具执行具体操作\n"
            "   - parameters 必须是 JSON 字符串格式\n"
            "   - 例如: parameters='{\"expression\": \"1+3\"}'\n"
        )
        
        # 根据技能类型添加特定提示
        skill_specific_hints = []
        for skill in skills:
            if "calculator" in skill.get("tags", []) or "math" in skill.get("tags", []):
                skill_specific_hints.append(
                    f"- 当用户需要进行**数学计算**时，必须使用 `{skill['name']}` 技能\n"
                    f"  示例: invoke_skill_tool(\n"
                    f"    skill_name='{skill['name']}',\n"
                    f"    tool_name='calculate',\n"
                    f"    parameters='{{\"expression\": \"1+3\"}}'\n"
                    f"  )"
                )
        
        if skill_specific_hints:
            lines.append("\n### 重要提醒")
            lines.extend(skill_specific_hints)
            lines.append("- 即使你觉得你知道答案，也应该使用工具来确保准确性和展示能力")

        return "\n".join(lines)

    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable,
    ) -> Any:
        """
        在 model call 前注入技能列表（同步版本）

        Args:
            request: ModelRequest 实例，包含 messages 等字段
            handler: 下一个处理器

        Returns:
            处理结果
        """
        if not self._skills_prompt:
            # 没有可用技能，直接传递
            logger.debug("没有可用技能，跳过中间件")
            return handler(request)
        
        # 追加技能列表到系统提示
        current_prompt = request.system_prompt or ""
        updated_prompt = current_prompt + self._skills_prompt
        
        logger.info(f"SkillMiddleware 注入技能提示 (长度: {len(self._skills_prompt)})")
        logger.debug(f"技能提示预览: {self._skills_prompt[:200]}...")
        
        # 使用 dataclasses.replace 创建新的 ModelRequest
        # 注意：必须将 system_message 设为 None，因为不能同时指定
        modified_request = replace(
            request,
            system_prompt=updated_prompt,
            system_message=None
        )
        
        return handler(modified_request)
    
    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable,
    ) -> Any:
        """
        在 model call 前注入技能列表（异步版本）

        Args:
            request: ModelRequest 实例，包含 messages 等字段
            handler: 下一个处理器

        Returns:
            处理结果
        """
        if not self._skills_prompt:
            # 没有可用技能，直接传递
            logger.debug("没有可用技能，跳过中间件")
            return await handler(request)
        
        # 追加技能列表到系统提示
        current_prompt = request.system_prompt or ""
        updated_prompt = current_prompt + self._skills_prompt
        
        logger.info(f"SkillMiddleware 注入技能提示 (长度: {len(self._skills_prompt)})")
        logger.debug(f"技能提示预览: {self._skills_prompt[:200]}...")
        
        # 使用 dataclasses.replace 创建新的 ModelRequest
        # 注意：必须将 system_message 设为 None，因为不能同时指定
        modified_request = replace(
            request,
            system_prompt=updated_prompt,
            system_message=None
        )
        
        return await handler(modified_request)

    def reload_skills(self) -> None:
        """重新加载技能列表"""
        self._skills_prompt = self._build_skills_prompt()
        logger.info(f"技能列表已更新，当前技能数: {len(self.skill_loader)}")
