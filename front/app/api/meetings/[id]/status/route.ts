import { NextResponse } from "next/server";
import { config } from "@/lib/config";
import { statResult } from "@/lib/minio";
import { getStatus, setStatus } from "@/lib/store";
import type { MeetingStatus } from "@/lib/types";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const MOCK_PROCESSING_MS = 6000;

export async function GET(
  _req: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  const stored = getStatus(id);

  if (config.mock) {
    if (!stored) {
      return NextResponse.json({ error: "Встреча не найдена" }, { status: 404 });
    }
    const elapsed = Date.now() - new Date(stored.updated_at).getTime();
    if (stored.state === "processing" && elapsed > MOCK_PROCESSING_MS) {
      return NextResponse.json(
        setStatus({
          meeting_id: id,
          state: "ready",
          result_key: `${id}/result.json`,
        }),
      );
    }
    return NextResponse.json(stored);
  }

  if (stored) {
    return NextResponse.json(stored);
  }

  // Fallback: consumer may have missed the event (restart, other instance).
  // Probe the results bucket directly.
  const resultKey = `${id}/result.json`;
  const stat = await statResult(resultKey).catch(() => null);
  if (stat) {
    const status: MeetingStatus = setStatus({
      meeting_id: id,
      state: "ready",
      result_key: resultKey,
    });
    return NextResponse.json(status);
  }

  return NextResponse.json({ error: "Встреча не найдена" }, { status: 404 });
}
