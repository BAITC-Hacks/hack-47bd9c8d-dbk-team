"""
STT Service — Whisper KSC2 (Kazakh-tuned) + ISSAI TurkicASR
OpenAI-compatible speech-to-text API.

Models:
  whisper-ksc2  — Whisper large-v3-turbo fine-tuned on KSC2 (1000h Kazakh)
  turkic-asr    — ISSAI TurkicASR (10 Turkic languages, ESPnet Conformer)

Точка входа контейнера — `uvicorn app:app` из /app, поэтому здесь ТОЛЬКО HTTP:
ручки, форма запроса и сборка ответа. Остальное лежит рядом, в том же каталоге:

    config.py      окружение, пути, языковые множества, предзагрузка CUDA 12
    audio.py       байты -> моно 16 кГц
    asr_models.py  загрузка моделей, держатели, прогрев, выбор маршрута
    decode.py      декодирование, длинная форма, word-тайминги

Патченые файлы живут в ПЕРЕЗАПИСЫВАЕМОМ слое контейнера и теряются при
`docker rm`, а забытый модуль — это ImportError на живом проде. Поэтому
копировать их надо ВСЕ И СРАЗУ, одной командой из REPRODUCE.md, а не по одному.
"""

import asyncio
import concurrent.futures
import os
import threading
import time

import torch
from fastapi import FastAPI, File, Form, UploadFile, HTTPException
from fastapi.responses import JSONResponse

import asr_models
from config import DEVICE, LOAD_TURKIC, PORT, WHISPER_MODEL_ID, logger, norm_lang
from decode import transcribe_turkic, transcribe_whisper

app = FastAPI(title="STT Service", version="1.0.0")


@app.on_event("startup")
def startup():
    asr_models.load_whisper()
    asr_models.warmup()
    if LOAD_TURKIC:
        try:
            asr_models.load_turkic_asr()
        except Exception as e:
            logger.error(f"Failed to load TurkicASR: {e}. Model will be unavailable.")
    else:
        logger.info("TurkicASR disabled (LOAD_TURKIC=0)")


@app.get("/health")
def health():
    return {
        "inflight": _inflight, "max_inflight": MAX_INFLIGHT,
        "rejected_total": _rejected_total,
        "status": "healthy",
        "models": {
            WHISPER_MODEL_ID: asr_models.whisper_model is not None,
            "turkic-asr": asr_models.turkic_asr_model is not None,
        },
        "device": DEVICE,
        "cuda_available": torch.cuda.is_available(),
        "gpu_memory_gb": round(torch.cuda.memory_allocated() / 1024**3, 2)
        if torch.cuda.is_available() and "cuda" in DEVICE
        else None,
    }


@app.get("/v1/models")
def list_models():
    models = []
    if asr_models.whisper_model is not None:
        models.append({"id": WHISPER_MODEL_ID, "object": "model", "owned_by": "systran"})
    if asr_models.turkic_asr_model is not None:
        models.append({"id": "turkic-asr", "object": "model", "owned_by": "issai"})
    return {"object": "list", "data": models}


# --- КОНТРОЛЬ ПРИЁМА -------------------------------------------------------
#
# Контейнер обслуживает запросы ПО ОДНОМУ: один воркер uvicorn и синхронный
# вызов внутри `async def` (замерено: два параллельных дают wall 376 мс против
# суммы 337). Значит предложенная нагрузка превращается прямо в глубину
# очереди, а очередь — в задержку того, кто за ней стоит.
#
# 11 сен 2026 это перестало быть теорией: один 41-минутный файл снаружи держал
# очередь ДЕСЯТЬ МИНУТ, health-проба показывала unhealthy, и всё это время
# голосовой агент не мог распознать реплику абонента. У TTS такой лимит есть
# (`OMNIVOICE_MAX_CONCURRENT=6`), у ASR не было.
#
# ПОЧЕМУ 4, и это не подобранное число: бюджет агента до первого звука ~1170 мс,
# из них ASR ~230 мс. Четвёртый в очереди ждёт три чужих декода, то есть ~700 мс
# плюс свой — впритык. Пятый гарантированно выходит за бюджет, и честный отказ
# ему полезнее молчаливого ожидания: `Retry-After` позволяет клиенту решить
# самому. Ладдер для уточнения — `training/bench_asr_load.py`.
#
# ЧЕГО ЭТОТ ЛИМИТ НЕ ЛЕЧИТ, и это надо знать: ОДИН длинный файл блокирует всё
# при любой глубине очереди. Настоящее лекарство — отдельная полоса для
# коротких реплик; здесь его нет. Поэтому запрос с длинным звуком пишет
# предупреждение в лог — чтобы блокировка была видна, а не гадалась.
MAX_INFLIGHT = int(os.environ.get("WHISPER_MAX_INFLIGHT", "4"))
LONG_AUDIO_WARN_S = float(os.environ.get("WHISPER_LONG_AUDIO_WARN_S", "120"))
_inflight = 0
_inflight_lock = threading.Lock()
_rejected_total = 0
# Один поток: декод остаётся строго последовательным, как и был.
_POOL = concurrent.futures.ThreadPoolExecutor(max_workers=1,
                                              thread_name_prefix="asr")


