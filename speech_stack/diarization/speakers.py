"""Реестр голосов: запись образца, хранение эмбеддинга, сопоставление.

Реестр — обычный JSON на диске. Голосов тут десятки (операторы колл-центра), а
не миллионы, поэтому база данных была бы лишней сущностью, а линейный перебор
192-мерных векторов на десятках записей стоит микросекунды.

ЧТО ЗДЕСЬ ХРАНИТСЯ И ПОЧЕМУ ЭТО ЧУВСТВИТЕЛЬНО. Эмбеддинг голоса — биометрия:
по нему человека можно узнать в другой записи, что и есть назначение сервиса.
Само аудио образца НЕ сохраняется, только вектор и имя, которое дал вызывающий.
"""
from __future__ import annotations

import json
import os
import tempfile
import threading
import time
import uuid

import numpy as np

from config import REGISTRY, SPK_DIM

_lock = threading.Lock()


def _load() -> dict:
    if not os.path.exists(REGISTRY):
        return {"speakers": {}}
    try:
        with open(REGISTRY, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        # Битый реестр не должен ронять сервис: диаризация от него не зависит,
        # а опознание честнее отдать пустым, чем упасть на каждом запросе.
        return {"speakers": {}}


def _save(db: dict) -> None:
    """Запись атомарная. Прямая перезапись уже стоила этому проекту гонки на
    манифесте: два процесса писали один файл, и цел он остался только потому,
    что оба писали одно и то же."""
    os.makedirs(os.path.dirname(REGISTRY), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(REGISTRY), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(db, f, ensure_ascii=False, indent=1)
        os.replace(tmp, REGISTRY)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def enroll(name: str, vecs: np.ndarray, seconds: float,
           speaker_id: str | None = None, replace: bool = False) -> dict:
    """Записать голос. Несколько образцов усредняются и снова нормируются.

    Усреднение, а не хранение всех векторов: разные образцы одного человека
    отличаются каналом и настроением, и центроид к этому устойчивее, чем
    максимум по образцам — максимум выбирал бы тот образец, чей канал ближе к
    проверяемой записи, то есть мерил бы канал.
    """
    v = vecs.mean(axis=0)
    v = v / (np.linalg.norm(v) + 1e-9)
    with _lock:
        db = _load()
        sid = speaker_id or uuid.uuid4().hex[:12]
        if sid in db["speakers"] and not replace:
            old = db["speakers"][sid]
            prev = np.asarray(old["vector"], dtype=np.float32) * old.get("samples", 1)
            v = (prev + vecs.sum(axis=0))
            v = v / (np.linalg.norm(v) + 1e-9)
            samples = old.get("samples", 1) + len(vecs)
            seconds += old.get("seconds", 0.0)
        else:
            samples = len(vecs)
        db["speakers"][sid] = {"id": sid, "name": name, "vector": [float(x) for x in v],
                               "samples": samples, "seconds": round(seconds, 2),
                               "updated": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
        _save(db)
        return {k: x for k, x in db["speakers"][sid].items() if k != "vector"}


def delete(sid: str) -> bool:
    with _lock:
        db = _load()
        if sid not in db["speakers"]:
            return False
        del db["speakers"][sid]
        _save(db)
        return True


def catalogue() -> list[dict]:
    return [{k: v for k, v in s.items() if k != "vector"}
            for s in _load()["speakers"].values()]


def matrix(only: list[str] | None = None) -> tuple[list[dict], np.ndarray]:
    """(метаданные, матрица эмбеддингов) — в одном порядке."""
    rows = [s for s in _load()["speakers"].values()
            if not only or s["id"] in only or s["name"] in only]
    if not rows:
        return [], np.zeros((0, SPK_DIM), dtype=np.float32)
    M = np.stack([np.asarray(s["vector"], dtype=np.float32) for s in rows])
    return rows, M


def match(vec: np.ndarray, rows: list[dict], M: np.ndarray,
          threshold: float) -> dict:
    """Ближайший голос реестра и отрыв от второго.

    ОТРЫВ ПЕЧАТАЕТСЯ ВСЕГДА и не участвует в решении. Он отвечает на вопрос,
    которого одно только сходство не различает: «похож на Ивана» и «похож на
    Ивана заметно больше, чем на остальных» — разные утверждения, и при двух
    близких кандидатах решение по порогу произвольно. Пусть это видит тот, кто
    читает ответ, а не прячет функция.
    """
    if M.shape[0] == 0:
        return {"identity": None, "identity_id": None, "score": None,
                "margin": None, "reason": "реестр пуст"}
    sims = M @ vec
    order = np.argsort(-sims)
    top = int(order[0])
    second = float(sims[int(order[1])]) if len(order) > 1 else None
    best = float(sims[top])
    hit = best >= threshold
    return {"identity": rows[top]["name"] if hit else None,
            "identity_id": rows[top]["id"] if hit else None,
            "score": round(best, 4),
            "margin": None if second is None else round(best - second, 4),
            "closest": rows[top]["name"],
            "closest_id": rows[top]["id"],
            "threshold": threshold,
            "reason": None if hit else "сходство ниже порога"}
