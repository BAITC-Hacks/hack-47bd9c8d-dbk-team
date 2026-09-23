import { Mic } from "lucide-react";

// Scenario 1 of the case: participants must see this notice verbatim.
export function RecordingNotice() {
  return (
    <div
      role="status"
      className="flex items-center justify-center gap-2 border-b border-sky-500/30 bg-sky-500/10 px-4 py-2 text-sm text-sky-200"
    >
      <Mic className="h-4 w-4 shrink-0" aria-hidden />
      <span>Ведётся запись и транскрибация с помощью ИИ</span>
    </div>
  );
}
