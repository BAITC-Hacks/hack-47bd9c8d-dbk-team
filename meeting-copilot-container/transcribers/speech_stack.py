"""
Клиент собственного речевого стека команды (speech_stack/, развёрнут на
stt.aibots.kz): распознавание речи и диаризация за одним шлюзом и одним токеном.

Ручки шлюза:
    GET  /health                   проба распознавания, токен не нужен
    GET  /health/diar              проба диаризации, токен не нужен
    POST /v1/audio/transcriptions  речь -> текст, OpenAI-совместимо
    POST /v1/audio/diarize         кто когда говорил
    GET  /v1/models                список моделей

Всё, кроме проб, требует `Authorization: Bearer $STT_TOKEN`. Неизвестные пути
шлюз тоже закрывает 401, поэтому 401 не обязательно означает плохой токен —
это может быть и опечатка в пути.

Отличия от ai.kdb.kz (KdbWhisperTranscriber), из-за которых это отдельный класс:
    * пути без префиксов /api/whisper и /api/diar;
    * диаризация — часть того же стека и того же токена;
    * поле `prompt` использовать нельзя: на материале этого стека оно резко
      портит результат (см. speech_stack/README.md);
    * поле `duration` в ответе не равно длине файла, полагаться на него нельзя.
"""

import io
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

import config
from audio_utils import get_audio_mime_type, validate_audio_file

from .base import BaseTranscriber
from .models import TranscriptionResult, TranscriptionSegment

# Шлюз стоит за Cloudflare, который отдаёт 403 на User-Agent по умолчанию
# у python-клиентов. Грабли уже описаны в tools/extract_commitments.py.
USER_AGENT = "dbk-meeting-copilot/1.0"


