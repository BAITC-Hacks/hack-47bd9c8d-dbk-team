"use client";

import { AlertTriangle, CheckCircle2, Loader2 } from "lucide-react";
import { useEffect, useState } from "react";
import type { MeetingStatus } from "@/lib/types";
import { formatTime } from "@/lib/utils";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const STAGES = [
  { id: "upload", label: "Запись загружена в хранилище" },
  { id: "asr", label: "Распознавание речи (ASR)" },
  { id: "diar", label: "Диаризация говорящих" },
  { id: "llm", label: "Саммари и поручения" },
];

export function MeetingProgress({
  status,
  startedAt,
}: {
  status: MeetingStatus;
  /** Начало обработки. Задан — таймер считается от него и переживает
   *  обновление страницы; не задан — от появления компонента. */
  startedAt?: string | null;
}) {
  const failed = status.state === "failed";
  const ready = status.state === "ready";
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    if (ready || failed) return;
    const since = startedAt ? new Date(startedAt).getTime() : Date.now();
    const tick = () =>
      setElapsed(Math.max(0, Math.floor((Date.now() - since) / 1000)));
    tick();
    const timer = setInterval(tick, 1000);
    return () => clearInterval(timer);
  }, [ready, failed, startedAt]);

  // The pipeline reports an explicit stage only on failure. While it is
  // unknown, no single stage gets the spinner — upload is done, the rest is
  // one honest "in progress" state with elapsed time in the header.
  const activeIndex = (() => {
    if (ready) return STAGES.length;
    const known = STAGES.findIndex((s) => s.id === status.stage);
    return known;
  })();
  const doneCount = ready ? STAGES.length : Math.max(activeIndex, 1);

  return (
    <Card>
      <CardHeader>
        <CardTitle>Обработка записи</CardTitle>
        <span className="inline-flex items-center gap-2 font-mono text-xs text-zinc-500 tabular-nums">
          {status.meeting_id}
          {!ready && !failed && (
            <>
              <Loader2 className="h-3 w-3 animate-spin text-navy-600" aria-hidden />
              {formatTime(elapsed)}
            </>
          )}
        </span>
      </CardHeader>
      <CardContent>
        <ol className="space-y-3">
          {STAGES.map((stage, index) => {
            const isFailedStage = failed && status.stage === stage.id;
            const isDone = index < doneCount;
            const isActive = !failed && !ready && index === activeIndex;
            return (
              <li key={stage.id} className="flex items-center gap-3 text-sm">
                {isFailedStage ? (
                  <AlertTriangle className="h-4 w-4 text-red-600" aria-hidden />
                ) : isDone ? (
                  <CheckCircle2 className="h-4 w-4 text-emerald-600" aria-hidden />
                ) : isActive ? (
                  <Loader2
                    className="h-4 w-4 animate-spin text-navy-600"
                    aria-hidden
                  />
                ) : (
                  <div
                    className="h-4 w-4 rounded-full border border-line"
                    aria-hidden
                  />
                )}
                <span
                  className={
                    isFailedStage
                      ? "text-red-700"
                      : isDone || isActive
                        ? "text-zinc-800"
                        : "text-zinc-500"
                  }
                >
                  {stage.label}
                </span>
              </li>
            );
          })}
        </ol>
        {failed && (
          <div className="mt-4 rounded-lg border border-red-500/30 bg-red-50 px-4 py-3 text-sm text-red-700">
            Ошибка на этапе «{status.stage}»: {status.error}
          </div>
        )}
        {!ready && !failed && (
          <p className="mt-4 text-xs text-zinc-500">
            Конвейер обрабатывает запись целиком: распознавание, диаризация и
            саммари идут последовательно. Страница обновится автоматически.
          </p>
        )}
        {ready && (
          <p className="mt-4 text-xs text-emerald-700">
            Протокол готов — результаты ниже.
          </p>
        )}
      </CardContent>
    </Card>
  );
}
