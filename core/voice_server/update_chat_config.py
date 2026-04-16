"""
火山语音聊天 UpdateVoiceChat 接口。

在对话进行中的任何时刻发送实时任务指令或更新任务配置。
"""

import json
from typing import Any

from core.logger import setup_logger
from core.voice_server.voice_api import (
    _get_http_session,
    _resolve_scene,
    _send_voice_request,
)

logger = setup_logger("update_chat_config")


# ── UpdateVoiceChat 支持的命令 ───────────────────────────────────────


class UpdateVoiceChatCommands:
    """UpdateVoiceChat 支持的命令常量。"""

    INTERRUPT = "interrupt"  # 打断 AI 说话
    FUNCTION = "function"  # 回传工具执行结果
    EXTERNAL_TTS = "ExternalTextToSpeech"  # 自定义语音播放
    EXTERNAL_PROMPTS = "ExternalPromptsForLLM"  # 动态传入上下文
    EXTERNAL_TEXT_TO_LLM = "ExternalTextToLLM"  # 文本提问
    FINISH_SPEECH = "FinishSpeechRecognition"  # 触发新一轮对话
    UPDATE_PARAMS = "UpdateParameters"  # 更新配置
    SET_TTS_CONTEXT = "SetTTSContext"  # 设置 TTS 指令标签
    UPDATE_VOICE_PRINT_SV = "UpdateVoicePrintSV"  # 更新声纹降噪配置
    UPDATE_FARFIELD_CONFIG = "UpdateFarfieldConfig"  # 更新远场人声抑制配置


class InterruptMode:
    """interrupt 命令的 InterruptMode 取值。"""

    ENABLE_VOICE_INTERRUPT = 0  # 开启语音打断（发声即打断）
    DISABLE_VOICE_INTERRUPT = 1  # 关闭语音打断


class PriorityMode:
    """ExternalTextToSpeech / ExternalTextToLLM 命令的 InterruptMode（优先级）取值。"""

    HIGH = 1  # 高优先级：强制终止 AI 当前交互，立即执行
    MEDIUM = 2  # 中优先级：等待 AI 完成当前交互后再执行
    LOW = 3  # 低优先级：AI 交互中则丢弃本次指令


# ── UpdateVoiceChat 代理接口 ────────────────────────────────────────


