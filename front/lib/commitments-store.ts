import { getMinio, ensureBucket } from "./minio";
import { config } from "./config";
import type { Commitment, MeetingResult } from "./types";

export interface CommitmentEntry extends Commitment {
  meeting_id: string;
  /** Куда слать напоминание. Задаётся руками: в записи адресов нет. */
  assignee_email?: string;
  /** Что уже отправлено по этому поручению, чтобы не слать одно и то же. */
  notified?: { soon?: string; overdue?: string };
}

// Поручения переживают перезапуск: Сценарий 2 — это контроль сроков неделями,
// и список, живущий до первого рестарта контейнера, такой задачи не решает.
// Хранилище — тот же MinIO, что и результаты: отдельная база ради одного
// файла на демо не нужна, а данные оказываются там же, где протоколы.
const INDEX_KEY = "commitments/index.json";

const globalRef = globalThis as unknown as {
  __commitmentsStore?: Map<string, CommitmentEntry>;
  __commitmentsLoaded?: boolean;
};

const store = (globalRef.__commitmentsStore ??= new Map());

function key(meetingId: string, commitmentId: string) {
  return `${meetingId}:${commitmentId}`;
}

async function readIndex(): Promise<CommitmentEntry[]> {
  try {
    const stream = await getMinio().getObject(
      config.minio.resultsBucket,
      INDEX_KEY,
    );
    const chunks: Buffer[] = [];
    for await (const chunk of stream) chunks.push(chunk as Buffer);
    return JSON.parse(Buffer.concat(chunks).toString("utf-8"));
  } catch {
    // первого запуска ещё не было — это не ошибка
    return [];
  }
}

async function writeIndex(): Promise<void> {
  const body = Buffer.from(
    JSON.stringify([...store.values()], null, 2),
    "utf-8",
  );
  await ensureBucket(config.minio.resultsBucket);
  await getMinio().putObject(
    config.minio.resultsBucket,
    INDEX_KEY,
    body,
    body.length,
    { "Content-Type": "application/json" },
  );
}

/** Поднимает сохранённые поручения один раз за жизнь процесса. */
export async function loadCommitments(): Promise<void> {
  if (globalRef.__commitmentsLoaded) return;
  globalRef.__commitmentsLoaded = true;
  for (const entry of await readIndex()) {
    store.set(key(entry.meeting_id, entry.id), entry);
  }
}

export async function cacheResult(result: MeetingResult): Promise<void> {
  await loadCommitments();
  for (const commitment of result.commitments) {
    const id = key(result.meeting_id, commitment.id);
    // Не затираем то, что человек уже правил руками: адрес получателя,
    // отметки об отправке и статус переживают повторный разбор записи.
    const existing = store.get(id);
    store.set(id, {
      ...commitment,
      meeting_id: result.meeting_id,
      assignee_email: existing?.assignee_email,
      notified: existing?.notified,
      status: existing?.status ?? commitment.status,
    });
  }
  await writeIndex().catch(() => {
    // хранилище недоступно — список останется в памяти до перезапуска
  });
}

export async function listCommitments(): Promise<CommitmentEntry[]> {
  await loadCommitments();
  return [...store.values()];
}

export async function updateCommitment(
  meetingId: string,
  commitmentId: string,
  patch: Partial<Pick<CommitmentEntry, "assignee_email" | "status" | "notified">>,
): Promise<CommitmentEntry | null> {
  await loadCommitments();
  const id = key(meetingId, commitmentId);
  const current = store.get(id);
  if (!current) return null;
  const next = { ...current, ...patch };
  store.set(id, next);
  await writeIndex().catch(() => {});
  return next;
}
