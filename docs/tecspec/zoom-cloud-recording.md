# Техспека: ингест записей Zoom через Cloud Recording API

Статус: к реализации. Исполнитель: агент. Креды Zoom API готовит владелец
аккаунта (см. раздел «Креды»).

## Цель

После завершения Zoom-встречи автоматически забрать её запись (аудио +
транскрипт VTT) и прогнать через существующий конвейер meeting-copilot
(MinIO `recordings/<meeting_id>/` → Kafka `meetings.uploaded` → протокол в UI).

## Выбранный подход

Zoom Cloud Recording через REST API с Server-to-Server OAuth.
Бот-участник **не** реализуем: REST API не умеет подключаться во встречу,
а Meeting SDK (headless Linux, raw audio, recording consent) не поднимается
в окно хакатона. Забираем готовую облачную запись постфактум.

## Предусловия и ограничения

- Работает только для встреч, где владелец Zoom-аккаунта — **хост**
  (или у приложения admin-скоупы на весь аккаунт).
- Нужен **платный тариф** Zoom (Pro+): на Basic нет cloud recording.
- Хост должен включить запись в облако; для VTT — включить
  «Audio transcript» в настройках записи аккаунта.
- Запись появляется в API с задержкой (обычно 1-10 минут после встречи).
- Live-сценарий невозможен этим методом — только пост-обработка.

## Креды (готовит человек, не агент)

В Zoom Marketplace → Develop → Build App → **Server-to-Server OAuth**:

- `ZOOM_ACCOUNT_ID`, `ZOOM_CLIENT_ID`, `ZOOM_CLIENT_SECRET` — добавить в
  `.env` и `.env.example` (пустые значения).
- Granular scopes приложения:
  - `cloud_recording:read:list_user_recordings`
  - `cloud_recording:read:recording`
  - `user:read:list_users` (резолв userId хоста)
- После создания приложение надо активировать (activation на странице app).

## Архитектура

Новый сервис `services/zoom-ingest/` (Python, минимум зависимостей:
`httpx`, `boto3`, `confluent-kafka` или `aiokafka` — по аналогии с тем, что
уже использует конвейер). Запускается как отдельный контейнер в
`infrastructure/docker-compose.yml` либо как CLI-скрипт для демо
(`python -m zoom_ingest.poll --once`).

Режим работы — **поллинг** (вебхук `recording.completed` опционален и
выносится за рамки v1: требует публичного endpoint и верификации URL
на стороне Zoom).

### Поток данных (один проход поллера)

1. OAuth: `POST https://zoom.us/oauth/token?grant_type=account_credentials&account_id=$ZOOM_ACCOUNT_ID`,
   Basic auth из client_id:client_secret → `access_token` (TTL ~1 ч,
   кэшировать в памяти, обновлять по 401/истечении).
2. Список встреч: `GET /v2/users/{userId}/recordings?from=<date>&to=<date>&page_size=300`
   (пагинация `next_page_token`). `userId` — хост; S2S не поддерживает
   `me` — резолвить через `GET /v2/users` или брать из `ZOOM_USER_ID`.
3. Для каждой встречи с `recording_files` в статусе `completed`:
   пропустить, если `uuid` уже в state (дедупликация).
4. Скачать файлы по `download_url?access_token=<token>`:
   - аудио `file_type=M4A` (если нет — `MP4`);
   - транскрипт `file_type=TRANSCRIPT` (VTT, если включён).
5. Загрузить в MinIO: `recordings/<meeting_id>/<filename>` и рядом
   `recordings/<meeting_id>/transcript.vtt` (если есть).
6. Отправить в Kafka событие `meetings.uploaded` строго по контракту
   (`front/lib/types.ts` → `UploadedEvent`):
   `{meeting_id, object_key, filename, lang_hint}`. `lang_hint` — из
   настроек Zoom-аккаунта или `auto`.
7. Обновить state (см. ниже), залогировать результат.

### meeting_id

`zoom-<meeting_id>-<recording_start UTC:YYYYMMDDTHHMMSS>` — детерминированно,
читаемо в UI, устойчиво к повторным записям одной встречи.

### Дедупликация / state

JSON-объект в MinIO `zoom-ingest/state.json`: список обработанных
`uuid` записей + timestamp последнего успешного прохода. При недоступности
MinIO — падать с ошибкой, не дублировать события.

## Конфигурация (env)

| Переменная | Назначение |
|---|---|
| `ZOOM_ACCOUNT_ID` / `ZOOM_CLIENT_ID` / `ZOOM_CLIENT_SECRET` | S2S OAuth |
| `ZOOM_USER_ID` | email/ID хоста, чьи записи забираем |
| `ZOOM_POLL_INTERVAL_SEC` | период поллинга, default 120 |
| `ZOOM_LOOKBACK_DAYS` | глубина окна `from`, default 1 |
| `KAFKA_BROKERS`, `MINIO_ENDPOINT`, `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY` | как у остальных сервисов стека |

## Edge cases

- `uuid` встречи может содержать `/` и `//` — при обращении к API по UUID
  его надо двойно URL-encode; мы используем UUID только как ключ
  дедупликации, в API по UUID не ходим.
- Встреча без включённой записи просто не появится в ответе — это норма.
- `recording_files` со статусом `processing` — пропустить, подхватится
  на следующем проходе.
- 401 → один раз обновить токен и повторить; 429 → backoff
  (Retry-After, min 5 c).
- Несколько сессий записи одной встречи → несколько наборов
  `recording_files`, каждый обрабатываем как отдельный meeting_id.

## VTT и имена говорящих

v1: VTT только складывается в MinIO рядом с аудио (контракт события не
меняем — он используется фронтом и конвейером). v1.1 (опционально, после
согласования): добавить в `UploadedEvent` поле `transcript_key` и учесть
его в конвейере для подстановки имён говорящих вместо диаризации.

## Тестирование

- Юнит-тесты поллера с моком `httpx`: парсинг ответа recordings,
  дедупликация, маппинг file_type → filename, формирование события.
- Ручной сценарий (с реальными кредами): создать встречу на 1 минуту,
  включить запись в облако + audio transcript, завершить, дождаться
  прохода поллера → проверить объект в MinIO, событие в Kafka (kafbat UI)
  и готовый протокол в UI.

## Definition of done

- [ ] `services/zoom-ingest/` с poller'ом, Dockerfile, README.
- [ ] Env-переменные в `.env.example` и `infrastructure/.env.example`.
- [ ] Сервис в compose (профиль, чтобы не ломать демо без кредов).
- [ ] Юнит-тесты на моках зелёные.
- [ ] Ручной прогон: запись реальной встречи дошла до протокола в UI.

## Out of scope

- Бот-участник через Meeting SDK / raw audio capture.
- Вебхуки Zoom (`recording.completed`) — v2, нужен публичный endpoint.
- RTMP-рестрим, live-транскрибация.
- Local recording (файлы на машине хоста) — API их не отдаёт.
