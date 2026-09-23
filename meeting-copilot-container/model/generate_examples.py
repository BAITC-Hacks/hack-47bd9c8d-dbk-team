#!/usr/bin/env python3
"""
Генерирует блоки с кодом и примерами для RecognitionRequest / RecognitionResponse
прямо из pydantic-моделей (model/models.py), чтобы контракты в README не
расходились с реальным кодом.

Использование:
    python3 model/generate_examples.py
"""

import inspect

from models import ErrorCode, RecognitionError, RecognitionRequest, RecognitionResponse

EXAMPLE_REQUEST = RecognitionRequest(
    messageId="1111",
    files="s3://uploads/2026-09-21/meeting-42/",
)

EXAMPLE_RESPONSE_OK = RecognitionResponse(
    messageId="1111",
    success=True,
)

EXAMPLE_RESPONSE_ERROR = RecognitionResponse(
    messageId="1111",
    success=False,
    errors=[
        RecognitionError(
            code=ErrorCode.FILES_NOT_FOUND,
            message="Папка MinIO не содержит нужных файлов",
        ),
    ],
)


def block(title: str, model) -> str:
    return (
        f"**{title}**\n\n```json\n"
        f"{model.model_dump_json(indent=2)}\n"
        f"```"
    )


def code_block(title: str, *classes) -> str:
    source = "\n\n".join(inspect.getsource(cls).rstrip() for cls in classes)
    return f"**{title}**\n\n```python\n{source}\n```"


def main():
    parts = [
        code_block("RecognitionRequest", RecognitionRequest),
        block("Пример RecognitionRequest", EXAMPLE_REQUEST),
        code_block("RecognitionResponse", ErrorCode, RecognitionError, RecognitionResponse),
        block("Пример RecognitionResponse (успех)", EXAMPLE_RESPONSE_OK),
        block("Пример RecognitionResponse (ошибка)", EXAMPLE_RESPONSE_ERROR),
    ]
    print("\n\n".join(parts))


if __name__ == "__main__":
    main()
