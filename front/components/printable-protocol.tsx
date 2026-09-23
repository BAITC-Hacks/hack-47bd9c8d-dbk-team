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
    <div className="hidden print:block print:text-black">
      <h1 className="text-center text-xl font-bold">
        Протокол встречи {result.meeting_id}
      </h1>
      <p className="text-center text-sm text-zinc-600">
        Сформировано автоматически · {new Date().toLocaleString("ru-KZ")}
      </p>

      {result.warnings.length > 0 && (
        <section className="mt-4">
          <h2 className="text-base font-semibold">Замечания проверки говорящих</h2>
          <ul className="list-disc pl-6 text-sm">
            {result.warnings.map((w, i) => (
              <li key={i}>{w}</li>
            ))}
          </ul>
        </section>
      )}

      <section className="mt-4">
        <h2 className="text-base font-semibold">Саммари</h2>
        <div className="mt-2">
          <MarkdownBlocks source={result.summary} print />
        </div>
      </section>

      <section className="mt-4">
        <h2 className="text-base font-semibold">Поручения</h2>
        <table className="mt-2 w-full border-collapse text-sm">
          <thead>
            <tr>
              {["Ответственный", "Срок", "Поручение", "Статус", "Уверенность"].map(
                (h) => (
                  <th key={h} className="border border-zinc-400 px-2 py-1 text-left">
                    {h}
                  </th>
                ),
              )}
            </tr>
          </thead>
          <tbody>
            {result.commitments.map((c) => (
              <tr key={c.id}>
                <td className="border border-zinc-400 px-2 py-1">{c.assignee}</td>
                <td className="border border-zinc-400 px-2 py-1">
                  {c.due_date ?? c.due_raw}
                </td>
                <td className="border border-zinc-400 px-2 py-1">{c.text}</td>
                <td className="border border-zinc-400 px-2 py-1">
                  {STATUS_TEXT[c.status] ?? c.status}
                </td>
                <td className="border border-zinc-400 px-2 py-1">
                  {c.confidence === "low" ? "низкая" : "высокая"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className="mt-4">
        <h2 className="text-base font-semibold">Транскрипт</h2>
        {result.transcript.map((s, i) => (
          <p key={i} className="mt-1 text-sm">
            <span className="font-mono text-xs">[{formatTime(s.t_start)}]</span>{" "}
            <strong>{s.name}:</strong> {s.text}
          </p>
        ))}
      </section>
    </div>
  );
}
