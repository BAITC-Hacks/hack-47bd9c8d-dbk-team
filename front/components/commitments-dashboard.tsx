"use client";

import { AlertTriangle, BellRing, Check, RefreshCw } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import type { CommitmentEntry } from "@/lib/commitments-store";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const DAY_MS = 86_400_000;
const DUE_SOON_DAYS = 3;

const STATUS_LABEL: Record<string, { label: string; variant: "info" | "danger" | "success" }> = {
  in_progress: { label: "В работе", variant: "info" },
  overdue: { label: "Просрочено", variant: "danger" },
  done: { label: "Выполнено", variant: "success" },
};

function daysUntil(dueDate: string | null): number | null {
  if (!dueDate) return null;
  const due = new Date(`${dueDate}T00:00:00`);
  if (Number.isNaN(due.getTime())) return null;
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  return Math.round((due.getTime() - today.getTime()) / DAY_MS);
}

function deadlineRank(entry: CommitmentEntry): number {
  const days = daysUntil(entry.due_date);
  if (entry.status === "done") return 2;
  if (days !== null && days < 0) return 0;
  return 1;
}

function DeadlineBadge({ entry }: { entry: CommitmentEntry }) {
  const days = daysUntil(entry.due_date);
  if (entry.status === "done") return null;
  if (days === null) {
    return <span className="text-xs text-zinc-500">срок не распознан</span>;
  }
  if (days < 0) {
    return (
      <Badge variant="danger">
        <AlertTriangle className="h-3 w-3" aria-hidden />
        просрочено на {-days} дн.
      </Badge>
    );
  }
  if (days <= DUE_SOON_DAYS) {
    return (
      <Badge variant="warning">
        {days === 0 ? "срок сегодня" : `осталось ${days} дн.`}
      </Badge>
    );
  }
  return <span className="text-xs text-zinc-500">осталось {days} дн.</span>;
}