def _take_slot() -> bool:
    """Занять место. Блокировка обязательна: `+=` не атомарен между потоком
    обработчика и потоком пула, которым FastAPI исполняет синхронный вызов."""
    global _inflight
    with _inflight_lock:
        if _inflight >= MAX_INFLIGHT:
            return False
        _inflight += 1
        return True


def _free_slot() -> None:
    """Идемпотентно: освобождение зовётся из `finally`, и двойной вызов при
    отвалившемся клиенте не должен уводить счётчик в минус. У TTS ровно этот
    дефект стоил вечных 503 на свободной службе."""
    global _inflight
    with _inflight_lock:
        _inflight = max(0, _inflight - 1)


@app.post("/v1/audio/transcriptions")
async def transcribe(
    file: UploadFile = File(...),
    model: str = Form(default="whisper-ksc2"),
    language: str = Form(default=None),
    response_format: str = Form(default="json"),
    prompt: str = Form(default=None),
    beam_size: int = Form(default=None),
    # A comma-separated list of proper nouns that may occur — street and
    # district names for the call agent. Optional and defaulting to None, so
    # every existing caller (document recognition, the agent, Open WebUI)
    # is byte-identical to before.
    hotwords: str = Form(default=None),
):
    """OpenAI-compatible speech-to-text endpoint.

    response_format:
      json         — {"text": "..."} (default, OpenAI-compatible)
      verbose_json — {"text", "segments", "words", "language", "duration"}
    """
    if model == "whisper-ksc2" and WHISPER_MODEL_ID != "whisper-ksc2":
        logger.warning("model=whisper-ksc2 is a deprecated alias; serving %s", WHISPER_MODEL_ID)
        model = WHISPER_MODEL_ID
    if model not in (WHISPER_MODEL_ID, "turkic-asr"):
        raise HTTPException(
            status_code=400,
            detail=f"Unknown model '{model}'. Available: {WHISPER_MODEL_ID}, turkic-asr",
        )

    audio_bytes = await file.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Empty audio file")

    # Место занимается ПОСЛЕ чтения тела и ДО любой работы: отказ должен быть
    # дешёвым, а занятое место — покрывать ровно то время, что держит очередь.
    global _rejected_total
    if not _take_slot():
        with _inflight_lock:
            _rejected_total += 1
        logger.warning("приём: занято %d из %d, отказ (всего отказов %d)",
                       MAX_INFLIGHT, MAX_INFLIGHT, _rejected_total)
        # 1 секунда, а не «подождите»: медиана декода реплики 100-300 мс, то
        # есть очередь из четырёх рассасывается быстрее секунды. Число должно
        # быть меньше терпения агента, иначе честный отказ хуже ожидания.
        return JSONResponse(
            status_code=503,
            headers={"Retry-After": "1"},
            content={"error": {
                "message": (f"ASR занят: {MAX_INFLIGHT} запросов в работе. "
                            f"Контейнер обслуживает по одному, поэтому очередь "
                            f"превращается в задержку. Повторите через секунду."),
                "type": "server_busy"}})

    try:
        # В ПУЛ, а не прямо здесь — и это половина всего контроля приёма.
        # Обработчик объявлен `async def`, но вся работа внутри синхронная, то
        # есть она блокирует ЦИКЛ СОБЫТИЙ. Пока он заблокирован, ни один другой
        # запрос не доходит до питона вовсе: очередь стоит в сокете, и никакой
        # счётчик её не видит. Первая версия этой правки была ровно такой и
        # оказалась МЁРТВОЙ: двенадцать параллельных запросов дали 12 ответов
        # 200 и ноль отказов, потому что `_take_slot` звался строго по одному.
        #
        # Пул из ОДНОГО потока сохраняет то, ради чего сериализация и была:
        # карта считает по одному декоду за раз, модели faster-whisper не
        # делятся между потоками. Освобождается только цикл событий — ровно
        # настолько, чтобы принять следующий запрос и честно ему отказать.
        return await asyncio.get_running_loop().run_in_executor(
            _POOL, _transcribe_inner, audio_bytes, model, language,
            response_format, prompt, beam_size, hotwords)
    finally:
        _free_slot()


