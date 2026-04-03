from app.http.handlers.base import router
from pydantic import BaseModel


class ModelsResponse(BaseModel):
    object: str = "list"
    data: list[ModelInfo] = []


class ModelInfo(BaseModel):
    id: str
    object: str = "model"
    created: int
    owned_by: str


SUPPORTED_MODELS = [
    ModelInfo(
        id="ark",
        created=1677610602,
        owned_by="奶龙成长报告",
    ),
    ModelInfo(
        id="nlchat",
        created=1677610602,
        owned_by="奶龙成长报告",
    ),
    ModelInfo(
        id="qwen",
        created=1677610602,
        owned_by="奶龙成长报告",
    ),
]


@router.get("/models", response_model=ModelsResponse)
def list_models():
    return ModelsResponse(data=SUPPORTED_MODELS)
