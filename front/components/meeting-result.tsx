"use client";

import { useEffect, useState } from "react";
import type { MeetingResult } from "@/lib/types";
import { isLang, type Lang } from "@/lib/languages";
import { readLang, rememberLang } from "@/lib/active-meeting";
import { CommitmentsTable } from "@/components/commitments-table";
import { ExportButtons } from "@/components/export-buttons";
import { LanguageSwitcher } from "@/components/language-switcher";
import { PrintableProtocol } from "@/components/printable-protocol";
import { SummaryView } from "@/components/summary-view";
import { TranscriptView } from "@/components/transcript-view";
import { WarningsBanner } from "@/components/warnings-banner";

export function MeetingResultView({ result }: { result: MeetingResult }) {
  const [lang, setLang] = useState<Lang>("ru");
  const [restored, setRestored] = useState(false);
  const [shown, setShown] = useState<MeetingResult>(result);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Переводы кэшируются на сервере, но и в рамках одного открытия держим уже
  // полученное: переключение туда-обратно не должно ждать модель заново.
  const [cache] = useState<Map<Lang, MeetingResult>>(
    () => new Map([["ru", result]]),
  );

  // Язык выбирают один раз и читают протокол дальше — после обновления
  // страницы он не должен сбрасываться на русский.
  useEffect(() => {
    if (restored) return;
    setRestored(true);
    const saved = readLang();
    if (isLang(saved) && saved !== "ru") void switchLang(saved);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [restored]);

  async function switchLang(next: Lang) {
    if (next === lang || busy) return;
    setError(null);

    const ready = cache.get(next);
    if (ready) {
      setLang(next);
      rememberLang(next);
      setShown(ready);
      return;
    }

    setBusy(true);
    try {
      // Перевод считается около двух минут, а прокси рвёт запрос на сотне
      // секунд. Поэтому запускаем работу и опрашиваем готовность. Уже
      // посчитанный перевод возвращается сразу же, первым ответом.
      const url = `/api/meetings/${result.meeting_id}/translate?lang=${next}`;
      let body = await (await fetch(url, { method: "POST" })).json();

      for (let i = 0; body.state === "pending" && i < 100; i += 1) {
        await new Promise((r) => setTimeout(r, 3000));
        const poll = await fetch(url);
        body = await poll.json();
        if (poll.status === 404) throw new Error("перевод не запустился");
      }
      if (body.state !== "ready" || !body.result) {
        throw new Error("перевод не готов");
      }

      cache.set(next, body.result as MeetingResult);
      setLang(next);
      rememberLang(next);
      setShown(body.result as MeetingResult);
    } catch {
      setError(
        "Не удалось перевести протокол. Перевод длинного саммари занимает " +
          "до двух минут — попробуйте ещё раз, начатая работа не пропадёт.",
      );
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
