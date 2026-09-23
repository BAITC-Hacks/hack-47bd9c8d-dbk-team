"use client";

import { useState } from "react";
import type { MeetingResult } from "@/lib/types";
import type { Lang } from "@/lib/languages";
import { CommitmentsTable } from "@/components/commitments-table";
import { ExportButtons } from "@/components/export-buttons";
import { LanguageSwitcher } from "@/components/language-switcher";
import { PrintableProtocol } from "@/components/printable-protocol";
import { SummaryView } from "@/components/summary-view";
import { TranscriptView } from "@/components/transcript-view";
import { WarningsBanner } from "@/components/warnings-banner";

export function MeetingResultView({ result }: { result: MeetingResult }) {
  const [lang, setLang] = useState<Lang>("ru");
  const [shown, setShown] = useState<MeetingResult>(result);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Переводы кэшируются на сервере, но и в рамках одного открытия держим уже
  // полученное: переключение туда-обратно не должно ждать модель заново.
  const [cache] = useState<Map<Lang, MeetingResult>>(
    () => new Map([["ru", result]]),
  );

  async function switchLang(next: Lang) {
    if (next === lang || busy) return;
    setError(null);

    const ready = cache.get(next);
    if (ready) {
      setLang(next);
      setShown(ready);
      return;
    }

    setBusy(true);
    try {
      const res = await fetch(
        `/api/meetings/${result.meeting_id}/translate?lang=${next}`,
        { method: "POST" },
      );
      const body = await res.json();
      if (!res.ok) throw new Error(body.error ?? "translate failed");
      cache.set(next, body as MeetingResult);
      setLang(next);
      setShown(body as MeetingResult);
    } catch {
      setError("Не удалось перевести протокол. Попробуйте ещё раз.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4 print:hidden">
        <h2 className="text-lg font-semibold text-navy-800">
          Протокол встречи{" "}
          <span className="font-mono text-zinc-500">{result.meeting_id}</span>
        </h2>
        <div className="flex flex-wrap items-center gap-4">
          <LanguageSwitcher value={lang} busy={busy} onChange={switchLang} />
          <ExportButtons result={shown} />
        </div>
      </div>

      {error && (
        <div
          role="alert"
          className="rounded-lg border border-red-500/30 bg-red-50 px-4 py-3 text-sm text-red-700 print:hidden"
        >
          {error}
        </div>
      )}

      <div className="print:hidden">
        <WarningsBanner warnings={shown.warnings} />
      </div>
      <div className="grid items-start gap-6 print:hidden lg:grid-cols-2">
        <SummaryView summary={shown.summary} />
        {/* Транскрипт не переводится: это дословная запись сказанного. */}
        <TranscriptView result={result} />
      </div>
      <div className="print:hidden">
        <CommitmentsTable commitments={shown.commitments} />
      </div>
      <PrintableProtocol result={shown} />
    </div>
  );
}
