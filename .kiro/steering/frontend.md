---
description: Front-end stack and UI/UX rules for the hackathon demo web app.
paths:
  - template/**
  - app/**
  - components/**
topics:
  - UI
  - UX
  - design system
  - frontend
  - styling
---

# Frontend Steering — стек и правила UI/UX

Источники: `HACKATHON.md` (секции 4-5), `.codex/hooks.json`, `tools/deploy.sh`.

## Стек

- **Next.js + AI Elements** (React/shadcn чат-компоненты) — основа демо-UI.
  Шаблон `template/`: готовый чат со stub-агентом в `app/api/chat/route.ts`,
  реальный SSE-стрим без ключа (описан в `HACKATHON.md`, секция 4;
  в репо каталог появится в день X — до этого факты по файлам не выдумывать).
- В день X заглушка в `app/api/chat/route.ts` меняется на OpenAI Agents SDK
  (выданные на площадке OpenAI-ключи, см. `AGENTS.md` → Models).
- Стили — через shadcn/Tailwind из состава AI Elements; отдельный
  CSS-фреймворк не добавлять.

## UI/UX процесс (impeccable)

- Весь UI-трек ведёт скилл `$impeccable`: дизайн-направление, исполнение,
  дизайн-QA. Его хуки уже подключены в `.codex/hooks.json`:
  PostToolUse (проверка после каждого Edit/Write/apply_patch) и
  Stop (финальный deep pass).
- Режим поверхности выбирается по задаче: демо-чат — **Operate**
  (scanability, консистентность важнее выразительности); лендинг для
  жюри, если появится, — **Persuade**.
- QA строго ограничен: один батчевый проход (desktop + mobile вместе),
  один батч правок, максимум один подтверждающий круг — и стоп.
  **Working demo beats polish** (`HACKATHON.md`).

## Правила

- Не выдумывать пользователей, метрики и фичи — только то, что реально
  работает в демо (правило README из `HACKATHON.md`).
- Никаких API-ключей в коде и GitHub: ключи только в `.env` (gitignored),
  проверять `git status` перед push.
- Дизайн-решения фиксировать в `DESIGN.md`/surface briefs impeccable,
  а не размазывать по steering-файлам.

## Деплой и проверка

- Деплой: `tools/deploy.sh` → docker-server (`git pull --ff-only` +
  `docker compose up -d --build`), приложение на порту 8181,
  публичный URL — https://app.aibots.kz.
- Перед сдачей: репетиция деплоя + прогон демо-сценария на deployed-версии,
  ссылка на https://app.aibots.kz обязательна в финальном README.

## Guardrails

- Keep this file focused; move unrelated rules to another domain file.
- Record only decisions and conventions that are actually enforced.
- Обновлять этот файл в том же коммите, что и изменение стека/процесса UI.
