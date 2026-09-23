from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


class RecognitionRequest(BaseModel):
    messageId: str = Field(..., description="Идентификатор сообщения/запроса")
    files: str = Field(..., description="Ссылка на папку в MinIO с файлами для обработки")


class ErrorCode(str, Enum):
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"
    TIMEOUT = "TIMEOUT"
    FILES_NOT_FOUND = "FILES_NOT_FOUND"


class RecognitionError(BaseModel):
    code: ErrorCode = Field(..., description="Код ошибки")
    message: str = Field(..., description="Текстовое описание ошибки")


class RecognitionResponse(BaseModel):
    messageId: str = Field(..., description="Идентификатор сообщения/запроса")
    success: bool = Field(..., description="Признак успешной обработки")
    errors: List[RecognitionError] = Field(default_factory=list, description="Список ошибок, если обработка завершилась неудачно")