def _build_update_voice_chat_body(
    request_body: dict[str, Any],
    session_id: str | None,
    runtime: dict[str, Any],
) -> dict[str, Any]:
    """构建 UpdateVoiceChat 请求体，根据 Command 类型填充不同字段。"""
    # 从请求或运行时状态获取必要参数
    app_id = request_body.get("AppId") or runtime.get("app_id")
    room_id = request_body.get("RoomId") or runtime.get("room_id")
    task_id = request_body.get("TaskId") or runtime.get("task_id")

    if not app_id:
        raise ValueError("AppId 不能为空，请先调用 StartVoiceChat")
    if not room_id:
        raise ValueError("RoomId 不能为空")
    if not task_id:
        raise ValueError("TaskId 不能为空，请先调用 StartVoiceChat")

    # 构建基础请求体
    body: dict[str, Any] = {
        "AppId": app_id,
        "RoomId": room_id,
        "TaskId": task_id,
    }

    # 获取命令类型
    command = request_body.get("Command")
    if not command:
        raise ValueError("Command 不能为空")

    body["Command"] = command

    # 根据不同命令处理请求体
    if command == UpdateVoiceChatCommands.INTERRUPT:
        # 打断 AI 说话，只需要基础参数
        # 可选：InterruptMode，0=开启语音打断，1=关闭
        interrupt_mode = request_body.get("InterruptMode")
        if interrupt_mode is not None:
            body["InterruptMode"] = interrupt_mode

    elif command == UpdateVoiceChatCommands.FUNCTION:
        # 回传工具执行结果
        message = request_body.get("Message")
        if not message:
            raise ValueError("Function 命令需要 Message 字段")
        body["Message"] = message

    elif command == UpdateVoiceChatCommands.EXTERNAL_TTS:
        # 自定义语音播放
        message = request_body.get("Message")
        if not message:
            raise ValueError("ExternalTextToSpeech 命令需要 Message 字段")
        body["Message"] = message
        # 必填：InterruptMode（优先级），1=高优先级，2=中优先级，3=低优先级
        interrupt_mode = request_body.get("InterruptMode")
        if interrupt_mode is None:
            raise ValueError(
                "ExternalTextToSpeech 命令需要 InterruptMode 字段"
                "（1=高优先级，2=中优先级，3=低优先级）"
            )
        body["InterruptMode"] = interrupt_mode

    elif command == UpdateVoiceChatCommands.EXTERNAL_PROMPTS:
        # 动态传入上下文
        message = request_body.get("Message")
        if not message:
            raise ValueError("ExternalPromptsForLLM 命令需要 Message 字段")
        body["Message"] = message

    elif command == UpdateVoiceChatCommands.EXTERNAL_TEXT_TO_LLM:
        # 文本提问（可同时传图片）
        message = request_body.get("Message")
        body["Message"] = message  # 可选（图片理解时可省略）
        # 必填：InterruptMode（优先级），1=高优先级，2=中优先级，3=低优先级
        interrupt_mode = request_body.get("InterruptMode")
        if interrupt_mode is None:
            raise ValueError(
                "ExternalTextToLLM 命令需要 InterruptMode 字段"
                "（1=高优先级，2=中优先级，3=低优先级）"
            )
        body["InterruptMode"] = interrupt_mode
        # 处理图片配置
        image_config = request_body.get("ImageConfig")
        if image_config:
            body["ImageConfig"] = image_config

    elif command == UpdateVoiceChatCommands.FINISH_SPEECH:
        # 强制结束当前对话，触发新一轮对话
        # 只需要基础参数
        pass

    elif command == UpdateVoiceChatCommands.UPDATE_PARAMS:
        # 更新任务配置
        parameters = request_body.get("Parameters")
        logger.info(f"[UpdateVoiceChat] 更新任务配置: {parameters}")

        if not parameters:
            raise ValueError("UpdateParameters 命令需要 Parameters 字段")
        body["Parameters"] = parameters

    elif command == UpdateVoiceChatCommands.SET_TTS_CONTEXT:
        # 设置 TTS 指令标签
        message = request_body.get("Message")
        if not message:
            raise ValueError("SetTTSContext 命令需要 Message 字段")
        body["Message"] = message

    elif command == UpdateVoiceChatCommands.UPDATE_VOICE_PRINT_SV:
        # 更新声纹降噪配置
        # 仅在 StartVoiceChat 中 VoicePrint.Mode 为 0 且 VoicePrint.IdList 为空时生效
        message = request_body.get("Message")
        if not message:
            raise ValueError("UpdateVoicePrintSV 命令需要 Message 字段")
        body["Message"] = message

    elif command == UpdateVoiceChatCommands.UPDATE_FARFIELD_CONFIG:
        # 更新远场人声抑制配置
        # 仅在使用火山语音识别大模型或火山声音复刻大模型时生效
        message = request_body.get("Message")
        if not message:
            raise ValueError("UpdateFarfieldConfig 命令需要 Message 字段")
        body["Message"] = message

    else:
        raise ValueError(f"不支持的命令: {command}")

    logger.info(
        f"[UpdateVoiceChat] command={command}, "
        f"AppId={app_id}, RoomId={room_id}, TaskId={task_id}"
    )

    return body


