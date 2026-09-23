"""
Модели: загрузка, глобальные держатели, прогрев и выбор маршрута по языку.

Держатели — модульные глобалы, а не значения, импортируемые по имени:
`from asr_models import whisper_model` захватил бы None во время импорта, до
startup, и остался бы None навсегда. Читать их снаружи надо через модуль —
`asr_models.whisper_model`.
"""

import glob
import os

from audio import load_audio
from config import (AUTO_LANGS, AUTO_MIN_PROB, DEFAULT_LANG, DEVICE, GENERAL_ROUTE_LANGS,
                    TURKIC_ASR_BASE, WHISPER_CT2_PATH, WHISPER_EN_CT2_PATH, WHISPER_HF_PATH,
                    logger, norm_lang)

# --- Global model holders ---
whisper_model = None        # primary: whisper-ksc2 (Kazakh-specialized, also good RU)
whisper_en_model = None     # EN routing: whisper-large-v3 (ksc2 fine-tune broke English)
turkic_asr_model = None


def load_whisper():
    """Load Whisper KSC2 via faster-whisper (CTranslate2)."""
    global whisper_model
    logger.info("Loading Whisper KSC2 (faster-whisper)...")

    if os.path.isdir(WHISPER_CT2_PATH):
        from faster_whisper import WhisperModel
        whisper_model = WhisperModel(
            WHISPER_CT2_PATH,
            device="cuda" if "cuda" in DEVICE else "cpu",
            compute_type="float16" if "cuda" in DEVICE else "float32",
        )
        logger.info("Whisper KSC2 loaded (CTranslate2 / faster-whisper).")
        # Also load a general model for EN routing (ksc2 fine-tune broke English).
        global whisper_en_model
        if os.path.isdir(WHISPER_EN_CT2_PATH):
            try:
                whisper_en_model = WhisperModel(
                    WHISPER_EN_CT2_PATH,
                    device="cuda" if "cuda" in DEVICE else "cpu",
                    compute_type="float16" if "cuda" in DEVICE else "float32",
                )
                logger.info("EN model loaded (%s) for language routing.", WHISPER_EN_CT2_PATH)
            except Exception as e:
                logger.warning("Failed to load EN routing model: %s", e)
        else:
            logger.info("EN routing model dir not found (%s); EN will use KSC2.", WHISPER_EN_CT2_PATH)
    else:
        # Fallback: use transformers directly
        logger.warning("CTranslate2 model not found, falling back to transformers...")
        from transformers import WhisperProcessor, WhisperForConditionalGeneration
        whisper_model = {
            "processor": WhisperProcessor.from_pretrained(WHISPER_HF_PATH),
            "model": WhisperForConditionalGeneration.from_pretrained(WHISPER_HF_PATH).to(DEVICE),
        }
        whisper_model["model"].eval()
        logger.info("Whisper KSC2 loaded (transformers).")


def load_turkic_asr():
    """Load ISSAI TurkicASR (ESPnet Conformer)."""
    global turkic_asr_model
    logger.info("Loading TurkicASR...")

    # Find model files
    config_candidates = glob.glob(f"{TURKIC_ASR_BASE}/**/config.yaml", recursive=True)
    model_candidates = glob.glob(f"{TURKIC_ASR_BASE}/**/*.pth", recursive=True)
    lm_config_candidates = glob.glob(f"{TURKIC_ASR_BASE}/**/lm_train*/config.yaml", recursive=True)
    lm_model_candidates = glob.glob(f"{TURKIC_ASR_BASE}/**/lm_train*/*.pth", recursive=True)

    # Pick ASR config/model (not LM)
    asr_config = None
    asr_model = None
    lm_config = None
    lm_model = None

    for c in config_candidates:
        if "asr_train" in c or ("lm_train" not in c and "lm" not in os.path.basename(os.path.dirname(c))):
            asr_config = c
            break
    for m in model_candidates:
        if "asr_train" in m or "valid.acc" in m:
            if "lm_train" not in m:
                asr_model = m
                break
    for c in lm_config_candidates:
        lm_config = c
        break
    for m in lm_model_candidates:
        lm_model = m
        break

    logger.info(f"  ASR config: {asr_config}")
    logger.info(f"  ASR model:  {asr_model}")
    logger.info(f"  LM config:  {lm_config}")
    logger.info(f"  LM model:   {lm_model}")

    if not asr_config or not asr_model:
        logger.error("TurkicASR model files not found! TurkicASR will be unavailable.")
        return

    from espnet2.bin.asr_inference import Speech2Text

    # ESPnet config uses relative paths for feats_stats — chdir to model base
    prev_cwd = os.getcwd()
    os.chdir(TURKIC_ASR_BASE)

    kwargs = {
        "asr_train_config": asr_config,
        "asr_model_file": asr_model,
        "device": DEVICE if "cuda" in DEVICE else "cpu",
        "beam_size": 10,
        "ctc_weight": 0.5,
        "penalty": 0.0,
        "nbest": 1,
    }
    if lm_config and lm_model:
        kwargs["lm_train_config"] = lm_config
        kwargs["lm_file"] = lm_model
        kwargs["lm_weight"] = 0.3

    turkic_asr_model = Speech2Text(**kwargs)
    os.chdir(prev_cwd)
    logger.info("TurkicASR loaded.")


