import { NextResponse } from "next/server";
import { getResultJson } from "@/lib/minio";
import { isLang } from "@/lib/languages";
import {
  isTranslating,
  readTranslation,
  startTranslation,
} from "@/lib/translate";
import type { MeetingResult } from "@/lib/types";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

// Перевод длинного саммари занимает около двух минут, а прокси перед нами
// рвёт запрос на сотне секунд. Поэтому POST только ставит работу в очередь,
// а интерфейс опрашивает GET до готовности.

export async function POST(
  req: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  const lang = new URL(req.url).searchParams.get("lang");
  if (!isLang(lang)) {
    return NextResponse.json(
      { error: "Укажите язык: ru, kk или en." },
      { status: 400 },
    );
  }

  const ready = await readTranslation(id, lang);
  if (ready) return NextResponse.json({ state: "ready", result: ready });

  try {
    const original = await getResultJson<MeetingResult>(`${id}/result.json`);
    startTranslation(original, lang);
    return NextResponse.json({ state: "pending" }, { status: 202 });
  } catch (err) {
    console.error("[translate] не удалось прочитать протокол", err);
    return NextResponse.json(
      { error: "Протокол не найден в хранилище." },
      { status: 404 },
    );
  }
}

export async function GET(
  req: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  const lang = new URL(req.url).searchParams.get("lang");
  if (!isLang(lang)) {
    return NextResponse.json(
      { error: "Укажите язык: ru, kk или en." },
      { status: 400 },
    );
  }

  const ready = await readTranslation(id, lang);
  if (ready) return NextResponse.json({ state: "ready", result: ready });
  if (isTranslating(id, lang)) {
    return NextResponse.json({ state: "pending" }, { status: 202 });
  }
  return NextResponse.json({ state: "idle" }, { status: 404 });
}
