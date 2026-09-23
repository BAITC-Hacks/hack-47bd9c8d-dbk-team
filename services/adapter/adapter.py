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

MONTHS = {"янв": 1, "фев": 2, "мар": 3, "апр": 4, "мая": 5, "май": 5, "июн": 6,
          "июл": 7, "авг": 8, "сен": 9, "окт": 10, "ноя": 11, "дек": 12}
ISO = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")
RU_DATE = re.compile(r"(\d{1,2})\s+([а-яё]{3})[а-яё]*", re.I)
YEAR = int(os.environ.get("MEETING_YEAR", "2026"))


def to_iso(raw: str) -> str | None:
    """«до 15 октября» → 2026-10-15. Год берём из окружения: в записи он
    обычно не звучит, а протоколу нужна дата, а не словесный срок."""
    m = ISO.search(raw or "")
    if m:
        return m.group(1)
    m = RU_DATE.search(raw or "")
    if m:
        mon = MONTHS.get(m.group(2).lower()[:3])
        if mon:
            return f"{YEAR}-{mon:02d}-{int(m.group(1)):02d}"
    return None


def parse_commitments(summary: str) -> list[dict]:
    """Разбирает таблицу поручений из summary.md.

    Обработчик отдаёт раздел «Поручения» markdown-таблицей
    «Поручение | Ответственный | Срок». Разбор таблицы детерминирован и не
    требует ещё одного вызова модели — на демо это лишняя минута ожидания.
    """
    out, in_table = [], False
    for line in summary.splitlines():
        low = line.lower()
        if "поручени" in low and line.lstrip().startswith("#") or low.strip().startswith("6."):
            in_table = True
            continue
        if not in_table:
            continue
        if not line.strip().startswith("|"):
            if out and line.strip() and not line.strip().startswith("|"):
                break
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 3 or set(cells[0]) <= set("-: ") or "поручение" in cells[0].lower():
            continue
        text, who, due_raw = cells[0], cells[1], cells[2]
        out.append({"id": f"c{len(out)+1}", "assignee": who or None,
                    "assignee_speaker": who if who.lower().startswith("speaker") else None,
                    "due_date": to_iso(due_raw), "due_raw": due_raw,
                    "text": text, "quote": text, "t_start": None,
                    # Ответственный пришёл ярлыком, а не именем — привязка
                    # к человеку не подтверждена, помечаем честно.
                    "confidence": "low" if who.lower().startswith("speaker") else "high",
                    "status": "in_progress"})
    return out


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

    commitments = parse_commitments(summary)

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
