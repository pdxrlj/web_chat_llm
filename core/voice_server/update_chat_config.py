"""
火山语音聊天 UpdateVoiceChat 接口。

在对话进行中的任何时刻发送实时任务指令或更新任务配置。
"""

import hashlib
import hmac
import json
from datetime import datetime, timezone
from typing import Any

import aiohttp

from core.logger import setup_logger

logger = setup_logger("update_chat_config")

# 共享 HTTP Session（从 voice_api 共享）
_http_session: aiohttp.ClientSession | None = None


def _get_http_session() -> aiohttp.ClientSession | None:
    """获取共享 aiohttp ClientSession。"""
    global _http_session
    return _http_session


def _set_http_session(session: aiohttp.ClientSession | None) -> None:
    """设置共享 aiohttp ClientSession。"""
    global _http_session
    _http_session = session


# ── 火山 OpenAPI V4 签名（复制自 voice_api） ──────────────────────────


def _hmac_sha256(key: bytes, msg: bytes) -> bytes:
    return hmac.new(key, msg, hashlib.sha256).digest()


def _get_signature_key(
    secret_key: str, date_stamp: str, region: str, service: str
) -> bytes:
    k_date = _hmac_sha256(secret_key.encode("utf-8"), date_stamp.encode("utf-8"))
    k_region = _hmac_sha256(k_date, region.encode("utf-8"))
    k_service = _hmac_sha256(k_region, service.encode("utf-8"))
    k_signing = _hmac_sha256(k_service, b"request")
    return k_signing


def _sign_request(
    method: str,
    host: str,
    path: str,
    query: str,
    headers: dict[str, str],
    body: bytes,
    access_key_id: str,
    secret_key: str,
    region: str = "cn-north-1",
    service: str = "rtc",
) -> dict[str, str]:
    """为火山 OpenAPI 请求计算 V4 签名并返回带签名的 headers。"""
    now = datetime.now(timezone.utc)
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    date_stamp = now.strftime("%Y%m%d")

    signed_headers_list = ["content-type", "host", "x-content-sha256", "x-date"]
    payload_hash = hashlib.sha256(body).hexdigest()

    canonical_headers = (
        f"content-type:{headers.get('content-type', 'application/json')}\n"
        f"host:{host}\n"
        f"x-content-sha256:{payload_hash}\n"
        f"x-date:{amz_date}\n"
    )
    signed_headers = ";".join(signed_headers_list)

    canonical_request = "\n".join(
        [
            method.upper(),
            path,
            query,
            canonical_headers,
            signed_headers,
            payload_hash,
        ]
    )

    credential_scope = f"{date_stamp}/{region}/{service}/request"
    string_to_sign = "\n".join(
        [
            "HMAC-SHA256",
            amz_date,
            credential_scope,
            hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
        ]
    )

    signing_key = _get_signature_key(secret_key, date_stamp, region, service)
    signature = hmac.new(
        signing_key, string_to_sign.encode("utf-8"), hashlib.sha256
    ).hexdigest()

    auth_header = (
        f"HMAC-SHA256 "
        f"Credential={access_key_id}/{credential_scope}, "
        f"SignedHeaders={signed_headers}, "
        f"Signature={signature}"
    )

    signed_headers_dict = dict(headers)
    signed_headers_dict["X-Date"] = amz_date
    signed_headers_dict["X-Content-Sha256"] = payload_hash
    signed_headers_dict["Authorization"] = auth_header
    return signed_headers_dict


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


async def update_voice_chat(
    scene_id: str,
    request_body: dict[str, Any],
    scenes_dir: str,
) -> dict[str, Any]:
    """
    代理火山 RTC UpdateVoiceChat 请求。

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
    from core.voice_server.scene_loader import load_scenes

    scenes = load_scenes(scenes_dir)
    json_data = scenes.get(scene_id)
    if not json_data:
        raise ValueError(f"{scene_id} 不存在, 请先在 scenes 目录下定义该场景的 JSON")

    account_config: dict[str, Any] = json_data.get("AccountConfig", {})
    # 从请求或运行时状态获取必要的 RoomId/AppId/TaskId
    app_id = request_body.get("AppId")
    room_id = request_body.get("RoomId")
    task_id = request_body.get("TaskId")

    # 尝试从 voice_api 的运行时状态获取
    from core.voice_server import voice_api

    if not app_id:
        app_id = voice_api._runtime_state.get(f"{scene_id}:app_id")
    if not room_id:
        room_id = voice_api._runtime_state.get(f"{scene_id}:room_id")
    if not task_id:
        task_id = voice_api._runtime_state.get(f"{scene_id}:task_id")

    logger.info(
        f"[UpdateVoiceChat] 使用账户配置:\n"
        f"  accessKeyId={account_config['accessKeyId']}\n"
        f"  请求的 AppId={app_id}\n"
        f"  scene={scene_id} 的 AppId={json_data.get('VoiceChat', {}).get('AppId')}"
    )

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

    # 构造火山 OpenAPI 请求
    host = "rtc.volcengineapi.com"
    path = "/"
    version = "2024-12-01"
    query = f"Action=UpdateVoiceChat&Version={version}"
    body_bytes = json.dumps(body, ensure_ascii=False).encode("utf-8")

    req_headers = {
        "Host": host,
        "Content-Type": "application/json",
    }

    signed_headers = _sign_request(
        method="POST",
        host=host,
        path=path,
        query=query,
        headers=req_headers,
        body=body_bytes,
        access_key_id=account_config["accessKeyId"],
        secret_key=account_config["secretKey"],
    )

    url = f"https://{host}{path}?{query}"
    session = _get_http_session()
    if not session or session.closed:
        session = aiohttp.ClientSession()
        _set_http_session(session)

    async with session.post(url, headers=signed_headers, data=body_bytes) as resp:
        result = await resp.json()

    logger.info(
        f"[UpdateVoiceChat] 请求发送成功\n"
        f"  command={command}\n"
        f"  AppId={app_id}\n"
        f"  RoomId={room_id}\n"
        f"  TaskId={task_id}\n"
        f"  请求体: {json.dumps(body, ensure_ascii=False)}\n"
        f"  返回结果: {json.dumps(result, ensure_ascii=False)}"
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
