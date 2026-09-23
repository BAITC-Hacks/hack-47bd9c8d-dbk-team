import { AlertTriangle } from "lucide-react";

// Contract: warnings[] and confidence:low must be shown, not hidden —
// they are the originality argument (verify_speakers).
export function WarningsBanner({ warnings }: { warnings: string[] }) {
  if (warnings.length === 0) return null;
  return (
    <div
      role="alert"
      className="rounded-xl border border-amber-500/40 bg-amber-500/10 px-5 py-4"
    >
      <div className="flex items-center gap-2 text-sm font-semibold text-amber-300">
        <AlertTriangle className="h-4 w-4" aria-hidden />
        Замечания проверки говорящих
      </div>
      <ul className="mt-2 list-disc space-y-1 pl-6 text-sm text-amber-200/90">
        {warnings.map((warning, i) => (
          <li key={i}>{warning}</li>
        ))}
      </ul>
    </div>
  );
}
