#!/usr/bin/env python3
"""
Проверки доступности зависимостей kafka_service.py: Kafka, MinIO и речевая
служба. Используются при старте сервиса, чтобы не начинать обработку
сообщений с заведомо неработающими зависимостями.

Речевая служба выбирается в config.DEFAULT_PROVIDER:
    speech_stack - свой стек (stt.aibots.kz): пробы /health и /health/diar,
                   это независимые блоки конфигурации, проверяются обе;
    kdb          - ai.kdb.kz: проба /api/whisper/health.
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


# Шлюз speech_stack стоит за Cloudflare, который отдаёт 403 на User-Agent
# по умолчанию у python-клиентов.
USER_AGENT = "dbk-meeting-copilot/1.0"

SPEECH_STACK_PROVIDERS = ("speech_stack", "speech-stack", "stt", "aibots")


def _check_speech_stack_probe(path: str, label: str) -> Optional[str]:
    """
    Дёргает пробу шлюза speech_stack. Пробы идут до проверки токена и
    спрашивают реальную службу, а не отвечают 200 сами.
    """
    url = f"{config.SPEECH_STACK_URL.rstrip('/')}{path}"
    try:
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=10)
        resp.raise_for_status()
        payload = resp.json()
    except Exception as e:
        return f"{label} недоступна ({url}): {e}"

    # Диаризация до загрузки моделей честно отвечает loading — это не
    # готовность, ждать надо именно смены статуса, а не появления процесса.
    status = payload.get("status")
    if status and status != "healthy":
        return f"{label} отвечает, но не готова: status={status} ({url})"
    return None


def _check_speech_stack_token() -> Optional[str]:
    """
    Проверяет, что токен принимается: GET /v1/models.

    Пробы /health идут ДО проверки токена и проходят с любым — даже с пустым.
    Без этой проверки сервис стартовал бы с неверным STT_TOKEN и падал бы
    только на первой записи, уже потратив время на скачивание и конвертацию.
    """
    url = f"{config.SPEECH_STACK_URL.rstrip('/')}/v1/models"
    try:
        resp = requests.get(
            url,
            headers={
                "Authorization": f"Bearer {config.SPEECH_STACK_TOKEN}",
                "User-Agent": USER_AGENT,
            },
            timeout=10,
        )
    except Exception as e:
        return f"Речевой стек недоступен ({url}): {e}"

    if resp.status_code == 401:
        return (
            f"Речевой стек отклонил STT_TOKEN ({url}, HTTP 401). "
            "Шлюз закрывает 401 и неизвестные пути, так что проверьте заодно "
            "SPEECH_STACK_URL."
        )
    if resp.status_code != 200:
        return f"Речевой стек ответил HTTP {resp.status_code} на {url}: {resp.text[:200]}"
    return None


def check_speech_stack() -> Optional[str]:
    """
    Проверяет собственный речевой стек: распознавание, диаризацию и токен.

    Распознавание и диаризация — разные блоки конфигурации и ломаются
    независимо, поэтому проверяются обе пробы, а не одна.
    """
    if not config.SPEECH_STACK_TOKEN:
        return (
            "Не задан STT_TOKEN — речевой стек "
            f"({config.SPEECH_STACK_URL}) не сконфигурирован"
        )

    for path, label in (("/health", "Проба распознавания"), ("/health/diar", "Проба диаризации")):
        error = _check_speech_stack_probe(path, label)
        if error:
            return error

    return _check_speech_stack_token()


def check_kdb() -> Optional[str]:
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


def check_whisper() -> Optional[str]:
    """Проверяет ту речевую службу, которая выбрана в DEFAULT_PROVIDER."""
    if config.DEFAULT_PROVIDER.lower() in SPEECH_STACK_PROVIDERS:
        return check_speech_stack()
    return check_kdb()


def speech_provider_label() -> str:
    """Человекочитаемое имя выбранной речевой службы — для логов и ошибок."""
    if config.DEFAULT_PROVIDER.lower() in SPEECH_STACK_PROVIDERS:
        return f"speech_stack ({config.SPEECH_STACK_URL})"
    return f"ai.kdb.kz ({config.AI_KDB_URL})"


def run_startup_checks(producer: KafkaProducer, minio_client: Minio) -> bool:
    """
    Проверяет Kafka, MinIO и речевую службу перед началом обработки.
    Kafka уже проверена раньше (иначе продюсера бы не было) — здесь только
    MinIO и распознавание, ошибки по которым можно и нужно отправить в Kafka.
    Возвращает True, если можно продолжать работу.
    """
    speech_label = speech_provider_label()
    errors = []
    for label, error in (
        ("MinIO", check_minio(minio_client)),
        (speech_label, check_whisper()),
    ):
        if error:
            errors.append(RecognitionError(code=ErrorCode.SERVICE_UNAVAILABLE, message=error))
            log.critical("Проверка '%s' не пройдена: %s", label, error)

    if not errors:
        log.info("Проверка зависимостей (Kafka/MinIO/%s) пройдена успешно", speech_label)
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
