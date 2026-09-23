"use client";

import { FileAudio, Loader2, UploadCloud } from "lucide-react";
import { useRef, useState, type DragEvent } from "react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";

const ACCEPT = ".mp3,.m4a,.mp4,.wav,.ogg,.flac,.webm";

interface UploadZoneProps {
  uploading: boolean;
  onUpload: (file: File) => void;
}

export function UploadZone({ uploading, onUpload }: UploadZoneProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [dragOver, setDragOver] = useState(false);

  function handleDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setDragOver(false);
    const dropped = event.dataTransfer.files?.[0];
    if (dropped) setFile(dropped);
  }

  return (
    <div className="space-y-4">
      <div
        role="button"
        tabIndex={0}
        aria-label="Выбрать файл записи"
        onClick={() => inputRef.current?.click()}
        onKeyDown={(e) => e.key === "Enter" && inputRef.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={handleDrop}
        className={cn(
          "flex cursor-pointer flex-col items-center justify-center gap-3 rounded-xl border-2 border-dashed px-6 py-12 text-center transition-colors",
          dragOver
            ? "border-sky-500 bg-sky-500/10"
            : "border-zinc-700 bg-zinc-900/40 hover:border-zinc-500",
        )}
      >
        <UploadCloud className="h-10 w-10 text-zinc-500" aria-hidden />
        <div className="text-sm text-zinc-300">
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
        <div className="flex items-center justify-between gap-4 rounded-lg border border-zinc-800 bg-zinc-900/60 px-4 py-3">
          <div className="flex min-w-0 items-center gap-3">
            <FileAudio className="h-5 w-5 shrink-0 text-sky-400" aria-hidden />
            <div className="min-w-0">
              <div className="truncate text-sm text-zinc-200">{file.name}</div>
              <div className="text-xs text-zinc-500">
                {(file.size / 1024 / 1024).toFixed(1)} МБ
              </div>
            </div>
          </div>
          <Button onClick={() => onUpload(file)} disabled={uploading}>
            {uploading && <Loader2 className="h-4 w-4 animate-spin" aria-hidden />}
            {uploading ? "Отправка…" : "Отправить в обработку"}
          </Button>
        </div>
      )}
    </div>
  );
}