def _transcribe_inner(audio_bytes, model, language, response_format,
                      prompt, beam_size, hotwords):
    # Длинный звук блокирует очередь ЦЕЛИКОМ при любой её глубине — лимит выше
    # этого не лечит. Пишем в лог, чтобы блокировку можно было увидеть, а не
    # диагностировать по жалобам: 11 сен 41-минутный файл держал очередь десять
    # минут, и понять это можно было только по логам faster-whisper.
    approx_s = len(audio_bytes) / 32000.0        # грубо: 16 кГц моно 16 бит
    if approx_s > LONG_AUDIO_WARN_S:
        logger.warning("приём: длинный звук ~%.0f с — очередь блокируется на "
                       "всё время его декода", approx_s)

    verbose = response_format == "verbose_json"
    t0 = time.time()

    if model == WHISPER_MODEL_ID:
        if asr_models.whisper_model is None:
            raise HTTPException(status_code=503, detail=f"{WHISPER_MODEL_ID} model not loaded")
        # Route on the language the caller EXPLICITLY asked for. Falling back to
        # DEFAULT_LANG here would silently move every caller that omits the
        # parameter onto the general model the moment "ru" joined the route —
        # including anyone sending KAZAKH audio without a language, who would go
        # from CER 0.0309 to 0.4742. Omitted language keeps the old behaviour:
        # KSC2, decoded as DEFAULT_LANG.  Сам маршрут — asr_models.pick_route.
        lang_norm = norm_lang(language)
        det, det_prob, det_used = None, 0.0, False
        # Детекция ЗАПРАШИВАЛАСЬ, но не состоялась: каталог общей модели не
        # смонтирован или detect_language бросил. Тогда запрос уезжает в KSC2 с
        # language=None — то есть в точности старое «auto == kk», от которого
        # эта правка и избавлялась. Отличить это клиент может только по
        # ОТСУТСТВИЮ `route`: `decode_auto` в agents/su-arnasy/stt/client.py
        # именно на пустой `route` возвращает ok=False и откатывается на двойное
        # декодирование. Поэтому при несостоявшейся детекции `route` не ставим
        # вовсе — иначе клиент запишет `_server_detects=True` и откат не сработает.
        auto_failed = False
        if lang_norm == "auto":
            auto = asr_models.detect_auto_language(audio_bytes)
            det, det_prob = auto.detected, auto.probability
            det_used, auto_failed = auto.accepted, auto.failed
            # None означает «язык не меняем»: тогда "auto" доезжает до декодера
            # как раньше и определяется уже там, внутри KSC2.
            if auto.language is not None:
                language = lang_norm = auto.language
        chosen, route = asr_models.pick_route(lang_norm)
        result = transcribe_whisper(audio_bytes, language, word_timestamps=verbose,
                                    prompt=prompt, model_obj=chosen, beam_size=beam_size,
                                    hotwords=hotwords)
        if not auto_failed:
            result["route"] = route
        if det:
            # `detected_language` — что СКАЗАЛ детектор, `language` — что было
            # использовано; при отвергнутом вердикте это разные вещи, и
            # `detected_accepted` говорит, какая из них решала.
            result["detected_language"] = det
            result["detected_probability"] = round(float(det_prob), 4)
            result["detected_accepted"] = det_used
    else:
        if asr_models.turkic_asr_model is None:
            raise HTTPException(status_code=503, detail="turkic-asr model not loaded")
        result = transcribe_turkic(audio_bytes)

    elapsed = time.time() - t0
    logger.info(f"STT [{model}] -> {len(result['text'])} chars in {elapsed:.3f}s")

    if verbose:
        return JSONResponse(content=result)
    # language/probability ride along on the plain response too: they are the
    # answer to "auto", and an OpenAI client ignores fields it does not know.
    plain = {
        "text": result["text"],
        "language": result.get("language"),
        "language_probability": result.get("language_probability"),
    }
    # `route` и `detected_probability` — на простом ответе тоже, потому что при
    # language=auto именно они говорят, КАК был выбран язык. Без них вызывающий
    # видит `language: kk` и не может отличить «детектор так решил» от «я сам
    # так попросил»: `language_probability` в этот момент всегда 1.0, его
    # возвращает декодер, которому язык уже назвали. Клиент OpenAI лишние поля
    # игнорирует, поэтому это не ломает никого.
    for k in ("route", "detected_language", "detected_probability",
              "detected_accepted"):
        if k in result:
            plain[k] = result[k]
    return JSONResponse(content=plain)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=PORT)
