"""
火山语音聊天 OpenAPI 代理 & getScenes 接口。

对应 JS 版 app.js 中 proxy 和 getScenes 两个路由逻辑。
"""

import copy
import hashlib
import hmac
import json
import math
import time
import uuid
from datetime import datetime, timezone
from typing import Any

import aiohttp

from core.logger import setup_logger
from core.voice_server.scene_loader import load_scenes
from core.voice_server.token import AccessToken, Privileges

logger = setup_logger("voice_api")

# 场景配置缓存（按 scenes_dir 缓存）
_scenes_cache: dict[str, dict[str, dict[str, Any]]] = {}

# 运行时状态：记录每个 scene 最近一次 StartVoiceChat 使用的参数
# key = f"{scene_id}:{app_id}:{room_id}", value = {AppId, RoomId, TaskId, ...}
_runtime_state: dict[str, dict[str, Any]] = {}

# 共享 HTTP Session
_http_session: aiohttp.ClientSession | None = None


def _get_scenes(scenes_dir: str) -> dict[str, dict[str, Any]]:
    """获取场景配置（按 scenes_dir 懒加载缓存）。"""
    if scenes_dir not in _scenes_cache:
        _scenes_cache[scenes_dir] = load_scenes(scenes_dir)
    return _scenes_cache[scenes_dir]


async def _get_http_session() -> aiohttp.ClientSession:
    """获取共享 aiohttp ClientSession。"""
    global _http_session
    if _http_session is None or _http_session.closed:
        _http_session = aiohttp.ClientSession()
    return _http_session


def _assert(condition: Any, msg: str) -> None:
    """断言条件为真，否则抛出 ValueError。"""
    if not condition or (isinstance(condition, str) and " " in condition):
        logger.error(f"校验失败: {msg}")
        raise ValueError(msg)


# ── 火山 OpenAPI V4 签名 ──────────────────────────────────────────────


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


# ── proxy 接口 ──────────────────────────────────────────────────────


