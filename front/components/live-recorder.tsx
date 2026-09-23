"use client";

import { Mic, Square, Loader2, Radio } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { formatTime } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const CHUNK_MS = 5000;
const NOTICE_URL = "/recording-notice.mp3";
const NOTICE_TIMEOUT_MS = 20000;

const MIME_CANDIDATES = [
  "audio/webm;codecs=opus",
  "audio/webm",
  "audio/mp4",
];

type RecorderState = "idle" | "starting" | "recording" | "stopping";

function pickMime(): string {
  if (typeof MediaRecorder === "undefined") return "";
  return (
    MIME_CANDIDATES.find((m) => MediaRecorder.isTypeSupported(m)) ?? ""
  );
}

// Plays the AI-recording notice for participants. Resolves when the audio
// ends; resolves anyway if the file is missing or takes too long — the
// demo flow must never stall on a missing asset.
function playNotice(): Promise<void> {
  return new Promise((resolve) => {
    const audio = new Audio(NOTICE_URL);
    const timer = setTimeout(done, NOTICE_TIMEOUT_MS);
    function done() {
      clearTimeout(timer);
      resolve();
    }
    audio.onended = done;
    audio.onerror = done;
    audio.play().catch(done);
  });
}

export function LiveRecorder({
  onFinished,
  onActiveChange,
}: {
  onFinished: (meetingId: string) => void;
  onActiveChange?: (active: boolean) => void;
}) {
  const [state, setState] = useState<RecorderState>("idle");
  const [elapsed, setElapsed] = useState(0);
  const [error, setError] = useState<string | null>(null);

  const recorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const meetingIdRef = useRef<string | null>(null);
  const seqRef = useRef(0);
  const pendingRef = useRef<Promise<unknown>[]>([]);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const setActive = useCallback(
    (active: boolean) => onActiveChange?.(active),
    [onActiveChange],
  );

  const cleanup = useCallback(() => {
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    recorderRef.current = null;
  }, []);

  useEffect(() => cleanup, [cleanup]);

  function uploadChunk(blob: Blob, mime: string): void {
    const meetingId = meetingIdRef.current;
    if (!meetingId || blob.size === 0) return;
    const seq = seqRef.current++;
    const promise = fetch(
      `/api/meetings/${meetingId}/chunk?seq=${seq}&mime=${encodeURIComponent(mime)}`,
      { method: "POST", body: blob },
    ).then((res) => {
      if (!res.ok) throw new Error(`chunk ${seq} failed`);
    });
    pendingRef.current.push(promise);
  }

  async function handleStart() {
    setError(null);
    setState("starting");
    setActive(true);
    try {
      const startRes = await fetch("/api/meetings/start", { method: "POST" });
      if (!startRes.ok) throw new Error("start failed");
      const { meeting_id: meetingId } = await startRes.json();
      meetingIdRef.current = meetingId;

      // Mic permission request runs in parallel with the notice playback.
      const [stream] = await Promise.all([
        navigator.mediaDevices.getUserMedia({ audio: true }),
        playNotice(),
      ]);
      streamRef.current = stream;

      const mime = pickMime();
      const recorder = new MediaRecorder(
        stream,
        mime ? { mimeType: mime } : undefined,
      );
      recorderRef.current = recorder;
      seqRef.current = 0;
      pendingRef.current = [];

      recorder.ondataavailable = (event) => {
        uploadChunk(event.data, recorder.mimeType || "audio/webm");
      };
      recorder.start(CHUNK_MS);

      setElapsed(0);
      timerRef.current = setInterval(() => setElapsed((s) => s + 1), 1000);
      setState("recording");
    } catch (err) {
      cleanup();
      setState("idle");
      setActive(false);
      if (err instanceof DOMException && err.name === "NotAllowedError") {
        setError(
          "Нет доступа к микрофону. Разрешите доступ в настройках браузера и повторите.",
        );
      } else {
        setError("Не удалось начать запись. Проверьте микрофон и сеть.");
      }
    }
  }

  async function handleStop() {
    setState("stopping");
    const recorder = recorderRef.current;
    const meetingId = meetingIdRef.current;
    if (!recorder || !meetingId) {
      setState("idle");
      setActive(false);
      return;
    }

    try {
      await new Promise<void>((resolve) => {
        recorder.onstop = () => resolve();
        recorder.stop();
      });
      cleanup();
      await Promise.allSettled(pendingRef.current);

      const res = await fetch(`/api/meetings/${meetingId}/finish`, {
        method: "POST",
      });
      const body = await res.json();
      if (!res.ok) {
        setError(body.error ?? "Не удалось сохранить запись.");
        setState("idle");
        setActive(false);
        return;
      }
      onFinished(meetingId);
    } catch {
      cleanup();
      setError("Сеть недоступна — запись не отправлена.");
      setState("idle");
      setActive(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Запись совещания</CardTitle>
        {state === "recording" && (
          <span className="inline-flex items-center gap-2 font-mono text-sm tabular-nums text-navy-800">
            <span className="relative flex h-2.5 w-2.5">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-red-500 opacity-60" />
              <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-red-600" />
            </span>
            {formatTime(elapsed)}
          </span>
        )}
      </CardHeader>
      <CardContent className="space-y-4">
        {state === "idle" && (
          <>
            <p className="text-sm text-zinc-600">
              Секретарь нажимает кнопку — участники слышат предупреждение о
              записи и транскрибации с помощью ИИ, затем начинается запись с
              микрофона. По завершении система распознает реплики, поручения
              и сформирует саммари.
            </p>
            <Button onClick={handleStart} size="lg">
              <Mic className="h-4 w-4" aria-hidden />
              Начать запись
            </Button>
          </>
        )}

        {state === "starting" && (
          <div className="flex items-center gap-3 text-sm text-zinc-600">
            <Loader2 className="h-4 w-4 animate-spin text-navy-600" aria-hidden />
            Предупреждение участникам о записи…
          </div>
        )}

        {state === "recording" && (
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div className="flex items-center gap-3 text-sm text-zinc-600">
              <Radio className="h-4 w-4 text-bronze-600" aria-hidden />
              Идёт запись — поток сохраняется в хранилище каждые{" "}
              {CHUNK_MS / 1000} секунд.
            </div>
            <Button onClick={handleStop} variant="secondary">
              <Square className="h-4 w-4" aria-hidden />
              Завершить запись
            </Button>
          </div>
        )}

        {state === "stopping" && (
          <div className="flex items-center gap-3 text-sm text-zinc-600">
            <Loader2 className="h-4 w-4 animate-spin text-navy-600" aria-hidden />
            Сохраняю запись и отправляю в обработку…
          </div>
        )}

        {error && (
          <div
            role="alert"
            className="rounded-lg border border-red-500/30 bg-red-50 px-4 py-3 text-sm text-red-700"
          >
            {error}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
