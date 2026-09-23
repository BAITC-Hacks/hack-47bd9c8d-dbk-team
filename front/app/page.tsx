"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { CommitmentsDashboard } from "@/components/commitments-dashboard";
import { LiveRecorder } from "@/components/live-recorder";
import { MeetingProgress } from "@/components/meeting-progress";
import { MeetingResultView } from "@/components/meeting-result";
import { UploadZone } from "@/components/upload-zone";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import type { MeetingResult, MeetingStatus } from "@/lib/types";

type Phase =
  | { kind: "idle" }
  | { kind: "uploading" }
  | { kind: "processing"; status: MeetingStatus }
  | { kind: "ready"; result: MeetingResult }
  | { kind: "failed"; status: MeetingStatus }
  | { kind: "error"; message: string };

const POLL_INTERVAL_MS = 2500;

export default function HomePage() {
  const [phase, setPhase] = useState<Phase>({ kind: "idle" });
  const [view, setView] = useState<"flow" | "commitments">("flow");
  const [recorderActive, setRecorderActive] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const stopPolling = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  useEffect(() => stopPolling, [stopPolling]);

  const pollStatus = useCallback(
    (meetingId: string) => {
      stopPolling();
      pollRef.current = setInterval(async () => {
        try {
          const res = await fetch(`/api/meetings/${meetingId}/status`);
          if (!res.ok) return;
          const status = (await res.json()) as MeetingStatus;

          if (status.state === "ready") {
            stopPolling();
            const resultRes = await fetch(`/api/meetings/${meetingId}/result`);
            if (resultRes.ok) {
              const result = (await resultRes.json()) as MeetingResult;
              setPhase({ kind: "ready", result });
            } else {
              setPhase({
                kind: "error",
                message: "Статус «готово», но результат не найден в хранилище.",
              });
            }
          } else if (status.state === "failed") {
            stopPolling();
            setPhase({ kind: "failed", status });
          } else {
            setPhase({ kind: "processing", status });
          }
        } catch {
          // transient network error — keep polling
        }
      }, POLL_INTERVAL_MS);
    },
    [stopPolling],
  );

  async function handleUpload(file: File) {
    setPhase({ kind: "uploading" });
    try {
      const form = new FormData();
      form.append("file", file);
      const res = await fetch("/api/meetings", { method: "POST", body: form });
      const body = await res.json();
      if (!res.ok) {
        setPhase({ kind: "error", message: body.error ?? "Ошибка загрузки." });
        return;
      }
      const meetingId = body.meeting_id as string;
      setPhase({
        kind: "processing",
        status: {
          meeting_id: meetingId,
          state: "processing",
          updated_at: new Date().toISOString(),
        },
      });
      pollStatus(meetingId);
    } catch {
      setPhase({
        kind: "error",
        message: "Сеть недоступна — не удалось отправить файл.",
      });
    }
  }

  function handleReset() {
    stopPolling();
    setPhase({ kind: "idle" });
  }

  function handleRecordingFinished(meetingId: string) {
    setRecorderActive(false);
    setPhase({
      kind: "processing",
      status: {
        meeting_id: meetingId,
        state: "processing",
        updated_at: new Date().toISOString(),
      },
    });
    pollStatus(meetingId);
  }

  return (
    <div className="space-y-6">
      <div
        role="tablist"
        aria-label="Разделы"
        className="flex gap-1 border-b border-line print:hidden"
      >
        {(
          [
            { id: "flow", label: "Запись и протокол" },
            { id: "commitments", label: "Контроль поручений" },
          ] as const
        ).map((tab) => (
          <button
            key={tab.id}
            role="tab"
            aria-selected={view === tab.id}
            onClick={() => setView(tab.id)}
            className={cn(
              "border-b-2 px-4 py-2 text-sm font-medium transition-colors",
              view === tab.id
                ? "border-bronze-500 text-navy-800"
                : "border-transparent text-zinc-500 hover:text-navy-700",
            )}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {view === "commitments" && <CommitmentsDashboard />}

      {view === "flow" && (phase.kind === "idle" || phase.kind === "uploading") && (
        <>
          <LiveRecorder
            onFinished={handleRecordingFinished}
            onActiveChange={setRecorderActive}
          />
          {!recorderActive && (
            <Card>
              <CardContent className="pt-6">
                <UploadZone
                  uploading={phase.kind === "uploading"}
                  onUpload={handleUpload}
                />
              </CardContent>
            </Card>
          )}
        </>
      )}

      {view === "flow" && phase.kind === "processing" && (
        <>
          <MeetingProgress status={phase.status} />
          <button
            onClick={handleReset}
            className="text-xs text-navy-600 underline-offset-2 hover:underline print:hidden"
          >
            Отменить и загрузить другую запись
          </button>
        </>
      )}

      {view === "flow" && phase.kind === "failed" && (
        <>
          <MeetingProgress status={phase.status} />
          <button
            onClick={handleReset}
            className="text-xs text-navy-600 underline-offset-2 hover:underline print:hidden"
          >
            Загрузить другую запись
          </button>
        </>
      )}

      {view === "flow" && phase.kind === "ready" && (
        <>
          <MeetingResultView result={phase.result} />
          <button
            onClick={handleReset}
            className="text-xs text-navy-600 underline-offset-2 hover:underline print:hidden"
          >
            Обработать ещё одну запись
          </button>
        </>
      )}

      {view === "flow" && phase.kind === "error" && (
        <Card className="border-red-500/40">
          <CardContent className="space-y-3 pt-6">
            <p className="text-sm text-red-700">{phase.message}</p>
            <button
              onClick={handleReset}
              className="text-xs text-navy-600 underline-offset-2 hover:underline"
            >
              Попробовать снова
            </button>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
