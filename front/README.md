# front — веб-интерфейс AI Meeting Copilot

Развёрнут: **https://app.aibots.kz**

Next.js (App Router) + Tailwind v4 + shadcn-паттерн компонентов. Работает с конвейером meeting-copilot через Kafka и MinIO.

Между интерфейсом и обработчиком стоит `services/adapter` — он переводит события
`meetings.*` в формат обработчика (`AiMeetingCopilot*`) и собирает `result.json`
по схеме `.planning/tasks/CONTRACT.md`. Интерфейс обработчика не знает и знать
не должен.

Бакет записей на развёрнутом стенде — `uploads` (переменная `RECORDINGS_BUCKET`):
инфраструктура выдаёт права именно на него.

## Что умеет

0. Загрузка файла с необязательными субтитрами Zoom: после выбора записи
   появляется строка «Приложить .vtt». Файл кладётся в ту же папку MinIO под
   именем `<basename>.transcript.vtt` — обработчик ищет его именно по этому
   суффиксу и, найдя, берёт из него тайминги и имена говорящих вместо
   безымянной диаризации. Валидация расширения на клиенте и на сервере.
1. Живая запись (Сценарий 1): кнопка «Начать запись» → предупреждение
   участникам на двух языках (`public/audio-warnings/kaz.mp3`, затем
   `rus.mp3`) → поток с микрофона чанками по 5 с (`MediaRecorder`, webm/opus) через
   `/api/meetings/start|chunk|finish` → сборка в MinIO
   `recordings/<meeting_id>/live.webm` → событие `meetings.uploaded` в Kafka.
2. Загрузка записи (mp3/m4a/mp4/wav/ogg/flac/webm) → MinIO `recordings/<meeting_id>/`,
   событие `meetings.uploaded` в Kafka.
3. Опрос статуса: события `meetings.ready` / `meetings.failed` (consumer в
   `instrumentation.ts` → in-memory стор; запасной вариант — probe
   `results/<meeting_id>/result.json` в MinIO).
4. Протокол: транскрипт с говорящими, таблица поручений (ответственный, срок,
   суть, статус, уверенность), саммари. `warnings[]` и `confidence: low`
   показываются явно — это фича, не баг.
5. Уведомление «Ведётся запись и транскрибация с помощью ИИ» — постоянная
   плашка (Сценарий 1 кейса).
6. Контроль поручений (Сценарий 2): вкладка «Контроль поручений» —
   все поручения всех обработанных совещаний, сортировка по сроку,
   просроченные подсвечены, «осталось N дн.» для ближайших. Данные —
   `GET /api/commitments` (in-memory агрегат результатов, которые сервер
   уже отдавал; в MOCK_MODE — демо-набор с просроченным поручением).
7. Экспорт на клиенте: DOCX (`lib/export-docx.ts`) и PDF через печать
   (`components/printable-protocol.tsx`, кириллица безопасна — шрифты
   системные).

Живая запись защищена от потерь: чанки нумеруются, сервер при `/finish`
проверяет непрерывность последовательности (409 + список пропущенных),
клиент досылает пропавшие из памяти; неудачная отправка чанка повторяется
один раз; «Отменить» сбрасывает сессию через `/api/meetings/[id]/cancel`.

## Структура

```
app/                  Next.js App Router
  api/meetings/       POST загрузка; [id]/status, [id]/result
  api/health/         проверка конфигурации
components/           экраны + ui/ примитивы (shadcn-паттерн)
lib/                  config, kafka, minio, store, types (контракт), export-docx
mock/                 sample-result.json для MOCK_MODE
instrumentation.ts    запуск Kafka-consumer'а при старте Node runtime
```

## Запуск локально

```bash
cp .env.example .env    # заполнить MINIO_ACCESS_KEY / MINIO_SECRET_KEY
npm install
npm run dev             # http://localhost:3000
```

Без инфраструктуры (демо-режим на моках):

```bash
MOCK_MODE=true npm run dev
```

## Деплой в инфраструктуру

```bash
cp .env.example .env    # KAFKA_BROKERS=kafka:9092, MINIO_ENDPOINT=minio, ключи
docker compose up -d --build
```

Compose-файл подключается к внешней сети `meeting-copilot_web` (создаётся
`infrastructure/docker-compose.yml`) и вешает traefik-роут `app.${DOMAIN}`.
Для локальной проверки без traefik: `docker compose up` и `docker port` /
`ports: ["8181:3000"]` добавить при необходимости.

## Ограничения

- Статусы в памяти процесса (как и у reference copilot-ui): после рестарта
  фронта незавершённые задачи видны только через probe MinIO.
- Чанки живой записи буферизуются в памяти процесса до «Завершить запись» —
  один инстанс фронта на запись; при рестарте процесса недошедшие чанки теряются.
- Файл загружается через API-роут целиком в память — для записей больше
  ~500 МБ нужен presigned upload (сознательно не делали на хакатоне).
- Ключи — только в `.env` (gitignored). В git не коммитить.
