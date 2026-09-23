import json

from kafka import KafkaProducer


class Events:
    """Kafka producer for the meetings.uploaded contract (front/lib/types.ts)."""

    def __init__(self, brokers: list[str], topic_uploaded: str):
        self._topic = topic_uploaded
        self._producer = KafkaProducer(
            bootstrap_servers=brokers,
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
            key_serializer=lambda k: k.encode("utf-8"),
        )

    def publish_uploaded(
        self,
        meeting_id: str,
        object_key: str,
        filename: str,
        lang_hint: str,
    ) -> None:
        event = {
            "meeting_id": meeting_id,
            "object_key": object_key,
            "filename": filename,
            "lang_hint": lang_hint,
        }
        self._producer.send(self._topic, key=meeting_id, value=event).get(
            timeout=30
        )

    def close(self) -> None:
        self._producer.flush(timeout=10)
        self._producer.close(timeout=10)