async def update_voice_chat(
    scene_id: str,
    request_body: dict[str, Any],
    scenes_dir: str,
) -> dict[str, Any]:
    """
    代理火山 RTC UpdateVoiceChat 请求。

    复用 voice_api 的签名和发送基础设施，仅处理 UpdateVoiceChat 特有的请求体构建逻辑。

    支持以下指令：
    - interrupt：打断 AI 说话
    - function：回传工具执行结果（Function Calling）
    - ExternalTextToSpeech：自定义语音播放（InterruptMode 必填）
    - ExternalPromptsForLLM：动态传入上下文
    - ExternalTextToLLM：文本提问（InterruptMode 必填）
    - FinishSpeechRecognition：触发新一轮对话
    - UpdateParameters：更新任务配置
    - SetTTSContext：设置 TTS 指令标签
    - UpdateVoicePrintSV：更新声纹降噪配置
    - UpdateFarfieldConfig：更新远场人声抑制配置
    """
    _, account_config, _ = _resolve_scene(scenes_dir, scene_id)

    # 从 session_id 获取运行时状态
    session_id = request_body.get("SessionId")
    from core.voice_server import voice_api

    runtime = voice_api._runtime_state.get(session_id, {}) if session_id else {}

    logger.info(
        f"[UpdateVoiceChat] 使用账户配置:\n"
        f"  accessKeyId={account_config['accessKeyId']}\n"
        f"  请求的 AppId={request_body.get('AppId')}\n"
        f"  scene={scene_id}"
    )

    body = _build_update_voice_chat_body(request_body, session_id, runtime)
    result = await _send_voice_request("UpdateVoiceChat", "2024-12-01", body, account_config)

    logger.info(
        f"[UpdateVoiceChat] 请求完成: "
        f"command={body.get('Command')}, "
        f"结果={json.dumps(result, ensure_ascii=False)[:500]}"
    )

    return result


# ── 便捷封装函数 ────────────────────────────────────────────────────


async def interrupt_voice_chat(
    scene_id: str,
    app_id: str,
    room_id: str,
    task_id: str,
    scenes_dir: str,
    interrupt_mode: int | None = None,
) -> dict[str, Any]:
    """打断 AI 说话。"""
    body: dict[str, Any] = {
        "AppId": app_id,
        "RoomId": room_id,
        "TaskId": task_id,
        "Command": UpdateVoiceChatCommands.INTERRUPT,
    }
    if interrupt_mode is not None:
        body["InterruptMode"] = interrupt_mode
    return await update_voice_chat(scene_id, body, scenes_dir)


async def send_function_result(
    scene_id: str,
    app_id: str,
    room_id: str,
    task_id: str,
    message: dict[str, Any],
    scenes_dir: str,
) -> dict[str, Any]:
    """回传 Function Calling 的工具调用结果。"""
    body = {
        "AppId": app_id,
        "RoomId": room_id,
        "TaskId": task_id,
        "Command": UpdateVoiceChatCommands.FUNCTION,
        "Message": message,
    }
    return await update_voice_chat(scene_id, body, scenes_dir)


async def external_text_to_speech(
    scene_id: str,
    app_id: str,
    room_id: str,
    task_id: str,
    text: str,
    interrupt_mode: int,
    scenes_dir: str,
) -> dict[str, Any]:
    """让 AI 主动播报指定文本。

    Args:
        interrupt_mode: 优先级，1=高优先级（强制打断），2=中优先级（等当前交互完成），3=低优先级（交互中则丢弃）
    """
    body: dict[str, Any] = {
        "AppId": app_id,
        "RoomId": room_id,
        "TaskId": task_id,
        "Command": UpdateVoiceChatCommands.EXTERNAL_TTS,
        "Message": text,
        "InterruptMode": interrupt_mode,
    }
    return await update_voice_chat(scene_id, body, scenes_dir)


async def send_external_prompts(
    scene_id: str,
    app_id: str,
    room_id: str,
    task_id: str,
    message: str,
    scenes_dir: str,
) -> dict[str, Any]:
    """向 LLM 传入下一轮对话的背景信息（不立即回复）。"""
    body = {
        "AppId": app_id,
        "RoomId": room_id,
        "TaskId": task_id,
        "Command": UpdateVoiceChatCommands.EXTERNAL_PROMPTS,
        "Message": message,
    }
    return await update_voice_chat(scene_id, body, scenes_dir)


