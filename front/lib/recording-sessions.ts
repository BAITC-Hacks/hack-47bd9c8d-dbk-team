// Server-side buffer for live microphone recordings (Scenario 1).
// Chunks arrive via /api/meetings/[id]/chunk and are assembled on /finish.
// In-memory, single-instance — same tradeoff as the status store.
const globalRef = globalThis as unknown as {
  __recordingSessions?: Map<
    string,
    { chunks: Map<number, Buffer>; mime: string }
  >;
};

export const recordingSessions = (globalRef.__recordingSessions ??= new Map());

export function createSession(meetingId: string): void {
  recordingSessions.set(meetingId, { chunks: new Map(), mime: "audio/webm" });
}

export function hasSession(meetingId: string): boolean {
  return recordingSessions.has(meetingId);
}

export function addChunk(
  meetingId: string,
  seq: number,
  data: Buffer,
  mime: string,
): void {
  const session = recordingSessions.get(meetingId);
  if (!session) return;
  session.chunks.set(seq, data);
  if (mime) session.mime = mime;
}

export function assembleSession(
  meetingId: string,
): { data: Buffer; mime: string } | null {
  const session = recordingSessions.get(meetingId);
  if (!session || session.chunks.size === 0) return null;
  const ordered = [...session.chunks.entries()].sort(([a], [b]) => a - b);
  return {
    data: Buffer.concat(ordered.map(([, buf]) => buf)),
    mime: session.mime,
  };
}

// Sequences must be contiguous 0..max — a gap means a chunk was lost
// in transit and the assembled file would silently skip audio.
export function missingSeqs(meetingId: string): number[] {
  const session = recordingSessions.get(meetingId);
  if (!session || session.chunks.size === 0) return [];
  const max = Math.max(...session.chunks.keys());
  const missing: number[] = [];
  for (let seq = 0; seq <= max; seq++) {
    if (!session.chunks.has(seq)) missing.push(seq);
  }
  return missing;
}

export function dropSession(meetingId: string): void {
  recordingSessions.delete(meetingId);
}
