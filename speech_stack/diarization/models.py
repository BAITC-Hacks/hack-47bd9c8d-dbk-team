"""Загрузка Sortformer и TitaNet один раз на процесс, плюс декод аудио.

Обе модели вместе занимают ~0.7 ГБ VRAM — на фоне 65 из 98 ГБ, которые держат
продакшн-сервисы, это ничто, поэтому обе держатся резидентно и запрос не платит
за загрузку (Sortformer поднимается ~25 с, TitaNet ~10 с).
"""
from __future__ import annotations

import io
import logging
import os
import threading
import uuid

import numpy as np

from config import DEVICE, DIAR_MODEL, SPK_MODEL, SR, TMPDIR

log = logging.getLogger("diar.models")
_lock = threading.Lock()
_diar = None
_spk = None


def _device() -> str:
    import torch
    return DEVICE if (DEVICE.startswith("cuda") and torch.cuda.is_available()) else "cpu"


def load() -> tuple:
    """(модель диаризации, модель голоса). Идемпотентно и потокобезопасно."""
    global _diar, _spk
    if _diar is not None and _spk is not None:
        return _diar, _spk
    with _lock:
        if _diar is None:
            from nemo.collections.asr.models import SortformerEncLabelModel
            log.info("гружу %s", DIAR_MODEL)
            m = SortformerEncLabelModel.from_pretrained(DIAR_MODEL).eval()
            _diar = m.to(_device())
        if _spk is None:
            from nemo.collections.asr.models import EncDecSpeakerLabelModel
            log.info("гружу %s", SPK_MODEL)
            m = EncDecSpeakerLabelModel.from_pretrained(SPK_MODEL).eval()
            _spk = m.to(_device())
    return _diar, _spk


def decode(data: bytes) -> np.ndarray:
    """Байты любого читаемого формата -> моно 16 кГц float32.

    Через librosa, а не soundfile напрямую: звонки приходят в mp3, и на них
    soundfile умеет далеко не всё. Рабочая точка у нас 8 кГц телефонная, но
    обе модели ждут 16 кГц, поэтому апсемплинг обязателен и он ничего не
    портит — верхняя половина полосы просто пуста, и модель это видела.
    """
    import librosa
    y, _ = librosa.load(io.BytesIO(data), sr=SR, mono=True)
    return np.asarray(y, dtype=np.float32)


def posteriors(y: np.ndarray) -> np.ndarray:
    """Матрица T x S апостериорных вероятностей активности говорящих.

    Через ВРЕМЕННЫЙ WAV, а не numpy, хотя numpy на 20 % быстрее. Пути расходятся
    систематически: на 40 звонках побайтово совпали 89.5 % сегментов, остальные
    сдвинуты на кадр (медиана 0.08 с, максимум 2.88 с). Приёмка слушателем — та
    самая, где 0 дефектов на 158 отрезках, — получена на wav-пути, и менять его
    ради скорости значит вносить неизмеренную дельту в то, что уже принято.

    Имя файла уникально на запрос: diar_full.py брал имя по PID, потому что был
    один процесс на прогон; у сервиса два параллельных запроса затёрли бы друг
    друга и вернули чужую диаризацию, не упав.
    """
    import soundfile as sf
    import torch

    diar, _ = load()
    tmp = os.path.join(TMPDIR, f"diar_{os.getpid()}_{uuid.uuid4().hex}.wav")
    try:
        sf.write(tmp, y, SR)
        with torch.inference_mode():
            out = diar.diarize(audio=[tmp], batch_size=1,
                               include_tensor_outputs=True, verbose=False)
        P = np.squeeze(out[1][0].detach().cpu().numpy())
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass
    if P.ndim == 1:
        P = P[:, None]
    # Sortformer иногда отдаёт S x T. Ориентируемся по тому, что говорящих
    # заведомо меньше, чем кадров: 4 против сотен.
    return P.T if P.shape[0] < P.shape[1] else P


def embed(chunks: list[np.ndarray]) -> np.ndarray:
    """L2-нормированные эмбеддинги TitaNet, по одному на кусок.

    Нормируем здесь, чтобы косинус дальше был обычным скалярным произведением
    и никто ниже по коду не забыл нормировать — сравнение ненормированных
    векторов дало бы правдоподобные, но неверные числа.
    """
    import torch

    _, spk = load()
    dev = _device()
    out = []
    with torch.inference_mode():
        for c in chunks:
            x = torch.from_numpy(np.asarray(c, dtype=np.float32)).unsqueeze(0).to(dev)
            n = torch.tensor([x.shape[1]], device=dev)
            _, e = spk.forward(input_signal=x, input_signal_length=n)
            v = e.squeeze(0).float().cpu().numpy()
            out.append(v / (np.linalg.norm(v) + 1e-9))
    return np.stack(out) if out else np.zeros((0, 192), dtype=np.float32)
