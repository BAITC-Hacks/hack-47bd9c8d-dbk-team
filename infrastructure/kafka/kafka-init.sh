#!/bin/sh
# Идемпотентное создание топиков приложения.
# Список — через KAFKA_TOPICS (пробел-сепаратор); дефолт покрывает оба
# контракта: воркер (AiMeetingCopilot*) и фронт (meetings.*).
set -eu

BOOTSTRAP=kafka:9092
TOPICS=${KAFKA_TOPICS:-"AiMeetingCopilotRequest AiMeetingCopilotResponse meetings.uploaded meetings.ready meetings.failed"}

for TOPIC in $TOPICS; do
  /opt/kafka/bin/kafka-topics.sh --bootstrap-server "$BOOTSTRAP" \
    --create --if-not-exists --topic "$TOPIC" \
    --partitions 1 --replication-factor 1
done

echo "kafka-init: топики созданы"
/opt/kafka/bin/kafka-topics.sh --bootstrap-server "$BOOTSTRAP" --list
