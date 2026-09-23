# AiMeetingCopilot — Распознавание речи (.mp3, .wav и др.) на русском языке

Модуль для отправки и распознавания аудиофайлов встреч и записей (в форматах `.mp3`, `.wav`, `.ogg`, `.flac` и др.) с поддержкой русского, казахского и английского языков.

Поддерживаемый провайдер:
1. **ai.kdb.kz (Голосовой стек)** — корпоративный сервис распознавания речи (Whisper STT) с поддержкой маршрутизации моделей (`general` для русского/английского, `ksc2` для казахского).

развертывается через ci cd 
---

## 🏗 Архитектура и взаимодействие

Контейнер работает как асинхронный обработчик: он не принимает файлы напрямую,
а забирает их из MinIO по сигналу из Kafka и туда же возвращает результат.
Файлы передаются через MinIO, управление — через Kafka.

```
  ┌──────────────────┐
  │ Внешняя система  │
  │ (загрузка записи)│
  └────────┬─────────┘
           │ ① кладёт запись (аудио/видео + опц. *.transcript.vtt)
           │    в папку  s3://<bucket>/<prefix>/
           ▼
      ┌─────────┐                        ┌──────────────────────────┐
      │  MinIO  │                        │  Kafka                   │
      │ <prefix>│                        │  AiMeetingCopilotRequest │◄─── ② RecognitionRequest
      └────┬────┘                        │  AiMeetingCopilotResponse│      {messageId, files}
           │                             └───────────┬──────────────┘
           │ ③ скачать файлы папки                   │ ③ прочитать сообщение
           │                                         │
           ▼                                         ▼
  ┌────────────────────────────────────────────────────────────┐
  │        meeting-copilot-container (kafka_service.py)        │
  │                                                            │
  │   ④ entrypoint.sh: ffmpeg → mp3 → распознавание → склейка  │
  │                    → суммаризация                          │
  └───────┬──────────────────────────────────┬─────────────────┘
          │                                  │
          │ ④ HTTPS                          │ ④ HTTPS
          ▼                                  ▼
  ┌─────────────────────┐          ┌──────────────────────┐
  │                     │          │  LLM (OpenRouter-    │
  │   /api/whisper      │          │  совместимый API)    │
  │   /api/diar         │          │  → summary.md        │
  └─────────────────────┘          └──────────────────────┘

          ⑤ transcript.json + summary.md  →  та же папка MinIO
          ⑥ RecognitionResponse {messageId, success, errors}
             →  топик AiMeetingCopilotResponse
```

### Шаги обработки

1. **Загрузка записи.** Внешняя система кладёт файлы встречи в папку MinIO:
   аудио/видео (`.mp3`, `.m4a`, `.mp4`, `.wav`, `.ogg`, `.flac`, `.webm`) и,
   опционально, Zoom-субтитры `*.transcript.vtt` с именами говорящих.
2. **Сигнал в Kafka.** В топик `AiMeetingCopilotRequest` отправляется
   `RecognitionRequest` с `messageId` и `files` — ссылкой на эту папку
   (`s3://<bucket>/<prefix>/` либо просто `<prefix>/`, тогда берётся бакет
   `MINIO_BUCKET` из конфига).
3. **Приём задачи.** Контейнер читает сообщение из топика и скачивает **все**
   файлы папки во временную директорию. Аудио определяется по расширению,
   VTT — по суффиксу `.transcript.vtt`. Если папка пуста или аудио в ней нет,
   обработка прерывается с кодом `FILES_NOT_FOUND`.
4. **Обработка.** Запускается пайплайн `entrypoint.sh`: конвертация в MP3
   (`ffmpeg`) → распознавание речи в **ai.kdb.kz** (`/api/whisper`; если VTT не
   передан, дополнительно `/api/diar` для определения спикеров) → склейка
   реплик → суммаризация через LLM. Подробности шагов — в разделе
   «Полный пайплайн в Docker». На всю обработку одного сообщения действует
   таймаут `PROCESSING_TIMEOUT_SECONDS` (по умолчанию 1800 сек).
5. **Результат в MinIO.** Готовые артефакты `transcript.json` и `summary.md`
   заливаются обратно в **ту же папку**, откуда были взяты исходные файлы.
6. **Ответ в Kafka.** В топик `AiMeetingCopilotResponse` публикуется
   `RecognitionResponse` с тем же `messageId` и флагом `success`. При неудаче
   в `errors` приходит код: `FILES_NOT_FOUND`, `TIMEOUT` или
   `SERVICE_UNAVAILABLE`. Офсет Kafka коммитится только после отправки ответа,
   поэтому сообщение не теряется при падении на любом из шагов.

Промежуточные файлы (MP3, сырые ответы ai.kdb.kz, скачанные исходники) живут
во временной директории и удаляются после обработки сообщения — ни в MinIO, ни
в образе они не остаются.

### Проверки при старте

Перед тем как начать читать очередь, сервис проверяет доступность зависимостей
(`check_health_services.py`):

- **Kafka недоступна** — сервис логирует ошибку и завершается: отправить отчёт
  о проблеме некуда.
- **MinIO и/или ai.kdb.kz недоступны** — в `AiMeetingCopilotResponse` уходит
  `RecognitionResponse` с `messageId: "startup-check"` и списком ошибок, после
  чего сервис завершается, не начав обработку сообщений.

### Образы

| Образ | Dockerfile | Роль |
|---|---|---|
| CLI-пайплайн | `Dockerfile` | Разовый прогон одного файла: `docker compose run --rm copilot /data/call.mp4` |
| Kafka-воркер | `Dockerfile.service` | Постоянно работающий сервис, описанный выше (`kafka_service.py`) |

