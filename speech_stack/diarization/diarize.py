"""Апостериорные вероятности -> сегменты, и склейка речи одного говорящего.

`segments_from` намеренно повторяет `training/diar_pilot_sortformer.py` строка
в строку: этой функцией размечен весь годовой архив и на ней получена приёмка
слушателя. Две реализации одной нарезки разошлись бы незаметно, и сервис начал
бы отдавать не то, что лежит в обучающей выборке.
"""
from __future__ import annotations

import numpy as np

from config import FRAME


def segments_from(P: np.ndarray, min_s: float, max_s: float):
    """(сегменты, время речи, время наложения) из матрицы T x S.

    СЕГМЕНТ — связный участок, где активен РОВНО ОДИН и тот же говорящий.
    Участки, где активны двое, в сегменты не попадают и остаются в знаменателе:
    это и есть та часть, которую никакая сегментация не спасёт. На годовом
    архиве наложение — 8.2 % речевого времени, то есть потолок метрики «доля
    речи в односпикерных сегментах» равен 91.8 %, а не 100 %. Прятать его,
    выбрасывая из знаменателя, значит рисовать цифру.
    """
    act = P > 0.5
    n_any = int(act.any(1).sum())
    n_ovl = int((act.sum(1) >= 2).sum())
    segs, cur, start = [], None, None
    for i in range(len(act)):
        who = np.where(act[i])[0]
        k = int(who[0]) if len(who) == 1 else None
        if k != cur:
            if cur is not None and start is not None:
                s, e = start * FRAME, i * FRAME
                if min_s <= e - s <= max_s:
                    segs.append({"start": round(s, 2), "end": round(e, 2), "speaker": cur})
            cur, start = k, i
    if cur is not None and start is not None:
        s, e = start * FRAME, len(act) * FRAME
        if min_s <= e - s <= max_s:
            segs.append({"start": round(s, 2), "end": round(e, 2), "speaker": cur})
    return segs, n_any * FRAME, n_ovl * FRAME


def pool(y: np.ndarray, segs: list[dict], spk: int, sr: int,
         limit_s: float, order: str = "long") -> np.ndarray:
    """Речь одного говорящего, склеенная в один кусок не длиннее limit_s.

    Берём САМЫЕ ДЛИННЫЕ сегменты, а не первые по времени: начало звонка это
    приветствие в полсекунды, а эмбеддинг на коротком отрезке — шум (тот же
    эффект, что записан про ECAPA в `diar_resplit.py`, и причина, по которой
    там окно 1.0 с, а не 0.5). Порядок кусков внутри склейки на эмбеддинг не
    влияет — TitaNet усредняет по времени, — поэтому сортировка по длине не
    искажает результат, а только выбирает материал.
    """
    mine = [s for s in segs if s["speaker"] == spk]
    if order == "long":
        mine = sorted(mine, key=lambda s: s["end"] - s["start"], reverse=True)
    parts, got = [], 0.0
    for s in mine:
        a, b = int(s["start"] * sr), int(s["end"] * sr)
        parts.append(y[a:b])
        got += s["end"] - s["start"]
        if got >= limit_s:
            break
    return np.concatenate(parts) if parts else np.zeros(0, dtype=np.float32)


def speaker_stats(segs: list[dict]) -> list[dict]:
    """Сколько речи у каждого найденного говорящего — в порядке убывания."""
    agg: dict[int, float] = {}
    for s in segs:
        agg[s["speaker"]] = agg.get(s["speaker"], 0.0) + (s["end"] - s["start"])
    return [{"speaker": k, "speech_s": round(v, 2), "segments":
             sum(1 for s in segs if s["speaker"] == k)}
            for k, v in sorted(agg.items(), key=lambda kv: -kv[1])]
