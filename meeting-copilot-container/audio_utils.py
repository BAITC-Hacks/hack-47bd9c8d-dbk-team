import io
import wave
from pathlib import Path

SUPPORTED_AUDIO_EXTENSIONS = {".mp3", ".m4a", ".wav", ".ogg", ".aac", ".flac", ".webm", ".mp4", ".mpeg", ".mpga"}


def validate_audio_file(file_path: str | Path) -> Path:
    """
    Проверяет существование файла и корректность расширения (.mp3, .m4a и т.д.).
    """
    path = Path(file_path).resolve()
    if not path.exists():
        raise FileNotFoundError(f"Аудиофайл не найден: {path}")

    if not path.is_file():
        raise ValueError(f"Указанный путь не является файлом: {path}")

    suffix = path.suffix.lower()
    if suffix not in SUPPORTED_AUDIO_EXTENSIONS:
        raise ValueError(
            f"Неподдерживаемый формат аудио: {suffix}. "
            f"Поддерживаются: {', '.join(sorted(SUPPORTED_AUDIO_EXTENSIONS))}"
        )

    file_size_mb = path.stat().st_size / (1024 * 1024)
    if file_size_mb == 0:
        raise ValueError(f"Файл {path.name} пуст (0 байт).")

    return path


def get_audio_mime_type(file_path: str | Path) -> str:
    """
    Возвращает MIME-тип для аудиофайла.
    """
    suffix = Path(file_path).suffix.lower()
    mime_types = {
        ".mp3": "audio/mpeg",
        ".m4a": "audio/mp4",
        ".wav": "audio/wav",
        ".ogg": "audio/ogg",
        ".aac": "audio/aac",
        ".flac": "audio/flac",
        ".webm": "audio/webm",
        ".mp4": "audio/mp4",
    }
    return mime_types.get(suffix, "application/octet-stream")


def pcm_to_wav_bytes(
    pcm_data: bytes,
    sample_rate: int = 16000,
    channels: int = 1,
    sample_width: int = 2
) -> bytes:
    """
    Упаковывает сырые PCM-байты в валидный WAV-файл в памяти.
    :param pcm_data: Байты сырого аудио (например, 16-bit PCM).
    :param sample_rate: Частота дискретизации (по умолчанию 16000 Гц).
    :param channels: Количество каналов (по умолчанию 1 - моно).
    :param sample_width: Байт на сэмпл (2 байта для 16-bit).
    :return: Байты WAV файла.
    """
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav_out:
        wav_out.setnchannels(channels)
        wav_out.setsampwidth(sample_width)
        wav_out.setframerate(sample_rate)
        wav_out.writeframes(pcm_data)
    return buf.getvalue()
