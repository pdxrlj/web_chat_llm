"""
火山引擎 RTC AccessToken 生成器。

从 JS token.js 移植，实现火山 RTC Token 的序列化与验证逻辑。
"""

import hashlib
import hmac
import math
import random
import struct
import time
from base64 import b64decode, b64encode
from typing import Optional


VERSION = "001"
VERSION_LENGTH = 3
APP_ID_LENGTH = 24


class Privileges:
    PrivPublishStream = 0
    privPublishAudioStream = 1
    privPublishVideoStream = 2
    privPublishDataStream = 3
    PrivSubscribeStream = 4


privileges = Privileges


class _ByteBuf:
    """二进制写入缓冲区，对应 JS 版 ByteBuf。"""

    def __init__(self) -> None:
        self._buf = bytearray()

    def pack(self) -> bytes:
        return bytes(self._buf)

    def put_uint16(self, v: int) -> "_ByteBuf":
        self._buf.extend(struct.pack("<H", v))
        return self

    def put_uint32(self, v: int) -> "_ByteBuf":
        self._buf.extend(struct.pack("<I", v))
        return self

    def put_bytes(self, data: bytes) -> "_ByteBuf":
        self.put_uint16(len(data))
        self._buf.extend(data)
        return self

    def put_string(self, s: str) -> "_ByteBuf":
        return self.put_bytes(s.encode("utf-8"))

    def put_tree_map_uint32(self, m: Optional[dict[int, int]]) -> "_ByteBuf":
        if not m:
            self.put_uint16(0)
            return self
        self.put_uint16(len(m))
        # JS 版 Object 的 for...in 对数字 key 自动排序，Python 需要显式排序
        for k in sorted(m.keys()):
            self.put_uint16(k)
            self.put_uint32(m[k])
        return self


class _ReadByteBuf:
    """二进制读取缓冲区，对应 JS 版 ReadByteBuf。"""

    def __init__(self, data: bytes) -> None:
        self._buf = data
        self._pos = 0

    def get_uint16(self) -> int:
        val = struct.unpack_from("<H", self._buf, self._pos)[0]
        self._pos += 2
        return val

    def get_uint32(self) -> int:
        val = struct.unpack_from("<I", self._buf, self._pos)[0]
        self._pos += 4
        return val

    def get_string(self) -> bytes:
        length = self.get_uint16()
        val = self._buf[self._pos : self._pos + length]
        self._pos += length
        return val

    def get_tree_map_uint32(self) -> dict[int, int]:
        result: dict[int, int] = {}
        length = self.get_uint16()
        for _ in range(length):
            k = self.get_uint16()
            v = self.get_uint32()
            result[k] = v
        return result


def _encode_hmac(key: str, message: bytes) -> bytes:
    """HMAC-SHA256 签名。"""
    return hmac.new(
        key.encode("utf-8"), message, hashlib.sha256
    ).digest()


class AccessToken:
    """火山 RTC AccessToken，对应 JS 版 AccessToken。"""

    def __init__(self, app_id: str, app_key: str, room_id: str, user_id: str) -> None:
        self.app_id = app_id
        self.app_key = app_key
        self.room_id = room_id
        self.user_id = user_id
        self.issued_at = math.floor(time.time())
        self.nonce = random.randint(0, 0xFFFFFFFF)
        self.expire_at = 0
        self._privileges: dict[int, int] = {}
        self._signature: str = ""

    def add_privilege(self, privilege: int, expire_timestamp: int) -> None:
        """添加权限及过期时间。"""
        self._privileges[privilege] = expire_timestamp
        if privilege == Privileges.PrivPublishStream:
            self._privileges[Privileges.privPublishAudioStream] = expire_timestamp
            self._privileges[Privileges.privPublishVideoStream] = expire_timestamp
            self._privileges[Privileges.privPublishDataStream] = expire_timestamp

    def expire_time(self, expire_timestamp: int) -> None:
        """设置 Token 整体过期时间。"""
        self.expire_at = expire_timestamp

    def _pack_msg(self) -> bytes:
        buf = _ByteBuf()
        buf.put_uint32(self.nonce)
        buf.put_uint32(self.issued_at)
        buf.put_uint32(self.expire_at)
        buf.put_string(self.room_id)
        buf.put_string(self.user_id)
        buf.put_tree_map_uint32(self._privileges)
        return buf.pack()

    def serialize(self) -> str:
        """生成 Token 字符串。"""
        msg_bytes = self._pack_msg()
        signature = _encode_hmac(self.app_key, msg_bytes)
        content = _ByteBuf().put_bytes(msg_bytes).put_bytes(signature).pack()
        return VERSION + self.app_id + b64encode(content).decode("utf-8")

    def verify(self, key: str) -> bool:
        """验证 Token 是否有效。"""
        if self.expire_at > 0 and math.floor(time.time()) > self.expire_at:
            return False
        self.app_key = key
        return _encode_hmac(self.app_key, self._pack_msg()).hex() == self._signature


def parse_token(raw: str) -> Optional[AccessToken]:
    """从原始字符串解析 Token 信息。"""
    try:
        if len(raw) <= VERSION_LENGTH + APP_ID_LENGTH:
            return None
        if raw[:VERSION_LENGTH] != VERSION:
            return None

        token = AccessToken("", "", "", "")
        token.app_id = raw[VERSION_LENGTH : VERSION_LENGTH + APP_ID_LENGTH]

        content_buf = b64decode(raw[VERSION_LENGTH + APP_ID_LENGTH :])
        reader = _ReadByteBuf(content_buf)

        msg = reader.get_string()
        token._signature = reader.get_string().hex()  # pyright: ignore[reportPrivateUsage]

        msg_reader = _ReadByteBuf(msg)
        token.nonce = msg_reader.get_uint32()
        token.issued_at = msg_reader.get_uint32()
        token.expire_at = msg_reader.get_uint32()
        token.room_id = msg_reader.get_string().decode("utf-8")
        token.user_id = msg_reader.get_string().decode("utf-8")
        token._privileges = msg_reader.get_tree_map_uint32()  # pyright: ignore[reportPrivateUsage]

        return token
    except Exception:
        return None



