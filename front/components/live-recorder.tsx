"use client";

import { Mic, Square, Loader2, Radio, X } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { formatTime } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const CHUNK_MS = 5000;
const NOTICE_URLS = ["/audio-warnings/rus.mp3", "/audio-warnings/kaz.mp3"];
const NOTICE_TIMEOUT_MS = 20000;
const RETRY_DELAY_MS = 1000;

const MIME_CANDIDATES = [
  "audio/webm;codecs=opus",
  "audio/webm",
  "audio/mp4",
];

type RecorderState = "idle" | "starting" | "recording" | "stopping";

function pickMime(): string {
  if (typeof MediaRecorder === "undefined") return "";
  return MIME_CANDIDATES.find((m) => MediaRecorder.isTypeSupported(m)) ?? "";
}

// Plays the AI-recording notice for participants in Russian, then Kazakh.
// Resolves anyway if a file is missing or takes too long — the demo flow
// must never stall on a missing asset.
function playNotice(): Promise<void> {
  return NOTICE_URLS.reduce(
    (chain, url) =>
      chain.then(
        () =>
          new Promise<void>((resolve) => {
            const audio = new Audio(url);
            const timer = setTimeout(done, NOTICE_TIMEOUT_MS);
            function done() {
              clearTimeout(timer);
              resolve();
            }
            audio.onended = done;
            audio.onerror = done;
            audio.play().catch(done);
          }),
      ),
    Promise.resolve(),
  );
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
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
  const [level, setLevel] = useState(0);
  const [error, setError] = useState<string | null>(null);

  const recorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const meetingIdRef = useRef<string | null>(null);
  const mimeRef = useRef("audio/webm");
  const seqRef = useRef(0);
  const blobsRef = useRef(new Map<number, Blob>());
  const pendingRef = useRef<Promise<unknown>[]>([]);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const audioCtxRef = useRef<AudioContext | null>(null);
  const rafRef = useRef<number | null>(null);

  const setActive = useCallback(
    (active: boolean) => onActiveChange?.(active),
    [onActiveChange],
  );

  const cleanup = useCallback(() => {
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
    if (rafRef.current !== null) {
      cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
    }
    audioCtxRef.current?.close().catch(() => {});
    audioCtxRef.current = null;
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    recorderRef.current = null;
  }, []);

  useEffect(() => cleanup, [cleanup]);

  // Warn before losing an in-progress recording via refresh/close.
  useEffect(() => {
    if (state !== "recording") return;
    const handler = (event: BeforeUnloadEvent) => {
      event.preventDefault();
    };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [state]);

  function startLevelMeter(stream: MediaStream): void {
    try {
      const ctx = new AudioContext();
      audioCtxRef.current = ctx;
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 256;
      ctx.createMediaStreamSource(stream).connect(analyser);
      const data = new Uint8Array(analyser.frequencyBinCount);
      let lastPaint = 0;
      const tick = (now: number) => {
        analyser.getByteTimeDomainData(data);
        let peak = 0;
        for (let i = 0; i < data.length; i++) {
          peak = Math.max(peak, Math.abs(data[i] - 128));
        }
        if (now - lastPaint > 100) {
          lastPaint = now;
          setLevel(Math.min(1, peak / 64));
        }
        rafRef.current = requestAnimationFrame(tick);
      };
      rafRef.current = requestAnimationFrame(tick);
    } catch {
      // Level meter is progressive enhancement — recording works without it.
    }
  }

  async function sendChunk(seq: number, blob: Blob): Promise<void> {
    const meetingId = meetingIdRef.current;
    if (!meetingId) return;
    const url = `/api/meetings/${meetingId}/chunk?seq=${seq}&mime=${encodeURIComponent(mimeRef.current)}`;
    for (let attempt = 0; attempt < 2; attempt++) {
      const res = await fetch(url, { method: "POST", body: blob });
      if (res.ok) return;
      if (attempt === 0) await sleep(RETRY_DELAY_MS);
    }
    throw new Error(`chunk ${seq} failed`);
  }

  function uploadChunk(blob: Blob): void {
    if (blob.size === 0) return;
    const seq = seqRef.current++;
    blobsRef.current.set(seq, blob);
    pendingRef.current.push(sendChunk(seq, blob));
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
      mimeRef.current = recorder.mimeType || "audio/webm";
      seqRef.current = 0;
      blobsRef.current = new Map();
      pendingRef.current = [];

      recorder.ondataavailable = (event) => uploadChunk(event.data);
      recorder.start(CHUNK_MS);

      startLevelMeter(stream);
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

  async function finishWithResend(meetingId: string): Promise<Response> {
    let res = await fetch(`/api/meetings/${meetingId}/finish`, {
      method: "POST",
    });
    if (res.status === 409) {
      const body = await res.json();
      const missing = (body.missing ?? []) as number[];
      // Resend the chunks the server never saw, then finish once more.
      for (const seq of missing) {
        const blob = blobsRef.current.get(seq);
        if (blob) await sendChunk(seq, blob).catch(() => {});
      }
      res = await fetch(`/api/meetings/${meetingId}/finish`, {
        method: "POST",
      });
    }
    return res;
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

      const res = await finishWithResend(meetingId);
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

  async function handleCancel() {
    const meetingId = meetingIdRef.current;
    const recorder = recorderRef.current;
    if (recorder && recorder.state !== "inactive") {
      recorder.ondataavailable = null;
      recorder.stop();
    }
    cleanup();
    blobsRef.current = new Map();
    pendingRef.current = [];
    if (meetingId) {
      await fetch(`/api/meetings/${meetingId}/cancel`, {
        method: "POST",
      }).catch(() => {});
    }
    setState("idle");
    setActive(false);
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Запись совещания</CardTitle>
        {state === "recording" && (
          <span className="inline-flex items-center gap-2 font-mono text-sm tabular-nums text-navy-800">
            <span className="relative flex h-2.5 w-2.5">
              <span className="absolute inline-flex h-full w-full rounded-full bg-red-500 opacity-60 motion-safe:animate-ping" />
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
              микрофона. Распознавание: русский, казахский и смешанная речь.
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
          <div className="space-y-3">
            <div
              className="h-1.5 w-full overflow-hidden rounded-full bg-line"
              role="meter"
              aria-label="Уровень микрофона"
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={Math.round(level * 100)}
            >
              <div
                className="h-full rounded-full bg-bronze-500 transition-[width] duration-100"
                style={{ width: `${Math.round(level * 100)}%` }}
              />
            </div>
            <div className="flex flex-wrap items-center justify-between gap-4">
              <div className="flex items-center gap-3 text-sm text-zinc-600">
                <Radio className="h-4 w-4 text-bronze-600" aria-hidden />
                Идёт запись — поток сохраняется в хранилище каждые{" "}
                {CHUNK_MS / 1000} секунд.
              </div>
              <div className="flex gap-2">
                <Button onClick={handleCancel} variant="ghost">
                  <X className="h-4 w-4" aria-hidden />
                  Отменить
                </Button>
                <Button onClick={handleStop} variant="secondary">
                  <Square className="h-4 w-4" aria-hidden />
                  Завершить запись
                </Button>
              </div>
            </div>
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