def warmup():
    """Run a dummy transcription per model to warm CUDA kernels — kills the ~6.6s
    cold-start on the first real request (critical for realtime)."""
    import numpy as np
    from faster_whisper import WhisperModel
    # ~6s of very low-amplitude noise so VAD passes and the full beam=5 decode
    # path compiles (matches real-request kernels — pure silence under-warms).
    rng = np.random.default_rng(0)
    sample = (rng.standard_normal(16000 * 6).astype(np.float32) * 1e-3)
    for m, lang in ((whisper_model, DEFAULT_LANG), (whisper_en_model, "en")):
        if isinstance(m, WhisperModel):
            try:
                segs, _ = m.transcribe(
                    sample, language=lang, beam_size=5, vad_filter=True,
                    condition_on_previous_text=False,
                )
                list(segs)
            except Exception as e:
                logger.warning("warmup failed: %s", e)
    logger.info("Whisper warmup done (models pre-initialized).")


def _model_tag(path: str) -> str:
    """Имя РЕАЛЬНО загруженной модели — из пути, а не из строки в коде.

    Метка была зашита как `general:large-v3`, и с 21 авг 2026 это враньё: в
    общем слоте стоит `whisper-v4-ct2`, наш файнтюн поверх large-v3-**turbo**.
    Поймано 11 сен, когда на прямой вопрос «large или turbo» API ответил
    «large-v3», а env контейнера — `WHISPER_EN_CT2_PATH=/app/models/whisper-v4-ct2`.

    Единственный источник, который не разъедется со слотом при следующей
    выкатке, — сам путь: подменить модель, не подменив путь, нельзя.
    """
    return os.path.basename(str(path).rstrip("/")) or "unknown"


def pick_route(lang_norm: str):
    """Какая модель отвечает на этот язык. Возвращает (модель, метка маршрута).

    Language routing: EN → general large-v3 (KSC2 fine-tune broke English);
    everything else (KK/RU/…) → KSC2.

    GENERAL_ROUTE_LANGS sends a language to stock large-v3 instead of the
    KSC2 fine-tune. It started as EN-only, because the fine-tune broke
    English; it is a set because the same question is open for Russian —
    measured 17 Aug 2026 on Common Voice at 8 kHz, KSC2 reads Russian at
    pooled CER 0.0832 against 0.0309 for Kazakh, and a call centre in
    Astana is majority Russian. Add "ru" here to route it, and MEASURE:
    training/bench_asr_telephony.py is the instrument.
    """
    if lang_norm in GENERAL_ROUTE_LANGS and whisper_en_model is not None:
        return whisper_en_model, f"general:{_model_tag(WHISPER_EN_CT2_PATH)}"
    return whisper_model, f"ksc2:{_model_tag(WHISPER_CT2_PATH)}"


class AutoDetect:
    """Итог автоопределения языка.

    `language is None` означает «язык менять нельзя»: либо детекция не
    состоялась (тогда `failed`), либо её просто не запрашивали.
    """

    __slots__ = ("language", "detected", "probability", "accepted", "failed")

    def __init__(self, language, detected, probability, accepted, failed):
        self.language, self.detected = language, detected
        self.probability, self.accepted, self.failed = probability, accepted, failed


def detect_auto_language(audio_bytes: bytes) -> AutoDetect:
    """Определить язык ДО декодера — один проход энкодера плюс один шаг декодера.

    "auto" РЕАЛЬНО определяет язык — с 21 авг 2026. До этого оно было
    байт-в-байт равно "kk": маршрут выбирается здесь, ДО декодера, и "auto"
    в GENERAL_ROUTE_LANGS не входило, поэтому всё уезжало в казахскую модель.

    Детектор берётся у ОБЩЕЙ модели, потому что там теперь v4, и её голова
    определения языка измерена: 99.0 % на казахской речи и 99.0 % на русской
    (по 200 клипов, 8 кГц), против 72.5 % на казахской у необученной базы.
    Стоит это один проход энкодера плюс один шаг декодера.

    Зачем: агент декодировал ОБА маршрута целиком и выбирал по доле
    казахских букв — два полных декода, 434 мс из бюджета в 1170. Теперь
    один декод, ~135 мс.
    """
    if whisper_en_model is None:
        logger.warning("auto запрошен, но общая модель не загружена — "
                       "маршрут остаётся ksc2, route не сообщаем")
        return AutoDetect(None, None, 0.0, False, True)
    try:
        det, det_prob, _ = whisper_en_model.detect_language(load_audio(audio_bytes))
        raw = norm_lang(det)
        if raw not in AUTO_LANGS:
            logger.warning("детектор дал %r (p=%.2f) — вне %s, беру %s",
                           raw, det_prob, sorted(AUTO_LANGS), DEFAULT_LANG)
            return AutoDetect(DEFAULT_LANG, det, det_prob, False, False)
        if det_prob < AUTO_MIN_PROB:
            logger.warning("детектор дал %r, но p=%.2f < %.2f — беру %s",
                           raw, det_prob, AUTO_MIN_PROB, DEFAULT_LANG)
            return AutoDetect(DEFAULT_LANG, det, det_prob, False, False)
        logger.info("auto -> %s (p=%.2f)", raw, det_prob)
        return AutoDetect(raw, det, det_prob, True, False)
    except Exception as e:
        # Не смогли определить — прежнее поведение, а не отказ.
        logger.warning("detect_language failed: %s", e)
        return AutoDetect(None, None, 0.0, False, True)
