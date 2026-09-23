import type { MeetingStatus } from "./types";

// In-memory status store. Lives for the lifetime of the Node process —
// same tradeoff as the reference copilot-ui (see infrastructure runbook 04).
const globalRef = globalThis as unknown as {
  __meetingStatusStore?: Map<string, MeetingStatus>;
};

export const statusStore =
  (globalRef.__meetingStatusStore ??= new Map<string, MeetingStatus>());

export function setStatus(
  status: Omit<MeetingStatus, "updated_at">,
): MeetingStatus {
  const full: MeetingStatus = {
    ...status,
    updated_at: new Date().toISOString(),
  };
  statusStore.set(status.meeting_id, full);
  return full;
}

export function getStatus(meetingId: string): MeetingStatus | undefined {
  return statusStore.get(meetingId);
}
