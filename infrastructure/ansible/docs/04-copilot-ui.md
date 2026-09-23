# Runbook: copilot-ui (тестовая веб-морда)

Ручной сквозной тест пайплайна «файл → транскрипт + summary» без
kafka-console-гуляний. **Тестовый инструмент, не прод-API**: состояние
в памяти контейнера, переживает только рестарт worker'а, не UI.

## Профиль сервиса

| Поле | Значение |
|---|---|
| URL | `http://<APP_HOST>:8080` (прямой порт, прокси не нужен) |
| Токен | `COPILOT_UI_TOKEN` из vault (опционален: если пустой — токен не требуется) |
| Юниты systemd | `copilot-ui.service`, `copilot-ui-deploy.service` |
| Стек | `/opt/copilot-ui/`: compose + `app/` (Flask, образ собирается **на хосте**, в registry не хранится) |
| .env | `vault_copilot_ui_env_content` (KAFKA_*, MINIO_*, COPILOT_UI_TOKEN; MinIO-secret тот же `copilot-app`, что у воркера) |
| Зависимости в образе | `flask`, `kafka-python-ng` (NG-форк! классический `kafka-python==2.0.2` ломается на Python 3.12: `kafka.vendor.six.moves`) |

## Как пользоваться

Открыть URL → вставить токен → выбрать mp3/m4a/mp4/wav/…
(+ опциональный `*.transcript.vtt`) → «Отправить». Файл уходит в
`s3://uploads/ui/<дата>/<id>/`, в `AiMeetingCopilotRequest` уходит
`{"messageId": "ui-…", "files": "s3://uploads/…"}`, UI фоном читает
`AiMeetingCopilotResponse` и рисует статус + даёт скачать
`transcript.json`/`summary.md`.

CLI-эквивалент:

```bash
T=$(ansible-vault view group_vars/<ENV>/vault.yml | grep COPILOT_UI_TOKEN= | cut -d= -f2)
curl -X POST -H "X-Token: $T" -F audio=@meet.mp3 http://<APP_HOST>:8080/api/jobs
curl -H "X-Token: $T" http://<APP_HOST>:8080/api/jobs/<messageId>            # status: processing/done/failed
curl -H "X-Token: $T" http://<APP_HOST>:8080/api/jobs/<messageId>/files/summary.md
```

## Деплой и смена конфигурации

```bash
ssh -p <SSH_PORT> -i ~/.ssh/deploy_ci deploy@<APP_HOST> copilot-ui
```

Смена переменных: правка `vault_copilot_ui_env_content` → прогон роли
→ `systemctl restart copilot-ui` (compose не отслеживает изменение
.env, как и у воркера).

## Known-ограничения

- Статус `fail` после рестарта UI для старых job (состояние в памяти).
- Бесшумное/тональное аудио → пустой транскрипт `[]` (LLM честно
  отвечает «расшифровка пустая» — это **не** ошибка пайплайна).
