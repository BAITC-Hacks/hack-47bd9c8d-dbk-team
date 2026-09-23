"""Скачивает ПУБЛИЧНЫЕ веса распознавания и конвертирует их в формат CTranslate2.

Почему конвертация, а не готовые ct2-веса с хаба: готовые бывают собраны другой
версией ctranslate2, и тогда модель грузится, но декодирует мусор. Конвертация
на месте занимает пару минут и снимает этот класс отказов целиком.

Казахская модель здесь НЕ скачивается: рабочая у нас — собственное дообучение
whisper-large-v3-turbo на KSC2 (CER 0.0017), и её веса не опубликованы. Пути
задаются окружением, так что своя модель подставляется без правки кода:

    WHISPER_CT2_PATH=/app/models/моя-казахская-ct2
"""
import os
import subprocess
import sys

MODELS = os.environ.get("STT_MODELS", "large-v3,large-v3-turbo").split(",")
OUT = "/app/models"

SOURCES = {
    "large-v3": ("openai/whisper-large-v3", "whisper-large-v3-ct2"),
    "large-v3-turbo": ("openai/whisper-large-v3-turbo", "whisper-large-v3-turbo-ct2"),
}


def main() -> int:
    for key in (m.strip() for m in MODELS if m.strip()):
        if key not in SOURCES:
            print(f"неизвестная модель {key!r}, знаю: {', '.join(SOURCES)}", file=sys.stderr)
            return 2
        repo, name = SOURCES[key]
        dst = f"{OUT}/{name}"
        if os.path.isdir(dst):
            print(f"{name}: уже на месте")
            continue
        print(f"{name}: конвертирую из {repo}")
        # float16 — то, в чём модель и работает на карте; хранить в float32
        # значит удвоить размер слоя образа ради числа, которое всё равно
        # будет приведено при загрузке.
        subprocess.run(
            ["ct2-transformers-converter", "--model", repo, "--output_dir", dst,
             "--copy_files", "tokenizer.json", "preprocessor_config.json",
             "--quantization", "float16"],
            check=True,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
