"use client";

import { Captions, FileAudio, Loader2, UploadCloud, X } from "lucide-react";
import { useRef, useState, type DragEvent } from "react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";

const ACCEPT = ".mp3,.m4a,.mp4,.wav,.ogg,.flac,.webm";

interface UploadZoneProps {
  uploading: boolean;
  onUpload: (file: File, vtt: File | null) => void;
}

export function UploadZone({ uploading, onUpload }: UploadZoneProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const vttInputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [vtt, setVtt] = useState<File | null>(null);
  const [vttError, setVttError] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);

  function acceptVtt(candidate: File | null | undefined) {
    if (!candidate) return;
    if (!candidate.name.toLowerCase().endsWith(".vtt")) {
      setVttError(`${candidate.name} — не файл субтитров. Нужен .vtt из Zoom.`);
      return;
    }
    setVttError(null);
    setVtt(candidate);
  }

  function handleDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setDragOver(false);
    // В зону можно уронить сразу пару «запись + субтитры»: разбираем по
    // расширению, чтобы не заставлять человека класть их по одному.
    for (const dropped of Array.from(event.dataTransfer.files ?? [])) {
      if (dropped.name.toLowerCase().endsWith(".vtt")) acceptVtt(dropped);
      else setFile(dropped);
    }
  }

  return (
    <div className="space-y-4">
      <div
        role="button"
        tabIndex={0}
        aria-label="Выбрать файл записи"
        onClick={() => inputRef.current?.click()}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            inputRef.current?.click();
          }
        }}
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={handleDrop}
        className={cn(
          "flex cursor-pointer flex-col items-center justify-center gap-3 rounded-xl border-2 border-dashed px-6 py-12 text-center transition-colors",
          dragOver
            ? "border-navy-600 bg-navy-600/5"
            : "border-line bg-paper hover:border-bronze-400",
        )}
      >
        <UploadCloud className="h-10 w-10 text-bronze-500" aria-hidden />
        <div className="text-sm text-zinc-700">
          Перетащите запись встречи сюда или нажмите, чтобы выбрать
        </div>
        <div className="text-xs text-zinc-500">
          mp3, m4a, mp4, wav, ogg, flac, webm
        </div>
        <input
          ref={inputRef}
          type="file"
          accept={ACCEPT}
          className="hidden"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
        />
      </div>

      {file && (
        <div className="space-y-3 rounded-lg border border-line bg-white px-4 py-3">
          <div className="flex items-center justify-between gap-4">
            <div className="flex min-w-0 items-center gap-3">
              <FileAudio
                className="h-5 w-5 shrink-0 text-navy-700"
                aria-hidden
              />
              <div className="min-w-0">
                <div className="truncate text-sm text-zinc-800">
                  {file.name}
                </div>
                <div className="text-xs text-zinc-500">
                  {(file.size / 1024 / 1024).toFixed(1)} МБ
                </div>
              </div>
            </div>
            <Button onClick={() => onUpload(file, vtt)} disabled={uploading}>
              {uploading && (
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
              )}
              {uploading ? "Отправка…" : "Отправить в обработку"}
            </Button>
          </div>

          <div className="border-t border-line pt-3">
            {vtt ? (
              <div className="flex items-start justify-between gap-4">
                <div className="flex min-w-0 items-start gap-3">
                  <Captions
                    className="mt-0.5 h-5 w-5 shrink-0 text-bronze-600"
                    aria-hidden
                  />
                  <div className="min-w-0">
                    <div className="truncate text-sm text-zinc-800">
                      {vtt.name}
                    </div>
                    <div className="text-xs text-emerald-700">
                      Имена участников возьмём из субтитров
                    </div>
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => {
                    setVtt(null);
                    setVttError(null);
                  }}
                  disabled={uploading}
                  className="shrink-0 rounded p-1 text-zinc-500 transition-colors hover:text-navy-700 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-navy-600 disabled:opacity-50"
                  aria-label="Убрать файл субтитров"
                >
                  <X className="h-4 w-4" aria-hidden />
                </button>
              </div>
            ) : (
              <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
                <p className="max-w-prose text-xs text-zinc-600">
                  Есть субтитры Zoom к этой записи? С ними в протоколе будут
                  настоящие имена участников. Без них говорящие останутся
                  безымянными — «Говорящий 1», «Говорящий 2».
                </p>
                <button
                  type="button"
                  onClick={() => vttInputRef.current?.click()}
                  disabled={uploading}
                  className="shrink-0 text-sm text-navy-600 underline-offset-4 transition-colors hover:text-bronze-600 hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-navy-600 disabled:opacity-50"
                >
                  Приложить .vtt
                </button>
              </div>
            )}
            {vttError && (
              <p role="alert" className="mt-2 text-xs text-red-700">
                {vttError}
              </p>
            )}
            <input
              ref={vttInputRef}
              type="file"
              accept=".vtt,text/vtt"
              className="hidden"
              onChange={(e) => acceptVtt(e.target.files?.[0])}
            />
          </div>
        </div>
      )}
    </div>
  );
}
