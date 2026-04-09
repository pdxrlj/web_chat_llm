"""增强版 Skill 加载器

支持：
- 从 YAML 加载技能指导（prompt）
- 从 Python 模块加载工具（代码与配置分离）
- 动态创建 LangChain 工具
- 按需加载，LRU 缓存

新目录结构：
skills/
└── skill_name/
    ├── __init__.py       # 工具实现
    └── skill.yaml        # 技能配置
"""

import importlib
import logging
import os
import sys
from collections import OrderedDict
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import yaml
from langchain_core.tools import BaseTool, StructuredTool, tool

logger = logging.getLogger(__name__)


class SkillLoader:
    """增强版 Skill 加载器

    功能：
    - 扫描本地 skills 目录
    - 加载技能内容（prompt + 工具）
    - 从 Python 模块动态加载工具
    - LRU 缓存

    使用示例:
        loader = SkillLoader("./skills")

        # 列出所有可用技能
        skills = loader.list_skills()

        # 加载技能内容（prompt）
        content = loader.load_skill("web_scraper")

        # 加载技能工具（返回工具列表）
        tools = loader.load_skill_tools("web_scraper")
    """

    def __init__(
        self,
        skills_dir: str = "./skills",
        cache_size: int = 10,
    ):
        """
        初始化 Skill 加载器

        Args:
            skills_dir: skills 目录路径
            cache_size: LRU 缓存大小（默认 10）
        """
        self.skills_dir = Path(skills_dir)
        self.cache_size = cache_size

        # LRU 缓存
        self._cache: OrderedDict[str, Dict[str, Any]] = OrderedDict()
        self._tools_cache: OrderedDict[str, List[BaseTool]] = OrderedDict()

        # 技能索引（name -> skill_dir）
        self._skill_index: Dict[str, Path] = {}

        # 添加 skills 目录到 Python 路径
        skills_parent = self.skills_dir.parent
        if str(skills_parent) not in sys.path:
            sys.path.insert(0, str(skills_parent))

        # 初始化时扫描技能目录
        self._scan_skills()

        logger.info(
            f"SkillLoader 初始化完成 - "
            f"目录: {skills_dir}, "
            f"发现技能: {len(self._skill_index)}, "
            f"缓存大小: {cache_size}"
        )

    def _scan_skills(self) -> None:
        """扫描 skills 目录，建立索引"""
        if not self.skills_dir.exists():
            logger.warning(f"Skills 目录不存在: {self.skills_dir}")
            self.skills_dir.mkdir(parents=True, exist_ok=True)
            return

        # 查找所有包含 skill.yaml 的目录
        for item in self.skills_dir.iterdir():
            if item.is_dir():
                skill_yaml = item / "skill.yaml"
                if skill_yaml.exists():
                    try:
                        with open(skill_yaml, "r", encoding="utf-8") as f:
                            data = yaml.safe_load(f)

                        if data and "name" in data:
                            skill_name = data["name"]
                            self._skill_index[skill_name] = item
                            logger.debug(f"索引技能: {skill_name} -> {item.name}")

                    except Exception as e:
                        logger.error(f"加载技能文件失败 {skill_yaml}: {e}")

    def list_skills(self) -> List[Dict[str, str]]:
        """列出所有可用技能"""
        skills = []

        for skill_name, skill_dir in self._skill_index.items():
            skill_yaml = skill_dir / "skill.yaml"

            try:
                with open(skill_yaml, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)

                skills.append({
                    "name": data.get("name", skill_name),
                    "description": data.get("description", ""),
                    "version": data.get("version", "1.0.0"),
                    "tags": data.get("tags", []),
                    "has_tools": bool(data.get("tools")),
                })

            except Exception as e:
                logger.error(f"读取技能元数据失败 {skill_name}: {e}")

        return skills

    def load_skill(self, skill_name: str) -> Optional[str]:
        """加载技能内容（prompt）"""
        # 检查缓存
        if skill_name in self._cache:
            self._cache.move_to_end(skill_name)
            logger.debug(f"从缓存加载技能: {skill_name}")
            return self._cache[skill_name].get("content")

        # 从文件加载
        if skill_name not in self._skill_index:
            logger.warning(f"技能不存在: {skill_name}")
            return None

        skill_dir = self._skill_index[skill_name]
        skill_yaml = skill_dir / "skill.yaml"

        try:
            with open(skill_yaml, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)

            content = data.get("content", "")

            # 添加到缓存
            self._add_to_cache(skill_name, data)

            logger.info(f"加载技能: {skill_name} (内容长度: {len(content)})")
            return content

        except Exception as e:
            logger.error(f"加载技能失败 {skill_name}: {e}")
            return None

    def load_skill_tools(self, skill_name: str) -> List[BaseTool]:
        """加载技能工具"""
        # 检查工具缓存
        if skill_name in self._tools_cache:
            self._tools_cache.move_to_end(skill_name)
            logger.debug(f"从缓存加载工具: {skill_name}")
            return self._tools_cache[skill_name]

        # 从文件加载
        if skill_name not in self._skill_index:
            logger.warning(f"技能不存在: {skill_name}")
            return []

        skill_dir = self._skill_index[skill_name]
        skill_yaml = skill_dir / "skill.yaml"

        try:
            with open(skill_yaml, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)

            tools_data = data.get("tools", [])

            if not tools_data:
                return []

            # 创建工具实例
            tools = []
            for tool_data in tools_data:
                try:
                    tool_instance = self._create_tool_from_module(tool_data, skill_dir)
                    if tool_instance:
                        tools.append(tool_instance)
                except Exception as e:
                    logger.error(f"创建工具失败 {tool_data.get('name')}: {e}")

            # 添加到缓存
            self._add_tools_to_cache(skill_name, tools)

            logger.info(f"加载技能工具: {skill_name} (工具数: {len(tools)})")
            return tools

        except Exception as e:
            logger.error(f"加载技能工具失败 {skill_name}: {e}")
            return []

    def _create_tool_from_module(
        self,
        tool_data: Dict[str, Any],
        skill_dir: Path,
    ) -> Optional[BaseTool]:
        """从 Python 模块创建工具实例"""
        tool_name = tool_data.get("name")
        description = tool_data.get("description", "")
        module_name = tool_data.get("module")
        function_name = tool_data.get("function")
        parameters = tool_data.get("parameters", {})

        if not tool_name or not module_name or not function_name:
            logger.warning(f"工具定义不完整: {tool_name}")
            return None

        try:
            # 动态导入模块
            module = importlib.import_module(f"skills.{module_name}")

            # 获取函数
            func = getattr(module, function_name)
            
            # 检查函数是否是异步的
            import asyncio
            is_async = asyncio.iscoroutinefunction(func)

            # 创建参数 schema
            from pydantic import Field, create_model

            fields = {}
            for param_name, param_info in parameters.items():
                param_type = param_info.get("type", "string")
                param_desc = param_info.get("description", "")
                param_default = param_info.get("default", ...)

                # 映射类型
                type_map = {
                    "string": str,
                    "number": float,
                    "integer": int,
                    "boolean": bool,
                    "array": list,
                }
                python_type = type_map.get(param_type, str)

                if param_default != ...:
                    fields[param_name] = (
                        python_type,
                        Field(default=param_default, description=param_desc),
                    )
                else:
                    fields[param_name] = (python_type, Field(..., description=param_desc))

            args_schema = create_model(f"{tool_name}Args", **fields) if fields else None

            # 创建工具
            tool_kwargs = {
                "name": tool_name,
                "description": description,
            }
            
            # 根据函数类型设置不同的参数
            if is_async:
                # 异步函数使用 coroutine 参数
                tool_kwargs["coroutine"] = func
                logger.debug(f"创建异步工具: {tool_name}")
            else:
                # 同步函数使用 func 参数
                tool_kwargs["func"] = func
                logger.debug(f"创建同步工具: {tool_name}")
            
            # 只有 args_schema 非空时才传递
            if args_schema is not None:
                tool_kwargs["args_schema"] = args_schema
            
            tool_instance = StructuredTool(**tool_kwargs)

            logger.info(f"创建工具成功: {tool_name} (异步: {is_async})")
            return tool_instance

        except Exception as e:
            logger.error(f"创建工具失败 {tool_name}: {e}", exc_info=True)
            return None

    def _add_to_cache(self, skill_name: str, data: Dict[str, Any]) -> None:
        """添加到 LRU 缓存"""
        if len(self._cache) >= self.cache_size:
            oldest = next(iter(self._cache))
            del self._cache[oldest]
            logger.debug(f"缓存已满，移除: {oldest}")

        self._cache[skill_name] = data

    def _add_tools_to_cache(self, skill_name: str, tools: List[BaseTool]) -> None:
        """添加工具到 LRU 缓存"""
        if len(self._tools_cache) >= self.cache_size:
            oldest = next(iter(self._tools_cache))
            del self._tools_cache[oldest]
            logger.debug(f"工具缓存已满，移除: {oldest}")

        self._tools_cache[skill_name] = tools

    def clear_cache(self) -> None:
        """清除所有缓存"""
        self._cache.clear()
        self._tools_cache.clear()
        logger.info("已清除技能缓存")

    def reload_skills(self) -> int:
        """重新扫描技能目录"""
        self._skill_index.clear()
        self._cache.clear()
        self._tools_cache.clear()
        self._scan_skills()

        return len(self._skill_index)

    def get_skill_metadata(self, skill_name: str) -> Optional[Dict[str, Any]]:
        """获取技能元数据"""
        if skill_name in self._cache:
            data = self._cache[skill_name]
            return {
                "name": data.get("name"),
                "description": data.get("description"),
                "version": data.get("version"),
                "tags": data.get("tags"),
                "has_tools": bool(data.get("tools")),
            }

        if skill_name not in self._skill_index:
            return None

        skill_dir = self._skill_index[skill_name]
        skill_yaml = skill_dir / "skill.yaml"

        try:
            with open(skill_yaml, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)

            return {
                "name": data.get("name"),
                "description": data.get("description"),
                "version": data.get("version"),
                "tags": data.get("tags"),
                "has_tools": bool(data.get("tools")),
            }

        except Exception as e:
            logger.error(f"读取技能元数据失败 {skill_name}: {e}")
            return None

    def __len__(self) -> int:
        return len(self._skill_index)

    def __contains__(self, skill_name: str) -> bool:
        return skill_name in self._skill_index

    def __repr__(self) -> str:
        return (
            f"SkillLoader(skills={len(self._skill_index)}, "
            f"cached={len(self._cache)}, "
            f"tools_cached={len(self._tools_cache)})"
        )
