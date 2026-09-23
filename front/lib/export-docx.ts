"use client";

import {
  AlignmentType,
  Document,
  HeadingLevel,
  Packer,
  Paragraph,
  Table,
  TableCell,
  TableRow,
  TextRun,
  WidthType,
} from "docx";
import type { MeetingResult } from "./types";
import { parseMarkdown, type Inline } from "./markdown";
import { formatTime } from "./utils";

const STATUS_TEXT: Record<string, string> = {
  in_progress: "В работе",
  overdue: "Просрочено",
  done: "Выполнено",
};

function text(value: string, bold = false): TextRun {
  return new TextRun({ text: value, bold });
}

function runs(inline: Inline[]): TextRun[] {
  return inline.map((part) => text(part.text, part.bold));
}

/**
 * Саммари в структуру Word: заголовки заголовками, списки списками, таблица
 * поручений таблицей. Разбор общий с экраном (`lib/markdown.ts`), поэтому
 * выгруженный файл выглядит так же, как то, что человек видел в браузере.
 */
function summaryBlocks(summary: string): (Paragraph | Table)[] {
  return parseMarkdown(summary).map((block) => {
    switch (block.kind) {
      case "heading":
        return new Paragraph({
          heading:
            block.level === 1 ? HeadingLevel.HEADING_2 : HeadingLevel.HEADING_3,
          spacing: { before: 200, after: 80 },
          children: runs(block.inline),
        });
      case "bullet":
        return new Paragraph({
          bullet: { level: 0 },
          children: runs(block.inline),
        });
      case "numbered":
        return new Paragraph({
          children: [text(`${block.marker} `), ...runs(block.inline)],
        });
      case "table":
        return new Table({
          width: { size: 100, type: WidthType.PERCENTAGE },
          rows: [
            new TableRow({
              children: block.head.map(
                (cell) =>
                  new TableCell({
                    children: [new Paragraph({ children: [text(cell, true)] })],
                  }),
              ),
            }),
            ...block.rows.map(
              (row) =>
                new TableRow({
                  children: row.map(
                    (cell) =>
                      new TableCell({
                        children: [new Paragraph({ children: [text(cell)] })],
                      }),
                  ),
                }),
            ),
          ],
        });
      default:
        return new Paragraph({
          spacing: { after: 80 },
          children: runs(block.inline),
        });
    }
  });
}

export async function exportDocx(result: MeetingResult): Promise<void> {
  const doc = new Document({
    sections: [
      {
        children: [
          new Paragraph({
            heading: HeadingLevel.TITLE,
            alignment: AlignmentType.CENTER,
            children: [text(`Протокол встречи ${result.meeting_id}`)],
          }),
          new Paragraph({
            alignment: AlignmentType.CENTER,
            children: [
              text(
                `Сформировано автоматически · ${new Date().toLocaleString("ru-KZ")}`,
              ),
            ],
          }),
          new Paragraph({ text: "" }),

          ...(result.warnings.length > 0
            ? [
                new Paragraph({
                  heading: HeadingLevel.HEADING_2,
                  children: [text("Замечания проверки говорящих", true)],
                }),
                ...result.warnings.map(
                  (w) => new Paragraph({ bullet: { level: 0 }, children: [text(w)] }),
                ),
                new Paragraph({ text: "" }),
              ]
            : []),

          new Paragraph({
            heading: HeadingLevel.HEADING_2,
            children: [text("Саммари", true)],
          }),
          ...summaryBlocks(result.summary),
          new Paragraph({ text: "" }),

          new Paragraph({
            heading: HeadingLevel.HEADING_2,
            children: [text("Поручения", true)],
          }),
          new Table({
            width: { size: 100, type: WidthType.PERCENTAGE },
            rows: [
              new TableRow({
                children: ["Ответственный", "Срок", "Поручение", "Статус", "Уверенность"].map(
                  (h) =>
                    new TableCell({
                      children: [new Paragraph({ children: [text(h, true)] })],
                    }),
                ),
              }),
              ...result.commitments.map(
                (c) =>
                  new TableRow({
                    children: [
                      c.assignee,
                      c.due_date ?? c.due_raw,
                      c.text,
                      STATUS_TEXT[c.status] ?? c.status,
                      c.confidence === "low" ? "низкая" : "высокая",
                    ].map(
                      (cell) =>
                        new TableCell({
                          children: [new Paragraph({ children: [text(cell)] })],
                        }),
                    ),
                  }),
              ),
            ],
          }),
          new Paragraph({ text: "" }),

          new Paragraph({
            heading: HeadingLevel.HEADING_2,
            children: [text("Транскрипт", true)],
          }),
          ...result.transcript.map(
            (s) =>
              new Paragraph({
                children: [
                  text(`[${formatTime(s.t_start)}] ${s.name}: `, true),
                  text(s.text),
                ],
              }),
          ),
        ],
      },
    ],
  });

  const blob = await Packer.toBlob(doc);
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `protocol-${result.meeting_id}.docx`;
  link.click();
  URL.revokeObjectURL(url);
}