---

## 🚀 Установка и настройка

1. Установите зависимости:
```bash
pip install -r requirements.txt
```

2. Настройте файл `.env` (за основу возьмите `.env.example`)
---

## 🐳 Полный пайплайн в Docker: аудио (+VTT?) → summary.md

Контейнер принимает на вход аудио/видео файл (`.mp3`, `.m4a`/mp4a, `.mp4`) и,
опционально, VTT-файл Zoom с таймингами и именами говорящих:

1. **Проверка языка VTT** (если VTT передан) — если реплики целиком на
   английском (кириллица не встречается), шаги 2–3 (конвертация в MP3 и
   распознавание речи) пропускаются: текст берётся прямо из субтитров VTT.
2. **Конвертация в MP3** (`ffmpeg`) — если файл уже `.mp3`, просто копируется;
   для видео (`.mp4`) аудиодорожка извлекается автоматически.
3. **Транскрибация** — `curl` на `ai.kdb.kz/api/whisper/v1/audio/transcriptions`
   (`response_format=verbose_json`, нужны пословные тайминги `words`).
4. **Склейка** (`merge_transcript.py`):
   - если VTT передан — тайминги/говорящие берутся из VTT, текст — из
     JSON-транскрипции (либо, для англоязычного VTT, из самих субтитров);
   - если VTT **не передан** — спикеры определяются диаризацией ai.kdb.kz
     (`/api/diar/v1/audio/diarize`, модель Sortformer, до 4 голосов) и
     склеиваются с текстом JSON-транскрипции. Спикеры в этом случае
     безымянные — `Speaker 0`, `Speaker 1` и т.д. (id локальны для записи).
5. **Суммаризация** (`summarize_transcript.py`) — отправляет склеенный
   транскрипт в LLM (OpenRouter-совместимый эндпоинт) и получает `summary.md`.

⚠️ `ai.kdb.kz` не умеет декодировать `.m4a`/AAC (декодер на сервере на базе
`libsndfile`, он не поддерживает AAC) — конвертация в MP3 перед отправкой
обязательна для обоих эндпоинтов (`/api/whisper` и `/api/diar`), несмотря на
то что документация ai.kdb.kz заявляет обратное.

В общую папку сохраняются только финальные артефакты — `transcript.json` и
`summary.md`. Промежуточные файлы (`audio.mp3`, сырой ответ ai.kdb.kz) создаются
во временной директории и удаляются после завершения.

### Сборка и запуск

Через `docker-compose.yml`:

```bash
docker compose run --rm copilot /data/call.mp4 /data/call.transcript.vtt
```

Без VTT (спикеры — через диаризацию):

```bash
docker compose run --rm copilot /data/call.mp4
```

Результат появится в `artifacts/call/`:
`transcript.json`, `summary.md`.
---

## 📨 Контракт запроса/ответа (`model/models.py`)

Асинхронная обработка запускается сообщением с ссылкой на папку в MinIO,
результат обработки возвращается отдельным ответом с флагом успеха и (при
неудаче) списком ошибок. Контракты описаны pydantic-моделями в
`model/models.py`:

- **`RecognitionRequest`** — входящее сообщение: `messageId` + `files`
  (ссылка на папку в MinIO с файлами для распознавания).
- **`RecognitionResponse`** — ответ по итогам обработки: `messageId`,
  `success` и `errors` (список `RecognitionError` с полями `code`/`message`).
- **`ErrorCode`** — перечисление возможных кодов ошибок:
  - `SERVICE_UNAVAILABLE` — недоступен внешний сервис (ai.kdb.kz / OpenRouter);
  - `TIMEOUT` — превышено время ожидания обработки;
  - `FILES_NOT_FOUND` — папка MinIO не содержит нужных файлов.

Ниже — код моделей и примеры, сгенерированные напрямую из `model/models.py`
(см. `model/generate_examples.py`), чтобы контракт в README не расходился с
кодом. Перегенерировать после изменения моделей:

```bash
python3 model/generate_examples.py
```

**RecognitionRequest**

```python
class RecognitionRequest(BaseModel):
    messageId: str = Field(..., description="Идентификатор сообщения/запроса")
    files: str = Field(..., description="Ссылка на папку в MinIO с файлами для обработки")
```

**Пример RecognitionRequest**

```json
{
  "messageId": "1111",
  "files": "s3://uploads/2026-09-21/meeting-42/"
}
```

**RecognitionResponse**

```python
class ErrorCode(str, Enum):
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"
    TIMEOUT = "TIMEOUT"
    FILES_NOT_FOUND = "FILES_NOT_FOUND"

class RecognitionError(BaseModel):
    code: ErrorCode = Field(..., description="Код ошибки")
    message: str = Field(..., description="Текстовое описание ошибки")

class RecognitionResponse(BaseModel):
    messageId: str = Field(..., description="Идентификатор сообщения/запроса")
    success: bool = Field(..., description="Признак успешной обработки")
    errors: List[RecognitionError] = Field(default_factory=list, description="Список ошибок, если обработка завершилась неудачно")
```

**Пример RecognitionResponse (успех)**

```json
{
  "messageId": "1111",
  "success": true,
  "errors": []
}
```

**Пример RecognitionResponse (ошибка)**

```json
{
  "messageId": "1111",
  "success": false,
  "errors": [
    {
      "code": "FILES_NOT_FOUND",
      "message": "Папка MinIO не содержит нужных файлов"
    }
  ]
}
```
