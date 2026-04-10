from core.logger import setup_logger
from core.memory import nl_memory
from core.config import config
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_core.tools import tool, BaseTool
from langchain_openai import ChatOpenAI
from langchain.agents import create_agent, AgentState
from langgraph.checkpoint.memory import MemorySaver


from pydantic import SecretStr
from typing import Any, AsyncGenerator, Optional
from typing_extensions import TypedDict
from pathlib import Path

from core.nl_chat.middlewares.emotion_speculate import EmotionSpeculateMiddleware
from .middlewares import SummarizationMiddleware
from .skill_loader import SkillLoader
import asyncio
import time
import json
import uuid

logger = setup_logger(__name__)


class ChatAgentState(AgentState):
    """自定义 Agent State，扩展 session_id 字段供中间件使用"""

    session_id: str


# 定义记忆搜索工具
@tool
async def search_memory(query: str, user_id: str) -> str:
    """搜索用户的相关记忆信息。用于获取用户偏好、历史事件等上下文信息。

    Args:
        query: 搜索查询内容
        user_id: 用户ID

    Returns:
        相关记忆的文本内容
    """
    memory_client = nl_memory.client()
    results = await memory_client.search(query=query, user_id=user_id, top_k=5)

    if results["results"]:
        memories = [r["content"] for r in results["results"]]
        return "\n".join(memories)
    return "未找到相关记忆"


