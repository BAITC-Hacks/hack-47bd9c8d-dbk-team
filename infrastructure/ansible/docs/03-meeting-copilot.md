# Runbook: ai-meeting-copilot (Kafka-воркер)

## Профиль сервиса

| Параметр | Значение |
|---|---|
| Каталог стека | `/opt/meeting-copilot` (на хосте группы `meeting_copilot` / `app`) |
| Контейнер | `meeting-copilot` (headless-воркер, никакого web) |
| Юниты systemd | `meeting-copilot.service` (up -d / down), `meeting-copilot-deploy.service` (pull + up -d) |
| Образ | `<REGISTRY>/<project>/ai-meeting-copilot:main` (сборка из `Dockerfile.service` в CI) |
| Конфиг | `/opt/meeting-copilot/.env` (из vault, 0600) — AI_*, OPEN_ROUTER_*, MINIO_*, KAFKA_* |
| Назначение | слушает `AiMeetingCopilotRequest`, тянет аудио из MinIO (бакет `uploads`), транскрибирует (`<AI_API_URL>` + LLM-прокси), результат в MinIO, ответ в `AiMeetingCopilotResponse` |
| Зависимости | docker.service, kafka, MinIO, `<AI_API_URL>`, `<LLM_PROXY_URL>` |

Критичность: средняя. Воркер лежит → задачи копятся в
`AiMeetingCopilotRequest`, обработка возобновляется после рестарта
(consumer group, auto-offset reset latest — см. код воркера).

## Health check

```bash
# контейнер + последние логи:
ansible -i inventory.ini meeting_copilot -m ansible.builtin.shell -a 'cd /opt/meeting-copilot && docker compose ps && docker logs meeting-copilot --tail 30'

# живой признак: строка в логах
#   "Слушаю топик 'AiMeetingCopilotRequest', ответы пишу в 'AiMeetingCopilotResponse'"
# и отсутствие рестартов контейнера (exit 1 = упали startup checks / зависимости).

# рестарты за последний час:
ansible -i inventory.ini meeting_copilot -m ansible.builtin.shell -a 'docker inspect meeting-copilot --format "{{.RestartCount}}"'
```

Startup checks при старте: Kafka, MinIO (`<S3_API_FQDN>:443`),
`<AI_API_URL>` (`/api/whisper/health`). Если любая недоступна —
контейнер делает exit 1 и рестартует (`restart: unless-stopped`).

## Деплой

Через CI (рекомендуется): push в main → job `build` собирает и пушит
`<REGISTRY>/<project>/ai-meeting-copilot:main` → manual job `deploy`
выполняет на хосте `meeting-copilot-deploy.service` (pull + up -d).

Переменные CI/CD проекта: `DEPLOY_SSH_KEY` — тип **Variable**, base64
(`base64 -w0 ~/.ssh/deploy_ci`) приватного ключа deploy-пользователя
app-хоста, Protected (+Masked). Deploy-job сам декодирует его в
`/tmp/deploy_key`. При смене ключа — перевыпустить переменную заново
(значение скрыто после сохранения).

Вручную (когда CI недоступен):

```bash
ssh -p <SSH_PORT> -i ~/.ssh/deploy_ci deploy@<APP_HOST> meeting-copilot
```

Смена токенов/переменных: правка `vault_meeting_copilot_env_content`
в `group_vars/<ENV>/vault.yml` → прогон роли
(`ansible-playbook --limit meeting_copilot site.yml`) → рестарт.
**Compose не отслеживает изменение .env** — нужен явный рестарт:

```bash
ansible -i inventory.ini meeting_copilot -m ansible.builtin.shell -a 'systemctl restart meeting-copilot.service'
```

## Типовые проблемы

| Симптом | Причина | Лечение |
|---|---|---|
| Restarting (exit 1), в логах `SERVICE_UNAVAILABLE` | одна из startup-зависимостей недоступна | проверить Kafka, `<S3_API_FQDN>`, `<AI_API_URL>` по health check выше |
| `getaddrinfo failed: <S3_API_FQDN>` | обрыв DNS | проверить резолвинг на хосте и внутри контейнера: `docker exec meeting-copilot python -c "import socket; print(socket.gethostbyname('<S3_API_FQDN>'))"` |
| 401/403 от `<AI_API_URL>` при обработке | неверный/протухший токен (`AI_*_TOKEN`) | обновить vault (`EDITOR=nano ansible-vault edit group_vars/<ENV>/vault.yml`) → прогон роли → рестарт |
| 401 от LLM-прокси | неверный `OPEN_ROUTER_AUTH_BEARER` | то же |
| 403 Forbidden от LLM-прокси в `SERVICE_UNAVAILABLE` | `OPEN_ROUTER_URL` без пути — код шлёт POST **на URL как есть**, нужен полный endpoint | в vault: `OPEN_ROUTER_URL=<LLM_PROXY_URL>` включая `/v1/chat/completions` → прогон роли → рестарт |
| deploy-юнит падает на `compose pull` с 401 | docker login осиротел/токен отозван | пересоздать pull-токен (read_registry) в registry → обновить `vault_registry_pull_token` → прогон роли (login-задача + `/root/.docker/config.json`) |
| CI deploy: `ssh: connect to host ... port 22: Operation timed out` | sshd на таргетах слушает `<SSH_PORT>`, не 22 | в ssh-команде джобы должен быть `-p <SSH_PORT>`; forced-command `deploy-run` принимает только имя приложения, остальное — `unknown app` |
| MinIO 403 на uploads | креды `copilot-app` не совпадают с s3-хостом | сверить `vault_s3_copilot_env_content` (MINIO_APP_USER/ключ) и `vault_meeting_copilot_env_content` |
| Лаг растёт, воркер Up | медленный speech-to-text API / большие файлы | посмотреть `kafka-consumer-groups --describe` (см. `01-kafka.md`) |

## Приёмка после деплоя

Быстро: тестовая веб-морда copilot-ui (см. `04-copilot-ui.md`) — один
реальный звуковой файл, дождаться `done` и скачать артефакты.

Вручную: отправить тестовый запрос в `AiMeetingCopilotRequest`
(аудио-файл заранее в бакете `uploads`) и дождаться записи в
`AiMeetingCopilotResponse`:

```bash
# producer на app-хосте (JSON сообщения — см. схему в репо приложения):
docker exec -i kafka /opt/kafka/bin/kafka-console-producer.sh --bootstrap-server localhost:9092 --topic AiMeetingCopilotRequest

# ответ:
docker exec kafka /opt/kafka/bin/kafka-console-consumer.sh --bootstrap-server localhost:9092 --topic AiMeetingCopilotResponse --from-beginning --max-messages 1
```
