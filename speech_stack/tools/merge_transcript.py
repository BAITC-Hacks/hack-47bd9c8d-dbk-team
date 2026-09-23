"""Склейка расшифровки с диаризацией: слово уходит тому, кто говорил в его СЕРЕДИНЕ.

Почему по середине, а не по началу: на стыке реплик начало слова часто попадает
в хвост предыдущего говорящего, и реплики начинают «перетекать» друг в друга.
Середина устойчивее на тех же данных.
"""
import json, sys
from pathlib import Path

def speaker_at(t, segs):
    for s in segs:
        if s["start"] <= t <= s["end"]:
            return s["speaker"]
    best, dist = None, 1e9
    for s in segs:                       # слово вне всех сегментов — берём ближайший
        d = 0 if s["start"] <= t <= s["end"] else min(abs(t - s["start"]), abs(t - s["end"]))
        if d < dist: best, dist = s["speaker"], d
    return best

def mmss(t): return f"{int(t)//60:02d}:{int(t)%60:02d}"

def build(asr, diar):
    segs = diar.get("segments", diar if isinstance(diar, list) else [])
    words = asr.get("words") or []
    turns = []
    for w in words:
        mid = (w["start"] + w["end"]) / 2
        spk = speaker_at(mid, segs)
        if turns and turns[-1]["speaker"] == spk:
            turns[-1]["words"].append(w)
        else:
            turns.append({"speaker": spk, "words": [w]})
    out = []
    for t in turns:
        text = " ".join(x["word"] for x in t["words"]).strip()
        text = text.replace(" ,", ",").replace(" .", ".").replace(" ?", "?").replace(" !", "!")
        out.append({"speaker": t["speaker"], "start": t["words"][0]["start"],
                    "end": t["words"][-1]["end"], "text": text})
    return out, segs

def main(asr_p, diar_p, title, src, out_p):
    asr = json.load(open(asr_p)); diar = json.load(open(diar_p))
    turns, segs = build(asr, diar)
    spk = sorted({t["speaker"] for t in turns})
    talk = {s: 0.0 for s in spk}
    for t in turns: talk[t["speaker"]] += t["end"] - t["start"]
    total = sum(talk.values()) or 1
    L = []
    L.append(f"# {title}\n")
    L.append(f"**Источник:** `{src}`  ")
    # Поле duration в ответе ASR врёт: на записи 274 с оно вернуло 16.6.
    # Берём фактический конец по данным — последнее слово и последний сегмент
    # диаризации, — а само поле оставляем как нижнюю границу.
    real_end = max(
        [asr.get("duration") or 0.0]
        + [w.get("end", 0.0) for w in (asr.get("words") or [])]
        + [sg.get("end", 0.0) for sg in (diar.get("segments") or [])]
        + [t["end"] for t in turns]
    )
    L.append(f"**Длительность:** {mmss(real_end)}  ")
    L.append(f"**Язык:** {asr.get('language')} (определён автоматически, уверенность {asr.get('language_probability')})  ")
    L.append(f"**Распознавание:** `{asr.get('route')}`  ")
    L.append("**Диаризация:** `nvidia/diar_streaming_sortformer_4spk-v2`\n")
    L.append("## Говорящие\n")
    L.append("Ярлыки условны и устойчивы только ВНУТРИ одной записи: «Говорящий 1» "
             "в двух разных файлах — это, вообще говоря, разные люди. Имена появятся, "
             "только если голоса зарегистрированы в службе опознания.\n")
    L.append("| Ярлык | Реплик | Речи, с | Доля |")
    L.append("|---|---:|---:|---:|")
    for s in spk:
        n = sum(1 for t in turns if t["speaker"] == s)
        L.append(f"| Говорящий {s + 1} | {n} | {talk[s]:.0f} | {talk[s] / total * 100:.0f} % |")
    L.append("\n## Расшифровка\n")
    for t in turns:
        if not t["text"]: continue
        L.append(f"**[{mmss(t['start'])}] Говорящий {t['speaker'] + 1}:** {t['text']}\n")
    Path(out_p).write_text("\n".join(L), encoding="utf-8")
    print(f"{out_p}: реплик {len(turns)}, говорящих {len(spk)}")

if __name__ == "__main__":
    main(*sys.argv[1:])
