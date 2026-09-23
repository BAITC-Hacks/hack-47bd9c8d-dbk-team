#!/bin/sh
# Идемпотентный bootstrap MinIO: бакет + политика + app-юзер.
# Повторный запуск безопасен: существующие объекты не перезаписываются.
# ВНИМАНИЕ: смена пароля существующего юзера здесь НЕ происходит —
# см. README («Смена кредов»).
set -eu

until mc alias set local "http://minio:9000" "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" > /dev/null 2>&1; do
  echo "mc-init: жду minio..."
  sleep 2
done

# MINIO_BUCKETS — все нужные бакеты (пробел-сепаратор); дефолт = MINIO_BUCKET.
# Контракт фронта: recordings + results; воркера: uploads.
BUCKETS=${MINIO_BUCKETS:-$MINIO_BUCKET}
for BUCKET in $BUCKETS; do
  mc mb --ignore-existing "local/$BUCKET"
done

mc admin policy create local copilot-uploads-rw /policy/copilot-uploads-rw.json \
  || mc admin policy add local copilot-uploads-rw /policy/copilot-uploads-rw.json

if ! mc admin user info local "$MINIO_APP_USER" > /dev/null 2>&1; then
  mc admin user add local "$MINIO_APP_USER" "$MINIO_APP_PASSWORD"
fi

mc admin policy attach local copilot-uploads-rw --user "$MINIO_APP_USER" \
  || mc admin policy set local copilot-uploads-rw "user=$MINIO_APP_USER"

echo "mc-init: готово (buckets=$BUCKETS, user=$MINIO_APP_USER)"
