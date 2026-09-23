# Инфраструктура ai-meeting-copilot as code

Документация для поднятия стека **с нуля** на произвольной инфраструктуре.
Никаких конкретных IP, доменов и корпоративных имён здесь нет — все
окружение-зависимые значения вынесены в переменные (см. «Карта переменных»).

> Для локального/MVP-запуска на одной машине используйте готовый
> docker-compose стек уровнем выше — см. `../README.md`.

## Компоненты

| Компонент | Назначение | Документ |
|---|---|---|
| Kafka (KRaft, single-broker) | очередь задач воркера | `docs/01-kafka.md` |
| Kafbat UI | веб-морда для Kafka | `docs/01-kafka.md` |
| MinIO (+ traefik) | S3-хранилище аудио и результатов | `docs/02-minio.md` |
| meeting-copilot | headless Kafka-воркер транскрибации | `docs/03-meeting-copilot.md` |
| copilot-ui | тестовая веб-морда сквозного теста | `docs/04-copilot-ui.md` |

Архитектура, потоки данных и топология хостов: `docs/00-architecture.md`.

## Модель развёртывания

- Каждый стек = каталог `/opt/<stack>` на таргете с `docker-compose.yml`
  и `.env` (0600, рендерится из ansible-vault).
- Каждый стек управляется двумя systemd-юнитами:
  - `<app>.service` — `docker compose up -d` / `down`;
  - `<app>-deploy.service` — `docker compose pull && up -d`.
- Деплой снаружи — по SSH под выделенным пользователем `deploy` через
  forced-command (`deploy-run`), который принимает **только имя
  приложения** и запускает соответствующий `<app>-deploy.service`.
  Любая другая команда отвечает `unknown app`.
- SSH на таргетах слушает нестандартный порт (переменная `ssh_port`) —
  все ssh-команды и CI-джобы обязаны указывать `-p {{ ssh_port }}`.
- Секреты — только в `group_vars/<env>/vault.yml` (ansible-vault).
  Несекретные переменные — в `group_vars/<env>/vars.yml`.

## Карта переменных

Все плейсхолдеры вида `<...>` в документах соответствуют переменным:

| Плейсхолдер | Пример переменной | Назначение |
|---|---|---|
| `<APP_HOST>` | группа `app` в inventory | хост Kafka + воркера + UI |
| `<S3_HOST>` | группа `s3` в inventory | хост MinIO (без egress в интернет!) |
| `<REGISTRY>` | `registry_url` | container registry с образом воркера |
| `<S3_API_FQDN>` | `minio_api_domain` | публичный FQDN S3 API (TLS) |
| `<S3_CONSOLE_FQDN>` | `minio_console_domain` | FQDN веб-консоли MinIO |
| `<KAFKA_FQDN>` | `kafka_tls_cn` | CN/SAN сертификата брокера для внешнего листенера |
| `<AI_API_URL>` | `ai_api_url` | endpoint сервиса транскрибации (whisper-compatible) |
| `<LLM_PROXY_URL>` | `llm_proxy_url` | **полный** endpoint LLM-прокси (`.../v1/chat/completions`) |
| `<SSH_PORT>` | `ssh_port` | нестандартный порт sshd на таргетах |
| `<ENV>` | имя окружения | `group_vars/<ENV>/...` |

Vault-переменные (содержимое `.env`-файлов и секреты):

| Vault-переменная | Что рендерит |
|---|---|
| `vault_meeting_copilot_env_content` | `/opt/meeting-copilot/.env` (AI_*, OPEN_ROUTER_*, MINIO_*, KAFKA_*) |
| `vault_copilot_ui_env_content` | `/opt/copilot-ui/.env` (KAFKA_*, MINIO_*, COPILOT_UI_TOKEN) |
| `vault_kafka_sasl_env_content` | `/opt/kafka/.env` (JAAS + пароль keystore) |
| `vault_kafka_tls_server_p12_b64` | PKCS12 keystore брокера (base64) |
| `vault_kafka_ui_env_content` | `/opt/kafka-ui/.env` (SPRING_SECURITY_USER_PASSWORD) |
| `vault_s3_copilot_env_content` | креды app-юзера MinIO (MINIO_APP_USER/PASSWORD) |
| `vault_registry_pull_token` | токен pull-доступа к registry (docker login на таргетах) |

## Порядок поднятия с нуля

1. Подготовить хосты: docker, userns-remap, sshd на `<SSH_PORT>`,
   пользователь `deploy` + forced-command, отдельный LV под данные MinIO.
2. `docs/02-minio.md` — MinIO (нужен воркеру и UI).
3. `docs/01-kafka.md` — Kafka + топики + Kafbat UI.
4. `docs/03-meeting-copilot.md` — воркер.
5. `docs/04-copilot-ui.md` — тестовая морда и приёмка сквозным тестом.
