import { AlertTriangle } from "lucide-react";
import type { Commitment } from "@/lib/types";
import { formatTime } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const STATUS_LABEL: Record<
  Commitment["status"],
  { label: string; variant: "info" | "danger" | "success" }
> = {
  in_progress: { label: "В работе", variant: "info" },
  overdue: { label: "Просрочено", variant: "danger" },
  done: { label: "Выполнено", variant: "success" },
};

export function CommitmentsTable({
  commitments,
}: {
  commitments: Commitment[];
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Поручения</CardTitle>
        <span className="text-xs text-zinc-400">{commitments.length} шт.</span>
      </CardHeader>
      <CardContent className="overflow-x-auto p-0">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-line text-left text-xs uppercase tracking-wide text-zinc-400">
              <th className="px-5 py-2 font-medium">Ответственный</th>
              <th className="px-3 py-2 font-medium">Срок</th>
              <th className="px-3 py-2 font-medium">Поручение</th>
              <th className="px-3 py-2 font-medium">Статус</th>
              <th className="px-5 py-2 font-medium">Уверенность</th>
            </tr>
          </thead>
          <tbody>
            {commitments.map((c) => (
              <tr
                key={c.id}
                className="border-b border-line/70 align-top last:border-0 hover:bg-paper"
              >
                <td className="whitespace-nowrap px-5 py-3 font-medium text-navy-800">
                  {c.assignee}
                </td>
                <td className="whitespace-nowrap px-3 py-3 text-zinc-600">
                  {c.due_date ?? c.due_raw}
                </td>
                <td className="px-3 py-3 text-zinc-700">
                  <div>{c.text}</div>
                  <div className="mt-1 text-xs text-zinc-400">
                    <span className="font-mono">{formatTime(c.t_start)}</span>
                    {" · «"}
                    {c.quote}
                    {"»"}
                  </div>
                </td>
                <td className="whitespace-nowrap px-3 py-3">
                  <Badge variant={STATUS_LABEL[c.status].variant}>
                    {STATUS_LABEL[c.status].label}
                  </Badge>
                </td>
                <td className="whitespace-nowrap px-5 py-3">
                  {c.confidence === "low" ? (
                    <Badge variant="warning">
                      <AlertTriangle className="h-3 w-3" aria-hidden />
                      низкая
                    </Badge>
                  ) : (
                    <Badge variant="success">высокая</Badge>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </CardContent>
    </Card>
  );
}
