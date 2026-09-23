import { NextResponse } from "next/server";
import { config } from "@/lib/config";
import { listCommitments, type CommitmentEntry } from "@/lib/commitments-store";
import type { Commitment } from "@/lib/types";
import sampleResult from "@/mock/sample-result.json";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

// Scenario 2: all commitments with deadlines, across meetings.
export async function GET() {
  if (config.mock) {
    const demo: CommitmentEntry[] = (
      sampleResult.commitments as unknown as Commitment[]
    ).map((c) => ({
      ...c,
      meeting_id: sampleResult.meeting_id,
    }));
    return NextResponse.json({ commitments: demo, mock: true });
  }
  return NextResponse.json({ commitments: listCommitments() });
}
