import { NextResponse } from "next/server";
import { config } from "@/lib/config";
import {
  listCommitments,
  updateCommitment,
  type CommitmentEntry,
} from "@/lib/commitments-store";
import type { Commitment } from "@/lib/types";
import sampleResult from "@/mock/sample-result.json";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

// Сценарий 2: все поручения со сроками, по всем совещаниям.
export async function GET() {
  if (config.mock) {
    const demo: CommitmentEntry[] = (
      sampleResult.commitments as unknown as Commitment[]
    ).map((c) => ({ ...c, meeting_id: sampleResult.meeting_id }));
    return NextResponse.json({ commitments: demo, mock: true });
  }
  return NextResponse.json({ commitments: await listCommitments() });
}

// Адрес получателя и отметка о выполнении задаются руками: в записи совещания
// почты нет, а «выполнено» знает только человек.
export async function PATCH(req: Request) {
  const body = (await req.json().catch(() => null)) as {
    meeting_id?: string;
    commitment_id?: string;
    assignee_email?: string;
    status?: "in_progress" | "overdue" | "done";
  } | null;

  if (!body?.meeting_id || !body?.commitment_id) {
    return NextResponse.json(
      { error: "Нужны meeting_id и commitment_id." },
      { status: 400 },
    );
  }
  if (
    body.assignee_email !== undefined &&
    body.assignee_email !== "" &&
    !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(body.assignee_email)
  ) {
    return NextResponse.json(
      { error: "Адрес не похож на почтовый." },
      { status: 400 },
    );
  }

  const patch: Parameters<typeof updateCommitment>[2] = {};
  if (body.assignee_email !== undefined) {
    patch.assignee_email = body.assignee_email || undefined;
  }
  if (body.status) patch.status = body.status;

  const updated = await updateCommitment(
    body.meeting_id,
    body.commitment_id,
    patch,
  );
  if (!updated) {
    return NextResponse.json({ error: "Поручение не найдено." }, { status: 404 });
  }
  return NextResponse.json({ commitment: updated });
}
