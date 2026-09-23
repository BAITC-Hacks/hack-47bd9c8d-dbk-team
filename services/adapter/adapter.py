#!/usr/bin/env python3
"""Адаптер контрактов между интерфейсом и обработчиком.

Интерфейс и обработчик писались параллельно и разошлись в трёх местах: имена
топиков, форма запроса и форма результата. Адаптер переводит одно в другое и
не трогает код ни той, ни другой стороны — это дешевле и безопаснее, чем
править чужие файлы перед сдачей.

    meetings.uploaded  {meeting_id, object_key}
        ──► AiMeetingCopilotRequest  {messageId, files: "s3://bucket/prefix/"}

    AiMeetingCopilotResponse  {messageId, success, errors}
        ──► собирает result.json из артефактов обработчика
        ──► meetings.ready {meeting_id, result_key} | meetings.failed {..., stage, error}
"""
import io
import json
import logging
import os
import re

from kafka import KafkaConsumer, KafkaProducer
from minio import Minio

log = logging.getLogger("adapter")

BOOTSTRAP = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
T_UPLOADED = os.environ.get("TOPIC_UPLOADED", "meetings.uploaded")
T_READY = os.environ.get("TOPIC_READY", "meetings.ready")
T_FAILED = os.environ.get("TOPIC_FAILED", "meetings.failed")
T_REQUEST = os.environ.get("KAFKA_REQUEST_TOPIC", "AiMeetingCopilotRequest")
T_RESPONSE = os.environ.get("KAFKA_RESPONSE_TOPIC", "AiMeetingCopilotResponse")

UPLOADS = os.environ.get("MINIO_BUCKET", "uploads")
RESULTS = os.environ.get("RESULTS_BUCKET", "results")

_ep = os.environ.get("MINIO_ENDPOINT", "http://minio:9000")
mc = Minio(
    _ep.split("://", 1)[-1],
    access_key=os.environ["MINIO_ACCESS_KEY"],
    secret_key=os.environ["MINIO_SECRET_KEY"],
    secure=_ep.startswith("https"),
)

DUE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")


def _prefix_of(object_key: str) -> str:
    """Обработчик забирает ПАПКУ целиком, интерфейс присылает ключ файла."""
    return object_key.rsplit("/", 1)[0] + "/" if "/" in object_key else ""


def _read(bucket: str, key: str) -> str | None:
    try:
        r = mc.get_object(bucket, key)
        try:
            return r.read().decode("utf-8")
        finally:
            r.close()
            r.release_conn()
    except Exception:
        return None


def build_result(meeting_id: str, prefix: str) -> dict:
    """Собирает result.json по схеме контракта из артефактов обработчика."""
    merged = _read(UPLOADS, prefix + "transcript.json")
    summary = _read(UPLOADS, prefix + "summary.md") or ""

    transcript, speakers = [], {}
    if merged:
        try:
            turns = json.loads(merged)
            if isinstance(turns, dict):
                turns = turns.get("segments") or turns.get("turns") or []
            for t in turns:
                label = str(t.get("speaker", "SPK_0"))
                speakers.setdefault(label, {"label": label, "name": None,
                                            "resolved_by": "diarization", "merged": False})
                transcript.append({"speaker": label, "name": None,
                                   "t_start": t.get("start", 0.0), "t_end": t.get("end", 0.0),
                                   "text": t.get("text", "")})
        except Exception as e:
            log.warning("transcript.json не разобран: %s", e)

    # Поручения в summary.md идут списком; вытаскиваем строки со сроком.
    commitments = []
    for i, line in enumerate(l.strip(" -*\t") for l in summary.splitlines()):
        if not line or len(line) < 15:
            continue
        m = DUE.search(line)
        if m:
            commitments.append({"id": f"c{len(commitments)+1}", "assignee": None,
                                "assignee_speaker": None, "due_date": m.group(1),
                                "due_raw": m.group(1), "text": line, "quote": line,
                                "t_start": None, "confidence": "low",
                                "status": "in_progress"})

    return {"meeting_id": meeting_id, "transcript": transcript,
            "speakers": list(speakers.values()), "commitments": commitments,
            "summary": summary,
            "warnings": [] if transcript else
                        ["Транскрипт не найден в артефактах обработчика"]}


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    producer = KafkaProducer(bootstrap_servers=BOOTSTRAP,
                             value_serializer=lambda v: json.dumps(v, ensure_ascii=False).encode())
    consumer = KafkaConsumer(T_UPLOADED, T_RESPONSE, bootstrap_servers=BOOTSTRAP,
                             group_id="contract-adapter", auto_offset_reset="latest",
                             value_deserializer=lambda b: json.loads(b.decode()))
    pending: dict[str, str] = {}
    log.info("адаптер слушает %s и %s", T_UPLOADED, T_RESPONSE)

    for msg in consumer:
        try:
            ev = msg.value
            if msg.topic == T_UPLOADED:
                mid = ev["meeting_id"]
                prefix = _prefix_of(ev.get("object_key", ""))
                pending[mid] = prefix
                producer.send(T_REQUEST, {"messageId": mid,
                                          "files": f"s3://{UPLOADS}/{prefix}"})
                log.info("%s → обработчику, папка %s", mid, prefix)
            else:
                mid = ev.get("messageId")
                prefix = pending.pop(mid, "")
                if not ev.get("success"):
                    errs = ev.get("errors") or [{}]
                    producer.send(T_FAILED, {"meeting_id": mid, "stage": "processing",
                                             "error": errs[0].get("message", "unknown")})
                    log.warning("%s провалился: %s", mid, errs)
                    continue
                result = build_result(mid, prefix)
                blob = json.dumps(result, ensure_ascii=False, indent=2).encode()
                key = f"{mid}/result.json"
                try:
                    mc.make_bucket(RESULTS)
                except Exception:
                    pass
                mc.put_object(RESULTS, key, io.BytesIO(blob), len(blob),
                              content_type="application/json")
                producer.send(T_READY, {"meeting_id": mid, "result_key": key})
                log.info("%s готов: %s, поручений %d", mid, key, len(result["commitments"]))
            producer.flush()
        except Exception:
            log.exception("сообщение не обработано")


if __name__ == "__main__":
    main()
