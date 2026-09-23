#!/usr/bin/env python3
"""
Отправляет объединённую расшифровку (merged.json — список реплик
{start, end, speaker, text}) в LLM через OpenRouter и получает summary.

Переменные окружения читаются из файла .env (простой формат KEY=VALUE),
который лежит рядом со скриптом, либо передаётся через --env-file.
Если переменная уже задана в окружении явно (export ...), она имеет приоритет
над значением из файла.

Нужные переменные:
    OPEN_ROUTER_URL          - URL эндпоинта (обычно
                                https://openrouter.ai/api/v1/chat/completions)
    OPEN_ROUTER_AUTH_BEARER  - Bearer-токен для авторизации
    OPEN_ROUTER_MODEL        - (необязательно) модель по умолчанию

Использование:
    python3 summarize_transcript.py transcript_merged.json summary.md
    python3 summarize_transcript.py transcript_merged.json summary.md --model openai/gpt-4o-mini
    python3 summarize_transcript.py transcript_merged.json summary.md --lang ru --prompt "своя инструкция"
    python3 summarize_transcript.py transcript_merged.json summary.md --env-file /path/to/.env
"""

import argparse
import json
import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv


DEFAULT_MODEL = "zai-org/GLM-5.3"
FLASH_MODEL = "zai-org/GLM-5.3-Flash"  # дешевле в ~9 раз, чуть ниже качество
DEFAULT_ENV_FILE = Path(__file__).resolve().parent / ".env"

DEFAULT_SYSTEM_PROMPT = (
    "Ты — ассистент, который делает краткое и структурированное summary "
    "деловой встречи по её расшифровке. Расшифровка дана в виде списка реплик "
    "с таймкодами и именами говорящих. "
    "Сделай summary на русском языке в следующем формате:\n"
    "1. Краткое резюме встречи (3-5 предложений)\n"
    "2. Ключевые темы обсуждения (списком)\n"
    "3. Договорённости / решения (если есть)\n"
    "4. Открытые вопросы / что осталось непроясненным (если есть)\n"
    "5. Дальнейшие шаги (если упоминались)\n"
    "6. Поручения — последним разделом, по правилам ниже\n"
    "Пиши по делу, без воды, сохраняя важные детали (цифры, названия, имена)."
)

# Правила для последнего раздела summary. Вынесены отдельно, потому что
# подставляются вместе со списком участников встречи: без него модель охотно
# назначает ответственными людей, которых на встрече не было (их упоминали
# в третьем лице), и поручения становятся непроверяемыми.
ASSIGNMENTS_PROMPT = (
    "\n\nРаздел «Поручения» — всегда последний в документе, после всех "
    "остальных разделов.\n"
    "Поручение — это конкретное действие, которое на встрече закрепили за "
    "участником: прямая просьба или указание сделать что-то, взятое "
    "обязательство («сделаю», «подготовлю», «до пятницы пришлю»), "
    "зафиксированная договорённость о работе.\n"
    "Правила:\n"
    "- Ответственным указывай ТОЛЬКО того, кто присутствовал на встрече, то "
    "есть кого-то из списка участников ниже. Имя пиши ровно так, как оно "
    "указано в списке.\n"
    "- Если работу поручили человеку, которого на встрече не было, "
    "ответственным всё равно ставь присутствующего участника, который за это "
    "отвечает (которому дали поручение), а исполнителя упомяни в тексте "
    "поручения. Например: «Обеспечить подготовку претензии поставщику "
    "(исполнитель — юрист департамента)».\n"
    "- Не выдумывай поручения: если действие только обсуждали и ни за кем не "
    "закрепили, это не поручение — его место в разделе «Открытые вопросы».\n"
    "- Срок бери из расшифровки дословно («до конца недели», «две недели», "
    "«к 15 числа»). Если срок не называли — пиши «не указан», ничего не "
    "додумывая.\n"
    "- Формулируй поручение глаголом в неопределённой форме: «подготовить "
    "смету», «согласовать график».\n"
    "Формат раздела — таблица Markdown ровно с такими колонками:\n"
    "## Поручения\n\n"
    "| Поручение | Ответственный | Срок |\n"
    "|---|---|---|\n"
    "| Подготовить смету по дополнительным группам обучения | Иванов И.И. | 1 неделя |\n\n"
    "Если на встрече не прозвучало ни одного поручения, всё равно выведи "
    "раздел «## Поручения» и одной строкой напиши: "
    "«Поручения на встрече не зафиксированы.» — таблицу в этом случае не рисуй."
)


