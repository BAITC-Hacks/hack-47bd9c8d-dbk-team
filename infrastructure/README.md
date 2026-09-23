# Инфраструктура ai-meeting-copilot

Всё для поднятия стека с нуля: локальный/MVP-запуск одной командой и
инфраструктурно-нейтральная документация для прод-развёртывания as code.

```
infrastructure/
├── README.md                     # этот файл
├── docker-compose.yml            # весь стек: traefik+LE, kafka, minio, kafka-ui, приложения
├── docker-compose.local.yml      # оверлей: локальный запуск без домена и traefik
├── local-up.sh                   # локальный стек одной командой
├── .env.example                  # шаблон конфигурации для прод/MVP с доменом
├── env.local.example             # шаблон конфигурации для локального запуска
├── kafka/
│   └── kafka-init.sh             # oneshot: создание топиков
├── minio/
│   ├── mc-init.sh                # oneshot: бакет + политика + app-юзер
│   └── copilot-uploads-rw.json   # политика rw только на бакет uploads
└── ansible/                      # документация для прод-развёртывания (IaC)
    ├── README.md                 # модель развёртывания + карта переменных/vault
    └── docs/
        ├── 00-architecture.md    # хосты, потоки данных, порты, зависимости
        ├── 01-kafka.md           # runbook Kafka (KRaft, SASL_SSL, Kafbat UI)
        ├── 02-minio.md           # runbook MinIO (TLS, mc-init, хост без egress)
        ├── 03-meeting-copilot.md # runbook воркера (startup checks, деплой, приёмка)
        └── 04-copilot-ui.md      # runbook тестовой веб-морды
```

## Два сценария использования

| Сценарий | Что использовать |
|---|---|
| Локальная разработка на своей машине (без домена) | `./local-up.sh` — см. «Локальный запуск» ниже |
| MVP на одной машине с публичным доменом и TLS | `docker-compose.yml` + `.env.example`, см. «Быстрый старт (MVP)» |
| Прод-развёртывание as code (ansible, systemd-юниты, vault) | `ansible/README.md` + runbook'и в `ansible/docs/` |

## Локальный запуск

Kafka, MinIO и их веб-интерфейсы на своей машине — одной командой:

```bash
cd infrastructure
./local-up.sh
```

Скрипт создаёт `.env` из `env.local.example` (если его ещё нет), поднимает
сервисы, дожидается их готовности, проверяет, что топики и бакет созданы,
и печатает адреса с паролями.

| Сервис | Адрес | Доступ |
|---|---|---|
| Kafka (с хоста) | `localhost:9094` | PLAINTEXT, без auth |
| Kafbat UI | http://localhost:8080 | `admin` / `KAFKA_UI_PASSWORD` |
| MinIO S3 API | http://localhost:9000 | `MINIO_APP_USER` / `MINIO_APP_PASSWORD` |
| MinIO консоль | http://localhost:9001 | `MINIO_ROOT_USER` / `MINIO_ROOT_PASSWORD` |

Все порты слушают только `127.0.0.1` — наружу стек не смотрит.

Остальные команды:

```bash
./local-up.sh down       # остановить, данные в томах сохранить
./local-up.sh destroy    # остановить и удалить тома (полный сброс)
./local-up.sh logs -f    # логи
```

Что делает оверлей `docker-compose.local.yml`: уводит traefik в профиль `tls`
(локально нет A-записей и открытых 80/443, Let's Encrypt всё равно не выпустит
сертификаты) и пробрасывает порты сервисов напрямую на loopback вместо
роутинга через traefik. Базовый `docker-compose.yml` не меняется — прод-сценарий
ниже работает как раньше.

Эквивалент без скрипта:

```bash
docker compose -f docker-compose.yml -f docker-compose.local.yml up -d \
  kafka kafka-init kafka-ui minio mc-init
```

### Подключение воркера

Креды локального стека уже прописаны в `meeting-copilot-container/.env.example`
(`KAFKA_BOOTSTRAP_SERVERS=localhost:9094`, `MINIO_ENDPOINT=localhost:9000`,
юзер `copilot-app`). Для запуска воркера с хоста:

```bash
cd ../meeting-copilot-container
cp .env.example .env
# подставить AI_KDB_TOKEN и OPEN_ROUTER_AUTH_BEARER
```

