#!/usr/bin/env python3
"""
Проверки доступности зависимостей kafka_service.py: Kafka, MinIO, ai.kdb.kz
(whisper). Используются при старте сервиса, чтобы не начинать обработку
сообщений с заведомо неработающими зависимостями.
"""

import logging
from typing import Optional

import requests
from kafka import KafkaConsumer, KafkaProducer
from minio import Minio

import config
from model.models import ErrorCode, RecognitionError, RecognitionResponse

log = logging.getLogger("kafka_service")

# messageId, под которым в KAFKA_RESPONSE_TOPIC уходит ошибка стартовых
# проверок (Kafka/MinIO/ai.kdb.kz) — само сообщение не привязано к
# конкретному RecognitionRequest, т.к. до успешного старта их ещё не читали.
STARTUP_CHECK_MESSAGE_ID = "startup-check"


def check_kafka() -> Optional[str]:
    """Проверяет, что брокер отвечает на metadata-запрос. None = всё ок."""
    try:
        probe = KafkaConsumer(
            bootstrap_servers=config.KAFKA_BOOTSTRAP_SERVERS,
            request_timeout_ms=5000,
            api_version_auto_timeout_ms=5000,
        )
        probe.topics()
        probe.close()
        return None
    except Exception as e:
        return f"Kafka недоступна ({config.KAFKA_BOOTSTRAP_SERVERS}): {e}"


def check_minio(client: Minio) -> Optional[str]:
    try:
        if not client.bucket_exists(config.MINIO_BUCKET):
            return f"Бакет MinIO '{config.MINIO_BUCKET}' не найден на {config.MINIO_ENDPOINT}"
        return None
    except Exception as e:
        return f"MinIO недоступен ({config.MINIO_ENDPOINT}): {e}"


def check_whisper() -> Optional[str]:
    """Проверяет голосовой стек ai.kdb.kz через /api/whisper/health."""
    if not config.AI_KDB_TOKEN:
        return "Не задан AI_KDB_TOKEN — сервис распознавания ai.kdb.kz не сконфигурирован"
    try:
        resp = requests.get(
            f"{config.AI_KDB_URL.rstrip('/')}/api/whisper/health",
            headers={"Authorization": f"Bearer {config.AI_KDB_TOKEN}"},
            timeout=10,
        )
        resp.raise_for_status()
        return None
    except Exception as e:
        return f"Сервис распознавания ai.kdb.kz недоступен ({config.AI_KDB_URL}): {e}"


def run_startup_checks(producer: KafkaProducer, minio_client: Minio) -> bool:
    """
    Проверяет Kafka, MinIO и ai.kdb.kz (whisper) перед началом обработки.
    Kafka уже проверена раньше (иначе продюсера бы не было) — здесь только
    MinIO и whisper, ошибки по которым можно и нужно отправить в Kafka.
    Возвращает True, если можно продолжать работу.
    """
    errors = []
    for label, error in (
        ("MinIO", check_minio(minio_client)),
        ("ai.kdb.kz (whisper)", check_whisper()),
    ):
        if error:
            errors.append(RecognitionError(code=ErrorCode.SERVICE_UNAVAILABLE, message=error))
            log.critical("Проверка '%s' не пройдена: %s", label, error)

    if not errors:
        log.info("Проверка зависимостей (Kafka/MinIO/ai.kdb.kz) пройдена успешно")
        return True

    response = RecognitionResponse(
        messageId=STARTUP_CHECK_MESSAGE_ID,
        success=False,
        errors=errors,
    )
    producer.send(config.KAFKA_RESPONSE_TOPIC, response.model_dump_json().encode("utf-8"))
    producer.flush()
    log.critical(
        "Стартовые проверки провалены, ошибка отправлена в '%s'. Сервис не запущен.",
        config.KAFKA_RESPONSE_TOPIC,
    )
    return False
