import { NextResponse } from "next/server";
import { cacheResult } from "@/lib/commitments-store";
import { config } from "@/lib/config";
import { getResultJson } from "@/lib/minio";
import type { MeetingResult } from "@/lib/types";
import sampleResult from "@/mock/sample-result.json";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(
  _req: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;

  if (config.mock) {
    return NextResponse.json({ ...sampleResult, meeting_id: id });
  }

  try {
    const result = await getResultJson<MeetingResult>(`${id}/result.json`);
    cacheResult(result);
    return NextResponse.json(result);
  } catch (err) {
    console.error("[result] failed to load", id, err);
    return NextResponse.json(
      { error: "Результат ещё не готов или не найден." },
      { status: 404 },
    );
  }
}
