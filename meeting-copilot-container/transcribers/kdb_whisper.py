import io
import socket
from pathlib import Path
from typing import Optional, Dict, Any, List
import requests

from .base import BaseTranscriber
from .models import TranscriptionResult, TranscriptionSegment
from audio_utils import validate_audio_file, get_audio_mime_type
import config


class HostResolverSession(requests.Session):
    """
    Сессия requests с поддержкой прямого сопоставления доменных имен в IP-адреса
    без изменения системного /etc/hosts и с сохранением SSL SNI.
    """

    def __init__(self, host_map: Optional[Dict[str, str]] = None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.host_map = host_map or {}

    def request(self, method, url, *args, **kwargs):
        if not self.host_map:
            return super().request(method, url, *args, **kwargs)

        orig_getaddrinfo = socket.getaddrinfo

        def custom_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
            target_host = self.host_map.get(host, host)
            return orig_getaddrinfo(target_host, port, family, type, proto, flags)

        socket.getaddrinfo = custom_getaddrinfo
        try:
            return super().request(method, url, *args, **kwargs)
        finally:
            socket.getaddrinfo = orig_getaddrinfo


class KdbWhisperTranscriber(BaseTranscriber):
    """
    Клиент для голосового стека ai.kdb.kz (Whisper STT).
    Поддерживает отправку аудиофайлов (.mp3, .wav, .ogg, .flac) на русском, казахском и английском языках.
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        token: Optional[str] = None,
        ip: Optional[str] = None,
        verify_ssl: bool = True,
        timeout: int = 600,
    ):
        self.base_url = (base_url or config.AI_KDB_URL).rstrip("/")
        self.token = token or config.AI_KDB_TOKEN
        self.ip = ip or config.AI_KDB_IP
        self.verify_ssl = verify_ssl
        self.timeout = timeout

        if not self.token:
            raise ValueError(
                "Токен доступа ai.kdb.kz не указан. Задайте AI_KDB_TOKEN в .env или передайте в конструктор."
            )

        host_map = {}
        if self.ip:
            # Извлекаем hostname из base_url
            from urllib.parse import urlparse
            parsed = urlparse(self.base_url)
            if parsed.hostname:
                host_map[parsed.hostname] = self.ip

        self.session = HostResolverSession(host_map=host_map)
        self.session.headers.update({
            "Authorization": f"Bearer {self.token}",
        })

    def check_health(self) -> Dict[str, Any]:
        """Проверка работоспособности сервиса распознавания речи."""
        url = f"{self.base_url}/api/whisper/health"
        resp = self.session.get(url, verify=self.verify_ssl, timeout=10)
        resp.raise_for_status()
        return resp.json()

    def transcribe(
        self,
        audio_path: str | Path,
        language: str = "ru",
        prompt: Optional[str] = None,
        response_format: str = "verbose_json",
        beam_size: Optional[int] = None,
        hotwords: Optional[str] = None,
        **kwargs
    ) -> TranscriptionResult:
        """
        Отправляет аудиофайл (.mp3, .wav, .ogg, .flac) на распознавание русской речи в ai.kdb.kz.

        :param audio_path: Путь к файлу аудио.
        :param language: Язык ('ru', 'auto', 'kk', 'en'). По умолчанию 'ru'.
        :param prompt: Контекстная подсказка (для совместимости).
        :param response_format: 'verbose_json' (с сегментами) или 'json' (только текст).
        :param beam_size: Опциональная ширина луча.
        :param hotwords: Список ключевых слов через запятую.
        :return: TranscriptionResult с распознанным текстом и метаданными.
        """
        valid_path = validate_audio_file(audio_path)
        mime_type = get_audio_mime_type(valid_path)
        with open(valid_path, "rb") as f:
            audio_bytes = f.read()

        return self.transcribe_bytes(
            audio_bytes=audio_bytes,
            filename=valid_path.name,
            mime_type=mime_type,
            language=language,
            prompt=prompt,
            response_format=response_format,
            beam_size=beam_size,
            hotwords=hotwords,
            **kwargs
        )

    def transcribe_bytes(
        self,
        audio_bytes: bytes,
        filename: str = "audio.wav",
        mime_type: str = "audio/wav",
        language: str = "ru",
        prompt: Optional[str] = None,
        response_format: str = "verbose_json",
        beam_size: Optional[int] = None,
        hotwords: Optional[str] = None,
        **kwargs
    ) -> TranscriptionResult:
        """
        Отправляет аудиобайты (например, WAV/MP3 из буфера памяти) на распознавание речи в ai.kdb.kz.

        :param audio_bytes: Байты аудиофайла.
        :param filename: Имя файла с расширением для multipart формы.
        :param mime_type: MIME-тип аудио.
        :param language: Язык ('ru', 'auto', 'kk', 'en').
        :param prompt: Контекстная подсказка.
        :param response_format: 'verbose_json' или 'json'.
        :param beam_size: Ширина луча.
        :param hotwords: Ключевые слова.
        :return: TranscriptionResult с распознанным текстом и метаданными.
        """
        url = f"{self.base_url}/api/whisper/v1/audio/transcriptions"

        data: Dict[str, Any] = {
            "language": language,
            "response_format": response_format,
        }
        if beam_size is not None:
            data["beam_size"] = str(beam_size)
        if hotwords:
            data["hotwords"] = hotwords

        files = {"file": (filename, io.BytesIO(audio_bytes), mime_type)}
        resp = self.session.post(
            url,
            data=data,
            files=files,
            verify=self.verify_ssl,
            timeout=self.timeout,
        )

        if resp.status_code == 401:
            raise PermissionError("Ошибка авторизации ai.kdb.kz (HTTP 401): неверный токен.")
        if resp.status_code != 200:
            raise RuntimeError(f"Ошибка распознавания ai.kdb.kz (HTTP {resp.status_code}): {resp.text}")

        res_data = resp.json()
        full_text = res_data.get("text", "")
        detected_lang = res_data.get("detected_language") or res_data.get("language") or language
        route = res_data.get("route")
        detected_prob = res_data.get("detected_probability")
        detected_acc = res_data.get("detected_accepted")
        duration = res_data.get("duration")

        segments: List[TranscriptionSegment] = []
        raw_segments = res_data.get("segments", [])
        for s in raw_segments:
            segments.append(
                TranscriptionSegment(
                    id=s.get("id"),
                    start=float(s.get("start", 0.0)),
                    end=float(s.get("end", 0.0)),
                    text=str(s.get("text", "")).strip(),
                )
            )

        return TranscriptionResult(
            text=full_text.strip(),
            language=detected_lang,
            route=route,
            detected_language=detected_lang,
            detected_probability=detected_prob,
            detected_accepted=detected_acc,
            duration=duration,
            segments=segments,
            raw_response=res_data,
        )
