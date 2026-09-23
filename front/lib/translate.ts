import { getMinio, ensureBucket } from "./minio";
import { config } from "./config";
import { LANGUAGES, type Lang } from "./languages";
import type { MeetingResult } from "./types";

/**
 * Перевод саммари и поручений на своей модели.
 *
 * Совещания в Казахстане идут на двух языках, а протокол нужен на том, на
 * котором его будут читать и согласовывать. Переводим только саммари и
 * поручения: транскрипт — это дословная запись, и переводить её значит
 * подменять сказанное.
 *
 * Модель та же, что и для разбора (`vllm.aibots.kz`), поэтому текст совещания
 * не покидает контур — этого требует раздел «Ограничения» кейса. Результат
 * кладётся рядом с исходным протоколом: перевод одного совещания считается
 * один раз.
 */

export { LANGUAGES, isLang, type Lang } from "./languages";

const BASE = (
  process.env.VLLM_BASE_URL ?? "https://vllm.aibots.kz/v1"
).replace(/\/$/, "");
const MODEL = process.env.VLLM_MODEL ?? "qwen3-vl-30b-instruct";

function cacheKey(meetingId: string, lang: Lang) {
  return `${meetingId}/result.${lang}.json`;
}

async function readCache(
  meetingId: string,
  lang: Lang,
): Promise<MeetingResult | null> {
  try {
    const stream = await getMinio().getObject(
      config.minio.resultsBucket,
      cacheKey(meetingId, lang),
    );
    const chunks: Buffer[] = [];
    for await (const c of stream) chunks.push(c as Buffer);
    return JSON.parse(Buffer.concat(chunks).toString("utf-8"));
  } catch {
    return null;
  }
}

async function writeCache(meetingId: string, lang: Lang, data: MeetingResult) {
  try {
    const body = Buffer.from(JSON.stringify(data, null, 2), "utf-8");
    await ensureBucket(config.minio.resultsBucket);
    await getMinio().putObject(
      config.minio.resultsBucket,
      cacheKey(meetingId, lang),
      body,
      body.length,
      { "Content-Type": "application/json" },
    );
  } catch {
    // перевод посчитается заново в следующий раз — не критично
  }
}

const SYSTEM = (lang: Lang) => `Ты переводчик деловых документов.

Переведи присланный JSON на ${LANGUAGES[lang]} язык. Правила:
- Переводи ТОЛЬКО значения полей summary, text, quote, due_raw, classification.
- Имена людей, названия организаций, даты в формате ГГГГ-ММ-ДД и идентификаторы
  оставляй без изменений.
- Сохраняй разметку саммари как есть: заголовки, списки, таблицы, выделение.
- Ничего не добавляй от себя и ничего не выбрасывай.

Ответ — ТОЛЬКО JSON того же вида, без markdown-обёртки.`;

interface Payload {
  summary: string;
  commitments: {
    id: string;
    text: string;
    quote: string;
    due_raw: string;
    classification?: string | null;
  }[];
}

// Перевод длинного саммари занимает около двух минут, а прокси рвёт запрос
// на сотне секунд. Поэтому работа идёт в фоне: запрос её запускает и сразу
// отвечает, интерфейс опрашивает готовность. Карта нужна, чтобы повторные
// нажатия не запускали второй счёт того же самого.
const globalRef = globalThis as unknown as {
  __translations?: Map<string, Promise<MeetingResult>>;
};
const inFlight = (globalRef.__translations ??= new Map());

function jobKey(meetingId: string, lang: Lang) {
  return `${meetingId}:${lang}`;
}

/** Готовый перевод, если он уже посчитан. */
export async function readTranslation(
  meetingId: string,
  lang: Lang,
): Promise<MeetingResult | null> {
  return readCache(meetingId, lang);
}

/** Считается ли перевод прямо сейчас. */
export function isTranslating(meetingId: string, lang: Lang): boolean {
  return inFlight.has(jobKey(meetingId, lang));
}

/** Запускает перевод в фоне и сразу возвращает управление. */
export function startTranslation(result: MeetingResult, lang: Lang): void {
  const key = jobKey(result.meeting_id, lang);
  if (inFlight.has(key)) return;
  const job = translateResult(result, lang).finally(() => inFlight.delete(key));
  // Ошибка обрабатывается опросом: перевода просто не появится, и интерфейс
  // скажет об этом. Здесь глушим, чтобы не было необработанного отказа.
  job.catch(() => {});
  inFlight.set(key, job);
}

export async function translateResult(
  result: MeetingResult,
  lang: Lang,
): Promise<MeetingResult> {
  const cached = await readCache(result.meeting_id, lang);
  if (cached) return cached;

  const key = process.env.VLLM_API_KEY;
  if (!key) throw new Error("Перевод не настроен: нет ключа модели.");

  const payload: Payload = {
    summary: result.summary,
    commitments: result.commitments.map((c) => ({
      id: c.id,
      text: c.text,
      quote: c.quote,
      due_raw: c.due_raw,
      classification: c.classification ?? null,
    })),
  };

  const res = await fetch(`${BASE}/chat/completions`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${key}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      model: MODEL,
      messages: [
        { role: "system", content: SYSTEM(lang) },
        { role: "user", content: JSON.stringify(payload, null, 2) },
      ],
      temperature: 0.1,
      max_tokens: 8000,
    }),
  });
  if (!res.ok) {
    throw new Error(`Модель ответила ${res.status}`);
  }

  const body = await res.json();
  let content: string = body.choices?.[0]?.message?.content ?? "";
  content = content.trim();
  if (content.startsWith("```")) {
    content = content.split("```")[1].replace(/^json/i, "").trim();
  }

  const translated = JSON.parse(content) as Payload;
  const byId = new Map(translated.commitments?.map((c) => [c.id, c]) ?? []);

  const out: MeetingResult = {
    ...result,
    summary: translated.summary || result.summary,
    commitments: result.commitments.map((c) => {
      const t = byId.get(c.id);
      return t
        ? {
            ...c,
            text: t.text || c.text,
            quote: t.quote || c.quote,
            due_raw: t.due_raw || c.due_raw,
            classification: t.classification ?? c.classification,
          }
        : c;
    }),
  };

  await writeCache(result.meeting_id, lang, out);
  return out;
}