Если воркер поднимается контейнером в сети стека — заменить адреса на
внутренние: `kafka:9092` и `minio:9000`.

## Быстрый старт (MVP)

### Требования

- Docker с compose v2.
- **Публичный домен**: A-записи `traefik.`, `s3.`, `s3-console.`,
  `kafka-ui.`, `copilot.` → IP машины.
- Открытые порты 80 и 443 (HTTP-01 challenge Let's Encrypt).

> Полностью локально (без домена и открытых портов) LE не сработает.
> Для этого случая есть готовый override `docker-compose.local.yml` —
> см. «Локальный запуск без домена» ниже.

## Локальный запуск без домена (Mac/Linux, для разработки)

Override `docker-compose.local.yml` отключает traefik (профиль `tls`) и
пробрасывает сервисы на loopback; фронт (`front/`) подключается к общей
сети стека:

```bash
cd infrastructure
cp .env.example .env    # для локали достаточно дефолтов; DOMAIN=localhost
docker compose -f docker-compose.yml -f docker-compose.local.yml up -d

cd ../front
cp .env.example .env    # MINIO_* креды = креды из infrastructure/.env
docker compose -f docker-compose.yml -f docker-compose.local.yml up -d --build
```

Локальные точки входа:

| Сервис | URL |
|---|---|
| Фронт (Next.js) | `http://localhost:3000` |
| Kafbat UI | `http://localhost:8181` (admin / `KAFKA_UI_PASSWORD`) |
| MinIO console | `http://localhost:9001` (root-креды из `.env`) |
| MinIO S3 API | `http://localhost:9000` |
| Kafka с хоста | `localhost:9094` (PLAINTEXT) |

Особенности локали:

- **Apple Silicon (arm64)**: запиненный hotfix-образ MinIO собран только
  под amd64 — в `docker-compose.local.yml` для minio задан
  `platform: linux/amd64` (эмуляция OrbStack/Rosetta). На x86-машине
  строку можно убрать.
- Фронт использует контракт `meetings.*` / бакеты `recordings`,
  `results`; воркер — `AiMeetingCopilot*` / `uploads`. Оба набора
  создаются init-контейнерами (переменные `KAFKA_TOPICS`, `MINIO_BUCKETS`).

### Запуск

```bash
cd infrastructure
cp .env.example .env
# отредактировать .env: DOMAIN, ACME_EMAIL, пароли, KAFKA_CLUSTER_ID, токены, образы
docker compose up -d                    # инфраструктура: traefik, kafka, minio, kafka-ui
docker compose --profile app up -d      # + приложения: meeting-copilot, copilot-ui
```

Приложения вынесены в профиль `app`: инфраструктура поднимается без них
(удобно, когда образы воркера/UI ещё не собраны).

По умолчанию в `.env.example` стоит **staging CA** Let's Encrypt (без
rate-limit, сертификаты недоверенные) — сначала убедитесь, что выпуск
работает, затем переключите `LE_CA_SERVER` на боевой
(`https://acme-v02.api.letsencrypt.org/directory`) и удалите старые
сертификаты:

```bash
docker compose down
docker volume rm meeting-copilot_letsencrypt
docker compose up -d
```

`KAFKA_CLUSTER_ID` сгенерировать (base64-UUID ровно 22 символа):

```bash
docker run --rm apache/kafka:3.9.0 /opt/kafka/bin/kafka-storage.sh random-uuid
```

## Точки входа

| Сервис | URL | Доступ |
|---|---|---|
| S3 API | `https://s3.<DOMAIN>` | app-креды `MINIO_APP_USER`/`MINIO_APP_PASSWORD` |
| MinIO console | `https://s3-console.<DOMAIN>` | root-креды из `.env` |
| Kafbat UI | `https://kafka-ui.<DOMAIN>` | login `admin` / `KAFKA_UI_PASSWORD` |
| copilot-ui | `https://copilot.<DOMAIN>` | токен `COPILOT_UI_TOKEN` (если задан) |
| Traefik dashboard | `https://traefik.<DOMAIN>` | basic auth `TRAEFIK_DASHBOARD_AUTH` |
| Kafka с хоста | `localhost:9094` | PLAINTEXT, без auth (только loopback) |

Внутри сети compose сервисы ходят друг в друга по PLAINTEXT
(`kafka:9092`, `http://minio:9000`) — TLS терминируется на traefik
только для входящих снаружи соединений.

