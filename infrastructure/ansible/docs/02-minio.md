# Runbook: MinIO (S3 для ai-meeting-copilot)

## Профиль сервиса

| Параметр | Значение |
|---|---|
| Каталог стека | `/opt/s3` (на хосте группы `s3`) |
| Контейнеры | `minio` (сервер), `mc-init` (oneshot: юзер+политика+бакет), `traefik` |
| Юниты systemd | `s3.service` (up -d / down), `s3-deploy.service` (pull + up -d) |
| Данные | `/opt/s3/data` — рекомендуется **отдельный LV** (например 10G) |
| Образы | `quay.io/minio/minio:<pin>`, traefik v3.x — запинены в compose-шаблоне |
| API | `https://<S3_API_FQDN>` (443, TLS через traefik) |
| Консоль | `https://<S3_CONSOLE_FQDN>` |
| Бакет | `uploads` (аудио и результаты воркера) |
| Юзеры | `copilot-app` (rw только на `uploads`, политика `copilot-uploads-rw`), root — из vault |
| Назначение | S3-хранилище ai-meeting-copilot; не связан с container registry |
| Зависимости | docker.service; от minio зависит воркер meeting-copilot |

Критичность: средняя. MinIO лёг → воркер не может скачать аудио и
положить результат, задачи падают с ошибкой (воркер жив, ждёт).

## ВАЖНО: хост без egress

Если у s3-хоста нет выхода в интернет, `docker compose pull` с
внешних реестров (quay.io/dockerhub) падает с connection refused.
Образы доставлять:

- из внутреннего registry (`<REGISTRY>`), доступного с s3-хоста, или
- переносом `docker save | docker load` с хоста, где egress есть.

## TLS

Traefik терминирует TLS сертификатом из `/opt/s3/certs` (wildcard
домена или отдельный серт под оба FQDN). Следить за сроком действия:
при истечении клиенты получают x509-ошибки. Обновление = положить
свежий сертификат в `/opt/s3/certs`, рестарт traefik.

DNS: у всех потребителей должны резолвиться `<S3_API_FQDN>` и
`<S3_CONSOLE_FQDN>` в адрес s3-хоста (A-записи у администратора DNS).

## Health check

```bash
# контейнеры (minio, traefik — Up (healthy); mc-init — exited 0, это норма):
ansible -i inventory.ini s3 -m ansible.builtin.shell -a 'cd /opt/s3 && docker compose ps'

# API снаружи (TLS валидный, без -k), 200 = жив:
curl -s -o /dev/null -w '%{http_code}\n' https://<S3_API_FQDN>/minio/health/ready

# консоль:
curl -s -o /dev/null -w '%{http_code}\n' https://<S3_CONSOLE_FQDN>
```

## Деплой

```bash
ssh -p <SSH_PORT> -i ~/.ssh/deploy_ci deploy@<S3_HOST> s3
```

mc-init идемпотентен: пересоздаёт политику/юзера только если их нет,
бакет — `--ignore-existing`. Рестарт стека безопасен.

Смена кредов `copilot-app`: правка `vault_s3_copilot_env_content`
(MINIO_APP_USER/MINIO_APP_PASSWORD) → прогон роли → **вручную**
обновить креды на MinIO (`mc admin user add` в mc-init не обновляет
существующего юзера) → рестарт. Проще: удалить юзера
`docker exec minio mc admin user remove local copilot-app` и
перезапустить стек — mc-init пересоздаст с новыми кредами из vault.

## Типовые проблемы

| Симптом | Причина | Лечение |
|---|---|---|
| `docker compose pull` падает (connection refused) | нет egress с s3-хоста | перенос образов save/load или внутренний registry (см. выше) |
| mc-init failed, в логах user exists | юзер уже есть с другим кредом | `docker exec minio mc admin user remove local copilot-app`, рестарт стека |
| x509 при обращении к `<S3_API_FQDN>` | сертификат в `/opt/s3/certs` истёк | положить свежий сертификат в `/opt/s3/certs`, рестарт traefik |
| Воркер: `getaddrinfo failed` | нет DNS-записи | A-запись `<S3_API_FQDN>` → адрес s3-хоста (админ DNS) |
| Диск переполнен | аудио/результаты копятся | почистить старые объекты в консоли или mc; следить за `df -h /opt/s3/data` |
