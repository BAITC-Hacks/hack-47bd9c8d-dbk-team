#!/usr/bin/env python3
"""
Kafka-сервис AiMeetingCopilot.

При старте проверяет доступность зависимостей — Kafka, MinIO и ai.kdb.kz
(whisper). Если Kafka недоступна, сервис просто логирует ошибку и завершается
(отправить её некуда). Если недоступны MinIO и/или ai.kdb.kz, в
KAFKA_RESPONSE_TOPIC уходит RecognitionResponse с описанием проблем, после
чего сервис завершается, не начиная обработку сообщений.

После успешных проверок слушает топик KAFKA_REQUEST_TOPIC
(AiMeetingCopilotRequest), для каждого
входящего RecognitionRequest:
  1. скачивает файлы из указанной папки MinIO;
  2. прогоняет их через существующий пайплайн (entrypoint.sh: аудио -> mp3 ->
     распознавание ai.kdb.kz -> склейка -> суммаризация -> экспорт в PDF);
  3. заливает результат (transcript.json, summary.md, summary.pdf) обратно
     в ту же папку MinIO;
  4. публикует RecognitionResponse в KAFKA_RESPONSE_TOPIC
     (AiMeetingCopilotResponse).

Формат `files` в запросе: "s3://<bucket>/<prefix>/" либо просто "<prefix>/"
(тогда используется бакет MINIO_BUCKET из конфига).

Запуск (локально, нужны ffmpeg/curl в PATH — как для entrypoint.sh):
    python3 kafka_service.py
"""

import json
import logging
import os
import signal
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from kafka import KafkaConsumer, KafkaProducer
from kafka.errors import CommitFailedError
from minio import Minio
from minio.error import S3Error
from pydantic import ValidationError

import config
from check_health_services import check_kafka, run_startup_checks
from model.models import ErrorCode, RecognitionError, RecognitionRequest, RecognitionResponse

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("kafka_service")

BASE_DIR = Path(__file__).resolve().parent
ENTRYPOINT = BASE_DIR / "entrypoint.sh"

AUDIO_EXTENSIONS = {".mp3", ".m4a", ".mp4", ".wav", ".ogg", ".flac", ".webm"}
VTT_SUFFIX = ".transcript.vtt"


