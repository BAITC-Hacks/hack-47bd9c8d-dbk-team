from typing import Optional
from .base import BaseTranscriber
from .kdb_whisper import KdbWhisperTranscriber
import config


def get_transcriber(
    provider: Optional[str] = None,
    api_key: Optional[str] = None,
    token: Optional[str] = None,
    base_url: Optional[str] = None,
    ip: Optional[str] = None,
    **kwargs
) -> BaseTranscriber:
    """
    Фабрика для получения транскрибатора по имени провайдера ('kdb').
    """
    selected_provider = (provider or config.DEFAULT_PROVIDER).lower()

    if selected_provider in ("kdb", "kdb_whisper", "ai.kdb.kz", "kdb.kz"):
        return KdbWhisperTranscriber(
            token=token or api_key,
            base_url=base_url,
            ip=ip,
            **kwargs
        )
    else:
        raise ValueError(
            f"Неизвестный провайдер распознавания речи: '{provider}'. "
            f"Доступные провайдеры: 'kdb'"
        )
