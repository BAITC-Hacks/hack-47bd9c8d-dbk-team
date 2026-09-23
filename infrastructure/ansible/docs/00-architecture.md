# Архитектура и потоки данных

## Хосты

| Роль | Группа inventory | Что крутится |
|---|---|---|
| app-хост | `app` (или раздельно `kafka`, `meeting_copilot`) | Kafka, Kafbat UI, meeting-copilot, copilot-ui |
| s3-хост | `s3` | MinIO, mc-init (oneshot), traefik |

Топология не зашита: Kafka, воркер и MinIO могут жить как на одном, так
и на разных хостах — связность задаётся переменными (FQDN/IP хостов в
inventory и group_vars).

**Важно про s3-хост:** у него может не быть egress в интернет. Образы
на него доставлять либо из внутреннего registry (`<REGISTRY>`, должен
быть доступен с s3-хоста), либо переносом `docker save | docker load`
с хоста, где egress есть.

## Поток данных (happy path)

1. Клиент кладёт аудиофайл в S3-бакет `uploads` на `<S3_API_FQDN>`.
2. Клиент отправляет в топик `AiMeetingCopilotRequest` сообщение
   `{"messageId": "...", "files": "s3://uploads/..."}`.
3. Воркер (consumer group `ai-meeting-copilot`) забирает задачу,
   скачивает аудио из MinIO.
4. Воркер транскрибирует через внешние сервисы:
   - `<AI_API_URL>` — whisper-compatible API распознавания речи;
   - `<LLM_PROXY_URL>` — OpenAI-compatible прокси для summary.
5. Результат (`transcript.json`, `summary.md`) кладётся в MinIO,
   в топик `AiMeetingCopilotResponse` уходит ответ.

## Порты

| Сервис | Порт | Протокол / доступ |
|---|---|---|
| Kafka internal | 9092 | PLAINTEXT, без auth — только для локальных воркера/UI |
| Kafka external | 9093 | SASL_SSL (TLS + PLAIN), логин/пароль из vault |
| Kafbat UI | 8181 | HTTP, login form (admin / пароль из vault) |
| copilot-ui | 8080 | HTTP, опциональный токен `COPILOT_UI_TOKEN` |
| MinIO API | 443 | HTTPS через traefik, `<S3_API_FQDN>` |
| MinIO console | 443 | HTTPS через traefik, `<S3_CONSOLE_FQDN>` |
| sshd на таргетах | `<SSH_PORT>` | нестандартный порт, forced-command для `deploy` |

## Внешние зависимости

| Зависимость | Переменная | Падение приводит к |
|---|---|---|
| Registry | `<REGISTRY>` | невозможность деплоя/обновления образов |
| S3 API | `<S3_API_FQDN>` | воркер не скачивает аудио / не кладёт результат |
| Speech-to-text API | `<AI_API_URL>` (`/api/whisper/health` — healthcheck) | startup check воркера падает, exit 1 |
| LLM-прокси | `<LLM_PROXY_URL>` | startup check / обработка падают |

## Критичность

- **Kafka — высокая.** Лежит → воркер не получает задач, запросы висят
  без обработки.
- **MinIO — средняя.** Лежит → задачи падают с ошибкой, воркер жив.
- **Воркер — средняя.** Лежит → задачи копятся в
  `AiMeetingCopilotRequest`; после рестарта обработка возобновляется
  (consumer group, auto-offset reset latest).

## CI/CD-модель (опционально, но рекомендуется)

- push в main → job `build` собирает образ из `Dockerfile.service` и
  пушит `<REGISTRY>/<project>/ai-meeting-copilot:main`.
- manual job `deploy` по SSH (`-p <SSH_PORT>`, ключ из CI-переменной
  `DEPLOY_SSH_KEY`, тип Variable, base64 приватного ключа, Protected
  + Masked) вызывает forced-command `deploy-run <app>`.
- При смене ключа переменную перевыпускают заново: значение скрыто
  после сохранения.
