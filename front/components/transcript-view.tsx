import { UserX } from "lucide-react";
import type { MeetingResult } from "@/lib/types";
import { cn, formatTime, speakerColor } from "@/lib/utils";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export function TranscriptView({ result }: { result: MeetingResult }) {
  const mergedLabels = new Set(
    result.speakers.filter((s) => s.merged).map((s) => s.label),
  );

  return (
    <Card>
      <CardHeader>
        <CardTitle>Транскрипт</CardTitle>
        <span className="text-xs text-zinc-500">
          {result.transcript.length} реплик · {result.speakers.length} говорящих
        </span>
      </CardHeader>
      <CardContent className="max-h-[520px] space-y-4 overflow-y-auto">
        {result.transcript.map((segment, i) => (
          <div key={i} className="flex gap-3">
            <div className="w-12 shrink-0 pt-1 font-mono text-xs text-zinc-500 tabular-nums">
              {formatTime(segment.t_start)}
            </div>
            <div className="min-w-0">
              <div className="mb-1 flex items-center gap-2">
                <span
                  className={cn(
                    "rounded-full border px-2 py-0.5 text-xs font-medium",
                    speakerColor(segment.speaker),
                  )}
                >
                  {segment.name}
                </span>
                {mergedLabels.has(segment.speaker) && (
                  <span
                    title="Ярлык, возможно, объединяет двух участников — см. замечания"
                    className="inline-flex items-center gap-1 text-xs text-amber-700"
                  >
                    <UserX className="h-3.5 w-3.5" aria-hidden />
                    объединён?
                  </span>
                )}
              </div>
              <p className="text-sm leading-relaxed text-zinc-700">
                {segment.text}
              </p>
            </div>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}
