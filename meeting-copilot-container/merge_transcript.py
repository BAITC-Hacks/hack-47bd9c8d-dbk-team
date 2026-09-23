#!/usr/bin/env python3
"""
Склеивает данные из двух источников:
  1. VTT-файл (Zoom) — из него берутся ТОЛЬКО тайминги (start/end) и имя говорящего.
     Собственный текст распознавания Zoom из VTT отбрасывается, т.к. он низкого качества.
  2. JSON-файл (распознавание, например Whisper) — из него берётся качественный текст
     на уровне отдельных слов (data['words']), с привязкой по времени.

Для каждой реплики (cue) из VTT скрипт находит все слова из JSON, чьё время
попадает в её временной интервал, и склеивает их в единый текст.
Если слово JSON "разрезано" между двумя репликами VTT — оно относится к той
реплике, в которую попадает середина слова (или к ближайшей по времени).

Результат — аккуратный, с отступами JSON вида:
[
  {
    "start": "00:14:18.516",
    "end": "00:14:20.149",
    "start_sec": 858.516,
    "end_sec": 860.149,
    "speaker": "АО \"НИХ \"Байтерек\"",
    "text": "..."
  },
  ...
]

Если VTT целиком на английском (кириллица в репликах не встречается), считаем,
что собственных субтитров Zoom достаточно — аудио на распознавание не отправляем,
а сразу схлопываем реплики VTT по говорящему (режим --vtt-only).

Если VTT вообще нет (например, запись с телефона/видео без субтитров Zoom),
роль "реплик со спикером" играют сегменты сервиса диаризации ai.kdb.kz
(/api/diar/v1/audio/diarize) — режим --diar-merge. Спикеры в этом случае
безымянные: "Speaker 0", "Speaker 1" и т.д., локальные для записи.

Использование:
    python3 merge_transcript.py transcript.vtt call.json output.json
    python3 merge_transcript.py transcript.vtt output.json --vtt-only
    python3 merge_transcript.py call.json diarize.json output.json --diar-merge
    python3 merge_transcript.py --detect-lang transcript.vtt
"""

import json
import re
import sys
import bisect
from pathlib import Path


TIMESTAMP_RE = re.compile(
    r"(\d{2}):(\d{2}):(\d{2})\.(\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2})\.(\d{3})"
)
CYRILLIC_RE = re.compile(r"[Ѐ-ӿ]")


def timestamp_to_seconds(h, m, s, ms):
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000.0


