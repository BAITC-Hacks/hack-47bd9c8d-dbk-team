#!/usr/bin/env bash
# Поднимает локальный стек одной командой: Kafka + Kafbat UI + MinIO + консоль.
#
#   ./local-up.sh            поднять стек и дождаться готовности
#   ./local-up.sh down       остановить (данные в томах сохраняются)
#   ./local-up.sh destroy    остановить и удалить тома (полный сброс)
#   ./local-up.sh logs       логи всех сервисов
#
# Traefik и Let's Encrypt не используются — см. docker-compose.local.yml.
set -euo pipefail

cd "$(dirname "$0")"

COMPOSE=(docker compose -f docker-compose.yml -f docker-compose.local.yml)
# Долгоживущие сервисы — их ждём по healthcheck.
DAEMONS=(kafka kafka-ui minio)
# Oneshot-контейнеры (топики, бакет) — завершаются сразу, их проверяем по коду выхода.
ONESHOTS=(kafka-init mc-init)

case "${1:-up}" in
  down)
    "${COMPOSE[@]}" down
    exit 0
    ;;
  destroy)
    "${COMPOSE[@]}" down -v
    exit 0
    ;;
  logs)
    shift
    "${COMPOSE[@]}" logs "$@"
    exit 0
    ;;
  up) ;;
  *)
    echo "Использование: $0 [up|down|destroy|logs]" >&2
    exit 1
    ;;
esac

if [ ! -f .env ]; then
  cp env.local.example .env
  echo "[*] Создан .env из env.local.example"
fi

echo "[*] Поднимаю: ${DAEMONS[*]} ${ONESHOTS[*]}"
# Сначала всё: compose сам соблюдает depends_on (kafka-init и mc-init
# стартуют после того, как их зависимости готовы).
"${COMPOSE[@]}" up -d "${DAEMONS[@]}" "${ONESHOTS[@]}"

# --wait только по долгоживущим: для oneshot-контейнеров штатный выход
# засчитывается как падение, и вся команда вернула бы ненулевой код.
"${COMPOSE[@]}" up -d --wait "${DAEMONS[@]}"

# Oneshot'ы проверяем по коду возврата: без топиков и бакета стек бесполезен.
for job in "${ONESHOTS[@]}"; do
  for _ in $(seq 60); do
    read -r state code <<<"$("${COMPOSE[@]}" ps -a --format '{{.Service}} {{.State}} {{.ExitCode}}' \
      | awk -v s="$job" '$1==s {print $2, $3}')"
    [ "${state:-}" = "exited" ] && break
    sleep 1
  done
  if [ "${state:-}" != "exited" ] || [ "${code:-1}" != "0" ]; then
    echo "[!] $job: state=${state:-?}, код выхода ${code:-?}" >&2
    "${COMPOSE[@]}" logs --no-log-prefix "$job" >&2
    exit 1
  fi
done

# shellcheck disable=SC1091
. ./.env

cat <<EOF

[+] Стек поднят.

  Kafka (с хоста)   localhost:9094            PLAINTEXT, без auth
  Kafbat UI         http://localhost:8080     admin / ${KAFKA_UI_PASSWORD}
  MinIO S3 API      http://localhost:9000     ${MINIO_APP_USER} / ${MINIO_APP_PASSWORD}
  MinIO консоль     http://localhost:9001     ${MINIO_ROOT_USER} / ${MINIO_ROOT_PASSWORD}

  Бакет: ${MINIO_BUCKET}
  Топики: AiMeetingCopilotRequest, AiMeetingCopilotResponse

  Эти же значения лежат в meeting-copilot-container/.env.example —
  скопируйте его в .env воркера и добавьте AI_KDB_TOKEN / OPEN_ROUTER_AUTH_BEARER.
EOF
