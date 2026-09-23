import { MarkdownBlocks } from "@/components/markdown-blocks";
import type { MeetingResult } from "@/lib/types";
import { formatTime } from "@/lib/utils";

const STATUS_TEXT: Record<string, string> = {
  in_progress: "В работе",
  overdue: "Просрочено",
  done: "Выполнено",
};

// Print-only protocol document. PDF export = browser print to PDF,
// which keeps Cyrillic intact without bundling fonts.
export function PrintableProtocol({ result }: { result: MeetingResult }) {
  return (
    <div className="print-doc hidden print:block print:text-black">
      <header className="mb-5 border-b border-black/20 pb-3 text-center">
        <h1 className="text-xl font-bold">Протокол встречи {result.meeting_id}</h1>
        <p className="mt-1 text-xs text-black/60">
          Сформировано автоматически · {new Date().toLocaleString("ru-KZ")}
        </p>
      </header>

      {result.warnings.length > 0 && (
        <section className="mt-6">
          <h2 className="mb-2 border-b border-black/15 pb-1 text-base font-semibold">Замечания проверки говорящих</h2>
          <ul className="list-disc pl-6 text-sm">
            {result.warnings.map((w, i) => (
              <li key={i}>{w}</li>
            ))}
          </ul>
        </section>
      )}

      <section className="mt-6">
        <h2 className="mb-2 border-b border-black/15 pb-1 text-base font-semibold">Саммари</h2>
        <div className="mt-2">
          <MarkdownBlocks source={result.summary} print />
        </div>
      </section>

      <section className="mt-6">
        <h2 className="mb-2 border-b border-black/15 pb-1 text-base font-semibold">Поручения</h2>
        <table className="mt-2 w-full border-collapse text-xs">
          <thead>
            <tr className="bg-black/5">
              {["Ответственный", "Срок", "Поручение", "Статус", "Уверенность"].map(
                (h) => (
                  <th key={h} className="border border-black/40 px-2 py-1 text-left font-semibold">
                    {h}
                  </th>
                ),
              )}
            </tr>
          </thead>
          <tbody>
            {result.commitments.map((c) => (
              <tr key={c.id}>
                <td className="border border-black/25 px-2 py-1 align-top">{c.assignee}</td>
                <td className="border border-black/25 px-2 py-1 align-top">
                  {c.due_date ?? c.due_raw}
                </td>
                <td className="border border-black/25 px-2 py-1 align-top">{c.text}</td>
                <td className="border border-black/25 px-2 py-1 align-top">
                  {STATUS_TEXT[c.status] ?? c.status}
                </td>
                <td className="border border-black/25 px-2 py-1 align-top">
                  {c.confidence === "low" ? "низкая" : "высокая"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className="mt-6">
        <h2 className="mb-2 border-b border-black/15 pb-1 text-base font-semibold">Транскрипт</h2>
        {result.transcript.map((s, i) => (
          <p key={i} className="print-line mt-1.5 text-sm">
            <span className="font-mono text-xs text-black/50">
              [{formatTime(s.t_start)}]
            </span>{" "}
            <strong>{s.name}:</strong> {s.text}
          </p>
        ))}
      </section>
    </div>
  );
}