## Образы приложений

`meeting-copilot` и `copilot-ui` (профиль `app`) подтягиваются из
registry (`COPILOT_IMAGE`, `COPILOT_UI_IMAGE` в `.env`). Если исходники
рядом, замените `image:` на `build:` с контекстом приложения. Имена
переменных окружения в compose (`KAFKA_*`, `MINIO_*`, `AI_API_*`,
`OPEN_ROUTER_*`) — по мотивам `ansible/docs/03-meeting-copilot.md`;
сверьте с реальными именами в коде приложения и поправьте при
необходимости. `OPEN_ROUTER_URL` должен быть **полным** endpoint'ом
(включая `/v1/chat/completions`).

## Health check

```bash
docker compose ps                                   # kafka — (healthy), minio — Up, *-init — Exited (0)
docker compose logs --tail 30 meeting-copilot       # живая строка: "Слушаю топик 'AiMeetingCopilotRequest'..."
docker exec kafka /opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 --list
docker exec kafka /opt/kafka/bin/kafka-consumer-groups.sh --bootstrap-server localhost:9092 --describe --group ai-meeting-copilot
curl -s -o /dev/null -w '%{http_code}\n' https://s3.<DOMAIN>/minio/health/ready   # 200
```

Startup checks воркера: Kafka, MinIO, `AI_API_URL` — при недоступности
контейнер падает (exit 1) и рестартует (`restart: unless-stopped`).

## Приёмка (сквозной тест)

Через copilot-ui (`https://copilot.<DOMAIN>`): загрузить mp3/wav →
дождаться статуса `done` → скачать `transcript.json` / `summary.md`.
CLI-эквивалент — см. `ansible/docs/04-copilot-ui.md` (URL заменить на
`https://copilot.<DOMAIN>`).

Вручную через Kafka с хоста (listener на `localhost:9094`):

```bash
docker exec -i kafka /opt/kafka/bin/kafka-console-producer.sh --bootstrap-server localhost:9092 --topic AiMeetingCopilotRequest
docker exec kafka /opt/kafka/bin/kafka-console-consumer.sh --bootstrap-server localhost:9092 --topic AiMeetingCopilotResponse --from-beginning --max-messages 1
```

Пустой транскрипт `[]` на бесшумном/тональном аудио — не ошибка
пайплайна (см. known-ограничения в `ansible/docs/04-copilot-ui.md`).

## Смена кредов и конфигурации

- Пароли/токены: правка `.env` → `docker compose up -d` (compose
  пересоздаст контейнеры, т.к. env — часть конфигурации; в отличие от
  systemd-стека явный рестарт не нужен).
- Креды `copilot-app` в MinIO: mc-init **не обновляет** существующего
  юзера. Удалить и пересоздать:

```bash
docker exec minio mc alias set local http://localhost:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD"
docker exec minio mc admin user remove local copilot-app
docker compose up -d --force-recreate mc-init
```

- Политика `copilot-uploads-rw.json` привязана к бакету `uploads`:
  если меняете `MINIO_BUCKET`, поправьте `Resource` в JSON.

## Типовые проблемы

| Симптом | Причина | Лечение |
|---|---|---|
| traefik: сертификаты не выпускаются | DNS не указывает на машину / закрыт 80 порт / staging vs prod | проверить A-записи и `docker compose logs traefik`; начать со staging CA |
| kafka Restarting, `AccessDeniedException .../data` | права на volume | `docker compose down`, пересоздать volume `kafka-data` (локально userns-remap обычно выключен) |
| kafka не стартует, ругается на cluster.id | невалидный `KAFKA_CLUSTER_ID` | сгенерировать заново (команда выше), base64-UUID ровно 22 символа |
| Воркер Restarting (exit 1), `SERVICE_UNAVAILABLE` | недоступна startup-зависимость | `docker compose ps` — kafka/minio healthy? проверить `AI_API_URL` из контейнера |
| 403 от LLM-прокси | `OPEN_ROUTER_URL` без пути | указать полный endpoint `.../v1/chat/completions` в `.env` |
| mc-init failed, user exists | юзер есть с другим паролем | смена кредов — см. выше |
| Лаг растёт, воркер Up | медленный speech-to-text / большие файлы | `kafka-consumer-groups --describe` (команда выше) |
