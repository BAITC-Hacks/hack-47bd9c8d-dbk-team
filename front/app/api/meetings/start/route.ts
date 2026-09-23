import { randomUUID } from "crypto";
import { NextResponse } from "next/server";
import { createSession } from "@/lib/recording-sessions";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

// Scenario 1: secretary presses «Начать запись» — we allocate a meeting_id
// and a chunk buffer before the microphone starts.
export async function POST() {
  const meetingId = `m-${randomUUID().slice(0, 8)}`;
  createSession(meetingId);
  return NextResponse.json({ meeting_id: meetingId });
}
