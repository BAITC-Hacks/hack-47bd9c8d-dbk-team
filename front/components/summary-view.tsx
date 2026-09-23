import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

// Minimal markdown rendering for the LLM summary (headings, bullets, paragraphs).
function renderMarkdown(md: string) {
  return md.split("\n").map((line, i) => {
    const trimmed = line.trim();
    if (trimmed.startsWith("## ")) {
      return (
        <h3 key={i} className="mt-3 text-base font-semibold text-zinc-100">
          {trimmed.slice(3)}
        </h3>
      );
    }
    if (trimmed.startsWith("# ")) {
      return (
        <h3 key={i} className="mt-3 text-lg font-semibold text-zinc-100">
          {trimmed.slice(2)}
        </h3>
      );
    }
    if (trimmed.startsWith("- ")) {
      return (
        <li key={i} className="ml-5 list-disc text-sm text-zinc-300">
          {trimmed.slice(2)}
        </li>
      );
    }
    if (trimmed === "") return <div key={i} className="h-2" />;
    return (
      <p key={i} className="text-sm leading-relaxed text-zinc-300">
        {trimmed}
      </p>
    );
  });
}

export function SummaryView({ summary }: { summary: string }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Саммари</CardTitle>
      </CardHeader>
      <CardContent className="space-y-1">{renderMarkdown(summary)}</CardContent>
    </Card>
  );
}
