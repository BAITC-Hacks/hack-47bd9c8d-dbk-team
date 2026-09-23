import os
from pathlib import Path
from dotenv import load_dotenv

# Загружаем переменные окружения из .env файла, если он существует
load_dotenv()

BASE_DIR = Path(__file__).resolve().parent

# Провайдер распознавания речи и диаризации:
#   speech_stack - собственный стек команды (stt.aibots.kz), исходники в
#                  speech_stack/ в корне репозитория;
#   kdb          - корпоративный голосовой стек ai.kdb.kz.
# Различаются путями ручек и именем токена, см. transcribers/factory.py
# и entrypoint.sh.
DEFAULT_PROVIDER = os.getenv("DEFAULT_PROVIDER", "speech_stack")

# Настройки собственного речевого стека (speech_stack/).
# Распознавание и диаризация живут за одним шлюзом и одним токеном:
#   POST /v1/audio/transcriptions  - речь -> текст (OpenAI-совместимо)
#   POST /v1/audio/diarize         - кто когда говорил
#   GET  /health, /health/diar     - пробы, токен не нужен
# Неизвестные пути шлюз тоже закрывает 401, поэтому снаружи не виден даже
# состав ручек.
# Имена переменных исторически разошлись: документация стека говорит
# STT_TOKEN, а рабочий .env команды — STT_API_KEY/STT_BASE_URL. Принимаем оба,
# чтобы копилот заводился с любым из них.
SPEECH_STACK_URL = os.getenv("SPEECH_STACK_URL") or os.getenv("STT_BASE_URL") or "https://stt.aibots.kz"
SPEECH_STACK_TOKEN = os.getenv("STT_TOKEN") or os.getenv("STT_API_KEY") or ""
# Языки распознавания: ru | kk | en | auto. auto возвращает route и
# detected_language, но детектору разрешён белый список — на шумной записи
# argmax по всем языкам whisper уходит к соседям казахского и модель начинает
# сочинять. Если язык известен, задавайте его явно.
SPEECH_STACK_LANGUAGE = os.getenv("SPEECH_STACK_LANGUAGE", "")
# Собственные имена через запятую — повышают точность ФИО в расшифровке.
SPEECH_STACK_HOTWORDS = os.getenv("SPEECH_STACK_HOTWORDS", "")

# Языковая модель для суммаризации: своя, OpenAI-совместимая (vllm.aibots.kz).
# Требование кейса — текст совещания не покидает контур, поэтому внешние
# облачные LLM запрещены. Имена OPEN_ROUTER_* оставлены как запасные: на них
# настроены старые .env.
VLLM_BASE_URL = os.getenv("VLLM_BASE_URL") or os.getenv("OPEN_ROUTER_URL") or ""
VLLM_API_KEY = os.getenv("VLLM_API_KEY") or os.getenv("OPEN_ROUTER_AUTH_BEARER") or ""
VLLM_MODEL = os.getenv("VLLM_MODEL") or os.getenv("OPEN_ROUTER_MODEL") or "qwen3-vl-30b-instruct"

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

# Настройки по умолчанию (DEFAULT_PROVIDER задаётся выше, рядом с настройками
# провайдеров)
DEFAULT_LANGUAGE = os.getenv("DEFAULT_LANGUAGE", "ru")