async def proxy_voice_api(
    action: str,
    version: str,
    scene_id: str,
    request_body: dict[str, Any],
    scenes_dir: str,
    http_headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    """
    代理火山 RTC AIGC OpenAPI 请求。

    对应 JS 版 /proxy 路由，根据 Action 拼装请求体并转发。
    """
    scenes = _get_scenes(scenes_dir)
    _assert(action, "Action 不能为空")
    _assert(version, "Version 不能为空")
    _assert(scene_id, "SceneID 不能为空, SceneID 用于指定场景的 JSON")

    json_data = scenes.get(scene_id)
    _assert(json_data, f"{scene_id} 不存在, 请先在 scenes 目录下定义该场景的 JSON")
    assert json_data is not None  # 类型窄化，_assert 已保证非 None

    account_config: dict[str, Any] = json_data.get("AccountConfig", {})
    voice_chat: dict[str, Any] = json_data.get("VoiceChat", {})
    _assert(account_config.get("accessKeyId"), "AccountConfig.accessKeyId 不能为空")
    _assert(account_config.get("secretKey"), "AccountConfig.secretKey 不能为空")

    body: dict[str, Any] = {}

    if action == "StartVoiceChat":
        # 深拷贝避免污染缓存
        body = copy.deepcopy(voice_chat)

        # 从请求参数获取 RoomId/UserId/AppId（由前端从 getScenes 返回值传入）
        # 多用户场景下不能依赖缓存，否则会互相覆盖
        room_id = request_body.get("RoomId")
        user_id = request_body.get("UserId")
        app_id = request_body.get("AppId")
        if room_id:
            body["RoomId"] = room_id
        if app_id:
            body["AppId"] = app_id
        if user_id:
            agent_config = body.get("AgentConfig", {})
            target_user_ids = agent_config.get("TargetUserId", [])
            if target_user_ids:
                target_user_ids[0] = user_id
            else:
                agent_config["TargetUserId"] = [user_id]

        # 合并客户端传入的自定义参数
        custom_llm_params = request_body.get("CustomLLMParams")
        custom_headers = request_body.get("CustomHeaders")
        custom_system_messages = request_body.get("CustomSystemMessages")

        if custom_llm_params:
            llm_config = body.setdefault("Config", {}).setdefault("LLMConfig", {})
            llm_config.update(custom_llm_params)

        if custom_headers:
            llm_config = body.setdefault("Config", {}).setdefault("LLMConfig", {})
            # 将 Authorization 写入 APIKey
            llm_config["APIKey"] = custom_headers.get("Authorization", "")

        # 将 session_id 写入 ExtraHeader，供 CustomLLM 回调时透传
        session_id = (http_headers or {}).get("session_id") or (
            request_body.get("SessionId")
        )
        logger.info(
            f"[proxy:StartVoiceChat] session_id from header: {session_id}, http_headers keys: {list((http_headers or {}).keys())}"
        )
        if session_id:
            extra_header = body.setdefault("Config", {}).setdefault("ExtraHeader", {})
            extra_header["session_id"] = session_id

        if custom_system_messages:
            llm_config = body.setdefault("Config", {}).setdefault("LLMConfig", {})
            existing = llm_config.get("SystemMessages", [])
            llm_config["SystemMessages"] = existing + list(custom_system_messages)

        logger.info(
            f"[proxy:StartVoiceChat] AppId={body.get('AppId')}, "
            f"RoomId={body.get('RoomId')}, "
            f"TargetUserId={body.get('AgentConfig', {}).get('TargetUserId')}"
        )
        logger.info(
            f"[proxy:StartVoiceChat] body: {json.dumps(body, ensure_ascii=False)}"
        )

    elif action == "StopVoiceChat":
        # 优先使用前端传入的参数
        # 其次使用运行时状态（StartVoiceChat 保存的参数）
        # 最后 fallback 到缓存原始值
        app_id = (
            request_body.get("AppId")
            or _runtime_state.get(f"{scene_id}:app_id")
            or voice_chat.get("AppId")
        )
        room_id = (
            request_body.get("RoomId")
            or _runtime_state.get(f"{scene_id}:room_id")
            or voice_chat.get("RoomId")
        )
        task_id = (
            request_body.get("TaskId")
            or _runtime_state.get(f"{scene_id}:task_id")
            or voice_chat.get("TaskId")
        )
        _assert(app_id, "VoiceChat.AppId 不能为空")
        _assert(room_id, "VoiceChat.RoomId 不能为空")
        _assert(task_id, "VoiceChat.TaskId 不能为空")
        body = {"AppId": app_id, "RoomId": room_id, "TaskId": task_id}
        logger.info(
            f"[proxy:StopVoiceChat] AppId={app_id}, RoomId={room_id}, TaskId={task_id}"
        )

    # 构造火山 OpenAPI 请求
    host = "rtc.volcengineapi.com"
    path = "/"
    query = f"Action={action}&Version={version}"
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
    session = await _get_http_session()
    async with session.post(url, headers=signed_headers, data=body_bytes) as resp:
        result = await resp.json()

    logger.info(f"[{action}] 请求结果: {json.dumps(result, ensure_ascii=False)[:500]}")

    # StartVoiceChat 成功后，保存运行时状态供 StopVoiceChat 使用
    if action == "StartVoiceChat" and result.get("Result") == "ok":
        _app_id = body.get("AppId")
        _room_id = body.get("RoomId")
        _task_id = body.get("TaskId")
        if _app_id is not None:
            _runtime_state[f"{scene_id}:app_id"] = _app_id
        if _room_id is not None:
            _runtime_state[f"{scene_id}:room_id"] = _room_id
        if _task_id is not None:
            _runtime_state[f"{scene_id}:task_id"] = _task_id
        logger.info(
            f"[proxy:StartVoiceChat] 已保存运行时状态: "
            f"AppId={_app_id}, RoomId={_room_id}, TaskId={_task_id}"
        )
    # StopVoiceChat 成功后，清除运行时状态
    elif action == "StopVoiceChat" and result.get("Result") == "ok":
        _runtime_state.pop(f"{scene_id}:app_id", None)
        _runtime_state.pop(f"{scene_id}:room_id", None)
        _runtime_state.pop(f"{scene_id}:task_id", None)
        logger.info(f"[proxy:StopVoiceChat] 已清除运行时状态: scene_id={scene_id}")

    return result


# ── getScenes 接口 ──────────────────────────────────────────────────


def get_scenes(
    username: str | None,
    scenes_dir: str,
) -> dict[str, Any]:
    """
    获取场景列表，并为每个场景生成 RTC Token。

    对应 JS 版 /getScenes 路由。
    """
    scenes = _get_scenes(scenes_dir)
    result_scenes = []

    logger.info(f"[getScenes] 请求参数: username={username}")

    for scene_id, json_data in scenes.items():
        # 深拷贝避免污染缓存（多用户场景下每个用户应有独立的 RoomId）
        scene_data = copy.deepcopy(json_data)

        scene_config = scene_data.get("SceneConfig", {})
        rtc_config = scene_data.get("RTCConfig", {})
        voice_chat = scene_data.get("VoiceChat", {})

        app_id = rtc_config.get("AppId")
        app_key = rtc_config.get("AppKey")
        _assert(app_id, f"{scene_id} 场景的 RTCConfig.AppId 不能为空")
        _assert(app_key, f"生成 Token 时, {scene_id} 场景的 RTCConfig.AppKey 不可为空")

        # 1. room_id: 每次随机生成
        room_id = str(uuid.uuid4())

        # 2. user_id: 使用传入的 username，否则随机生成
        user_id = username or str(uuid.uuid4())

        # 更新拷贝上的配置
        rtc_config["RoomId"] = room_id
        rtc_config["UserId"] = user_id
        voice_chat["RoomId"] = room_id
        agent_config = voice_chat.get("AgentConfig", {})
        target_user_ids = agent_config.get("TargetUserId", [])
        if target_user_ids:
            target_user_ids[0] = user_id
        else:
            agent_config["TargetUserId"] = [user_id]

        logger.info(
            f"[getScenes] {scene_id} - AppId: {app_id}, RoomId: {room_id}, UserId: {user_id}"
        )

        # 3. 生成 Token
        token_obj = AccessToken(app_id, app_key, room_id, user_id)
        token_obj.add_privilege(Privileges.PrivSubscribeStream, 0)
        token_obj.add_privilege(Privileges.PrivPublishStream, 0)
        token_obj.expire_time(math.floor(time.time()) + 7 * 24 * 3600)  # 7天
        token = token_obj.serialize()
        rtc_config["Token"] = token

        # 不对外暴露 AppKey
        rtc_result = {
            "AppId": app_id,
            "RoomId": room_id,
            "UserId": user_id,
            "Token": token,
        }

        # 组装前端需要的场景信息
        scene_config["id"] = scene_id
        scene_config["botName"] = agent_config.get("UserId")
        config = voice_chat.get("Config", {})
        scene_config["isInterruptMode"] = config.get("InterruptMode") == 0
        vision_config = config.get("LLMConfig", {}).get("VisionConfig", {})
        scene_config["isVision"] = vision_config.get("Enable", False)
        scene_config["isScreenMode"] = (
            vision_config.get("SnapshotConfig", {}).get("StreamType") == 1
        )
        avatar_config = config.get("AvatarConfig", {})
        scene_config["isAvatarScene"] = avatar_config.get("Enabled", False)
        scene_config["avatarBgUrl"] = avatar_config.get("BackgroundUrl", "")

        logger.info(
            f"[getScenes] {scene_id} - AppId: {app_id}, RoomId: {room_id}, UserId: {user_id}"
        )

        result_scenes.append(
            {
                "scene": scene_config,
                "rtc": rtc_result,
            }
        )

    return {"scenes": result_scenes}
