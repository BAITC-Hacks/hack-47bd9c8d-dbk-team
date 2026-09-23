#!/usr/bin/env python3
"""
Экспорт summary.md в PDF.

Рендерит то подмножество Markdown, в котором приходит summary от модели:
заголовки, абзацы, маркированные и нумерованные списки, таблицы (в них
оформляются поручения), горизонтальные линии, блоки кода и инлайновое
оформление (**жирный**, *курсив*, `моноширинный`, ссылки).

Кириллица требует TTF-шрифта с юникодом: встроенные шрифты reportlab
(Helvetica и прочие Type 1) её не содержат и дают пустые квадраты. Берём
DejaVu Sans (пакет fonts-dejavu-core в образе), с откатом на Liberation /
FreeSans, если DejaVu в системе нет.

Использование:
    python3 export_pdf.py summary.md summary.pdf
    python3 export_pdf.py summary.md            # рядом, с расширением .pdf
"""

import argparse
import re
import sys
from html import escape
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    HRFlowable,
    ListFlowable,
    ListItem,
    Paragraph,
    Preformatted,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# Имена, под которыми шрифты регистрируются в reportlab.
FONT_REGULAR = "SummarySans"
FONT_BOLD = "SummarySans-Bold"
FONT_ITALIC = "SummarySans-Oblique"
FONT_MONO = "SummaryMono"

# Кандидаты в порядке предпочтения: (обычный, жирный, курсив, моноширинный).
FONT_CANDIDATES = [
    (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    ),
    (
        "/usr/share/fonts/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans-Oblique.ttf",
        "/usr/share/fonts/dejavu/DejaVuSansMono.ttf",
    ),
    (
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Italic.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf",
    ),
    (
        "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansOblique.ttf",
        "/usr/share/fonts/truetype/freefont/FreeMono.ttf",
    ),
]


class FontsNotFound(RuntimeError):
    """В системе нет ни одного TTF-шрифта с поддержкой кириллицы."""


def register_fonts():
    """Регистрирует первый найденный набор шрифтов. Возвращает путь к нему."""
    for regular, bold, italic, mono in FONT_CANDIDATES:
        if not Path(regular).exists():
            continue
        # Жирное/курсивное начертание может отсутствовать — тогда подставляем
        # обычное: текст останется читаемым, просто без выделения.
        bold = bold if Path(bold).exists() else regular
        italic = italic if Path(italic).exists() else regular
        mono = mono if Path(mono).exists() else regular

        pdfmetrics.registerFont(TTFont(FONT_REGULAR, regular))
        pdfmetrics.registerFont(TTFont(FONT_BOLD, bold))
        pdfmetrics.registerFont(TTFont(FONT_ITALIC, italic))
        pdfmetrics.registerFont(TTFont(FONT_MONO, mono))
        # Без этой привязки reportlab на <b>/<i> подставит Helvetica, которая
        # кириллицу не умеет.
        pdfmetrics.registerFontFamily(
            FONT_REGULAR,
            normal=FONT_REGULAR,
            bold=FONT_BOLD,
            italic=FONT_ITALIC,
            boldItalic=FONT_BOLD,
        )
        return regular

    raise FontsNotFound(
        "Не найден TTF-шрифт с кириллицей. Ожидался один из: "
        + ", ".join(c[0] for c in FONT_CANDIDATES)
        + ". В Debian/Ubuntu ставится пакетом fonts-dejavu-core."
    )


def build_styles():
    base = getSampleStyleSheet()
    styles = {
        "body": ParagraphStyle(
            "body",
            parent=base["Normal"],
            fontName=FONT_REGULAR,
            fontSize=10,
            leading=14,
            spaceAfter=6,
            alignment=TA_LEFT,
        ),
        "code": ParagraphStyle(
            "code",
            parent=base["Normal"],
            fontName=FONT_MONO,
            fontSize=8.5,
            leading=11,
            backColor=colors.HexColor("#f4f4f5"),
            borderPadding=6,
            spaceAfter=8,
        ),
        "cell": ParagraphStyle(
            "cell",
            parent=base["Normal"],
            fontName=FONT_REGULAR,
            fontSize=9,
            leading=12,
        ),
        "cell_head": ParagraphStyle(
            "cell_head",
            parent=base["Normal"],
            fontName=FONT_BOLD,
            fontSize=9,
            leading=12,
            textColor=colors.white,
        ),
    }
    # Заголовки: чем глубже уровень, тем мельче кегль.
    for level, (size, space_before) in enumerate(
        [(18, 0), (14, 12), (12, 10), (11, 8), (10, 8), (10, 8)], start=1
    ):
        styles[f"h{level}"] = ParagraphStyle(
            f"h{level}",
            parent=base["Normal"],
            fontName=FONT_BOLD,
            fontSize=size,
            leading=size * 1.3,
            spaceBefore=space_before,
            spaceAfter=6,
            textColor=colors.HexColor("#1b1b1f"),
        )
    return styles


