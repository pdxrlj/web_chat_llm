from email import message
from core.logger import setup_logger
from core.memory import nl_memory
from core.config import config
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_core.tools import BaseTool
from langchain_openai import ChatOpenAI
from langchain.agents import create_agent
from langchain.agents.middleware.types import AgentState
from langgraph.checkpoint.memory import MemorySaver
from langgraph.errors import GraphRecursionError

from pydantic import SecretStr
from typing import Any, AsyncGenerator, NotRequired, Optional
from pathlib import Path

from core.nl_chat.middlewares.change_role import ChangeRoleMiddleware
from core.nl_chat.middlewares.emotion_speculate import EmotionSpeculateMiddleware
from core.nl_chat.middlewares.chat_history_saver import ChatHistorySaverMiddleware
from core.nl_chat.middlewares.chat_topic import ChatTopicMiddleware
from core.nl_chat.prompt_mgr import get_session_prompt, reset_session_prompt
from core.nl_chat.tools.memory_search import search_memory
from core.nl_chat.tools.read_file import read_file
from core.nl_chat.tools.system_tools import get_all_system_tools
from core.nl_chat.tools.skills_tool import create_skills_tool
from .middlewares import SummarizationMiddleware, DebugPromptMiddleware
import asyncio
import json
import time
import uuid
from datetime import datetime

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


# 技能提示映射
_SKILL_HINTS: dict[str, str] = {
    "web-search": "🔍 正在搜索互联网...\n",
    "web-scraper": "🌐 正在抓取网页内容...\n",
    "calculator": "🧮 正在计算...\n",
    "file-manager": "📁 正在处理文件...\n",
}


def _skill_hint(skill_name: str) -> str:
    """根据技能名返回即时提示文本。"""
    return _SKILL_HINTS.get(skill_name, "🎯 正在使用技能，请稍等...\n")


class ChatAgentState(AgentState):
    """自定义 Agent State，扩展字段供中间件使用"""

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

    def _create_agent(self, model: str) -> Any:
        """创建或获取 Agent 实例

        Args:
            model: 模型名称

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

        chat_history_saver_middleware = ChatHistorySaverMiddleware()

        chat_topic_middleware = ChatTopicMiddleware()

        change_role_middleware = ChangeRoleMiddleware()

        agent = create_agent(
            model=llm,
            tools=self.tools,
            system_prompt="",
            middleware=[
                summarization_middleware,
                emotion_speculate_middleware,
                chat_history_saver_middleware,
                chat_topic_middleware,
                DebugPromptMiddleware(),
                change_role_middleware,
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
        memory_context = ""
        try:
            memory_start = time.perf_counter()
            memory_results = await self.memory_client.search(
                query=question, user_id=session_id, top_k=5
            )
            memory_time = time.perf_counter() - memory_start

            search_results = memory_results.get("results", [])
            if search_results:
                memory_context = "\n".join(
                    [f"- {r['content']}" for r in search_results[:5]]
                )

            logger.info(f"{'='*60}")
            logger.info(
                f"📝 记忆搜索结果 (耗时: {memory_time:.3f}s, 结果数: {memory_results.get('total', 0)})"
            )
            logger.info(f"{'='*60}")
            if search_results:
                for i, r in enumerate(search_results, 1):
                    score = r.get("score", 0)
                    content = r.get("content", "")
                    logger.info(
                        f"  [{i}] (相似度: {score:.4f}) {content[:100]}{'...' if len(content) > 100 else ''}"
                    )
            else:
                logger.info("  (无结果)")
            logger.info(f"{'='*60}")
        except Exception as e:
            logger.error(f"记忆搜索失败，将跳过记忆上下文: {e}")

        # 2. 创建或获取 Agent
        agent = self._create_agent(model)

        # 3. 构建输入消息
        messages: list[BaseMessage] = []

        # 动态注入当前 session 的 system prompt
        # create_agent 的 system_prompt 设为空串，由这里统一注入以支持角色切换后 prompt 更新
        session_prompt = get_session_prompt(session_id)
        if session_prompt:
            messages.append(SystemMessage(content=session_prompt))

        # 注入当前时间信息
        now = datetime.now()
        time_info = f"当前时间: {now.strftime('%Y年%m月%d日 %H时%M分%S秒')} (星期{'一二三四五六日'[now.weekday()]})"
        messages.append(SystemMessage(content=time_info))
        messages.append(
            SystemMessage(
                content="不要输出任何markdown格式的内容,只输出普通文本,不能包含任何特殊字符"
            )
        )

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

        try:
            async for event in agent.astream_events(
                {"messages": messages, "session_id": session_id},
                config=config_dict,
                version="v2",
            ):
                kind = event.get("event")

                # 检测工具调用 → 识别 Skill 使用，并即时推送提示
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
                            # 即时推送"正在处理"提示
                            hint = _skill_hint(skill_name)
                            if hint:
                                hint_chunk = {
                                    "id": completion_id,
                                    "object": "chat.completion.chunk",
                                    "created": created_timestamp,
                                    "model": model,
                                    "choices": [
                                        {
                                            "index": 0,
                                            "delta": {"content": hint},
                                            "finish_reason": None,
                                        }
                                    ],
                                }
                                yield f"data: {json.dumps(hint_chunk, ensure_ascii=False)}\n\n"
                                full_response_content += hint
                    elif tool_name == "shell_execute":
                        # shell 工具调用时推送处理提示
                        hint_chunk = {
                            "id": completion_id,
                            "object": "chat.completion.chunk",
                            "created": created_timestamp,
                            "model": model,
                            "choices": [
                                {
                                    "index": 0,
                                    "delta": {"content": "⏳ 正在执行...\n"},
                                    "finish_reason": None,
                                }
                            ],
                        }
                        yield f"data: {json.dumps(hint_chunk, ensure_ascii=False)}\n\n"
                        full_response_content += "⏳ 正在执行...\n"

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
        except GraphRecursionError:
            logger.warning(f"Agent 递归次数超限 (session: {session_id})，返回已有内容")
            # 推送提示消息
            fallback_msg = "\n抱歉，处理过程过于复杂，我暂时无法完成这个请求，请简化问题后重试。"
            fallback_chunk = {
                "id": completion_id,
                "object": "chat.completion.chunk",
                "created": created_timestamp,
                "model": model,
                "choices": [
                    {
                        "index": 0,
                        "delta": {"content": fallback_msg},
                        "finish_reason": None,
                    }
                ],
            }
            yield f"data: {json.dumps(fallback_chunk, ensure_ascii=False)}\n\n"
            full_response_content += fallback_msg

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

            messages = [
                {"role": "user", "content": question},
                {"role": "assistant", "content": response},
            ]

            result = await self.memory_client.add(
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
        # 只清空指定 session 的 checkpointer，不影响其他会话
        reset_session_prompt(session_id)
        try:
            self._checkpointer.delete_thread(session_id)
        except (AttributeError, NotImplementedError):
            # MemorySaver 可能不支持 delete_thread，则重建 checkpointer
            # 旧 agent 持有已失效的 checkpointer 引用，必须一并清空
            logger.warning(
                f"MemorySaver 不支持按 session 删除，将重建 checkpointer（影响所有会话）- session_id: {session_id}"
            )
            self._checkpointer = MemorySaver()
            self._agents.clear()
        logger.info(f"会话历史已清空 - session_id: {session_id}")
