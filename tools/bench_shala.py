"""Шала-казахский: какой маршрут распознавания на нём лучше.

Корпус: Tim2190/kazakh-codeswitch-asr (CC BY 4.0) — 31 запись живой смешанной
речи с ЧЕЛОВЕЧЕСКОЙ дословной расшифровкой. Метка не от whisper, а значит числу
можно верить: CER, посчитанный против чужой расшифровки, есть согласие с
учителем, а не точность.

    huggingface-cli download Tim2190/kazakh-codeswitch-asr \
        --repo-type dataset --local-dir ./kazakh-codeswitch-asr

    export STT_TOKEN=...
    python3 tools/bench_shala.py kk ru auto

Считаем pooled CER: сумма правок делить на сумму символов эталона. Рядом
печатаем три контроля, без которых число нечитаемо:
  * пустая гипотеза            — тривиальный потолок ошибки;
  * бессмыслица той же длины   — не меряем ли мы длину строки;
  * ЧУЖОЙ эталон               — умеет ли стенд провалиться вообще.
Если CER против чужого эталона близок к CER против своего, замер не о чём.
"""
import csv
import json
import os
import random
import re
import subprocess
import sys

# Куда стучимся и где лежит корпус — оба через окружение, чтобы скрипт
# работал и против шлюза с токеном, и против службы напрямую.
SRV = os.environ.get("STT_URL", "http://localhost:8080")
TOKEN = os.environ.get("STT_TOKEN", "")
ROOT = os.environ.get("SHALA_DIR", "./kazakh-codeswitch-asr")
KK = "аәбвгғдеёжзийкқлмнңоөпрстуұүфхһцчшщъыіьэюя "


def norm(s: str) -> str:
    """Регистр, пометки расшифровщика и пунктуация к делу не относятся."""
    s = s.lower()
    s = re.sub(r"\[[^\]]*\]", " ", s)          # [false_start] и прочие пометки
    s = re.sub(r"[^\w\s]", " ", s, flags=re.UNICODE)
    return re.sub(r"\s+", " ", s).strip()


def cer_parts(ref: str, hyp: str) -> tuple[int, int]:
    """(правок, символов эталона). Левенштейн на двух строках."""
    if not ref:
        return 0, 0
    prev = list(range(len(hyp) + 1))
    for i, rc in enumerate(ref, 1):
        cur = [i]
        for j, hc in enumerate(hyp, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (rc != hc)))
        prev = cur
    return prev[-1], len(ref)


def asr(path: str, lang: str) -> dict:
    cmd = ["curl", "-s", "--max-time", "180", "-F", f"file=@{path}",
           "-F", f"language={lang}", "-F", "response_format=json"]
    if TOKEN:
        cmd += ["-H", f"Authorization: Bearer {TOKEN}"]
    cmd.append(f"{SRV}/v1/audio/transcriptions")
    out = subprocess.run(cmd, capture_output=True, text=True, check=True).stdout
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        return {"text": "", "route": "ОШИБКА"}


def pooled(pairs) -> float:
    e = sum(x for x, _ in pairs)
    n = sum(y for _, y in pairs)
    return e / n if n else float("nan")


def main() -> int:
    rows = list(csv.DictReader(open(f"{ROOT}/metadata.csv")))
    langs = [l for l in (sys.argv[1:] or ["kk", "ru", "auto"])]
    refs, hyps = [], {l: [] for l in langs}
    routes = {l: {} for l in langs}

    for r in rows:
        path = f"{ROOT}/{r['file_name']}"
        if not os.path.exists(path):
            continue
        ref = norm(r["transcript_verbatim"])
        if not ref:
            continue
        refs.append(ref)
        for l in langs:
            d = asr(path, l)
            hyps[l].append(norm(d.get("text") or ""))
            k = d.get("route", "?")
            routes[l][k] = routes[l].get(k, 0) + 1

    print(f"записей: {len(refs)}, символов эталона: {sum(len(x) for x in refs)}\n")
    print(f"{'маршрут':10} {'pooled CER':>11}   куда ушло")
    print("-" * 60)
    for l in langs:
        c = pooled([cer_parts(a, b) for a, b in zip(refs, hyps[l])])
        rt = ", ".join(f"{k}×{v}" for k, v in sorted(routes[l].items()))
        print(f"{l:10} {c:11.4f}   {rt}")

    print("\nКОНТРОЛИ (без них число выше нечитаемо)")
    print("-" * 60)
    print(f"{'пустая гипотеза':34} {pooled([cer_parts(a, '') for a in refs]):8.4f}")

    rnd = random.Random(20260923)
    noise = ["".join(rnd.choice(KK) for _ in range(len(a))) for a in refs]
    print(f"{'бессмыслица той же длины':34} {pooled([cer_parts(a, b) for a, b in zip(refs, noise)]):8.4f}")

    best = langs[0]
    shifted = refs[1:] + refs[:1]
    print(f"{'ЧУЖОЙ эталон (' + best + ')':34} "
          f"{pooled([cer_parts(a, b) for a, b in zip(shifted, hyps[best])]):8.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
