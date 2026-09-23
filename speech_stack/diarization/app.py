"""Диаризация и опознание говорящего — HTTP-сервис.

    GET  /health
    GET  /v1/models
    POST /v1/audio/diarize    файл            -> кто когда говорил
    POST /v1/audio/identify   файл            -> то же + имя из реестра голосов
    POST /v1/audio/verify     два файла       -> один ли это человек
    GET  /v1/speakers                         -> реестр
    POST /v1/speakers         имя + образцы   -> записать голос
    DELETE /v1/speakers/{id}

ПОЧЕМУ ОТДЕЛЬНЫЙ СЕРВИС, А НЕ РУЧКА В КОНТЕЙНЕРЕ WHISPER. Тот контейнер
сериализует запросы (один воркер uvicorn, синхронный вызов внутри `async def`:
два параллельных дают wall 376 мс против суммы 337), и его латентность лежит в
бюджете голосового агента ~1170 мс до первого звука. Диаризация минутного
звонка — это секунды, то есть каждая такая заявка встала бы поперёк живого
разговора. Здесь она никому не мешает.

У whisper НЕТ никакой спикерной способности: у `transcribe` 36 параметров, ни
один не про говорящего. Всё, что называется «whisper with diarization», — это
whisper плюс отдельная модель, и вот она.
"""
from __future__ import annotations

import logging
import os
import sys
import time

import numpy as np
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import models                                                   # noqa: E402
import speakers as reg                                          # noqa: E402
from config import (DIAR_MODEL, EMBED_POOL_S, MATCH_THRESHOLD,   # noqa: E402
                    MAX_SEG_S, MAX_UPLOAD_MB, MIN_EMBED_S, MIN_SEG_S,
                    SPK_MODEL, SR)
from diarize import pool, segments_from, speaker_stats           # noqa: E402

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("diar")
app = FastAPI(title="Diarization & speaker ID", version="1.0")


async def _read(f: UploadFile) -> np.ndarray:
    data = await f.read()
    if not data:
        raise HTTPException(400, "пустой файл")
    if len(data) > MAX_UPLOAD_MB * 2 ** 20:
        raise HTTPException(413, f"файл больше {MAX_UPLOAD_MB} МБ")
    try:
        y = models.decode(data)
    except Exception as e:                       # noqa: BLE001 — формат любой
        raise HTTPException(400, f"не удалось декодировать аудио: {type(e).__name__}")
    if len(y) < SR // 2:
        raise HTTPException(400, "короче полусекунды — делить нечего")
    return y


def _diarize(y: np.ndarray, min_s: float, max_s: float) -> dict:
    t0 = time.time()
    P = models.posteriors(y)
    segs, speech, ovl = segments_from(P, min_s, max_s)
    dur = len(y) / SR
    in_seg = sum(s["end"] - s["start"] for s in segs)
    return {"duration_s": round(dur, 2),
            "speech_s": round(speech, 2),
            "overlap_s": round(ovl, 2),
            # Доля речи В СЕГМЕНТАХ — та метрика, которую нельзя поднять
            # дроблением, в отличие от «доли чистых сегментов». Её потолок на
            # этой записи равен 100 % минус наложение.
            "speech_in_segments_pct": round(100 * in_seg / speech, 1) if speech else None,
            "overlap_pct_of_speech": round(100 * ovl / speech, 1) if speech else None,
            "ceiling_pct": round(100 - 100 * ovl / speech, 1) if speech else None,
            "speakers": speaker_stats(segs),
            "segments": segs,
            "took_s": round(time.time() - t0, 2)}


@app.get("/health")
def health():
    loaded = models._diar is not None and models._spk is not None
    return {"status": "healthy" if loaded else "loading",
            "models": {"diarization": DIAR_MODEL, "speaker": SPK_MODEL},
            "loaded": loaded, "device": models._device(),
            "enrolled_voices": len(reg.catalogue()),
            "match_threshold": MATCH_THRESHOLD}


@app.get("/v1/models")
def list_models():
    return {"object": "list", "data": [
        {"id": DIAR_MODEL, "object": "model", "owned_by": "nvidia", "task": "diarization"},
        {"id": SPK_MODEL, "object": "model", "owned_by": "nvidia", "task": "speaker-embedding"}]}


@app.post("/v1/audio/diarize")
async def diarize(file: UploadFile = File(...),
                  min_segment_s: float = Form(default=MIN_SEG_S),
                  max_segment_s: float = Form(default=MAX_SEG_S)):
    """Кто когда говорил. Метки говорящих (0, 1, ...) локальны для ЭТОЙ записи
    и в другой записи означают других людей — постоянные имена даёт только
    /v1/audio/identify по реестру голосов."""
    y = await _read(file)
    return JSONResponse(_diarize(y, min_segment_s, max_segment_s))


