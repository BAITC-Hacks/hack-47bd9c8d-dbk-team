import type { Commitment, MeetingResult } from "./types";

export interface CommitmentEntry extends Commitment {
  meeting_id: string;
}

// Aggregates commitments from every result the server has served,
// so the dashboard (Scenario 2) can show deadlines across meetings.
// In-memory — same tradeoff as the status store.
const globalRef = globalThis as unknown as {
  __commitmentsStore?: Map<string, CommitmentEntry>;
};

const store = (globalRef.__commitmentsStore ??= new Map());

export function cacheResult(result: MeetingResult): void {
  for (const commitment of result.commitments) {
    store.set(`${result.meeting_id}:${commitment.id}`, {
      ...commitment,
      meeting_id: result.meeting_id,
    });
  }
}

export function listCommitments(): CommitmentEntry[] {
  return [...store.values()];
}
