from core.logger import setup_logger
from core.memory import nl_memory
from core.config import config
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_core.tools import BaseTool
from langchain_openai import ChatOpenAI
from langchain.agents import create_agent
from langchain.agents.middleware.types import AgentState
from langgraph.checkpoint.memory import MemorySaver

from pydantic import SecretStr
from typing import Any, AsyncGenerator, Optional
from pathlib import Path

from core.nl_chat.middlewares.emotion_speculate import EmotionSpeculateMiddleware
from core.nl_chat.middlewares.chat_topic import ChatTopicMiddleware
from core.nl_chat.prompt_mgr import get_session_prompt
from core.nl_chat.tools.memory_search import search_memory
from core.nl_chat.tools.read_file import read_file
from core.nl_chat.tools.system_tools import get_all_system_tools
from core.nl_chat.tools.skills_tool import create_skills_tool
from .middlewares import SummarizationMiddleware, DebugPromptMiddleware
import asyncio
import time
import json
import uuid

logger = setup_logger(__name__)

# ---------------------------------------------------------------------------
# Windows UTF-8 兼容补丁
# langchain-skills-adapters 0.1.x 的 SkillsLoader 使用 Path.read_text()
# 未指定 encoding，在 Windows 上默认使用 GBK 导致中文 SKILL.md 读取失败。
# 通过 monkey-patch 将默认编码改为 UTF-8。
# ---------------------------------------------------------------------------
_orig_path_read_text = Path.read_text


def _utf8_default_read_text(self, encoding="utf-8", errors=None, newline=None):
    return _orig_path_read_text(self, encoding=encoding, errors=errors, newline=newline)


Path.read_text = _utf8_default_read_text  # type: ignore[assignment]


class ChatAgentState(AgentState):
    """自定义 Agent State，扩展 session_id 字段供中间件使用"""

    session_id: str


