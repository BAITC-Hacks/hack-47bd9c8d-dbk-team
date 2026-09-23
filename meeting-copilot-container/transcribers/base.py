from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional
from .models import TranscriptionResult


class BaseTranscriber(ABC):
    """
    Базовый интерфейс для транскрибаторов аудио.
    """

    @abstractmethod
    def transcribe(
        self,
        audio_path: str | Path,
        language: str = "ru",
        prompt: Optional[str] = None,
        **kwargs
    ) -> TranscriptionResult:
        """
        Отправляет аудиофайл (.mp3, .m4a и др.) на распознавание.

        :param audio_path: Путь к файлу аудио.
        :param language: Код языка (по умолчанию 'ru' для русского).
        :param prompt: Контекстная подсказка.
        :return: TranscriptionResult с текстом и сегментами.
        """
        pass

    @abstractmethod
    def transcribe_bytes(
        self,
        audio_bytes: bytes,
        filename: str = "audio.wav",
        mime_type: str = "audio/wav",
        language: str = "ru",
        prompt: Optional[str] = None,
        **kwargs
    ) -> TranscriptionResult:
        """
        Отправляет аудиобайты (например, буфер памяти) на распознавание.
        """
        pass
