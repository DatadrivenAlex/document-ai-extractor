"""Render a validated document to plain text, a digital PDF, or a PNG."""

from __future__ import annotations

from pathlib import Path

from document_ai.dates import format_date
from document_ai.models import ValidatedDocument
from document_ai.money import format_amount, format_qty, format_rate

_FONT_CANDIDATES = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
)


def render_text(fields: ValidatedDocument, layout: str, date_style: str) -> str:
    if layout == "labeled":
        return _render_labeled(fields, date_style)
    if layout == "table":
        return _render_table(fields, date_style)
    if layout == "receipt":
        return _render_receipt(fields, date_style)
    if layout == "prose":
        return _render_prose(fields)
    raise ValueError(f"unknown layout: {layout}")


def render_pdf(lines: list[str], path: Path) -> None:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    path.parent.mkdir(parents=True, exist_ok=True)
    pdf = canvas.Canvas(str(path), pagesize=A4)
    _width, height = A4
    y = height - 72
    for line in lines:
        if y < 72:
            pdf.showPage()
            y = height - 72
        pdf.setFont("Helvetica", 11)
        pdf.drawString(54, y, line)
        y -= 16
    pdf.save()


def render_png(lines: list[str], path: Path) -> None:
    from PIL import Image, ImageDraw, ImageFont

    path.parent.mkdir(parents=True, exist_ok=True)
    font = _load_font(ImageFont, 32)
    padding = 28
    line_height = 48
    widths = [int(font.getlength(line)) for line in lines] or [0]
    width = max(900, max(widths) + padding * 2 + 8)
    height = padding * 2 + line_height * max(len(lines), 1)
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    y = padding
    for line in lines:
        draw.text((padding, y), line, fill="black", font=font)
        y += line_height
    image.save(path, format="PNG")


def _load_font(image_font: object, size: int) -> object:
    for candidate in _FONT_CANDIDATES:
        if Path(candidate).is_file():
            return image_font.truetype(candidate, size=size)  # type: ignore[attr-defined]
    try:
        return image_font.load_default(size=size)  # type: ignore[attr-defined]
    except TypeError:
        return image_font.load_default()  # type: ignore[attr-defined]


def _totals(fields: ValidatedDocument) -> list[str]:
    currency = fields.currency
    return [
        f"Subtotal: {format_amount(fields.subtotal, currency)}",
        f"VAT Rate: {format_rate(fields.vat_rate)}",
        f"VAT Amount: {format_amount(fields.vat_amount, currency)}",
        f"Total: {format_amount(fields.total, currency)}",
    ]


def _render_labeled(fields: ValidatedDocument, date_style: str) -> str:
    if fields.document_type == "receipt":
        header = [
            "RECEIPT",
            f"Merchant: {fields.vendor}",
            f"Receipt: {fields.document_number}",
            f"Date: {format_date(fields.issue_date, date_style)}",
        ]
    else:
        header = [
            "INVOICE",
            f"Vendor: {fields.vendor}",
            f"Invoice Number: {fields.document_number}",
            f"Invoice Date: {format_date(fields.issue_date, date_style)}",
        ]
        if fields.due_date is not None:
            header.append(f"Due Date: {format_date(fields.due_date, date_style)}")
    header.append(f"Currency: {fields.currency}")
    header.append("Items:")
    items = [
        (
            f"- {item.description} | qty {format_qty(item.quantity)} | "
            f"unit {format_amount(item.unit_price, fields.currency)} | "
            f"amount {format_amount(item.line_total, fields.currency)}"
        )
        for item in fields.line_items
    ]
    return "\n".join([*header, *items, *_totals(fields)])


def _render_table(fields: ValidatedDocument, date_style: str) -> str:
    lines = [
        "INVOICE",
        f"From: {fields.vendor}",
        f"No.: {fields.document_number}",
        f"Date: {format_date(fields.issue_date, date_style)}",
    ]
    if fields.due_date is not None:
        lines.append(f"Due: {format_date(fields.due_date, date_style)}")
    lines.append(f"Currency: {fields.currency}")
    lines.append("Description; Qty; Unit Price; Line Total")
    for item in fields.line_items:
        lines.append(
            f"{item.description}; {format_qty(item.quantity)}; "
            f"{format_amount(item.unit_price, fields.currency)}; "
            f"{format_amount(item.line_total, fields.currency)}"
        )
    lines.extend(_totals(fields))
    return "\n".join(lines)


def _render_receipt(fields: ValidatedDocument, date_style: str) -> str:
    lines = [
        "RECEIPT",
        f"Merchant: {fields.vendor}",
        f"Receipt: {fields.document_number}",
        f"Date: {format_date(fields.issue_date, date_style)}",
        f"Currency: {fields.currency}",
    ]
    for item in fields.line_items:
        lines.append(
            f"{format_qty(item.quantity)} x {item.description} @ "
            f"{format_amount(item.unit_price, fields.currency)} = "
            f"{format_amount(item.line_total, fields.currency)}"
        )
    lines.extend(_totals(fields))
    return "\n".join(lines)


def _render_prose(fields: ValidatedDocument) -> str:
    lines = [
        f"This invoice was issued by {fields.vendor}.",
        f"Reference code {fields.document_number}.",
        f"Issued on {format_date(fields.issue_date, 'long')}.",
    ]
    if fields.due_date is not None:
        lines.append(f"Payment is due on {format_date(fields.due_date, 'long')}.")
    lines.append(f"Amounts are in {fields.currency}.")
    for item in fields.line_items:
        lines.append(
            f'Bought {format_qty(item.quantity)} of "{item.description}" '
            f"priced at {format_amount(item.unit_price, fields.currency)} each "
            f"(line {format_amount(item.line_total, fields.currency)})."
        )
    lines.append(f"The net amount is {format_amount(fields.subtotal, fields.currency)}.")
    lines.append(
        "Value added tax at "
        f"{format_rate(fields.vat_rate)} comes to "
        f"{format_amount(fields.vat_amount, fields.currency)}."
    )
    lines.append(f"The grand total is {format_amount(fields.total, fields.currency)}.")
    return "\n".join(lines)