def seconds_to_timestamp(total_seconds):
    if total_seconds < 0:
        total_seconds = 0
    h = int(total_seconds // 3600)
    m = int((total_seconds % 3600) // 60)
    s = int(total_seconds % 60)
    ms = int(round((total_seconds - int(total_seconds)) * 1000))
    if ms == 1000:  # защита от округления
        ms = 0
        s += 1
        if s == 60:
            s = 0
            m += 1
            if m == 60:
                m = 0
                h += 1
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"


def parse_vtt(vtt_path):
    """
    Возвращает список реплик (cues):
        {"start_sec": float, "end_sec": float, "speaker": str, "own_text": str}
    own_text — собственный текст реплики из VTT (субтитры Zoom). В обычном
    режиме (склейка с JSON-транскрипцией) он отбрасывается, т.к. обычно
    низкого качества, но используется напрямую в режиме --vtt-only и при
    определении языка (--detect-lang).
    Формат реплики Zoom: "Имя говорящего: текст".
    """
    raw = Path(vtt_path).read_text(encoding="utf-8-sig")
    # Убираем CR, разбиваем на блоки по пустым строкам
    raw = raw.replace("\r\n", "\n").replace("\r", "\n")
    blocks = raw.split("\n\n")

    cues = []
    for block in blocks:
        lines = [l for l in block.split("\n") if l.strip() != ""]
        if not lines:
            continue

        # Находим строку с таймкодом внутри блока
        ts_line_idx = None
        for i, line in enumerate(lines):
            if "-->" in line:
                ts_line_idx = i
                break
        if ts_line_idx is None:
            continue  # блок без таймкода (например "WEBVTT")

        m = TIMESTAMP_RE.search(lines[ts_line_idx])
        if not m:
            continue
        start_sec = timestamp_to_seconds(*m.groups()[0:4])
        end_sec = timestamp_to_seconds(*m.groups()[4:8])

        # Текст реплики — все строки после таймкода
        text_lines = lines[ts_line_idx + 1:]
        if not text_lines:
            continue
        full_text = " ".join(text_lines).strip()

        # Имя говорящего до первого ": "
        speaker = None
        own_text = full_text
        if ":" in full_text:
            speaker, _, rest = full_text.partition(":")
            speaker = speaker.strip()
            own_text = rest.strip()
        if not speaker:
            speaker = "Unknown"

        cues.append({
            "start_sec": start_sec,
            "end_sec": end_sec,
            "speaker": speaker,
            "own_text": own_text,
        })

    cues.sort(key=lambda c: c["start_sec"])
    return cues


def load_words(json_path):
    """
    Возвращает список слов вида {"word": str, "start": float, "end": float},
    отсортированный по времени начала.
    """
    data = json.loads(Path(json_path).read_text(encoding="utf-8"))
    words = data.get("words")
    if not words:
        # fallback: если по какой-то причине слов нет, разбиваем сегменты на "слова"
        # с равномерным распределением времени внутри сегмента
        words = []
        for seg in data.get("segments", []):
            tokens = seg["text"].split()
            if not tokens:
                continue
            seg_start, seg_end = seg["start"], seg["end"]
            dur = (seg_end - seg_start) / len(tokens)
            for i, tok in enumerate(tokens):
                words.append({
                    "word": tok,
                    "start": seg_start + i * dur,
                    "end": seg_start + (i + 1) * dur,
                })
    words = [w for w in words if w.get("word", "").strip() != ""]
    words.sort(key=lambda w: w["start"])
    return words


def assign_words_to_cues(cues, words):
    """
    Для каждого слова находит подходящую реплику (cue) по времени:
    сначала ищем cue, чей интервал [start, end] содержит середину слова;
    если такой не нашёлся (пауза/несовпадение таймингов) — берём ближайшую
    по времени реплику.
    """
    cue_starts = [c["start_sec"] for c in cues]

    for cue in cues:
        cue["_words"] = []

    for w in words:
        mid = (w["start"] + w["end"]) / 2.0

        # бинарный поиск: последняя реплика, чей start <= mid
        idx = bisect.bisect_right(cue_starts, mid) - 1

        # Проверяем сам idx и соседний (idx+1) — слово могло попасть
        # в промежуток между репликами, тогда сравниваем расстояние.
        candidates = [i for i in (idx, idx + 1) if 0 <= i < len(cues)]

        best_idx, best_dist = None, None
        for i in candidates:
            c = cues[i]
            if c["start_sec"] <= mid <= c["end_sec"]:
                best_idx = i
                best_dist = 0
                break
            # расстояние от слова до интервала реплики
            if mid < c["start_sec"]:
                dist = c["start_sec"] - mid
            else:
                dist = mid - c["end_sec"]
            if best_dist is None or dist < best_dist:
                best_dist = dist
                best_idx = i

        if best_idx is None:
            # совсем крайний случай — ближайшая реплика по индексу idx
            best_idx = max(0, min(idx, len(cues) - 1))

        cues[best_idx]["_words"].append(w)

    return cues


def diar_segments_to_cues(diar_path):
    """
    Превращает ответ /api/diar/v1/audio/diarize в список реплик (cues) того
    же вида, что и parse_vtt: {"start_sec", "end_sec", "speaker"}. Спикеры —
    безымянные числовые id из диаризации ("Speaker 0", "Speaker 1", ...),
    локальные для конкретной записи.
    """
    data = json.loads(Path(diar_path).read_text(encoding="utf-8"))
    cues = []
    for seg in data.get("segments", []):
        cues.append({
            "start_sec": float(seg["start"]),
            "end_sec": float(seg["end"]),
            "speaker": f"Speaker {seg['speaker']}",
        })
    cues.sort(key=lambda c: c["start_sec"])
    return cues


def is_english_only(cues):
    """
    Эвристика: считаем VTT англоязычным, если ни в одной реплике нет
    кириллических символов (и есть хоть какой-то текст вообще). В этом
    случае можно не гонять аудио через распознавание речи, а взять текст
    прямо из субтитров Zoom.
    """
    has_text = False
    for cue in cues:
        text = cue.get("own_text", "")
        if text:
            has_text = True
        if CYRILLIC_RE.search(text):
            return False
    return has_text


def build_output(cues, merge_consecutive=True, text_from_words=True):
    result = []
    for cue in cues:
        if text_from_words:
            words = sorted(cue["_words"], key=lambda w: w["start"])
            text = " ".join(w["word"] for w in words).strip()
        else:
            text = cue.get("own_text", "").strip()
        if not text:
            continue  # пропускаем реплики, для которых не нашлось текста
        result.append({
            "start_sec": cue["start_sec"],
            "end_sec": cue["end_sec"],
            "speaker": cue["speaker"],
            "text": text,
        })

    if merge_consecutive:
        result = merge_consecutive_same_speaker(result)

    # приводим тайминги к строковому формату и порядку ключей start/end/speaker/text
    return [
        {
            "start": seconds_to_timestamp(item["start_sec"]),
            "end": seconds_to_timestamp(item["end_sec"]),
            "speaker": item["speaker"],
            "text": item["text"],
        }
        for item in result
    ]


def merge_consecutive_same_speaker(items):
    """
    Схлопывает подряд идущие реплики одного и того же говорящего в одну:
    - start берётся от первой реплики серии,
    - end берётся от последней реплики серии,
    - text склеивается через пробел.
    """
    if not items:
        return items

    merged = [dict(items[0])]
    for item in items[1:]:
        last = merged[-1]
        if item["speaker"] == last["speaker"]:
            last["end_sec"] = item["end_sec"]
            last["text"] = (last["text"] + " " + item["text"]).strip()
        else:
            merged.append(dict(item))
    return merged


def require_vtt_extension(path):
    if not path.endswith(".transcript.vtt"):
        print(
            f"Ошибка: ожидается файл с расширением .transcript.vtt, получено: {path}",
            file=sys.stderr,
        )
        sys.exit(1)


def write_result(result, out_path):
    Path(out_path).write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Готово: {len(result)} реплик записано в {out_path}")


def main():
    argv = sys.argv[1:]
    flags = {a for a in argv if a.startswith("--")}
    args = [a for a in argv if not a.startswith("--")]

    usage = (
        "Использование:\n"
        "  python3 merge_transcript.py <input.vtt> <input.json> <output.json> [--no-merge]\n"
        "  python3 merge_transcript.py <input.vtt> <output.json> --vtt-only [--no-merge]\n"
        "  python3 merge_transcript.py <input.json> <diarize.json> <output.json> --diar-merge [--no-merge]\n"
        "  python3 merge_transcript.py --detect-lang <input.vtt>\n"
        "  --no-merge    не схлопывать подряд идущие реплики одного говорящего\n"
        "  --vtt-only    не использовать JSON-транскрипцию, взять текст прямо из VTT\n"
        "  --diar-merge  склеить JSON-транскрипцию с сегментами диаризации (без VTT)\n"
        "  --detect-lang вывести 'en', если VTT целиком на английском, иначе 'other'"
    )

    if "--detect-lang" in flags:
        if len(args) != 1:
            print(usage, file=sys.stderr)
            sys.exit(1)
        vtt_path = args[0]
        require_vtt_extension(vtt_path)
        cues = parse_vtt(vtt_path)
        print("en" if is_english_only(cues) else "other")
        return

    diar_merge = "--diar-merge" in flags
    vtt_only = "--vtt-only" in flags
    merge_consecutive = "--no-merge" not in flags

    if diar_merge:
        if len(args) != 3:
            print(usage, file=sys.stderr)
            sys.exit(1)
        json_path, diar_path, out_path = args
        cues = assign_words_to_cues(diar_segments_to_cues(diar_path), load_words(json_path))
        result = build_output(cues, merge_consecutive=merge_consecutive, text_from_words=True)
        write_result(result, out_path)
        return

    if vtt_only:
        if len(args) != 2:
            print(usage, file=sys.stderr)
            sys.exit(1)
        vtt_path, out_path = args
        json_path = None
    else:
        if len(args) != 3:
            print(usage, file=sys.stderr)
            sys.exit(1)
        vtt_path, json_path, out_path = args

    require_vtt_extension(vtt_path)
    cues = parse_vtt(vtt_path)

    if vtt_only:
        result = build_output(cues, merge_consecutive=merge_consecutive, text_from_words=False)
    else:
        cues = assign_words_to_cues(cues, load_words(json_path))
        result = build_output(cues, merge_consecutive=merge_consecutive, text_from_words=True)

    write_result(result, out_path)


if __name__ == "__main__":
    main()
