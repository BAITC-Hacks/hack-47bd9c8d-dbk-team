# Контракт — правит ТОЛЬКО лид. Старт 13:30.

Кейс: `docs/TASK/task.md`. Решение: `docs/designs/meeting-protocol-agent.md`.

## Железное правило
**Аудио и текст совещания не уходят во внешние облака.** Требование постановки и ограничение
кейса. Все модели — свои. OpenAI только в Codex при разработке, не в инференсе по содержанию.

## Архитектура (зафиксирована 23.09)
```
UI (Руслан)  ──Kafka events──►  ingest-service (Антон)  ──►  MinIO
     ▲                                │
     │ статус, ссылки                 ├─► ASR        ai.kdb.kz/api/whisper
     └────────────────────────────────┤─► диаризация ai.kdb.kz/api/diar
                                      └─► LLM        llm.aibots.kz  qwen3-8-27b
```
Экспорт PDF/DOCX — **на клиенте, в UI** (решение D2).
Агент на OpenAI Agents SDK живёт **внутри ingest-service** (решение D3).

## Сервисы и владельцы
| Ветка | Владелец | Зона записи |
|---|---|---|
| `ingest` | Антон | `services/ingest/**`, схема событий |
| `ui` | Руслан | `ui/**`, экспорт PDF/DOCX |
| `main` | лид | `docker-compose.yml`, деплой, мерджи, README |

## Эндпоинты и ключи (в .env, в git НЕ едут)
| Что | Адрес | Переменная |
|---|---|---|
| ASR | `https://ai.kdb.kz/api/whisper/v1/audio/transcriptions` | `KDB_GATEWAY_TOKEN` |
| Диаризация | `https://ai.kdb.kz/api/diar/v1/audio/diarize` | `KDB_GATEWAY_TOKEN` |
| LLM | `https://llm.aibots.kz/v1` модель `qwen3-8-27b-fp8` | `LLM_API_KEY` |
| MinIO | `minio:9000` | `MINIO_ROOT_USER` / `MINIO_ROOT_PASSWORD` |
| Kafka | `redpanda:9092` | — |

## Kafka-топики
- `meetings.uploaded` — появилась запись. `{meeting_id, object_key, filename, lang_hint}`
- `meetings.ready` — готово. `{meeting_id, result_key, protocol_key}`
- `meetings.failed` — ошибка. `{meeting_id, stage, error}`

## MinIO-бакеты
- `recordings` — исходные записи
- `results` — `<meeting_id>/result.json`

## ASR — грабли, не изобретать заново
- `response_format=verbose_json` — нужны ПОСЛОВНЫЕ метки, иначе склейка невозможна.
- `language=auto` — определяет язык одним шагом, возвращает `route` и `detected_language`.
  Шала-казахский держится на этом. Доля казахских букв как признак проверена и отвергнута.
- `hotwords` — ФИО участников через запятую.
- **`prompt` НЕ использовать** — замерено, CER растёт до 0.194.
- **Длительность брать из файла**, поле `duration` врёт (274 с → вернуло 16).

## Склейка ASR + диаризации
Расшифровать запись ЦЕЛИКОМ, диаризовать ту же запись отдельно, каждое слово отдать тому,
кто говорил **в его СЕРЕДИНЕ**. Не в начале: на стыке реплик начало слова попадает в хвост
предыдущего говорящего. Резать аудио на сегменты — хуже, теряется контекст.

## Потолок диаризации
Модель различает **ровно четыре голоса**, пятый сливается. Это архитектура модели.
`verify_speakers` сверяет диаризацию с текстовым каналом (упоминание в третьем лице
доказывает, что говорит НЕ этот человек), кладёт находку в `warnings[]` и ставит
`confidence: low` затронутым поручениям. Это наша ставка на оригинальность — показывать,
а не прятать.

## Схема `result.json` — контракт между ingest и UI
```json
{
  "meeting_id": "m-001",
  "transcript": [{"speaker":"SPK_1","name":"Нурлан Сагатович","t_start":0.0,"t_end":4.2,"text":"..."}],
  "speakers":   [{"label":"SPK_1","name":"Нурлан Сагатович","resolved_by":"text","merged":false}],
  "commitments":[{"id":"c1","assignee":"Гульмира Сериковна","assignee_speaker":"SPK_2",
                  "due_date":"2026-10-15","due_raw":"до 15 октября",
                  "text":"подготовить смету по второму корпусу",
                  "quote":"Ответственный Гульмира Сериковна. Срок до 15 октября.",
                  "t_start":412.8,"confidence":"high","status":"in_progress"}],
  "summary": "...",
  "warnings": ["Ярлык SPK_3 похоже объединяет двух участников, точка раздела ~612.4 с"]
}
```
`confidence`: `high` | `low`. `status`: `in_progress` | `overdue` | `done`.

## Правила дня
- Пуш **раз в час** со своей машины. Старт 13:30 → 14:30, 15:30, 16:30, 17:30.
- Мерж в main каждые 30-40 минут, конфликт резолвит лид.
- В 4:15 от старта — код-фриз.
- `bash tools/hackathon-watcher.sh "13:30"` у каждого.