export function CommitmentsDashboard() {
  const [items, setItems] = useState<CommitmentEntry[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [notifying, setNotifying] = useState(false);
  const [mailNote, setMailNote] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch("/api/commitments");
      const body = await res.json();
      if (!res.ok) throw new Error(body.error ?? "load failed");
      setItems(body.commitments as CommitmentEntry[]);
    } catch {
      setError("Не удалось загрузить поручения. Проверьте сеть и повторите.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  // Сохраняем правку сразу: адрес и отметка «выполнено» задаются руками,
  // и терять их при обновлении страницы нельзя.
  const patch = useCallback(
    async (entry: CommitmentEntry, body: Record<string, unknown>) => {
      const res = await fetch("/api/commitments", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          meeting_id: entry.meeting_id,
          commitment_id: entry.id,
          ...body,
        }),
      });
      if (res.ok) load();
    },
    [load],
  );

  const notify = useCallback(async () => {
    setNotifying(true);
    setMailNote(null);
    try {
      const res = await fetch("/api/commitments/notify", { method: "POST" });
      const body = await res.json();
      const parts: string[] = [];
      if (body.sent) parts.push(`отправлено: ${body.sent}`);
      if (body.failed) parts.push(`не доставлено: ${body.failed}`);
      if (body.pending) parts.push(`в журнале: ${body.pending}`);
      if (!body.mail_configured) {
        parts.push("почта не настроена — письма записаны, но не отправлены");
      }
      setMailNote(
        parts.length ? parts.join(" · ") : "Напоминать пока не о чем.",
      );
      load();
    } catch {
      setMailNote("Не удалось проверить сроки. Повторите.");
    } finally {
      setNotifying(false);
    }
  }, [load]);

  const sorted = [...(items ?? [])].sort((a, b) => {
    const rank = deadlineRank(a) - deadlineRank(b);
    if (rank !== 0) return rank;
    const da = a.due_date ?? "9999";
    const db = b.due_date ?? "9999";
    return da.localeCompare(db);
  });
  const overdueCount = sorted.filter(
    (c) => deadlineRank(c) === 0,
  ).length;

  return (
    <Card>
      <CardHeader>
        <CardTitle>Контроль поручений</CardTitle>
        <div className="flex items-center gap-3">
          {items !== null && (
            <span className="text-xs text-zinc-500">
              {items.length} поручений
              {overdueCount > 0 && (
                <span className="text-red-700">
                  {" "}
                  · просрочено: {overdueCount}
                </span>
              )}
            </span>
          )}
          <Button
            variant="ghost"
            size="sm"
            onClick={notify}
            disabled={notifying}
          >
            <BellRing
              className={notifying ? "h-3.5 w-3.5 animate-pulse" : "h-3.5 w-3.5"}
              aria-hidden
            />
            Проверить сроки
          </Button>
          <Button variant="ghost" size="sm" onClick={load} disabled={loading}>
            <RefreshCw
              className={loading ? "h-3.5 w-3.5 animate-spin" : "h-3.5 w-3.5"}
              aria-hidden
            />
            Обновить
          </Button>
        </div>
      </CardHeader>
      <CardContent className="overflow-x-auto p-0">
        {mailNote && (
          <p className="border-b border-line bg-paper px-5 py-2 text-xs text-zinc-600">
            {mailNote}
          </p>
        )}
        {error && (
          <div
            role="alert"
            className="m-5 rounded-lg border border-red-500/30 bg-red-50 px-4 py-3 text-sm text-red-700"
          >
            {error}
          </div>
        )}
        {items !== null && sorted.length === 0 && !error && (
          <p className="px-5 py-8 text-sm text-zinc-500">
            Поручений пока нет — обработайте запись совещания, и они появятся
            здесь со сроками и ответственными.
          </p>
        )}
        {sorted.length > 0 && (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-line text-left text-xs uppercase tracking-wide text-zinc-500">
                <th className="px-5 py-2 font-medium">Срок</th>
                <th className="px-3 py-2 font-medium">Ответственный</th>
                <th className="px-3 py-2 font-medium">Поручение</th>
                <th className="px-3 py-2 font-medium">Совещание</th>
                <th className="px-3 py-2 font-medium">Почта для напоминаний</th>
                <th className="px-3 py-2 font-medium">Статус</th>
                <th className="px-5 py-2 font-medium">Контроль срока</th>
              </tr>
            </thead>
            <tbody>
              {sorted.map((c) => {
                const overdue = deadlineRank(c) === 0;
                return (
                  <tr
                    key={`${c.meeting_id}:${c.id}`}
                    className={
                      overdue
                        ? "border-b border-line/70 bg-red-50/60 align-top last:border-0"
                        : "border-b border-line/70 align-top last:border-0 hover:bg-paper"
                    }
                  >
                    <td className="whitespace-nowrap px-5 py-3 font-medium text-navy-800">
                      {c.due_date ?? c.due_raw}
                    </td>
                    <td className="whitespace-nowrap px-3 py-3 text-zinc-700">
                      {c.assignee}
                    </td>
                    <td className="px-3 py-3 text-zinc-700">{c.text}</td>
                    <td className="whitespace-nowrap px-3 py-3 font-mono text-xs text-zinc-500">
                      {c.meeting_id}
                    </td>
                    <td className="px-3 py-3">
                      <input
                        type="email"
                        defaultValue={c.assignee_email ?? ""}
                        placeholder="адрес не задан"
                        aria-label={`Почта для напоминаний по поручению ${c.id}`}
                        onBlur={(e) => {
                          const next = e.target.value.trim();
                          if (next !== (c.assignee_email ?? "")) {
                            patch(c, { assignee_email: next });
                          }
                        }}
                        className="w-48 rounded border border-line bg-white px-2 py-1 text-xs text-zinc-700 placeholder:text-zinc-400 focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-navy-600"
                      />
                    </td>
                    <td className="whitespace-nowrap px-3 py-3">
                      <Badge
                        variant={
                          (STATUS_LABEL[c.status] ?? STATUS_LABEL.in_progress)
                            .variant
                        }
                      >
                        {
                          (STATUS_LABEL[c.status] ?? STATUS_LABEL.in_progress)
                            .label
                        }
                      </Badge>
                    </td>
                    <td className="whitespace-nowrap px-5 py-3">
                      <div className="flex items-center gap-3">
                        <DeadlineBadge entry={c} />
                        {c.status !== "done" && (
                          <button
                            type="button"
                            onClick={() => patch(c, { status: "done" })}
                            className="inline-flex items-center gap-1 text-xs text-zinc-500 transition-colors hover:text-emerald-700 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-navy-600"
                          >
                            <Check className="h-3.5 w-3.5" aria-hidden />
                            выполнено
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </CardContent>
    </Card>
  );
}
