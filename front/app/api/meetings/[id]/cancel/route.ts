import { NextResponse } from "next/server";
import { dropSession, hasSession } from "@/lib/recording-sessions";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

// Discard a live recording session (secretary pressed «Отменить запись»).
export async function POST(
  _req: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  if (!hasSession(id)) {
    return NextResponse.json(
      { error: "Сессия записи не найдена." },
      { status: 404 },
    );
  }
  dropSession(id);
  return NextResponse.json({ ok: true });
}
