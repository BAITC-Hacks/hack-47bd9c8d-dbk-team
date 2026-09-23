# zoom-ingest — записи Zoom → конвейер meeting-copilot

Два режима попадания записи встречи в конвейер (MinIO `recordings/` →
Kafka `meetings.uploaded` → протокол в UI). Оба эмитят один и тот же
контракт события (`front/lib/types.ts` → `UploadedEvent`), поэтому
конвейер и фронт не меняются.

## Режим 1. poll — облачная запись постфактум (по техспеке)

После завершения встречи забирает из Zoom Cloud Recording аудио (M4A,
фолбэк MP4) и VTT-транскрипт. Подробности и ограничения:
`docs/tecspec/zoom-cloud-recording.md`.

```bash
cp .env.example .env   # заполнить ZOOM_* и MINIO_*
pip install -r requirements.txt
python -m zoom_ingest poll --dry-run   # что нашлось, без скачивания
python -m zoom_ingest poll --once      # один проход
python -m zoom_ingest poll             # цикл с ZOOM_POLL_INTERVAL_SEC
```

Дедупликация — `state.json` в бакете `zoom-ingest` (обработанные UUID).
meeting_id: `zoom-<id>-<UTC YYYYMMDDTHHMMSS>`.

## Режим 2. bot — участник встречи (live-запись)

Бот входит во встречу через веб-клиент Zoom в headless Chromium и пишет
смикшированный аудиопоток с виртуального звукового устройства. Когда
встреча завершается (или истекает `--max-minutes`), файл уходит в MinIO
и в Kafka уходит событие — дальше протокол собирается автоматически.

```bash
docker build -f Dockerfile.bot -t zoom-bot .
docker run --rm --env-file .env zoom-bot \
  "https://zoom.us/j/12345678901?pwd=XXX" --name "ИИ-секретарь (запись)"
```

meeting_id: `zoom-live-<id>-<UTC YYYYMMDDTHHMMSS>`, файл
`recordings/<meeting_id>/live.webm` (opus).

Ограничения бота:

- Микрофона у бота нет — пишется только то, что звучит во встрече;
  для протокола этого достаточно.
- Хост должен пустить бота из зала ожидания, если она включена.
- Селекторы веб-клиента Zoom периодически меняются — `bot.py` пробует
  несколько стабильных вариантов, но это самая хрупкая часть.
- Юридически: участники должны знать о записи — имя бота это показывает,
  а фронт дополнительно играет аудио-предупреждение (Сценарий 1).

## Тесты

```bash
python -m pytest tests/ -q
```

## Что дальше (v2)

- Webhook `recording.completed` вместо поллинга (нужен публичный endpoint;
  `ZOOM_WEBHOOK_SECRET_TOKEN` уже предусмотрен в конфиге).
- Подстановка VTT-имён говорящих в конвейер (`transcript_key` в событии).