@app.post("/v1/audio/identify")
async def identify(file: UploadFile = File(...),
                   speakers: str = Form(default=None),
                   threshold: float = Form(default=MATCH_THRESHOLD),
                   min_segment_s: float = Form(default=MIN_SEG_S),
                   max_segment_s: float = Form(default=MAX_SEG_S)):
    """Диаризация плюс имя каждого говорящего из реестра.

    Эмбеддинг считается по СКЛЕЙКЕ самых длинных сегментов говорящего, а не по
    каждому сегменту отдельно: на отрезке короче пары секунд эмбеддинг — шум, и
    посегментное опознание давало бы разные имена одному человеку внутри одного
    звонка. `speakers` — список id или имён через запятую, чтобы сравнивать не
    со всем реестром, когда заранее известно, кого ждём.
    """
    y = await _read(file)
    out = _diarize(y, min_segment_s, max_segment_s)
    only = [x.strip() for x in speakers.split(",")] if speakers else None
    rows, M = reg.matrix(only)
    ids = [s["speaker"] for s in out["speakers"]]
    chunks, usable = [], []
    for k in ids:
        c = pool(y, out["segments"], k, SR, EMBED_POOL_S)
        if len(c) >= MIN_EMBED_S * SR:
            chunks.append(c)
            usable.append(k)
    V = models.embed(chunks) if chunks else np.zeros((0, 192), dtype=np.float32)
    by = {}
    for k, v in zip(usable, V):
        by[k] = reg.match(v, rows, M, threshold)
    for s in out["speakers"]:
        s.update(by.get(s["speaker"], {
            "identity": None, "identity_id": None, "score": None, "margin": None,
            "reason": f"меньше {MIN_EMBED_S} с речи — эмбеддинг был бы шумом"}))
    name = {s["speaker"]: s.get("identity") for s in out["speakers"]}
    for s in out["segments"]:
        s["identity"] = name.get(s["speaker"])
    out["registry_size"] = len(rows)
    return JSONResponse(out)


@app.post("/v1/audio/verify")
async def verify(file_a: UploadFile = File(...), file_b: UploadFile = File(...),
                 threshold: float = Form(default=MATCH_THRESHOLD)):
    """Один ли человек на двух записях. Реестр не нужен и не используется."""
    ya, yb = await _read(file_a), await _read(file_b)
    for y, nm in ((ya, "file_a"), (yb, "file_b")):
        if len(y) < MIN_EMBED_S * SR:
            raise HTTPException(400, f"{nm} короче {MIN_EMBED_S} с — эмбеддинг был бы шумом")
    V = models.embed([ya, yb])
    s = float(V[0] @ V[1])
    return {"score": round(s, 4), "threshold": threshold, "same_speaker": s >= threshold,
            "seconds": [round(len(ya) / SR, 2), round(len(yb) / SR, 2)]}


@app.get("/v1/speakers")
def speakers_list():
    return {"object": "list", "data": reg.catalogue()}


@app.post("/v1/speakers")
async def speakers_enroll(name: str = Form(...),
                          files: list[UploadFile] = File(...),
                          speaker_id: str = Form(default=None),
                          replace: bool = Form(default=False),
                          diarize_first: bool = Form(default=False)):
    """Записать голос по образцу. Несколько файлов усредняются.

    `diarize_first=true` — если образец это кусок разговора: тогда берётся
    речь САМОГО ГОВОРЯЩЕГО ГОВОРЯЩЕГО. По умолчанию выключено, потому что
    нормальный образец — это запись одного человека, и лишняя диаризация на
    ней только тратила бы время и могла бы отрезать половину.
    """
    chunks, secs = [], 0.0
    for f in files:
        y = await _read(f)
        if diarize_first:
            d = _diarize(y, MIN_SEG_S, MAX_SEG_S)
            if not d["speakers"]:
                raise HTTPException(400, f"{f.filename}: речи не найдено")
            y = pool(y, d["segments"], d["speakers"][0]["speaker"], SR, EMBED_POOL_S)
        if len(y) < MIN_EMBED_S * SR:
            raise HTTPException(400, f"{f.filename}: меньше {MIN_EMBED_S} с речи")
        chunks.append(y[:int(EMBED_POOL_S * SR)])
        secs += len(chunks[-1]) / SR
    V = models.embed(chunks)
    return reg.enroll(name, V, secs, speaker_id=speaker_id, replace=replace)


@app.delete("/v1/speakers/{sid}")
def speakers_delete(sid: str):
    if not reg.delete(sid):
        raise HTTPException(404, f"голос '{sid}' не найден")
    return {"deleted": sid}


@app.on_event("startup")
def _warm():
    """Греем на старте, а не на первом запросе: Sortformer поднимается ~25 с, и
    первый вызывающий не должен платить за это таймаутом."""
    t = time.time()
    models.load()
    log.info("модели загружены за %.1f с", time.time() - t)
