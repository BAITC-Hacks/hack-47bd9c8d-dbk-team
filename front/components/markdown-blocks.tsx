import { Fragment } from "react";
import { parseMarkdown, type Block, type Inline } from "@/lib/markdown";
import { cn } from "@/lib/utils";

function InlineText({ parts }: { parts: Inline[] }) {
  return (
    <>
      {parts.map((part, i) =>
        part.bold ? (
          <strong key={i} className="font-semibold text-navy-800">
            {part.text}
          </strong>
        ) : (
          <Fragment key={i}>{part.text}</Fragment>
        ),
      )}
    </>
  );
}

const HEADING_CLASS: Record<1 | 2 | 3, string> = {
  1: "mt-5 text-lg font-semibold text-navy-800 first:mt-0",
  2: "mt-5 text-base font-semibold text-navy-800 first:mt-0",
  3: "mt-4 text-sm font-semibold uppercase tracking-wide text-navy-700 first:mt-0",
};

/**
 * Саммари в читаемом виде. `print` включает вариант для бумаги: без цвета
 * подложек и с чёрным текстом, чтобы протокол печатался экономно и читался
 * на чёрно-белом принтере.
 */
export function MarkdownBlocks({
  source,
  print = false,
}: {
  source: string;
  print?: boolean;
}) {
  const blocks = parseMarkdown(source);
  const body = print ? "text-sm text-black" : "text-sm text-zinc-700";

  return (
    <div className={print ? "space-y-1" : "space-y-1.5"}>
      {blocks.map((block: Block, i) => {
        switch (block.kind) {
          case "heading": {
            const Tag = block.level === 1 ? "h3" : block.level === 2 ? "h4" : "h5";
            return (
              <Tag
                key={i}
                className={
                  print
                    ? "mt-3 text-sm font-semibold text-black first:mt-0"
                    : HEADING_CLASS[block.level]
                }
              >
                <InlineText parts={block.inline} />
              </Tag>
            );
          }
          case "bullet":
            return (
              <div key={i} className={cn("flex gap-2 pl-1", print && "print-line", body)}>
                <span
                  aria-hidden
                  className={print ? "text-black" : "text-bronze-500"}
                >
                  •
                </span>
                <span className="leading-relaxed">
                  <InlineText parts={block.inline} />
                </span>
              </div>
            );
          case "numbered":
            return (
              <div key={i} className={cn("flex gap-2 pl-1", print && "print-line", body)}>
                <span className="tabular-nums text-zinc-500">
                  {block.marker}
                </span>
                <span className="leading-relaxed">
                  <InlineText parts={block.inline} />
                </span>
              </div>
            );
          case "table":
            return (
              <div key={i} className="my-3 overflow-x-auto">
                <table className="w-full border-collapse text-xs">
                  <thead>
                    <tr
                      className={
                        print
                          ? "border-b border-black/40 text-left"
                          : "border-b border-line text-left text-zinc-500"
                      }
                    >
                      {block.head.map((cell, c) => (
                        <th key={c} className="px-2 py-1.5 font-medium">
                          {cell}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {block.rows.map((row, r) => (
                      <tr
                        key={r}
                        className={
                          print
                            ? "border-b border-black/15 align-top"
                            : "border-b border-line/70 align-top"
                        }
                      >
                        {row.map((cell, c) => (
                          <td
                            key={c}
                            className={cn(
                              "px-2 py-1.5",
                              print ? "text-black" : "text-zinc-700",
                              c === 0 && "font-medium",
                            )}
                          >
                            {cell}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            );
          default:
            return (
              <p key={i} className={cn("leading-relaxed", body)}>
                <InlineText parts={block.inline} />
              </p>
            );
        }
      })}
    </div>
  );
}
