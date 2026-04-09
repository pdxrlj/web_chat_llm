from __future__ import annotations

from collections.abc import Mapping

from fastapi.responses import JSONResponse
from starlette.background import BackgroundTask

# JSON 可序列化类型
JsonType = dict[str, object] | list[object] | str | int | float | bool | None

class NlResponse(JSONResponse):
    def __init__(self,*, content: JsonType, message: str, status_code: int = 200,
                 headers: Mapping[str, str] | None = None, 
                 media_type: str | None = None, 
                 background: BackgroundTask | None = None) -> None:
        response_content = {
            "message": message,
            "data": content
        }
        super().__init__(response_content, status_code, headers, media_type, background)
        
    @classmethod
    def success(cls, content: JsonType, message: str = "success", status_code: int = 200) -> NlResponse:
        return cls(content=content, message=message, status_code=status_code)

        
    @classmethod
    def fail(cls, content: JsonType, message: str = "fail", status_code: int = 400) -> NlResponse:
        return cls(content=content, message=message, status_code=status_code)