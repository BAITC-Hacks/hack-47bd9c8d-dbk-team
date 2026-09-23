"use client";

import { AlertTriangle, CheckCircle2, Loader2 } from "lucide-react";
import type { MeetingStatus } from "@/lib/types";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const STAGES = [
  { id: "upload", label: "Запись загружена в хранилище" },
  { id: "asr", label: "Распознавание речи (ASR)" },
  { id: "diar", label: "Диаризация говорящих" },
  { id: "llm", label: "Саммари и поручения" },
];

export function MeetingProgress({ status }: { status: MeetingStatus }) {
  const failed = status.state === "failed";
  const ready = status.state === "ready";

  return (
    <Card>
      <CardHeader>
        <CardTitle>Обработка записи</CardTitle>
        <span className="font-mono text-xs text-zinc-400">
          {status.meeting_id}
        </span>
      </CardHeader>
      <CardContent>
        <ol className="space-y-3">
          {STAGES.map((stage, index) => {
            const isFailedStage = failed && status.stage === stage.id;
            return (
              <li key={stage.id} className="flex items-center gap-3 text-sm">
                {isFailedStage ? (
                  <AlertTriangle className="h-4 w-4 text-red-600" aria-hidden />
                ) : index === 0 || ready ? (
                  <CheckCircle2 className="h-4 w-4 text-emerald-600" aria-hidden />
                ) : failed ? (
                  <CheckCircle2 className="h-4 w-4 text-zinc-300" aria-hidden />
                ) : index === 1 ? (
                  <Loader2 className="h-4 w-4 animate-spin text-navy-600" aria-hidden />
                ) : (
                  <div className="h-4 w-4 rounded-full border border-line" aria-hidden />
                )}
                <span
                  className={
                    isFailedStage
                      ? "text-red-700"
                      : index === 0 || ready
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
          <p className="mt-4 text-xs text-zinc-400">
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