class ChatAgent:
    """基于 LangGraph 的对话 Agent，使用 langchain-skills-adapters 管理技能

    技能加载使用 SkillsTool（activate_skill 工具）实现渐进式披露：
    1. 层级1（目录）：SkillsTool 的 description 包含 <available_skills> XML，模型通过工具列表即可看到
    2. 层级2（完整指令）：模型调用 activate_skill(name="xxx") 获取完整 SKILL.md 内容
    3. 层级3（资源文件）：模型按需读取 references/、scripts/ 等目录中的文件
    """

    def __init__(
        self,
        summarization_tokens: int = 8000,
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

        # Skills 目录
        if skills_dir is None:
            project_root = Path(__file__).parent.parent.parent
            skills_dir = str(project_root / "skills")
        self.skills_dir = skills_dir

        # 创建技能工具（SkillsTool）
        # 技能目录自动嵌入到工具的 description 中，模型调用 activate_skill 获取完整指令
        self._skills_tool = create_skills_tool(skills_dir)

        # 系统工具（文件管理 + Shell）
        system_tools = get_all_system_tools()

        # 注册的工具列表（包含 activate_skill）
        self.tools: list[BaseTool] = [
            search_memory,
            read_file,
            self._skills_tool,
        ] + system_tools

        # 打印注册的工具
        logger.info(f"📦 已注册工具: {[t.name for t in self.tools]}")
        for t in self.tools:
            desc = t.description[:100] if len(t.description) > 100 else t.description
            logger.debug(f"  - {t.name}: {desc}")

        # Agent 实例缓存 (按 model 缓存)
        self._agents: dict[str, Any] = {}
        self._checkpointer = MemorySaver()

        logger.info(
            f"ChatAgent 初始化完成 - "
            f"工具数: {len(self.tools)}, "
            f"技能目录: {skills_dir}"
        )

    def _get_llm(self, model: str) -> ChatOpenAI:
        """获取 LLM 实例

        Args:
            model: 模型名称（对应 config.yaml 中的 llm.name）
        """
        llm_config = config.get_llm(model)
        if not llm_config:
            raise ValueError(f"未找到 LLM 配置: {model}")

        if not llm_config.model:
            raise ValueError(f"LLM 配置缺少 model 字段: {model}")

        chat_kwargs = {
            "model": llm_config.model,
            "base_url": llm_config.base_url,
            "temperature": 0.7,
            "extra_body": {"enable_thinking": False},
        }

        if llm_config.api_key:
            chat_kwargs["api_key"] = SecretStr(llm_config.api_key)

        return ChatOpenAI(**chat_kwargs)

    def _create_agent(self, model: str, session_id: str) -> Any:
        """创建或获取 Agent 实例

        Args:
            model: 模型名称
            session_id: 会话ID

        Returns:
            CompiledStateGraph 实例
        """
        if model in self._agents:
            return self._agents[model]

        llm = self._get_llm(model)

        summarization_middleware = SummarizationMiddleware(
            summary_model=llm,
            trigger_tokens=self.summarization_tokens,
            keep_messages=self.summarization_keep_msgs,
        )

        emotion_speculate_middleware = EmotionSpeculateMiddleware()

        chat_topic_middleware = ChatTopicMiddleware()

        agent = create_agent(
            model=llm,
            tools=self.tools,
            system_prompt=get_session_prompt(session_id),
            middleware=[
                summarization_middleware,
                emotion_speculate_middleware,
                chat_topic_middleware,
                DebugPromptMiddleware(),
            ],
            state_schema=ChatAgentState,
            checkpointer=self._checkpointer,
        )

        self._agents[model] = agent
        logger.info(f"已创建 Agent - 模型: {model}, 工具数: {len(self.tools)}")

        return agent

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

        # 1. 自动搜索相关记忆
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
        agent = self._create_agent(model, session_id)

        # 3. 构建输入消息
        messages: list[BaseMessage] = []

        if memory_context:
            messages.append(
                SystemMessage(content=f"关于这个用户，你知道：\n{memory_context}")
            )

        messages.append(HumanMessage(content=question))

        # 打印最终给模型的 prompt
        logger.info(f"{'='*60}")
        logger.info(f"🤖 最终 Prompt (模型: {model})")
        logger.info(f"{'='*60}")
        for msg in messages:
            role = msg.type.upper()
            content = msg.content
            if isinstance(content, list):
                content = json.dumps(content, ensure_ascii=False)
            if len(content) > 500:
                content = content[:500] + "...(已截断)"
            logger.info(f"  [{role}]\n  {content}\n")
        logger.info(f"{'='*60}")

        # 4. 执行 Agent 流式
        config_dict = {
            "configurable": {
                "thread_id": session_id,
            },
            "recursion_limit": 40,
            "extra_body": {"enable_thinking": False},
        }

        completion_id = f"chatcmpl-{uuid.uuid4().hex[:24]}"
        created_timestamp = int(time.time())

        full_response_content = ""
        # 追踪本轮对话使用的技能
        used_skills: set[str] = set()
        # ANSI 高亮颜色
        _CYAN = "\033[96m"
        _YELLOW = "\033[93m"
        _BOLD = "\033[1m"
        _RESET = "\033[0m"

        async for event in agent.astream_events(
            {"messages": messages, "session_id": session_id},
            config=config_dict,
            version="v2",
        ):
            kind = event.get("event")

            # 检测工具调用 → 识别 Skill 使用
            if kind == "on_tool_start":
                tool_name = event.get("name", "")
                tool_input = event.get("data", {}).get("input", {})
                if tool_name == "activate_skill":
                    skill_name = (
                        tool_input.get("name", "")
                        if isinstance(tool_input, dict)
                        else ""
                    )
                    if skill_name and skill_name not in used_skills:
                        used_skills.add(skill_name)
                        logger.info(f"{_CYAN}{_BOLD}🎯 使用技能: {skill_name}{_RESET}")

            if kind == "on_chat_model_stream":
                content = event.get("data", {}).get("chunk", {})

                if hasattr(content, "content"):
                    chunk_content = content.content
                elif isinstance(content, dict):
                    chunk_content = content.get("content", "")
                else:
                    chunk_content = str(content)

                if chunk_content:
                    full_response_content += chunk_content

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

        # 5. 异步保存记忆
        if full_response_content:
            asyncio.create_task(
                self._save_memory_async(
                    question=question,
                    response=full_response_content,
                    session_id=session_id,
                )
            )

        elapsed_time = time.perf_counter() - start_time
        if used_skills:
            logger.info(
                f"{_YELLOW}{_BOLD}🎯 本轮使用技能: {', '.join(used_skills)}{_RESET}"
            )
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

            memory_client = nl_memory.client()

            messages = [
                {"role": "user", "content": question},
                {"role": "assistant", "content": response},
            ]

            result = await memory_client.add(
                messages=messages,
                user_id=session_id,
                session_id=session_id,
                infer=True,
                auto_detect_conflict=True,
                flush_after=False,
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
            logger.error(f"记忆保存失败: {e}", exc_info=True)

    def clear_history(self, session_id: str) -> None:
        """清空指定会话的历史

        Args:
            session_id: 会话ID
        """
        self._checkpointer = MemorySaver()
        self._agents.clear()
        logger.info(f"会话历史已清空 - session_id: {session_id}")