class ProcessingError(Exception):
    """Ошибка обработки сообщения с уже готовым кодом для RecognitionError."""

    def __init__(self, code: ErrorCode, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def make_minio_client() -> Minio:
    return Minio(
        config.MINIO_ENDPOINT,
        access_key=config.MINIO_ACCESS_KEY,
        secret_key=config.MINIO_SECRET_KEY,
        secure=config.MINIO_SECURE,
    )


def parse_files_location(files: str):
    """
    Разбирает поле `files` запроса в (bucket, prefix).
    Поддерживает "s3://bucket/prefix/" и просто "prefix/" (бакет по умолчанию
    из config.MINIO_BUCKET).
    """
    parsed = urlparse(files)
    if parsed.scheme == "s3" and parsed.netloc:
        bucket = parsed.netloc
        prefix = parsed.path.lstrip("/")
    else:
        bucket = config.MINIO_BUCKET
        prefix = files.lstrip("/")

    if prefix and not prefix.endswith("/"):
        prefix += "/"
    return bucket, prefix


def download_input_files(client: Minio, bucket: str, prefix: str, dest_dir: Path) -> list[Path]:
    try:
        objects = list(client.list_objects(bucket, prefix=prefix, recursive=True))
    except S3Error as e:
        raise ProcessingError(
            ErrorCode.FILES_NOT_FOUND,
            f"Не удалось прочитать папку MinIO '{bucket}/{prefix}': {e}",
        ) from e

    objects = [obj for obj in objects if not obj.object_name.endswith("/")]
    if not objects:
        raise ProcessingError(
            ErrorCode.FILES_NOT_FOUND,
            f"Папка MinIO '{bucket}/{prefix}' не содержит файлов",
        )

    downloaded = []
    for obj in objects:
        local_path = dest_dir / Path(obj.object_name).name
        client.fget_object(bucket, obj.object_name, str(local_path))
        downloaded.append(local_path)
    return downloaded


def pick_audio_and_vtt(files: list[Path]) -> tuple[Path, Optional[Path]]:
    audio_file = next((f for f in files if f.suffix.lower() in AUDIO_EXTENSIONS), None)
    if audio_file is None:
        raise ProcessingError(
            ErrorCode.FILES_NOT_FOUND,
            "В папке MinIO не найден аудио/видео файл для распознавания",
        )
    vtt_file = next((f for f in files if f.name.lower().endswith(VTT_SUFFIX)), None)
    return audio_file, vtt_file


def run_pipeline(audio_file: Path, vtt_file: Optional[Path], output_dir: Path) -> None:
    args = [str(ENTRYPOINT), str(audio_file)]
    if vtt_file:
        args.append(str(vtt_file))
    args.append(str(output_dir))

    # start_new_session=True делает entrypoint.sh лидером своей группы процессов,
    # поэтому по таймауту можно убить всю группу (сам скрипт + ffmpeg/curl/python3,
    # которых он порождает) разом через os.killpg, а не только сам entrypoint.sh.
    process = subprocess.Popen(
        args,
        cwd=BASE_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    try:
        stdout, stderr = process.communicate(timeout=config.PROCESSING_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        os.killpg(os.getpgid(process.pid), signal.SIGKILL)
        process.communicate()  # добираем завершение самого entrypoint.sh, освобождаем пайпы

        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            try:
                pid, _ = os.waitpid(-1, os.WNOHANG)
            except ChildProcessError:
                break
            if pid == 0:
                time.sleep(0.05)

        raise ProcessingError(
            ErrorCode.TIMEOUT,
            f"Обработка не уложилась в {config.PROCESSING_TIMEOUT_SECONDS} сек",
        )

    if process.returncode != 0:
        stderr_tail = stderr.strip()[-500:]
        # entrypoint.sh падает с ненулевым кодом в первую очередь на ошибках
        # запросов к речевым службам и языковой модели (сеть, HTTP-код, таймаут curl) —
        # других причин у него практически нет, поэтому весь этот класс
        # ошибок помечается как недоступность внешнего сервиса.
        raise ProcessingError(
            ErrorCode.SERVICE_UNAVAILABLE,
            f"Пайплайн завершился с ошибкой (код {process.returncode}): {stderr_tail}",
        )


# Артефакты, которые заливаются обратно в папку MinIO. summary.pdf —
# производный от summary.md, его может не быть, если экспорт в entrypoint.sh
# не удался; отсутствующие файлы просто пропускаются.
RESULT_FILES = ("transcript.json", "summary.md", "summary.pdf")


def upload_results(client: Minio, bucket: str, prefix: str, output_dir: Path) -> None:
    for name in RESULT_FILES:
        local_path = output_dir / name
        if local_path.exists():
            client.fput_object(bucket, f"{prefix}{name}", str(local_path))


def process_message(req: RecognitionRequest, client: Minio) -> RecognitionResponse:
    bucket, prefix = parse_files_location(req.files)

    with tempfile.TemporaryDirectory(prefix="ai-meeting-copilot-") as tmp:
        tmp_path = Path(tmp)
        input_dir = tmp_path / "input"
        output_dir = tmp_path / "output"
        input_dir.mkdir()
        output_dir.mkdir()

        files = download_input_files(client, bucket, prefix, input_dir)
        audio_file, vtt_file = pick_audio_and_vtt(files)

        run_pipeline(audio_file, vtt_file, output_dir)
        upload_results(client, bucket, prefix, output_dir)

    return RecognitionResponse(messageId=req.messageId, success=True)


def build_error_response(message_id: str, code: ErrorCode, message: str) -> RecognitionResponse:
    return RecognitionResponse(
        messageId=message_id,
        success=False,
        errors=[RecognitionError(code=code, message=message)],
    )


def main() -> None:
    log.info("Подключение к Kafka: %s", config.KAFKA_BOOTSTRAP_SERVERS)

    kafka_error = check_kafka()
    if kafka_error:
        # Отправить ошибку некуда — сама Kafka недоступна.
        log.critical("%s. Сервис не запущен.", kafka_error)
        raise SystemExit(1)

    producer = KafkaProducer(bootstrap_servers=config.KAFKA_BOOTSTRAP_SERVERS)
    minio_client = make_minio_client()

    if not run_startup_checks(producer, minio_client):
        producer.close()
        raise SystemExit(1)

    consumer = KafkaConsumer(
        config.KAFKA_REQUEST_TOPIC,
        bootstrap_servers=config.KAFKA_BOOTSTRAP_SERVERS,
        group_id=config.KAFKA_CONSUMER_GROUP,
        enable_auto_commit=False,
        auto_offset_reset="earliest",
        # Обработка одного сообщения (реальная транскрибация + суммаризация)
        # синхронно блокирует цикл poll() и может занимать много минут —
        # max_poll_interval_ms должен быть больше PROCESSING_TIMEOUT_SECONDS,
        # иначе брокер выкидывает консьюмера из группы ещё до завершения
        # обработки, и последующий commit() падает с CommitFailedError.
        max_poll_interval_ms=(config.PROCESSING_TIMEOUT_SECONDS + 120) * 1000,
    )

    running = True

    def stop(signum, frame):
        nonlocal running
        log.info("Получен сигнал %s, завершаю после текущего сообщения...", signum)
        running = False

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)

    log.info(
        "Слушаю топик '%s', ответы пишу в '%s'",
        config.KAFKA_REQUEST_TOPIC,
        config.KAFKA_RESPONSE_TOPIC,
    )

    while running:
        batch = consumer.poll(timeout_ms=1000)
        for records in batch.values():
            for record in records:
                handle_record(record, minio_client, producer)
                try:
                    consumer.commit()
                except CommitFailedError:
                    # Ребаланс группы (например, из-за долгой обработки) успел
                    # забрать партицию у нас раньше, чем мы закоммитили офсет.
                    # Ответ в Kafka уже отправлен — не роняем весь сервис,
                    # просто логируем: при следующем ребалансе консьюмер
                    # получит актуальный офсет от новых владельцев партиции.
                    log.warning(
                        "Не удалось закоммитить офсет (группа перебалансировалась во время обработки)"
                    )
        if not running:
            break

    consumer.close()
    producer.close()


def handle_record(record, minio_client: Minio, producer: KafkaProducer) -> None:
    raw = record.value.decode("utf-8")
    try:
        req = RecognitionRequest(**json.loads(raw))
    except (json.JSONDecodeError, ValidationError) as e:
        log.error("Некорректное сообщение в '%s', пропускаю: %s", config.KAFKA_REQUEST_TOPIC, e)
        return

    log.info("[%s] Обработка, files=%s", req.messageId, req.files)
    try:
        response = process_message(req, minio_client)
        log.info("[%s] Готово, success=True", req.messageId)
    except ProcessingError as e:
        log.error("[%s] Ошибка обработки (%s): %s", req.messageId, e.code, e.message)
        response = build_error_response(req.messageId, e.code, e.message)
    except Exception as e:
        log.exception("[%s] Непредвиденная ошибка", req.messageId)
        response = build_error_response(req.messageId, ErrorCode.SERVICE_UNAVAILABLE, str(e)[:500])

    producer.send(config.KAFKA_RESPONSE_TOPIC, response.model_dump_json().encode("utf-8"))
    producer.flush()


if __name__ == "__main__":
    main()
