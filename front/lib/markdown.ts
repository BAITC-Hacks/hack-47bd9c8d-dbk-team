/**
 * Разбор саммари в блоки.
 *
 * Модель отдаёт обычный markdown: заголовки `###`, списки `*` и `-`, выделение
 * `**`, нумерованные пункты и таблицу поручений. Раньше это показывалось как
 * есть — в протоколе стояли решётки, звёздочки и палки таблицы. Разбор один на
 * три места вывода: экран, печать и DOCX; иначе они расходятся, и протокол в
 * файле выглядит иначе, чем на экране.
 */

export type Inline = { text: string; bold: boolean };

export type Block =
  | { kind: "heading"; level: 1 | 2 | 3; inline: Inline[] }
  | { kind: "paragraph"; inline: Inline[] }
  | { kind: "bullet"; inline: Inline[] }
  | { kind: "numbered"; marker: string; inline: Inline[] }
  | { kind: "table"; head: string[]; rows: string[][] };

/** `**жирный**` внутри строки. Незакрытые звёздочки остаются текстом. */
export function parseInline(raw: string): Inline[] {
  const out: Inline[] = [];
  const re = /\*\*(.+?)\*\*/g;
  let last = 0;
  let m: RegExpExecArray | null;
  while ((m = re.exec(raw))) {
    if (m.index > last) out.push({ text: raw.slice(last, m.index), bold: false });
    out.push({ text: m[1], bold: true });
    last = m.index + m[0].length;
  }
  if (last < raw.length) out.push({ text: raw.slice(last), bold: false });
  return out.length ? out : [{ text: raw, bold: false }];
}

export function inlineToText(inline: Inline[]): string {
  return inline.map((i) => i.text).join("");
}

function splitRow(line: string): string[] {
  return line
    .trim()
    .replace(/^\||\|$/g, "")
    .split("|")
    .map((c) => c.trim());
}

const SEPARATOR = /^\|?[\s:|-]+\|[\s:|-]*$/;

export function parseMarkdown(md: string): Block[] {
  const lines = (md ?? "").split("\n");
  const blocks: Block[] = [];

  for (let i = 0; i < lines.length; i += 1) {
    const line = lines[i];
    const t = line.trim();
    if (!t) continue;

    // Таблица: строка с палками, под ней разделитель. Без разделителя это
    // обычный текст, в котором случайно встретилась палка.
    if (t.startsWith("|") && SEPARATOR.test(lines[i + 1]?.trim() ?? "")) {
      const head = splitRow(t);
      const rows: string[][] = [];
      i += 2;
      while (i < lines.length && lines[i].trim().startsWith("|")) {
        const cells = splitRow(lines[i]);
        if (cells.some((c) => c)) rows.push(cells);
        i += 1;
      }
      i -= 1;
      blocks.push({ kind: "table", head, rows });
      continue;
    }

    const heading = /^(#{1,6})\s+(.*)$/.exec(t);
    if (heading) {
      const level = Math.min(heading[1].length, 3) as 1 | 2 | 3;
      blocks.push({ kind: "heading", level, inline: parseInline(heading[2]) });
      continue;
    }

    const bullet = /^[*-]\s+(.*)$/.exec(t);
    if (bullet) {
      blocks.push({ kind: "bullet", inline: parseInline(bullet[1]) });
      continue;
    }

    const numbered = /^(\d+[.)])\s+(.*)$/.exec(t);
    if (numbered) {
      // «1. **Краткое резюме**» — модель нумерует разделы, а не пункты списка.
      // Такую строку показываем заголовком: так она и задумана.
      const inline = parseInline(numbered[2]);
      const wholeBold = inline.length === 1 && inline[0].bold;
      blocks.push(
        wholeBold
          ? { kind: "heading", level: 2, inline }
          : { kind: "numbered", marker: numbered[1], inline },
      );
      continue;
    }

    blocks.push({ kind: "paragraph", inline: parseInline(t) });
  }

  return blocks;
}