def participants_prompt(transcript):
    """Список участников встречи для промпта — по именам говорящих в расшифровке."""
    seen = []
    for item in transcript:
        speaker = (item.get("speaker") or "").strip()
        if speaker and speaker not in seen:
            seen.append(speaker)

    if not seen:
        return (
            "\n\nУчастники встречи по расшифровке не определены. "
            "Раздел «Поручения» всё равно выведи: если ответственного "
            "однозначно назвать нельзя, пиши в колонке «Ответственный» "
            "«не определён»."
        )

    return (
        "\n\nУчастники встречи (только они могут быть ответственными "
        "за поручения):\n" + "\n".join(f"- {name}" for name in seen)
    )


def load_env_file(path):
    """Загружает .env файл, не перезаписывая уже заданные переменные окружения."""
    load_dotenv(path, override=False)


def load_transcript(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("Ожидался список реплик в merged.json")
    return data


def transcript_to_text(transcript):
    """Приводит список реплик к плоскому текстовому виду для промпта."""
    lines = []
    for item in transcript:
        start = item.get("start", "")
        speaker = item.get("speaker", "Unknown")
        text = item.get("text", "")
        lines.append(f"[{start}] {speaker}: {text}")
    return "\n".join(lines)


def call_openrouter(transcript_text, model, system_prompt, api_url, api_key, extra_headers=None):
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    if extra_headers:
        headers.update(extra_headers)

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Вот расшифровка встречи:\n\n{transcript_text}"},
        ],
        "temperature": 0.3,
    }

    resp = requests.post(api_url, headers=headers, json=payload, timeout=180)
    resp.raise_for_status()
    data = resp.json()

    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as e:
        raise RuntimeError(f"Неожиданный формат ответа от OpenRouter: {json.dumps(data, ensure_ascii=False)[:2000]}") from e


def main():
    parser = argparse.ArgumentParser(description="Summary расшифровки через OpenRouter")
    parser.add_argument("input", help="Путь к merged.json")
    parser.add_argument("output", nargs="?", default=None, help="Куда сохранить summary (.md). По умолчанию печатает в stdout")
    parser.add_argument(
        "--env-file",
        default=str(DEFAULT_ENV_FILE),
        help=f"Путь к файлу с переменными окружения (по умолчанию {DEFAULT_ENV_FILE.name} рядом со скриптом)",
    )
    parser.add_argument(
        "--model",
        default=None,
        help=f"Модель OpenRouter (по умолчанию {DEFAULT_MODEL}, можно задать через OPEN_ROUTER_MODEL в env-файле)",
    )
    parser.add_argument(
        "--flash",
        action="store_true",
        help=f"Использовать дешёвую модель {FLASH_MODEL} вместо {DEFAULT_MODEL}",
    )
    parser.add_argument("--prompt", default=None, help="Свой системный промпт вместо дефолтного")
    args = parser.parse_args()

    load_env_file(args.env_file)

    model = args.model or os.environ.get("OPEN_ROUTER_MODEL", DEFAULT_MODEL)
    if args.flash:
        model = FLASH_MODEL
    args.model = model

    api_url = os.environ.get("OPEN_ROUTER_URL")
    api_key = os.environ.get("OPEN_ROUTER_AUTH_BEARER")

    if not api_url or not api_key:
        print(
            f"Ошибка: не заданы OPEN_ROUTER_URL и/или OPEN_ROUTER_AUTH_BEARER.\n"
            f"Задай их в файле {args.env_file} (формат KEY=VALUE) или через export в окружении.",
            file=sys.stderr,
        )
        sys.exit(1)

    transcript = load_transcript(args.input)
    transcript_text = transcript_to_text(transcript)

    # Правила по поручениям и список участников дописываются и к дефолтному
    # промпту, и к пользовательскому (--prompt): раздел с поручениями нужен
    # в summary в любом случае.
    system_prompt = (args.prompt or DEFAULT_SYSTEM_PROMPT) + ASSIGNMENTS_PROMPT
    system_prompt += participants_prompt(transcript)

    print(f"Отправляю {len(transcript)} реплик в модель {args.model}...", file=sys.stderr)
    summary = call_openrouter(
        transcript_text=transcript_text,
        model=args.model,
        system_prompt=system_prompt,
        api_url=api_url,
        api_key=api_key,
    )

    if args.output:
        Path(args.output).write_text(summary, encoding="utf-8")
        print(f"Готово: summary сохранено в {args.output}", file=sys.stderr)
    else:
        print(summary)


if __name__ == "__main__":
    main()
