"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { CommitmentsDashboard } from "@/components/commitments-dashboard";
import { LiveRecorder } from "@/components/live-recorder";
import { MeetingProgress } from "@/components/meeting-progress";
import { MeetingResultView } from "@/components/meeting-result";
import { UploadZone } from "@/components/upload-zone";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import {
  forgetActiveMeeting,
  readActiveMeeting,
  rememberActiveMeeting,
} from "@/lib/active-meeting";
import type { MeetingResult, MeetingStatus } from "@/lib/types";

type Phase =
  | { kind: "idle" }
  | { kind: "uploading" }
  | { kind: "processing"; status: MeetingStatus }
  | { kind: "ready"; result: MeetingResult }
  | { kind: "failed"; status: MeetingStatus }
  | { kind: "error"; message: string };

const POLL_INTERVAL_MS = 2500;

// Сколько ещё ждать встречу, которую сервер не помнит. Контейнер интерфейса
// мог перезапуститься, пока запись обрабатывалась: статус тогда отвечает 404,
// хотя конвейер жив и результат вот-вот появится в хранилище. Через этот срок
// сдаёмся и возвращаем человека к загрузке, чтобы он не ждал вечно.
const ORPHAN_GRACE_MS = 15 * 60 * 1000;

export default function HomePage() {
  const [phase, setPhase] = useState<Phase>({ kind: "idle" });
  const [view, setView] = useState<"flow" | "commitments">("flow");
  const [recorderActive, setRecorderActive] = useState(false);
  const [startedAt, setStartedAt] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const stopPolling = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  useEffect(() => stopPolling, [stopPolling]);

  const beginProcessing = useCallback(
    (meetingId: string, since?: string) => {
      const startIso = since ?? new Date().toISOString();
      setStartedAt(startIso);
      rememberActiveMeeting(meetingId, startIso);
      setPhase({
        kind: "processing",
        status: {
          meeting_id: meetingId,
          state: "processing",
          updated_at: startIso,
        },
      });
    },
    [],
  );

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

  // Восстановление после обновления страницы: серверу известно состояние
  // обработки, браузеру — какая встреча его интересует. Соединяем одно с другим.
  useEffect(() => {
    const active = readActiveMeeting();
    if (!active) return;
    let cancelled = false;

    (async () => {
      try {
        const res = await fetch(`/api/meetings/${active.meetingId}/status`);
        if (cancelled) return;

        if (res.status === 404) {
          // Сервер про эту встречу не знает. Либо она давно завершилась и
          // память браузера устарела, либо интерфейс перезапустился на полпути.
          const age = Date.now() - new Date(active.startedAt).getTime();
          if (age > ORPHAN_GRACE_MS) {
            forgetActiveMeeting();
            return;
          }
          beginProcessing(active.meetingId, active.startedAt);
          pollStatus(active.meetingId);
          return;
        }
        if (!res.ok) return;

        const status = (await res.json()) as MeetingStatus;
        setStartedAt(active.startedAt);

        if (status.state === "ready") {
          const resultRes = await fetch(
            `/api/meetings/${active.meetingId}/result`,
          );
          if (cancelled) return;
          if (resultRes.ok) {
            setPhase({
              kind: "ready",
              result: (await resultRes.json()) as MeetingResult,
            });
          } else {
            forgetActiveMeeting();
          }
        } else if (status.state === "failed") {
          setPhase({ kind: "failed", status });
        } else {
          setPhase({ kind: "processing", status });
          pollStatus(active.meetingId);
        }
      } catch {
        // сеть подведёт — останемся на экране загрузки, память не трогаем
      }
    })();

    return () => {
      cancelled = true;
    };
    // один раз при монтировании: дальше состоянием управляют обработчики
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function handleUpload(file: File, vtt: File | null = null) {
    setPhase({ kind: "uploading" });
    try {
      const form = new FormData();
      form.append("file", file);
      if (vtt) form.append("vtt", vtt);
      const res = await fetch("/api/meetings", { method: "POST", body: form });
      const body = await res.json();
      if (!res.ok) {
        setPhase({ kind: "error", message: body.error ?? "Ошибка загрузки." });
        return;
      }
      const meetingId = body.meeting_id as string;
      beginProcessing(meetingId);
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
    forgetActiveMeeting();
    setStartedAt(null);
    setPhase({ kind: "idle" });
  }

  function handleRecordingFinished(meetingId: string) {
    setRecorderActive(false);
    beginProcessing(meetingId);
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
          <MeetingProgress status={phase.status} startedAt={startedAt} />
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
          <MeetingProgress status={phase.status} startedAt={startedAt} />
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
