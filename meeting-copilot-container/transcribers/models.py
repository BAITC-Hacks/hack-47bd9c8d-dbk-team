from typing import List, Optional, Any, Dict
from pydantic import BaseModel, Field


class TranscriptionSegment(BaseModel):
    id: Optional[int] = None
    start: float = Field(default=0.0, description="Время начала сегмента в секундах")
    end: float = Field(default=0.0, description="Время окончания сегмента в секундах")
    text: str = Field(..., description="Распознанный текст сегмента")
    speaker: Optional[str] = Field(default=None, description="Идентификатор спикера, если определен")


class TranscriptionResult(BaseModel):
    text: str = Field(..., description="Полный распознанный текст")
    language: str = Field(default="ru", description="Язык распознавания")
    route: Optional[str] = Field(default=None, description="Маршрут/модель (general для ru/en, ksc2 для kk)")
    detected_language: Optional[str] = Field(default=None, description="Определенный детектором язык")
    detected_probability: Optional[float] = Field(default=None, description="Вероятность определенного языка")
    detected_accepted: Optional[bool] = Field(default=None, description="Принята ли детекция языка сервером")
    duration: Optional[float] = Field(default=None, description="Длительность аудио в секундах")
    segments: List[TranscriptionSegment] = Field(default_factory=list, description="Сегменты с таймкодами")
    diarization: Optional[Dict[str, Any]] = Field(default=None, description="Данные диаризации спикеров")
    raw_response: Optional[Dict[str, Any]] = Field(default=None, description="Сырой ответ от API")

    def to_srt(self) -> str:
        """Форматирует результат в виде субтитров SRT."""
        if not self.segments:
            return self.text

        def format_timestamp(seconds: float) -> str:
            hrs = int(seconds // 3600)
            mins = int((seconds % 3600) // 60)
            secs = int(seconds % 60)
            millis = int((seconds - int(seconds)) * 1000)
            return f"{hrs:02d}:{mins:02d}:{secs:02d},{millis:03d}"

        lines = []
        for idx, segment in enumerate(self.segments, start=1):
            lines.append(str(idx))
            lines.append(f"{format_timestamp(segment.start)} --> {format_timestamp(segment.end)}")
            speaker_prefix = f"[{segment.speaker}] " if segment.speaker else ""
            lines.append(f"{speaker_prefix}{segment.text.strip()}\n")
        return "\n".join(lines)