class ChatAgent:
    """基于 LangGraph 的对话 Agent，支持 middleware 和 skill 扩展"""

    def __init__(
        self,
        summarization_tokens: int = 4000,
        summarization_keep_msgs: int = 4,
        skills_dir: Optional[str] = None,
    ) -> None:
        """
        初始化 ChatAgent

        Args:
            summarization_tokens: 触发摘要的 token 数
            summarization_keep_msgs: 摘要时保留的消息数
            skills_dir: skills 目录路径（默认为项目根目录下的 skills/）
        """
        self.memory_client = nl_memory.client()

        # Agent 配置
        self.summarization_tokens = summarization_tokens
        self.summarization_keep_msgs = summarization_keep_msgs

        # Skill 加载器
        if skills_dir is None:
            # 默认使用项目根目录下的 skills/
            project_root = Path(__file__).parent.parent.parent
            skills_dir = str(project_root / "skills")

        self.skill_loader = SkillLoader(skills_dir, cache_size=10)

        # Skill 中间件（延迟初始化）
        self._skill_middleware = None

        # 注册的工具列表
        self.tools: list[BaseTool] = [search_memory]

        # 添加 Skill 相关工具
        self.tools.extend(self._create_skill_tools())

        # 打印注册的工具
        logger.info(f"📦 已注册工具: {[t.name for t in self.tools]}")
        for t in self.tools:
            logger.debug(
                f"  - {t.name}: {t.description[:100] if len(t.description) > 100 else t.description}"
            )

        # Agent 实例缓存 (按 model 缓存)
        self._agents: dict[str, Any] = {}
        self._checkpointer = MemorySaver()

        logger.info(
            f"ChatAgent 初始化完成 - "
            f"工具数: {len(self.tools)}, "
            f"可用技能: {len(self.skill_loader)}"
        )

    def _get_llm(self, model: str) -> ChatOpenAI:
        """获取 LLM 实例

        Args:
            model: 模型名称（对应 config.yaml 中的 llm.name）
        """
        llm_config = config.get_llm(model)
        if not llm_config:
            raise ValueError(f"未找到 LLM 配置: {model}")

        # 确保 model 参数有效
        if not llm_config.model:
            raise ValueError(f"LLM 配置缺少 model 字段: {model}")

        # 构建参数，确保类型安全
        chat_kwargs = {
            "model": llm_config.model,
            "base_url": llm_config.base_url,
            "temperature": 0.7,
            "extra_body": {"enable_thinking": False},
        }

        # api_key 可选
        if llm_config.api_key:
            chat_kwargs["api_key"] = SecretStr(llm_config.api_key)

        return ChatOpenAI(**chat_kwargs)

    def _create_agent(self, model: str) -> Any:
        """创建或获取 Agent 实例

        Args:
            model: 模型名称

        Returns:
            CompiledStateGraph 实例
        """
        if model in self._agents:
            return self._agents[model]

        # 创建 LLM
        llm = self._get_llm(model)

        # 创建摘要中间件
        summarization_middleware = SummarizationMiddleware(
            summary_model=llm,
            trigger_tokens=self.summarization_tokens,
            keep_messages=self.summarization_keep_msgs,
        )

        emotion_speculate_middleware = EmotionSpeculateMiddleware()

        # 创建 Skill 中间件（延迟初始化）
        if self._skill_middleware is None:
            from .middlewares.skill_middleware import SkillMiddleware

            self._skill_middleware = SkillMiddleware(self.skill_loader)

        # 创建 Agent
        agent = create_agent(
            model=llm,
            tools=self.tools,
            system_prompt="你是一个友善、自然的对话伙伴。在与用户交流时，像一个贴心的朋友一样自然地运用你对用户的了解。不要刻意提及'记忆'、'数据库'或'之前提到过'等术语，就像普通人聊天一样随意自然。用简洁、真诚的方式回应。",
            middleware=[
                summarization_middleware,
                emotion_speculate_middleware,
                self._skill_middleware,  # 注入技能列表
            ],
            state_schema=ChatAgentState,  # 自定义 state schema，包含 session_id
            checkpointer=self._checkpointer,
        )

        # 缓存 agent
        self._agents[model] = agent
        logger.info(f"已创建 Agent - 模型: {model}, 工具数: {len(self.tools)}")

        return agent

    def _create_skill_tools(self) -> list[BaseTool]:
        """创建 Skill 相关工具"""

        @tool
        def list_skills() -> str:
            """列出所有可用的技能。

            返回技能列表，包括名称、描述、标签和是否包含工具。
            使用 load_skill 加载技能指导，使用 invoke_skill_tool 调用技能工具。
            """
            skills = self.skill_loader.list_skills()

            if not skills:
                return "当前没有可用的技能"

            result_lines = ["可用技能列表：\n"]
            for skill in skills:
                tags_str = ", ".join(skill.get("tags", []))
                has_tools = "✓ 包含工具" if skill.get("has_tools") else "仅指导"
                result_lines.append(
                    f"- **{skill['name']}**: {skill['description']}\n"
                    f"  版本: {skill.get('version', 'N/A')} | 标签: {tags_str}\n"
                    f"  类型: {has_tools}"
                )

            result_lines.append(
                "\n使用方式:\n"
                "- load_skill: 加载技能指导内容\n"
                "- invoke_skill_tool: 调用技能工具"
            )

            return "\n".join(result_lines)

        @tool
        def load_skill(skill_name: str) -> str:
            """加载指定技能的详细指导内容。

            当你需要专业能力处理特定类型的问题时，使用此工具加载技能指导。
            技能内容包括详细的专业指导和最佳实践。

            Args:
                skill_name: 技能名称（如 "sql_expert", "calculator"）

            Returns:
                技能的详细指导内容
            """
            content = self.skill_loader.load_skill(skill_name)

            if content is None:
                available = [s["name"] for s in self.skill_loader.list_skills()]
                return (
                    f"未找到技能 '{skill_name}'。\n" f"可用技能: {', '.join(available)}"
                )

            return f"已加载技能: {skill_name}\n\n{content}"

        @tool
        async def invoke_skill_tool(
            skill_name: str, tool_name: str, parameters: str
        ) -> str:
            """调用技能中的工具。

            当需要执行具体操作时，使用此工具调用技能提供的可执行工具。

            Args:
                skill_name: 技能名称（如 "calculator", "web_scraper"）
                tool_name: 工具名称（如 "calculate", "fetch_webpage"）
                parameters: 工具参数的 JSON 字符串（如 '{"expression": "1+3"}'）

            Returns:
                工具执行结果

            Example:
                invoke_skill_tool(
                    skill_name="calculator",
                    tool_name="calculate",
                    parameters='{"expression": "1+3"}'
                )
            """
            logger.info(
                f"🔧 调用技能工具: {skill_name}.{tool_name}, 参数: {parameters}"
            )

            # 解析参数 JSON
            try:
                kwargs = json.loads(parameters) if parameters else {}
            except json.JSONDecodeError as e:
                logger.error(f"参数 JSON 解析失败: {e}")
                return f"参数格式错误，必须是有效的 JSON 字符串: {str(e)}"

            # 加载技能工具
            tools = self.skill_loader.load_skill_tools(skill_name)

            if not tools:
                # 检查技能是否存在
                if skill_name not in self.skill_loader:
                    available = [s["name"] for s in self.skill_loader.list_skills()]
                    logger.warning(f"技能 '{skill_name}' 不存在")
                    return (
                        f"技能 '{skill_name}' 不存在。可用技能: {', '.join(available)}"
                    )

                logger.warning(f"技能 '{skill_name}' 不包含可执行工具")
                return f"技能 '{skill_name}' 不包含可执行工具"

            # 查找指定工具
            target_tool = None
            for t in tools:
                if t.name == tool_name:
                    target_tool = t
                    break

            if not target_tool:
                available_tools = [t.name for t in tools]
                logger.warning(f"工具 '{tool_name}' 不存在于技能 '{skill_name}' 中")
                return (
                    f"工具 '{tool_name}' 不存在于技能 '{skill_name}' 中。\n"
                    f"可用工具: {', '.join(available_tools)}"
                )

            # 执行工具
            try:
                logger.info(f"⚙️ 开始执行工具: {target_tool.name}, 参数: {kwargs}")
                # 使用 ainvoke 支持异步工具
                result = await target_tool.ainvoke(kwargs)

                # 确保 result 是字符串
                if isinstance(result, str):
                    result_str = result
                else:
                    result_str = str(result)

                # 打印日志
                preview = result_str[:100] if len(result_str) > 100 else result_str
                logger.info(f"✅ 工具执行成功: {preview}")

                return f"执行结果:\n{result_str}"
            except Exception as e:
                logger.error(f"❌ 工具执行失败: {str(e)}", exc_info=True)
                return f"执行失败: {str(e)}"

        return [list_skills, load_skill, invoke_skill_tool]

    async def chat_stream(
        self,
        model: str,
        session_id: str,
        question: str,
    ) -> AsyncGenerator[str, None]:
        """使用 Agent 进行流式对话

        Args:
            model: 模型名称
            session_id: 会话ID
            question: 用户问题

        Yields:
            OpenAI 格式的 SSE 流式数据
        """
        start_time = time.perf_counter()

        # 1. 自动搜索相关记忆（按 session_id 搜索）
        memory_start = time.perf_counter()
        memory_results = await self.memory_client.search(
            query=question, user_id=session_id, top_k=5
        )
        memory_time = time.perf_counter() - memory_start

        memory_context = ""
        if memory_results["results"]:
            memory_context = "\n".join(
                [f"- {r['content']}" for r in memory_results["results"][:5]]
            )

        # 美化打印搜索结果
        logger.info(f"{'='*60}")
        logger.info(
            f"📝 记忆搜索结果 (耗时: {memory_time:.3f}s, 结果数: {memory_results['total']})"
        )
        logger.info(f"{'='*60}")
        if memory_results["results"]:
            for i, r in enumerate(memory_results["results"], 1):
                score = r.get("score", 0)
                content = r.get("content", "")
                logger.info(
                    f"  [{i}] (相似度: {score:.4f}) {content[:100]}{'...' if len(content) > 100 else ''}"
                )
        else:
            logger.info("  (无结果)")
        logger.info(f"{'='*60}")

        # 2. 创建或获取 Agent
        agent = self._create_agent(model)

        # 3. 构建输入消息
        messages: list[BaseMessage] = []

        # 添加记忆上下文（用更自然的格式）
        if memory_context:
            messages.append(
                SystemMessage(content=f"关于这个用户，你知道：\n{memory_context}")
            )

        # 添加用户问题
        messages.append(HumanMessage(content=question))

        # 打印最终给模型的 prompt
        logger.info(f"{'='*60}")
        logger.info(f"🤖 最终 Prompt (模型: {model})")
        logger.info(f"{'='*60}")
        for msg in messages:
            role = msg.type.upper()
            content = msg.content
            # 处理 content 可能是字符串或列表的情况
            if isinstance(content, list):
                content = json.dumps(content, ensure_ascii=False)
            # 截断过长的内容
            if len(content) > 500:
                content = content[:500] + "...(已截断)"
            logger.info(f"  [{role}]\n  {content}\n")
        logger.info(f"{'='*60}")

        # 4. 执行 Agent 流式
        config_dict = {
            "configurable": {
                "thread_id": session_id,  # 使用 session_id 作为 thread_id
            },
            "extra_body": {"enable_thinking": False},
        }

        # 生成唯一的 completion ID
        completion_id = f"chatcmpl-{uuid.uuid4().hex[:24]}"
        created_timestamp = int(time.time())

        # 收集完整响应用于保存历史
        full_response_content = ""

        # 使用 astream_events 进行流式输出
        # 在输入中添加 session_id，以便 middleware 可以访问
        async for event in agent.astream_events(
            {"messages": messages, "session_id": session_id},
            config=config_dict,
            version="v2",
        ):
            kind = event.get("event")

            # 处理聊天模型流式输出
            if kind == "on_chat_model_stream":
                content = event.get("data", {}).get("chunk", {})

                # 提取内容
                if hasattr(content, "content"):
                    chunk_content = content.content
                elif isinstance(content, dict):
                    chunk_content = content.get("content", "")
                else:
                    chunk_content = str(content)

                if chunk_content:
                    full_response_content += chunk_content

                    # 构建 OpenAI 格式的流式响应
                    chunk_data = {
                        "id": completion_id,
                        "object": "chat.completion.chunk",
                        "created": created_timestamp,
                        "model": model,
                        "choices": [
                            {
                                "index": 0,
                                "delta": {"content": chunk_content},
                                "finish_reason": None,
                            }
                        ],
                    }

                    # 返回 SSE 格式的数据
                    yield f"data: {json.dumps(chunk_data, ensure_ascii=False)}\n\n"

        # 发送结束标记
        finish_chunk = {
            "id": completion_id,
            "object": "chat.completion.chunk",
            "created": created_timestamp,
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "delta": {},
                    "finish_reason": "stop",
                }
            ],
        }
        yield f"data: {json.dumps(finish_chunk, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

        # 5. 异步保存记忆（fire-and-forget，不阻塞主流程）
        if full_response_content:
            asyncio.create_task(
                self._save_memory_async(
                    question=question,
                    response=full_response_content,
                    session_id=session_id,
                )
            )

        elapsed_time = time.perf_counter() - start_time
        logger.info(f"对话完成 - 总耗时: {elapsed_time:.3f}s")

    async def _save_memory_async(
        self,
        question: str,
        response: str,
        session_id: str,
    ) -> None:
        """异步保存记忆（后台任务）

        Args:
            question: 用户问题
            response: 模型回复
            session_id: 会话ID
        """
        try:
            logger.info(f"开始异步保存记忆 - session: {session_id}")

            # 获取 memory client
            memory_client = nl_memory.client()

            # 构建对话消息
            messages = [
                {"role": "user", "content": question},
                {"role": "assistant", "content": response},
            ]

            # 添加记忆（使用 LLM 提取关键信息）
            result = await memory_client.add(
                messages=messages,
                user_id=session_id,
                session_id=session_id,
                infer=True,  # 使用 LLM 提取记忆
                auto_detect_conflict=True,
                flush_after=False,  # 不强制 flush，提高性能
            )

            memories_extracted = result.get("memories_extracted", 0)
            memories_added = result.get("memories_added", 0)
            conflicts = result.get("conflicts_detected", [])

            logger.info(
                f"记忆保存完成 - 提取: {memories_extracted}, "
                f"存储: {memories_added}, 冲突处理: {len(conflicts)}, session: {session_id}"
            )

            if conflicts:
                for conflict in conflicts:
                    logger.debug(f"检测到冲突: {conflict}")

        except Exception as e:
            # 记忆保存失败不应影响主流程，只记录错误
            logger.error(f"记忆保存失败: {e}", exc_info=True)

    def clear_history(self, session_id: str) -> None:
        """清空指定会话的历史

        Args:
            session_id: 会话ID
        """
        # MemorySaver 没有直接的清空方法，需要通过重新创建 checkpointer
        self._checkpointer = MemorySaver()
        self._agents.clear()
        logger.info(f"会话历史已清空 - session_id: {session_id}")
