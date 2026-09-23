import { MarkdownBlocks } from "@/components/markdown-blocks";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export function SummaryView({ summary }: { summary: string }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Саммари</CardTitle>
      </CardHeader>
      <CardContent>
        <MarkdownBlocks source={summary} />
      </CardContent>
    </Card>
  );
}