class SpeechStackTranscriber(BaseTranscriber):
    """Распознавание и диаризация через собственный стек speech_stack."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        token: Optional[str] = None,
        verify_ssl: bool = True,
        timeout: int = 900,
    ):
        self.base_url = (base_url or config.SPEECH_STACK_URL).rstrip("/")
        self.token = token or config.SPEECH_STACK_TOKEN
        self.verify_ssl = verify_ssl
        # Шлюз держит соединение до 900 с на чтение: часовая запись
        # распознаётся не мгновенно.
        self.timeout = timeout

        if not self.token:
            raise ValueError(
                "Токен речевого стека не задан. Укажите STT_TOKEN в .env "
                "или передайте token= в конструктор."
            )

        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {self.token}",
                "User-Agent": USER_AGENT,
            }
        )

    # --- пробы (без токена) -------------------------------------------------

    def check_health(self) -> Dict[str, Any]:
        """Проба распознавания: GET /health."""
        resp = requests.get(
            f"{self.base_url}/health",
            headers={"User-Agent": USER_AGENT},
            verify=self.verify_ssl,
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()

    def check_health_diar(self) -> Dict[str, Any]:
        """
        Проба диаризации: GET /health/diar.

        Это отдельный блок конфигурации, ломается независимо от распознавания,
        поэтому проверять надо обе пробы. Пока модели грузятся, ручка честно
        отвечает status=loading — ждать надо именно её, а не появления процесса.
        """
        resp = requests.get(
            f"{self.base_url}/health/diar",
            headers={"User-Agent": USER_AGENT},
            verify=self.verify_ssl,
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()

    # --- распознавание ------------------------------------------------------

    def transcribe(
        self,
        audio_path: str | Path,
        language: str = "ru",
        prompt: Optional[str] = None,
        response_format: str = "verbose_json",
        hotwords: Optional[str] = None,
        **kwargs,
    ) -> TranscriptionResult:
        """
        Распознаёт аудиофайл целиком.

        :param language: 'ru' | 'kk' | 'en' | 'auto'.
        :param prompt: принимается для совместимости с интерфейсом и
            игнорируется — на материале этого стека portит результат.
        :param response_format: 'verbose_json' даёт сегменты и пословные метки
            времени, без которых склейка с диаризацией невозможна.
        :param hotwords: собственные имена через запятую.
        """
        valid_path = validate_audio_file(audio_path)
        with open(valid_path, "rb") as f:
            audio_bytes = f.read()

        return self.transcribe_bytes(
            audio_bytes=audio_bytes,
            filename=valid_path.name,
            mime_type=get_audio_mime_type(valid_path),
            language=language,
            prompt=prompt,
            response_format=response_format,
            hotwords=hotwords,
            **kwargs,
        )

    def transcribe_bytes(
        self,
        audio_bytes: bytes,
        filename: str = "audio.mp3",
        mime_type: str = "audio/mpeg",
        language: str = "ru",
        prompt: Optional[str] = None,
        response_format: str = "verbose_json",
        hotwords: Optional[str] = None,
        **kwargs,
    ) -> TranscriptionResult:
        """Распознаёт аудио из буфера памяти. Параметры — как у transcribe()."""
        data: Dict[str, Any] = {
            "language": language,
            "response_format": response_format,
        }
        effective_hotwords = hotwords or config.SPEECH_STACK_HOTWORDS
        if effective_hotwords:
            data["hotwords"] = effective_hotwords

        res_data = self._post_audio("/v1/audio/transcriptions", audio_bytes, filename, mime_type, data)

        segments = [
            TranscriptionSegment(
                id=s.get("id"),
                start=float(s.get("start", 0.0)),
                end=float(s.get("end", 0.0)),
                text=str(s.get("text", "")).strip(),
            )
            for s in res_data.get("segments", [])
        ]

        detected_lang = res_data.get("detected_language") or res_data.get("language") or language

        return TranscriptionResult(
            text=str(res_data.get("text", "")).strip(),
            language=detected_lang,
            route=res_data.get("route"),
            detected_language=res_data.get("detected_language"),
            detected_probability=res_data.get("detected_probability"),
            detected_accepted=res_data.get("detected_accepted"),
            # duration тут — не длина файла; берите её из самого файла.
            duration=res_data.get("duration"),
            segments=segments,
            raw_response=res_data,
        )

    # --- диаризация ---------------------------------------------------------

    def diarize(
        self,
        audio_path: str | Path,
        min_segment_s: Optional[float] = None,
        max_segment_s: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Размечает, кто когда говорил: POST /v1/audio/diarize.

        Возвращает сырой ответ стека — `segments[]` с `start`, `end`, `speaker`.

        Модель различает ровно четыре голоса: пятый участник неизбежно
        сливается с одним из четырёх. Это архитектура модели, а не настройка.
        """
        valid_path = validate_audio_file(audio_path)
        with open(valid_path, "rb") as f:
            audio_bytes = f.read()

        return self.diarize_bytes(
            audio_bytes=audio_bytes,
            filename=valid_path.name,
            mime_type=get_audio_mime_type(valid_path),
            min_segment_s=min_segment_s,
            max_segment_s=max_segment_s,
        )

    def diarize_bytes(
        self,
        audio_bytes: bytes,
        filename: str = "audio.mp3",
        mime_type: str = "audio/mpeg",
        min_segment_s: Optional[float] = None,
        max_segment_s: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Диаризация аудио из буфера памяти. Параметры — как у diarize()."""
        data: Dict[str, Any] = {}
        if min_segment_s is not None:
            data["min_segment_s"] = str(min_segment_s)
        if max_segment_s is not None:
            data["max_segment_s"] = str(max_segment_s)

        return self._post_audio("/v1/audio/diarize", audio_bytes, filename, mime_type, data)

    # --- общее --------------------------------------------------------------

    def transcribe_with_speakers(
        self,
        audio_path: str | Path,
        language: str = "ru",
        hotwords: Optional[str] = None,
    ) -> TranscriptionResult:
        """
        Распознавание + диаризация одной записи.

        Порядок важен и соблюдён здесь намеренно: запись расшифровывается
        ЦЕЛИКОМ (модель видит контекст, ошибок на границах реплик меньше), та
        же запись отдельно диаризуется, и только потом слова раздаются
        говорящим. Резать аудио на сегменты и распознавать по одному — хуже:
        теряется контекст и растёт число вызовов.

        Сама раздача слов говорящим здесь не делается: этим занимается
        merge_transcript.py, который отдаёт слово тому, кто говорил в его
        СЕРЕДИНЕ (на стыке реплик начало слова часто попадает в хвост
        предыдущего говорящего).
        """
        result = self.transcribe(audio_path, language=language, hotwords=hotwords)
        result.diarization = self.diarize(audio_path)
        return result

    def _post_audio(
        self,
        path: str,
        audio_bytes: bytes,
        filename: str,
        mime_type: str,
        data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """POST multipart на ручку шлюза с разбором типовых ошибок."""
        url = f"{self.base_url}{path}"
        files = {"file": (filename, io.BytesIO(audio_bytes), mime_type)}

        resp = self.session.post(
            url,
            data=data,
            files=files,
            verify=self.verify_ssl,
            timeout=self.timeout,
        )

        if resp.status_code == 401:
            raise PermissionError(
                f"Речевой стек отклонил запрос к {path} (HTTP 401). "
                "Проверьте STT_TOKEN — и заодно сам путь: неизвестные пути "
                "шлюз тоже закрывает 401."
            )
        if resp.status_code != 200:
            raise RuntimeError(
                f"Ошибка речевого стека на {path} (HTTP {resp.status_code}): {resp.text[:500]}"
            )

        return resp.json()


def collect_speakers(diarization: Dict[str, Any]) -> List[str]:
    """Список ярлыков говорящих из ответа диаризации, в порядке появления."""
    seen: List[str] = []
    for segment in diarization.get("segments", []):
        speaker = segment.get("speaker")
        if speaker and speaker not in seen:
            seen.append(speaker)
    return seen
