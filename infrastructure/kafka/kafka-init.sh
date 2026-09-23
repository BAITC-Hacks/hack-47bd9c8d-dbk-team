#!/bin/sh
# Идемпотентное создание топиков приложения.
set -eu

BOOTSTRAP=kafka:9092

for TOPIC in AiMeetingCopilotRequest AiMeetingCopilotResponse; do
  /opt/kafka/bin/kafka-topics.sh --bootstrap-server "$BOOTSTRAP" \
    --create --if-not-exists --topic "$TOPIC" \
    --partitions 1 --replication-factor 1
done

echo "kafka-init: топики созданы"
/opt/kafka/bin/kafka-topics.sh --bootstrap-server "$BOOTSTRAP" --list
