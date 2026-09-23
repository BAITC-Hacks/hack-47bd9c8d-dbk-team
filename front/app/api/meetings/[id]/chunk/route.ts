import { NextResponse } from "next/server";
import { addChunk, hasSession } from "@/lib/recording-sessions";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

// Receives MediaRecorder chunks (raw body) with ?seq=N&mime=audio/webm.
export async function POST(
  req: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  if (!hasSession(id)) {
    return NextResponse.json(
      { error: "Сессия записи не найдена." },
      { status: 404 },
    );
  }

  const url = new URL(req.url);
  const seq = Number(url.searchParams.get("seq"));
  const mime = url.searchParams.get("mime") ?? "audio/webm";
  if (!Number.isInteger(seq) || seq < 0) {
    return NextResponse.json({ error: "Некорректный seq." }, { status: 400 });
  }

  const body = Buffer.from(await req.arrayBuffer());
  if (body.length === 0) {
    return NextResponse.json({ error: "Пустой чанк." }, { status: 400 });
  }

  addChunk(id, seq, body, mime);
  return NextResponse.json({ ok: true, seq, bytes: body.length });
}
