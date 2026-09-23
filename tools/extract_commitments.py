#!/usr/bin/env python3
"""Из склеенного транскрипта — поручения с ответственным и сроком, плюс саммари.

Модель локальная: текст совещания не покидает контур (ограничение кейса).
Схема ответа — .planning/tasks/CONTRACT.md.
"""
import json, os, sys, urllib.request

BASE = os.environ.get("VLLM_BASE_URL", "https://vllm.aibots.kz/v1").rstrip("/")
KEY = os.environ["VLLM_API_KEY"]
MODEL = os.environ.get("VLLM_MODEL", "qwen3-vl-30b-instruct")

SYSTEM = """Ты секретарь совещания. Из расшифровки выдели поручения и составь саммари.

Поручение — это назначенная работа с ответственным лицом. Срок указывай в ISO (YYYY-MM-DD),
год бери текущий, если не назван явно. Если срока нет, ставь null.
assignee — фамилия и отчество ровно так, как звучат в записи.
quote — дословная фраза, которой поручение назначено.
speaker — ярлык говорящего, который произнёс назначение.

Отвечай ТОЛЬКО JSON без markdown-обёртки:
{"commitments":[{"id":"c1","assignee":"...","speaker":"Говорящий 1","due_date":"2026-10-15",
"due_raw":"до 15 октября","text":"...","quote":"...","confidence":"high","status":"in_progress"}],
"summary":"3-5 предложений по существу"}"""


def extract(transcript: str) -> dict:
    body = json.dumps({
        "model": MODEL,
        "messages": [{"role": "system", "content": SYSTEM},
                     {"role": "user", "content": transcript}],
        "temperature": 0.1,
        "max_tokens": 4000,
    }).encode()
    req = urllib.request.Request(
        f"{BASE}/chat/completions", data=body,
        headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json",
                 # Cloudflare отдаёт 403 на User-Agent по умолчанию у python-urllib
                 "User-Agent": "dbk-meeting-copilot/1.0"})
    with urllib.request.urlopen(req, timeout=300) as r:
        out = json.load(r)["choices"][0]["message"]["content"]
    # модель иногда заворачивает в ```json — снимаем обёртку
    out = out.strip()
    if out.startswith("```"):
        out = out.split("```")[1].removeprefix("json").strip()
    return json.loads(out)


if __name__ == "__main__":
    text = open(sys.argv[1], encoding="utf-8").read()
    res = extract(text)
    json.dump(res, open(sys.argv[2], "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"{sys.argv[2]}: поручений {len(res.get('commitments', []))}")