def inline(text):
    """Инлайновый Markdown -> разметка reportlab."""
    # Экранируем раньше всего: иначе <, > и & из текста сломают разбор тегов.
    text = escape(text, quote=False)
    text = re.sub(r"`([^`]+)`", rf'<font face="{FONT_MONO}">\1</font>', text)
    text = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", r'<link href="\2" color="#1a5fb4">\1</link>', text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"__(.+?)__", r"<b>\1</b>", text)
    text = re.sub(r"(?<![\w*])\*([^*\n]+)\*(?![\w*])", r"<i>\1</i>", text)
    return text


def split_table_row(line):
    """'| a | b |' -> ['a', 'b']."""
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|"):
        line = line[:-1]
    return [c.strip() for c in line.split("|")]


def is_table_delimiter(line):
    """Строка-разделитель шапки таблицы: |---|:---:|---|."""
    stripped = line.strip()
    if "-" not in stripped or "|" not in stripped:
        return False
    return re.fullmatch(r"\|?[\s:|-]+\|[\s:|-]*", stripped) is not None


def parse_markdown(md_text):
    """Markdown -> список блоков вида {'type': ..., ...}."""
    lines = md_text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    blocks = []
    para = []
    i = 0

    def flush_para():
        if para:
            blocks.append({"type": "para", "text": " ".join(para)})
            para.clear()

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Блок кода ```...```
        if stripped.startswith("```"):
            flush_para()
            i += 1
            code = []
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code.append(lines[i])
                i += 1
            i += 1  # закрывающая ограда
            blocks.append({"type": "code", "text": "\n".join(code)})
            continue

        # Пустая строка — конец абзаца
        if not stripped:
            flush_para()
            i += 1
            continue

        # Горизонтальная линия (проверяется раньше таблицы: '---' ей не является)
        if re.fullmatch(r"(\*\s*){3,}|(-\s*){3,}|(_\s*){3,}", stripped):
            flush_para()
            blocks.append({"type": "hr"})
            i += 1
            continue

        # Заголовок
        m = re.match(r"(#{1,6})\s+(.*)", stripped)
        if m:
            flush_para()
            blocks.append({"type": "heading", "level": len(m.group(1)), "text": m.group(2).strip()})
            i += 1
            continue

        # Таблица: строка с | и следующая — разделитель шапки
        if "|" in stripped and i + 1 < len(lines) and is_table_delimiter(lines[i + 1]):
            flush_para()
            header = split_table_row(stripped)
            i += 2
            rows = []
            while i < len(lines) and "|" in lines[i] and lines[i].strip():
                rows.append(split_table_row(lines[i]))
                i += 1
            blocks.append({"type": "table", "header": header, "rows": rows})
            continue

        # Списки: собираем подряд идущие пункты одного вида
        m = re.match(r"[-*+]\s+(.*)", stripped)
        if m:
            flush_para()
            items = []
            while i < len(lines):
                m2 = re.match(r"[-*+]\s+(.*)", lines[i].strip())
                if not m2:
                    break
                items.append(m2.group(1).strip())
                i += 1
            blocks.append({"type": "list", "ordered": False, "items": items})
            continue

        m = re.match(r"\d+[.)]\s+(.*)", stripped)
        if m:
            flush_para()
            items = []
            while i < len(lines):
                m2 = re.match(r"\d+[.)]\s+(.*)", lines[i].strip())
                if not m2:
                    break
                items.append(m2.group(1).strip())
                i += 1
            blocks.append({"type": "list", "ordered": True, "items": items})
            continue

        para.append(stripped)
        i += 1

    flush_para()
    return blocks


# Длинная колонка не должна съедать всю строку.
MAX_WEIGHT = 60
# Горизонтальные отступы ячейки, заданы в TableStyle ниже (LEFT + RIGHT).
CELL_PADDING = 10


def _widest_word(text, font_name, font_size):
    """Ширина самого длинного слова — колонка уже него рвёт слова посередине."""
    return max(
        (pdfmetrics.stringWidth(word, font_name, font_size) for word in text.split()),
        default=0,
    )


