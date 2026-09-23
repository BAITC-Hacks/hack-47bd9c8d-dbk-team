import argparse
import sys
from pathlib import Path
from typing import Optional

from transcribers import get_transcriber, TranscriptionResult
import config


def transcribe_audio_file(
    audio_path: str | Path,
    provider: str = "kdb",
    language: str = "ru",
    prompt: Optional[str] = None,
    output_path: Optional[str | Path] = None,
    format_output: str = "text",
    token: Optional[str] = None,
    **kwargs
) -> TranscriptionResult:
    """
    Основная функция для отправки аудиофайлов (.mp3, .wav и др.) на распознавание русской речи.

    :param audio_path: Путь к аудиофайлу (.mp3, .wav и т.д.).
    :param provider: Провайдер ('kdb').
    :param language: Язык ('ru', 'auto', 'kk', 'en' - по умолчанию 'ru').
    :param prompt: Контекстная подсказка (термины, имена).
    :param output_path: Путь для сохранения результата в файл (опционально).
    :param format_output: Формат сохранения ('text', 'srt', 'json').
    :param token: Токен доступа (если не задан в конфиге).
    :return: Объект TranscriptionResult.
    """
    print(f"[*] Инициализация транскрибатора '{provider}'...")
    transcriber = get_transcriber(provider=provider, token=token, **kwargs)

    print(f"[*] Отправка файла '{audio_path}' на распознавание (язык: {language})...")
    result = transcriber.transcribe(
        audio_path=audio_path,
        language=language,
        prompt=prompt,
    )

    print("[+] Распознавание завершено успешно!")
    if result.route:
        print(f"[*] Маршрут: {result.route} (детектированный язык: {result.detected_language}, вероятность: {result.detected_probability})")

    if output_path:
        out_file = Path(output_path)
        out_file.parent.mkdir(parents=True, exist_ok=True)
        if format_output == "srt":
            content = result.to_srt()
        elif format_output == "json":
            content = result.model_dump_json(indent=2)
        else:
            content = result.text

        out_file.write_text(content, encoding="utf-8")
        print(f"[+] Результат сохранен в '{out_file}'")

    return result


def main():
    parser = argparse.ArgumentParser(
        description="AiMeetingCopilot: Распознавание русской речи из аудиофайлов (.m4a, .mp3 и др.) через ai.kdb.kz"
    )
    parser.add_argument("file", help="Путь к аудиофайлу (.m4a, .mp3, .wav, .ogg, .flac и т.д.)")
    parser.add_argument(
        "--provider",
        choices=["kdb"],
        default=config.DEFAULT_PROVIDER,
        help="Сервис распознавания (по умолчанию: %(default)s)",
    )
    parser.add_argument(
        "--language",
        "-l",
        default=config.DEFAULT_LANGUAGE,
        help="Язык распознавания ('ru', 'auto', 'kk', 'en', по умолчанию: %(default)s)",
    )
    parser.add_argument(
        "--token",
        "-t",
        default=None,
        help="Токен авторизации (по умолчанию берется из конфигурации)",
    )
    parser.add_argument(
        "--prompt",
        "-p",
        default=None,
        help="Подсказка / контекст / имена участников для повышения точности",
    )
    parser.add_argument(
        "--output",
        "-o",
        default=None,
        help="Путь к файлу для сохранения результата",
    )
    parser.add_argument(
        "--format",
        "-f",
        choices=["text", "srt", "json"],
        default="text",
        help="Формат вывода при сохранении (text, srt, json)",
    )

    args = parser.parse_args()

    try:
        res = transcribe_audio_file(
            audio_path=args.file,
            provider=args.provider,
            language=args.language,
            token=args.token,
            prompt=args.prompt,
            output_path=args.output,
            format_output=args.format,
        )
        print("\n--- РАСПОЗНАННЫЙ ТЕКСТ ---")
        print(res.text)
    except Exception as e:
        print(f"[!] Ошибка: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
