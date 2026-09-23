import { MarkdownBlocks } from "@/components/markdown-blocks";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export function SummaryView({ summary }: { summary: string }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Саммари</CardTitle>
      </CardHeader>
      {/* Тот же потолок, что и у транскрипта: иначе длинное саммари растягивает
          страницу на несколько экранов, а колонка с репликами обрывается рядом
          коротким огрызком. */}
      <CardContent className="max-h-[520px] overflow-y-auto">
        <MarkdownBlocks source={summary} />
      </CardContent>
    </Card>
  );
}
