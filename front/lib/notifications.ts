import { getMinio, ensureBucket } from "./minio";
import { config } from "./config";
import { listCommitments, updateCommitment } from "./commitments-store";
import type { CommitmentEntry } from "./commitments-store";

/**
 * Сценарий 2: напоминание при приближении срока и при просрочке.
 *
 * Отправка идёт по HTTP, а не по SMTP: провайдеры (Resend, Mailgun, Postmark,
 * MailChannels) принимают обычный POST, и это не тянет новых зависимостей в
 * образ. Настройка — три переменные окружения. Не заданы — письма копятся в
 * журнале с пометкой «не отправлено», и это честное состояние, а не тишина:
 * на демо видно, кому и что ушло бы.
 */

const OUTBOX_KEY = "commitments/outbox.json";

/** За сколько дней до срока предупреждаем. */
const SOON_DAYS = Number(process.env.NOTIFY_SOON_DAYS ?? "3");

export type NotifyKind = "soon" | "overdue";

export interface OutboxEntry {
  id: string;
  kind: NotifyKind;
  meeting_id: string;
  commitment_id: string;
  to: string | null;
  subject: string;
  body: string;
  /** sent — ушло провайдеру; pending — почта не настроена; failed — провайдер отказал. */
  state: "sent" | "pending" | "failed";
  detail?: string;
  created_at: string;
}

const globalRef = globalThis as unknown as { __outbox?: OutboxEntry[] };
const outbox = (globalRef.__outbox ??= []);

function mailConfig() {
  const url = process.env.MAIL_API_URL;
  const key = process.env.MAIL_API_KEY;
  const from = process.env.MAIL_FROM;
  return url && key && from ? { url, key, from } : null;
}

export function mailConfigured(): boolean {
  return mailConfig() !== null;
}

function daysUntil(due: string, now: number): number {
  const diff = new Date(`${due}T23:59:59`).getTime() - now;
  return Math.floor(diff / 86_400_000);
}

function compose(c: CommitmentEntry, kind: NotifyKind, days: number) {
  const when =
    kind === "overdue"
      ? `срок истёк ${Math.abs(days)} дн. назад`
      : days === 0
        ? "срок истекает сегодня"
        : `до срока ${days} дн.`;
  const subject =
    kind === "overdue"
      ? `Просрочено поручение: ${c.text.slice(0, 60)}`
      : `Напоминание о поручении: ${c.text.slice(0, 60)}`;
  const body = [
    `Поручение: ${c.text}`,
    `Ответственный: ${c.assignee ?? "не указан"}`,
    `Срок: ${c.due_date ?? c.due_raw} (${when})`,
    c.classification ? `Классификация: ${c.classification}` : null,
    c.quote ? `\nКак прозвучало на совещании:\n«${c.quote}»` : null,
    `\nПротокол совещания ${c.meeting_id}: ${process.env.APP_PUBLIC_URL ?? "https://app.aibots.kz"}`,
  ]
    .filter(Boolean)
    .join("\n");
  return { subject, body };
}

async function deliver(
  to: string,
  subject: string,
  body: string,
): Promise<{ state: OutboxEntry["state"]; detail?: string }> {
  const mail = mailConfig();
  if (!mail) return { state: "pending", detail: "почта не настроена" };
  try {
    const res = await fetch(mail.url, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${mail.key}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        from: mail.from,
        to: [to],
        subject,
        text: body,
      }),
    });
    if (!res.ok) {
      return { state: "failed", detail: `HTTP ${res.status}` };
    }
    return { state: "sent" };
  } catch (err) {
    return { state: "failed", detail: String(err).slice(0, 200) };
  }
}

async function persistOutbox(): Promise<void> {
  try {
    const body = Buffer.from(JSON.stringify(outbox, null, 2), "utf-8");
    await ensureBucket(config.minio.resultsBucket);
    await getMinio().putObject(
      config.minio.resultsBucket,
      OUTBOX_KEY,
      body,
      body.length,
      { "Content-Type": "application/json" },
    );
  } catch {
    // журнал не критичен: он для показа, а состояние отправки живёт в поручении
  }
}

export function listOutbox(): OutboxEntry[] {
  return [...outbox].reverse();
}

/**
 * Проходит по всем поручениям и отправляет то, что назрело.
 * Повторно одно и то же не шлёт: отметка хранится в самом поручении.
 */
export async function runNotifications(nowMs: number): Promise<OutboxEntry[]> {
  const commitments = await listCommitments();
  const fresh: OutboxEntry[] = [];

  for (const c of commitments) {
    if (c.status === "done" || !c.due_date) continue;

    const days = daysUntil(c.due_date, nowMs);
    const kind: NotifyKind | null =
      days < 0 ? "overdue" : days <= SOON_DAYS ? "soon" : null;
    if (!kind) continue;
    if (c.notified?.[kind]) continue; // уже напоминали об этом же

    const { subject, body } = compose(c, kind, days);
    const to = c.assignee_email ?? null;
    const result = to
      ? await deliver(to, subject, body)
      : { state: "pending" as const, detail: "адрес получателя не задан" };

    const entry: OutboxEntry = {
      id: `${c.meeting_id}:${c.id}:${kind}`,
      kind,
      meeting_id: c.meeting_id,
      commitment_id: c.id,
      to,
      subject,
      body,
      state: result.state,
      detail: result.detail,
      created_at: new Date(nowMs).toISOString(),
    };
    outbox.push(entry);
    fresh.push(entry);

    // Помечаем отправленным только то, что действительно ушло: иначе
    // настроенная позже почта никогда не догонит старые поручения.
    if (result.state === "sent") {
      await updateCommitment(c.meeting_id, c.id, {
        notified: { ...(c.notified ?? {}), [kind]: entry.created_at },
      });
    }
    // Просрочка важнее приближения срока: статус обновляем и без отправки.
    if (kind === "overdue" && c.status !== "overdue") {
      await updateCommitment(c.meeting_id, c.id, { status: "overdue" });
    }
  }

  if (fresh.length) await persistOutbox();
  return fresh;
}
