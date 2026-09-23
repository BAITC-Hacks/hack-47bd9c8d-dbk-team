"use client";

import { Languages, Loader2 } from "lucide-react";
import { LANGUAGES, type Lang } from "@/lib/languages";
import { cn } from "@/lib/utils";

/**
 * Язык протокола. Совещания идут на двух языках, а согласовывать протокол
 * нужно на том, на котором его читают. Переводятся саммари и поручения;
 * транскрипт остаётся как сказано — это дословная запись, и переводить её
 * значит подменять сказанное.
 */
export function LanguageSwitcher({
  value,
  busy,
  onChange,
}: {
  value: Lang;
  busy: boolean;
  onChange: (lang: Lang) => void;
}) {
  return (
    <div className="flex items-center gap-1.5">
      <Languages className="h-4 w-4 shrink-0 text-zinc-500" aria-hidden />
      <div
        role="group"
        aria-label="Язык протокола"
        className="flex overflow-hidden rounded-md border border-line"
      >
        {(Object.keys(LANGUAGES) as Lang[]).map((lang) => (
          <button
            key={lang}
            type="button"
            onClick={() => onChange(lang)}
            disabled={busy}
            aria-pressed={value === lang}
            title={LANGUAGES[lang]}
            className={cn(
              "px-2.5 py-1 text-xs font-medium uppercase transition-colors",
              "focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-navy-600",
              "disabled:opacity-60",
              value === lang
                ? "bg-navy-800 text-white"
                : "bg-white text-zinc-600 hover:bg-paper hover:text-navy-700",
            )}
          >
            {lang}
          </button>
        ))}
      </div>
      {busy && (
        <span className="flex items-center gap-1 text-xs text-zinc-500">
          <Loader2 className="h-3 w-3 animate-spin" aria-hidden />
          {/* Перевод идёт до двух минут: человек должен видеть, что именно
              переводится и почему транскрипт остался на языке записи. */}
          переводим саммари и поручения
        </span>
      )}
    </div>
  );
}
