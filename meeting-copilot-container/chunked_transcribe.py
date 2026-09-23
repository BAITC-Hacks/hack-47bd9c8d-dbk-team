#!/usr/bin/env python3
"""Распознавание длинной записи через прокси с ограничением по времени ответа.

Зачем. Шлюз за Cloudflare ждёт ответ около 100 секунд и дальше отдаёт 524,
не дожидаясь. На часовом совещании распознавание в один запрос в это окно не
укладывается — обработка падала с «HTTP 524» на втором шаге конвейера.

Как. Короткая запись идёт одним запросом, как раньше: поведение не меняется.
Длинная режется на куски и склеивается обратно со сдвигом таймкодов. Кусок
берётся большим — десять минут по умолчанию: при RTF около 0.06 это секунд
сорок работы, вдвое меньше лимита, а границ на часовой записи получается
всего пять. Резать мельче вредно: модель теряет контекст и путает слова на
стыках, а стыков становится больше.

Формат ответа тот же verbose_json, что и у одиночного запроса, — вызывающий
код о разрезании не знает.

    python3 chunked_transcribe.py ВХОД.mp3 ВЫХОД.json \
        --url https://stt.aibots.kz/v1/audio/transcriptions \
        --token "$STT_TOKEN" --language auto [--hotwords "Иванов,Петров"]
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import requests

# Порог и размер куска. Оба настраиваются окружением: у другого шлюза окно
# может быть иным, и менять код ради этого не нужно.
CHUNK_SECONDS = int(os.environ.get("ASR_CHUNK_SECONDS", "600"))
CHUNK_THRESHOLD = int(os.environ.get("ASR_CHUNK_THRESHOLD_SECONDS", "900"))
REQUEST_TIMEOUT = int(os.environ.get("ASR_REQUEST_TIMEOUT", "300"))


def audio_duration(path: Path) -> float:
    """Длительность из самого файла.

    Поле duration в ответе распознавания занижено (на записи 274 с возвращает
    16.6), поэтому доверять можно только контейнеру.
    """
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    return float(out)


def transcribe_one(path: Path, url: str, token: str, language: str,
                   hotwords: str | None) -> dict:
    files = {"file": (path.name, path.open("rb"), "audio/mpeg")}
    data = {"language": language, "response_format": "verbose_json"}
    if hotwords:
        data["hotwords"] = hotwords
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    resp = requests.post(url, files=files, data=data, headers=headers,
                         timeout=REQUEST_TIMEOUT)
    if resp.status_code != 200:
        raise RuntimeError(
            f"HTTP {resp.status_code} от {url}: {resp.text[:400]}"
        )
    return resp.json()


def split_audio(path: Path, work: Path, seconds: int) -> list[Path]:
    """Режет по границам кусков без перекодирования — быстро и без потерь."""
    pattern = str(work / "part_%03d.mp3")
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(path),
         "-f", "segment", "-segment_time", str(seconds), "-c", "copy", pattern],
        check=True,
    )
    return sorted(work.glob("part_*.mp3"))


def shift(items: list[dict], offset: float) -> list[dict]:
    """Таймкоды куска — от его начала; переводим в шкалу всей записи."""
    out = []
    for item in items:
        moved = dict(item)
        for key in ("start", "end"):
            if isinstance(moved.get(key), (int, float)):
                moved[key] = moved[key] + offset
        out.append(moved)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("audio")
    ap.add_argument("output")
    ap.add_argument("--url", required=True)
    ap.add_argument("--token", default="")
    ap.add_argument("--language", default="auto")
    ap.add_argument("--hotwords", default="")
    args = ap.parse_args()

    audio = Path(args.audio)
    hotwords = args.hotwords or None

    try:
        duration = audio_duration(audio)
    except Exception as exc:                      # ffprobe недоступен или битый файл
        print(f"[!] Не удалось определить длительность: {exc}", file=sys.stderr)
        duration = 0.0

    if duration and duration > CHUNK_THRESHOLD:
        parts_note = int(duration // CHUNK_SECONDS) + 1
        print(f"[*] Запись {duration / 60:.1f} мин — режем на {parts_note} "
              f"куска по {CHUNK_SECONDS // 60} мин: шлюз не ждёт дольше "
              f"полутора минут на запрос", file=sys.stderr)
    else:
        result = transcribe_one(audio, args.url, args.token, args.language, hotwords)
        Path(args.output).write_text(
            json.dumps(result, ensure_ascii=False), encoding="utf-8")
        return 0

    merged: dict = {"text": "", "segments": [], "words": []}
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        parts = split_audio(audio, work, CHUNK_SECONDS)
        if not parts:
            raise RuntimeError("ffmpeg не создал ни одного куска")

        texts: list[str] = []
        offset = 0.0
        for index, part in enumerate(parts, 1):
            print(f"[*] Кусок {index}/{len(parts)}", file=sys.stderr)
            piece = transcribe_one(part, args.url, args.token, args.language, hotwords)

            texts.append((piece.get("text") or "").strip())
            merged["segments"].extend(shift(piece.get("segments") or [], offset))
            merged["words"].extend(shift(piece.get("words") or [], offset))

            # Первый кусок задаёт язык и маршрут для всей записи.
            if index == 1:
                for key in ("language", "language_probability", "route",
                            "detected_language"):
                    if key in piece:
                        merged[key] = piece[key]

            # Сдвиг следующего куска — по фактической длине этого, а не по
            # заданному размеру: последний кусок короче, и ffmpeg режет по
            # ближайшему кадру, а не ровно по секунде.
            offset += audio_duration(part)

    merged["text"] = " ".join(t for t in texts if t)
    merged["duration"] = duration
    Path(args.output).write_text(
        json.dumps(merged, ensure_ascii=False), encoding="utf-8")
    print(f"[*] Склеено: {len(merged['words'])} слов, "
          f"{len(merged['segments'])} сегментов", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
