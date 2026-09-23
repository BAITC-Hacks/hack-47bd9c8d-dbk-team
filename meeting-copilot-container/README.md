# AiMeetingCopilot — Распознавание речи (.mp3, .wav и др.) на русском языке

Модуль для отправки и распознавания аудиофайлов встреч и записей (в форматах `.mp3`, `.wav`, `.ogg`, `.flac` и др.) с поддержкой русского, казахского и английского языков.

Поддерживаемый провайдер:
1. **ai.kdb.kz (Голосовой стек)** — корпоративный сервис распознавания речи (Whisper STT) с поддержкой маршрутизации моделей (`general` для русского/английского, `ksc2` для казахского).

развертывается через ci cd 
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
