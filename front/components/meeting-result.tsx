import type { MeetingResult } from "@/lib/types";
import { CommitmentsTable } from "@/components/commitments-table";
import { ExportButtons } from "@/components/export-buttons";
import { PrintableProtocol } from "@/components/printable-protocol";
import { SummaryView } from "@/components/summary-view";
import { TranscriptView } from "@/components/transcript-view";
import { WarningsBanner } from "@/components/warnings-banner";

export function MeetingResultView({ result }: { result: MeetingResult }) {
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-4 print:hidden">
        <h2 className="text-lg font-semibold text-navy-800">
          Протокол встречи{" "}
          <span className="font-mono text-zinc-400">{result.meeting_id}</span>
        </h2>
        <ExportButtons result={result} />
      </div>
      <div className="print:hidden">
        <WarningsBanner warnings={result.warnings} />
      </div>
      <div className="grid gap-6 print:hidden lg:grid-cols-2">
        <SummaryView summary={result.summary} />
        <TranscriptView result={result} />
      </div>
      <div className="print:hidden">
        <CommitmentsTable commitments={result.commitments} />
      </div>
      <PrintableProtocol result={result} />
    </div>
  );
}
