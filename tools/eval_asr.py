#!/usr/bin/env python3
"""Замер качества распознавания на казахском и шала-казахском.

CER считается против эталонного текста, с которого синтезировались сэмплы.
Нормализация: NFKC, нижний регистр, пунктуация выброшена, пробелы схлопнуты.
Аудио в репозиторий не публикуется — задайте SAMPLES на свой каталог.
"""
import json, os, subprocess, unicodedata, re
S = os.environ.get("SAMPLES", "./samples")
def norm(s):
    s = unicodedata.normalize("NFKC", s).lower()
    s = re.sub(r"[^\w\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()
def lev(a, b):
    prev = list(range(len(b)+1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j]+1, cur[j-1]+1, prev[j-1]+(ca != cb)))
        prev = cur
    return prev[-1]
def asr(p, lang="auto"):
    o = subprocess.run(["curl","-s","-m","120","-F","file=@"+p,"-F","language="+lang,
        "-F","response_format=verbose_json",
        os.environ.get("ASR_URL", "http://127.0.0.1:18000") + "/v1/audio/transcriptions"], capture_output=True, text=True).stdout
    return json.loads(o)
KK = "Мен енді қазақша осылай сөйлей аламын, керек болса нақты уақытта да!"
RU_MIX = "Здравствуйте Азамат! Вы айтпақшы что-то говорили про плохое качество генерации на казахском?"
CASES = [("azamat_kk_onevoice", KK, "чистый казахский"),
         ("azamat_seam", RU_MIX + " " + RU_MIX + " " + KK, "шала: 2 варианта русской + казахская")]
for name, ref, what in CASES:
    r = asr(S + "/" + name + ".wav")
    hyp = r.get("text") or ""
    R, H = norm(ref), norm(hyp)
    print("--- %s (%s)" % (name, what))
    print("    route=%s lang=%s" % (r.get("route"), r.get("language")))
    print("    CER=%.3f (эталон %d симв.)" % (lev(R,H)/max(len(R),1), len(R)))
    print("    распознано: " + hyp[:200])