def column_widths(header, rows, ncols, frame_width):
    """
    Ширины колонок пропорционально длине содержимого.

    Равные доли плохи для таблицы поручений: колонка «Поручение» длиннее
    остальных в разы, и при равных долях текст в ней рвётся на обрывки, а
    «Срок» стоит полупустым. Вес колонки — длина самой длинной ячейки,
    ограниченная сверху, чтобы одна колонка не забрала всю строку.

    Нижняя граница считается по самому длинному НЕРАЗРЫВНОМУ слову колонки,
    а не берётся константой: иначе заголовок вроде «Ответственный» переносится
    посередине слова.
    """
    weights = []
    minimums = []
    for i in range(ncols):
        head = header[i] if i < len(header) else ""
        longest = len(head)
        # Заголовок набран жирным — он шире того же текста обычным начертанием.
        min_w = _widest_word(head, FONT_BOLD, 9)
        for row in rows:
            if i < len(row):
                longest = max(longest, len(row[i]))
                min_w = max(min_w, _widest_word(row[i], FONT_REGULAR, 9))
        weights.append(min(max(longest, 1), MAX_WEIGHT))
        minimums.append(min_w + CELL_PADDING)

    total = sum(weights)
    widths = [frame_width * w / total for w in weights]

    # Колонки, которым не хватает до минимума, добираем за счёт тех, у кого
    # есть запас. Если минимумы в строку не влезают (очень длинные слова),
    # честнее отдать всем поровну, чем ломать вёрстку.
    if sum(minimums) >= frame_width:
        return [frame_width / ncols] * ncols

    deficit = sum(m - w for w, m in zip(widths, minimums) if w < m)
    if deficit > 0:
        surplus = sum(w - m for w, m in zip(widths, minimums) if w > m)
        widths = [
            m if w < m else w - (w - m) * deficit / surplus
            for w, m in zip(widths, minimums)
        ]
    return widths


def build_table(block, styles, frame_width):
    """Блок-таблица -> flowable с колонками по ширине содержимого."""
    header = block["header"]
    rows = block["rows"]
    ncols = max([len(header)] + [len(r) for r in rows]) if rows else len(header)

    def pad(row):
        return row + [""] * (ncols - len(row))

    data = [[Paragraph(inline(c), styles["cell_head"]) for c in pad(header)]]
    for row in rows:
        data.append([Paragraph(inline(c), styles["cell"]) for c in pad(row)])

    table = Table(data, colWidths=column_widths(header, rows, ncols, frame_width), repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#3b4252")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f4f4f5")]),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#c7c7cc")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return table


def blocks_to_flowables(blocks, styles, frame_width):
    flowables = []
    for block in blocks:
        kind = block["type"]

        if kind == "heading":
            flowables.append(Paragraph(inline(block["text"]), styles[f"h{block['level']}"]))
        elif kind == "para":
            flowables.append(Paragraph(inline(block["text"]), styles["body"]))
        elif kind == "code":
            flowables.append(Preformatted(block["text"], styles["code"]))
        elif kind == "hr":
            flowables.append(Spacer(1, 4))
            flowables.append(HRFlowable(width="100%", thickness=0.6, color=colors.HexColor("#c7c7cc")))
            flowables.append(Spacer(1, 6))
        elif kind == "list":
            items = [
                ListItem(Paragraph(inline(text), styles["body"]), leftIndent=12)
                for text in block["items"]
            ]
            flowables.append(
                ListFlowable(
                    items,
                    bulletType="1" if block["ordered"] else "bullet",
                    bulletFontName=FONT_REGULAR,
                    bulletFontSize=9,
                    leftIndent=14,
                    spaceAfter=6,
                )
            )
        elif kind == "table":
            flowables.append(Spacer(1, 2))
            flowables.append(build_table(block, styles, frame_width))
            flowables.append(Spacer(1, 8))

    return flowables


def markdown_to_pdf(md_text, output_path, title=None):
    """Рендерит Markdown-текст в PDF по указанному пути."""
    register_fonts()
    styles = build_styles()

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    margin = 18 * mm
    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        leftMargin=margin,
        rightMargin=margin,
        topMargin=margin,
        bottomMargin=margin,
        title=title or output_path.stem,
        author="AiMeetingCopilot",
    )

    blocks = parse_markdown(md_text)
    flowables = blocks_to_flowables(blocks, styles, doc.width)
    if not flowables:
        flowables = [Paragraph("Summary пустой.", styles["body"])]

    doc.build(flowables)
    return output_path


def export_summary_pdf(md_path, pdf_path=None):
    """summary.md -> summary.pdf. Возвращает путь к созданному файлу."""
    md_path = Path(md_path)
    if pdf_path is None:
        pdf_path = md_path.with_suffix(".pdf")

    md_text = md_path.read_text(encoding="utf-8")

    # Заголовок PDF-документа: первый H1 из summary, иначе имя файла.
    m = re.search(r"^#\s+(.+)$", md_text, flags=re.MULTILINE)
    title = m.group(1).strip() if m else md_path.stem

    return markdown_to_pdf(md_text, pdf_path, title=title)


def main():
    parser = argparse.ArgumentParser(description="Экспорт summary.md в PDF")
    parser.add_argument("input", help="Путь к summary.md")
    parser.add_argument(
        "output",
        nargs="?",
        default=None,
        help="Куда сохранить PDF (по умолчанию рядом с input, с расширением .pdf)",
    )
    args = parser.parse_args()

    try:
        path = export_summary_pdf(args.input, args.output)
    except FontsNotFound as e:
        print(f"Ошибка: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"Готово: PDF сохранён в {path}", file=sys.stderr)


if __name__ == "__main__":
    main()
