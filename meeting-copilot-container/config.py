import os
from pathlib import Path
from dotenv import load_dotenv

# Загружаем переменные окружения из .env файла, если он существует
load_dotenv()

BASE_DIR = Path(__file__).resolve().parent

# Настройки голосового стека ai.kdb.kz
AI_KDB_URL = os.getenv("AI_KDB_URL", "https://ai.kdb.kz")
AI_KDB_TOKEN = os.getenv("AI_KDB_TOKEN", "")
AI_KDB_IP = os.getenv("AI_KDB_IP", "")

# Настройки MinIO (хранилище входных/выходных файлов)
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "localhost:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "")
MINIO_BUCKET = os.getenv("MINIO_BUCKET", "uploads")
MINIO_SECURE = os.getenv("MINIO_SECURE", "false").lower() == "true"

# Настройки Kafka (входящие/исходящие сообщения RecognitionRequest/RecognitionResponse)
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
KAFKA_REQUEST_TOPIC = os.getenv("KAFKA_REQUEST_TOPIC", "AiMeetingCopilotRequest")
KAFKA_RESPONSE_TOPIC = os.getenv("KAFKA_RESPONSE_TOPIC", "AiMeetingCopilotResponse")
KAFKA_CONSUMER_GROUP = os.getenv("KAFKA_CONSUMER_GROUP", "ai-meeting-copilot")

# Таймаут обработки одного сообщения (сек) — после него пайплайн прерывается
# и в Kafka уходит RecognitionResponse с ошибкой TIMEOUT
PROCESSING_TIMEOUT_SECONDS = int(os.getenv("PROCESSING_TIMEOUT_SECONDS", "1800"))

# Настройки по умолчанию
DEFAULT_LANGUAGE = os.getenv("DEFAULT_LANGUAGE", "ru")
DEFAULT_PROVIDER = os.getenv("DEFAULT_PROVIDER", "kdb")
