import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatTime(seconds: number): string {
  const total = Math.max(0, Math.round(seconds));
  const mins = Math.floor(total / 60);
  const secs = total % 60;
  return `${String(mins).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
}

const SPEAKER_PALETTE = [
  "bg-sky-50 text-sky-800 border-sky-300",
  "bg-emerald-50 text-emerald-800 border-emerald-300",
  "bg-violet-50 text-violet-800 border-violet-300",
  "bg-amber-50 text-amber-800 border-amber-300",
  "bg-rose-50 text-rose-800 border-rose-300",
  "bg-cyan-50 text-cyan-800 border-cyan-300",
];

export function speakerColor(label: string): string {
  let hash = 0;
  for (let i = 0; i < label.length; i++) {
    hash = (hash * 31 + label.charCodeAt(i)) | 0;
  }
  return SPEAKER_PALETTE[Math.abs(hash) % SPEAKER_PALETTE.length];
}