async def text_to_llm(
    scene_id: str,
    app_id: str,
    room_id: str,
    task_id: str,
    interrupt_mode: int,
    scenes_dir: str,
    text: str | None = None,
    image_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """通过文本直接向 AI 提问，或传入图片理解。

    Args:
        interrupt_mode: 优先级，1=高优先级（强制打断），2=中优先级（等当前交互完成），3=低优先级（交互中则丢弃）
        text: 文本问题（图片理解时可省略）
        image_config: 图片配置（可选）
    """
    body: dict[str, Any] = {
        "AppId": app_id,
        "RoomId": room_id,
        "TaskId": task_id,
        "Command": UpdateVoiceChatCommands.EXTERNAL_TEXT_TO_LLM,
        "InterruptMode": interrupt_mode,
    }
    if text is not None:
        body["Message"] = text
    if image_config:
        body["ImageConfig"] = image_config
    return await update_voice_chat(scene_id, body, scenes_dir)


async def finish_speech_and_restart(
    scene_id: str,
    app_id: str,
    room_id: str,
    task_id: str,
    scenes_dir: str,
) -> dict[str, Any]:
    """结束当前语音输入，触发新一轮对话。"""
    body = {
        "AppId": app_id,
        "RoomId": room_id,
        "TaskId": task_id,
        "Command": UpdateVoiceChatCommands.FINISH_SPEECH,
    }
    return await update_voice_chat(scene_id, body, scenes_dir)


async def update_parameters(
    scene_id: str,
    app_id: str,
    room_id: str,
    task_id: str,
    parameters: dict[str, Any],
    scenes_dir: str,
) -> dict[str, Any]:
    """更新任务配置（如 TTS、LLM 等）。"""
    body = {
        "AppId": app_id,
        "RoomId": room_id,
        "TaskId": task_id,
        "Command": UpdateVoiceChatCommands.UPDATE_PARAMS,
        "Parameters": parameters,
    }
    return await update_voice_chat(scene_id, body, scenes_dir)


async def set_tts_context(
    scene_id: str,
    app_id: str,
    room_id: str,
    task_id: str,
    message: str,
    scenes_dir: str,
) -> dict[str, Any]:
    """设置 TTS 指令标签，控制 AI 下一轮回复的语气、语速、音量等。"""
    body = {
        "AppId": app_id,
        "RoomId": room_id,
        "TaskId": task_id,
        "Command": UpdateVoiceChatCommands.SET_TTS_CONTEXT,
        "Message": message,
    }
    return await update_voice_chat(scene_id, body, scenes_dir)


async def update_voice_print_sv(
    scene_id: str,
    app_id: str,
    room_id: str,
    task_id: str,
    message: str,
    scenes_dir: str,
) -> dict[str, Any]:
    """更新声纹降噪配置。

    仅在 StartVoiceChat 中 VoicePrint.Mode 为 0 且 VoicePrint.IdList 为空时生效。

    Args:
        message: JSON 转义字符串，如 '{"Enable": true, "VoiceDuration": 10}'
    """
    body = {
        "AppId": app_id,
        "RoomId": room_id,
        "TaskId": task_id,
        "Command": UpdateVoiceChatCommands.UPDATE_VOICE_PRINT_SV,
        "Message": message,
    }
    return await update_voice_chat(scene_id, body, scenes_dir)


async def update_farfield_config(
    scene_id: str,
    app_id: str,
    room_id: str,
    task_id: str,
    message: str,
    scenes_dir: str,
) -> dict[str, Any]:
    """更新远场人声抑制配置。

    仅在使用火山语音识别大模型或火山声音复刻大模型时生效。

    Args:
        message: JSON 转义字符串，如 '{"Enable": true, "Level": "Medium", "Threshold": 0, "FixedSource": false}'
    """
    body = {
        "AppId": app_id,
        "RoomId": room_id,
        "TaskId": task_id,
        "Command": UpdateVoiceChatCommands.UPDATE_FARFIELD_CONFIG,
        "Message": message,
    }
    return await update_voice_chat(scene_id, body, scenes_dir)
