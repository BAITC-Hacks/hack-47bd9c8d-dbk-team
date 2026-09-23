// Contract: .planning/tasks/CONTRACT.md — result.json schema (ingest → UI).

export interface TranscriptSegment {
  speaker: string;
  name: string;
  t_start: number;
  t_end: number;
  text: string;
}

export interface Speaker {
  label: string;
  name: string;
  resolved_by: "text" | "diar" | string;
  merged: boolean;
}

export type Confidence = "high" | "low";
export type CommitmentStatus = "in_progress" | "overdue" | "done";

export interface Commitment {
  id: string;
  assignee: string;
  assignee_speaker: string;
  due_date: string | null;
  due_raw: string;
  text: string;
  quote: string;
  t_start: number;
  confidence: Confidence;
  status: CommitmentStatus;
  /** «Срочно · Договорная работа» — классификация из раздела «Дополнительно». */
  classification?: string | null;
  urgency?: string | null;
  area?: string | null;
}

export interface MeetingResult {
  meeting_id: string;
  transcript: TranscriptSegment[];
  speakers: Speaker[];
  commitments: Commitment[];
  summary: string;
  warnings: string[];
}

// Kafka events (CONTRACT.md)
export interface UploadedEvent {
  meeting_id: string;
  object_key: string;
  filename: string;
  lang_hint: string;
  /** Рядом с записью лежат субтитры Zoom: обработчик возьмёт имена из них. */
  has_vtt?: boolean;
}

export interface ReadyEvent {
  meeting_id: string;
  result_key: string;
  protocol_key?: string;
}

export interface FailedEvent {
  meeting_id: string;
  stage: string;
  error: string;
}

// UI-facing status
export type MeetingState = "processing" | "ready" | "failed";

export interface MeetingStatus {
  meeting_id: string;
  state: MeetingState;
  stage?: string;
  error?: string;
  result_key?: string;
  updated_at: string;
}
