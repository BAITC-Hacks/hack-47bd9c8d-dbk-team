import { NextResponse } from "next/server";
import { getResultJson } from "@/lib/minio";
import { isLang } from "@/lib/languages";
import { translateResult } from "@/lib/translate";
import type { MeetingResult } from "@/lib/types";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
// Перевод считается на своей модели и занимает десятки секунд на длинном
// саммари; результат кэшируется, поэтому долгим бывает только первый запрос.
export const maxDuration = 300;

export async function POST(
  req: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  const { searchParams } = new URL(req.url);
  const lang = searchParams.get("lang");

  if (!isLang(lang)) {
    return NextResponse.json(
      { error: "Укажите язык: ru, kk или en." },
      { status: 400 },
    );
  }

  try {
    const original = await getResultJson<MeetingResult>(`${id}/result.json`);
    const translated = await translateResult(original, lang);
    return NextResponse.json(translated);
  } catch (err) {
    console.error("[translate] failed", err);
    return NextResponse.json(
      { error: "Не удалось перевести протокол. Попробуйте ещё раз." },
      { status: 502 },
    );
  }
}
