---
owner: anton
branch: ingest
status: ready
files:
  - services/ingest/**
contract: .planning/tasks/CONTRACT.md
design: docs/designs/meeting-protocol-agent.md
case: docs/TASK/task.md
---

# anton — ingest-service: вся обработка записи

Читай сначала контракт, там схема `result.json`, топики, бакеты и грабли ASR.

## Конвейер внутри сервиса
1. Событие `meetings.uploaded` из Kafka → забираешь объект из MinIO бакета `recordings`.
2. **ASR**: `verbose_json`, `language=auto`, `hotwords` из карточки. `prompt` НЕ передавать.
3. **Диаризация**: та же запись, отдельный вызов `/api/diar`. Это пункт 6 минимума.
4. **Склейка**: слово отдаёшь тому, кто говорил в его СЕРЕДИНЕ.
5. **Агент** на OpenAI Agents SDK, `base_url` → `https://llm.aibots.kz/v1`, модель
   `qwen3-8-27b-fp8`. Тулы: `resolve_speakers`, `verify_speakers`, `extract_commitments`,
   `make_summary`. Агент сам решает, когда переспросить модель и когда пометить привязку
   неуверенной — это и есть agentic-слой, за него критерий на 25 баллов.
6. `result.json` в бакет `results`, событие `meetings.ready` в Kafka. Ошибка → `meetings.failed`
   с полем `stage`, чтобы UI показал, на чём упало.

## Границы
- PDF/DOCX **не твои** — их собирает UI на клиенте.
- Kafka не взлетает за 30 минут → зовём прямым HTTP, схему `result.json` не меняем.

## Готово, когда
Одна запись проходит путь целиком и в `results` лежит `result.json` по схеме контракта,
с непустыми `transcript`, `speakers`, `commitments`, `summary`.
