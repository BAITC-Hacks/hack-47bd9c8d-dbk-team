"""
STT Service — конфигурация: окружение, пути моделей, языковые маршруты.

Здесь только ЗНАЧЕНИЯ и их обоснования: ни одна строка не грузит модель и не
трогает звук, поэтому файл читается целиком, когда надо понять, чем управляет
окружение контейнера. Импортируется первым из всех модулей — поэтому здесь же
стоят logging.basicConfig и предзагрузка CUDA 12: она обязана случиться до
того, как faster-whisper попросит у линковщика свои библиотеки.
"""

import logging
import os

import torch

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
# Имя логгера задано строкой, а не __name__: формат печатает %(name)s, и после
# разделения на модули строки лога стали бы называться то "config", то "decode",
# то "asr_models". Логи контейнера грепают, поэтому имя остаётся прежним — "app".
logger = logging.getLogger("app")

DEVICE = os.environ.get("DEVICE", "cuda:0" if torch.cuda.is_available() else "cpu")
PORT = int(os.environ.get("PORT", "8000"))

WHISPER_CT2_PATH = os.environ.get("WHISPER_CT2_PATH", "/app/models/whisper-turbo-ksc2-ct2")
WHISPER_MODEL_ID = os.environ.get("WHISPER_MODEL_ID", "whisper-ksc2")
# English is routed to a general model because the KSC2 fine-tune degraded EN.
WHISPER_EN_CT2_PATH = os.environ.get("WHISPER_EN_CT2_PATH", "/app/models/whisper-large-v3-ct2")
# Which languages go to stock large-v3 instead of the KSC2 fine-tune. Measured
# 17 Aug 2026 on 11 Common Voice clips resampled to 8 kHz (telephone bandwidth),
# training/bench_asr_telephony.py, pooled CER:
#
#            KSC2     large-v3
#   ru       0.0832   0.0275      <- 3x better, so ru joins the route
#   kk       0.0309   0.4742      <- and must never join it
#
# The KSC2 fine-tune broke English; it turns out it cost Russian too, just less
# visibly. Overridable so the split can be re-tested without editing code.
GENERAL_ROUTE_LANGS = set(
    x.strip().lower() for x in
    os.environ.get("GENERAL_ROUTE_LANGS", "en,english,eng,ru,rus,russian").split(",") if x.strip())
DEFAULT_LANG = os.environ.get("DEFAULT_LANG", "ru")
# ЧТО ДЕТЕКТОРУ РАЗРЕШЕНО ВЕРНУТЬ. `detect_language` берёт argmax по ВСЕМУ
# набору языковых токенов whisper — их около сотни, и на шумной телефонной
# реплике соседи казахского и русского («tt», «ba», «uz», «uk», «tg») вполне
# выигрывают. Чужой языковой токен даёт не ошибки, а СОЧИНЕНИЕ: измерено
# 21 авг, казахский звук с токеном ru -> CER 1.2246, то есть правок больше,
# чем символов в эталоне, при внешне нормальном ответе. Замер 99.0 %
# (bench_v4_lid.py) сделан на корпусном звуке и ровно на двух классах — как
# часто argmax уходит в третий язык на телефоне, он не измерял.
# Ровно от этого защищал старый клиент своим белым списком ru/kk.
AUTO_LANGS = set(
    x.strip().lower() for x in
    os.environ.get("AUTO_LANGS", "ru,kk,en").split(",") if x.strip())
# Порог по уверенности детектора. По умолчанию ВЫКЛЮЧЕН (0.0): на телефонной
# полосе он не измерян, а произвольное число здесь молча уводило бы часть
# казахских реплик в русский маршрут. Включать вместе с замером.
AUTO_MIN_PROB = float(os.environ.get("AUTO_MIN_PROB", "0.0"))
LOAD_TURKIC = os.environ.get("LOAD_TURKIC", "0") == "1"
DEFAULT_PROMPT = os.environ.get("WHISPER_INITIAL_PROMPT") or None


# CTranslate2 is built against CUDA 12 while this image ships CUDA 13, so the
# CUDA 12 runtime comes from pip wheels. Preloading them by absolute path puts
# the sonames into the process before faster-whisper asks the linker for them.
def _preload_cuda12():
    import ctypes
    import glob

    base = "/opt/venv/lib/python3.12/site-packages/nvidia"
    patterns = (
        f"{base}/cublas/lib/libcublasLt.so.12",
        f"{base}/cublas/lib/libcublas.so.12",
        f"{base}/cudnn/lib/libcudnn.so.9",
        f"{base}/cudnn/lib/libcudnn_*.so.9",
    )
    for pattern in patterns:
        for lib in sorted(glob.glob(pattern)):
            try:
                ctypes.CDLL(lib, mode=ctypes.RTLD_GLOBAL)
            except OSError as exc:
                logger.warning("preload failed %s: %s", lib, exc)


_preload_cuda12()
WHISPER_HF_PATH = "/app/models/whisper-turbo-ksc2"
TURKIC_ASR_BASE = "/app/models/turkic-asr"

# Above this many seconds we stop letting faster-whisper segment the audio and
# feed it one VAD chunk at a time instead.  Its `vad_filter` finds the speech
# correctly but then MERGES the chunks into ~30 s windows and decodes each window
# in a single pass, and that pass stops early: measured on a 132 s recording,
# 16 VAD chunks became 5 windows of ~31 s and only 75.3 % of the reference words
# came back.  Decoding the same 16 chunks separately recovers 99.5 % for ~28 %
# more wall clock.  Upstream issue: SYSTRAN/faster-whisper#1270.
# 15, not 30. The loss does not start at whisper's 30 s window — it starts around
# 18 s, because `without_timestamps=True` (the setting that took Kazakh CER from
# 0.0274 to 0.0017) removes the very tokens the single decode pass uses to keep
# going. Measured on one 25.3 s synthesis, transcript length against audio cut at
# 10 / 14 / 18 / 22 / 26 s: 152 / 202 / 254 / 282 / 303 characters — a steady
# ~51 chars per 4 s up to 18 s, then 28 and 21. The tail is dropped silently, and
# every clip this project has ever judged was under 11 s, so it never showed.
LONGFORM_S = float(os.environ.get("WHISPER_LONGFORM_S", "15"))
DEFAULT_BEAM = int(os.environ.get("WHISPER_BEAM_SIZE", "5"))
VAD_MIN_SILENCE_MS = int(os.environ.get("WHISPER_VAD_MIN_SILENCE_MS", "500"))


def norm_lang(language: str | None) -> str:
    """Приводит язык к той же форме, в которой построены множества выше.

    GENERAL_ROUTE_LANGS и AUTO_LANGS собираются через .strip().lower(), поэтому
    и всё, что с ними сравнивают — параметр запроса, вердикт детектора — должно
    проходить ровно эту нормализацию. None даёт "", а не падение.
    """
    return (language or "").strip().lower()
