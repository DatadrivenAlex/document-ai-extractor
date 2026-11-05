"""Seeded synthetic invoices and receipts with PDF, PNG, and ground-truth JSON."""

from __future__ import annotations

import json
import random
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from document_ai.models import LineItem, ValidatedDocument
from document_ai.money import money
from document_ai.render import render_pdf, render_png, render_text

LAYOUTS: tuple[str, ...] = ("labeled", "table", "receipt", "prose")
DATE_STYLES: tuple[str, ...] = ("iso", "dmy_dot", "dmy_mon")
CURRENCIES: tuple[str, ...] = ("EUR", "USD", "GBP")
VAT_RATES: tuple[Decimal, ...] = (
    Decimal("0"),
    Decimal("0.05"),
    Decimal("0.07"),
    Decimal("0.19"),
    Decimal("0.20"),
    Decimal("0.21"),
)
VENDORS: tuple[str, ...] = (
    "Northwind Traders",
    "Acme GmbH",
    "Brightline Studio",
    "Cafe Lumen",
    "Harbor and Co",
    "Paperplane Supplies",
    "Danube Analytics",
    "Blacksea Retail",
    "Linden Apothecary",
    "Copper Kettle",
    "Atlas Freight",
    "Mesa Components",
)
PRODUCTS: tuple[tuple[str, str], ...] = (
    ("A4 paper ream", "6.40"),
    ("USB-C cable", "9.90"),
    ("Consulting hour", "120.00"),
    ("Espresso", "2.80"),
    ("Croissant", "3.40"),
    ("Notebook", "4.20"),
    ("Whiteboard marker", "1.80"),
    ("Cloud storage plan", "15.00"),
    ("Train ticket", "27.50"),
    ("Desk lamp", "32.00"),
    ("Server migration", "1250.00"),
    ("Annual support", "2400.00"),
)
ISSUE_START = date(2023, 1, 1)
ISSUE_END = date(2025, 12, 1)


@dataclass(frozen=True)
class GeneratedDocument:
    id: str
    layout: str
    fields: ValidatedDocument
    text: str
    pdf_path: Path
    png_path: Path
    json_path: Path


def generate_corpus(seed: int, count: int, dest_dir: Path) -> list[GeneratedDocument]:
    """Write `count` documents. Layouts rotate so every block of four covers all forms."""
    if count < 1:
        raise ValueError("count must be at least 1")
    rng = random.Random(seed)
    destination = Path(dest_dir)
    return [
        generate_one(rng=rng, index=index, dest_dir=destination) for index in range(1, count + 1)
    ]


def generate_one(
    *,
    rng: random.Random,
    index: int,
    dest_dir: Path,
    layout: str | None = None,
    currency: str | None = None,
) -> GeneratedDocument:
    """Build one document. Forced layout or currency still consumes the same RNG draws."""
    chosen_layout = layout or LAYOUTS[(index - 1) % len(LAYOUTS)]
    if chosen_layout not in LAYOUTS:
        raise ValueError(f"unknown layout: {chosen_layout}")
    document_type = "receipt" if chosen_layout == "receipt" else "invoice"

    vendor = rng.choice(VENDORS)
    picked_currency = rng.choice(CURRENCIES)
    if currency is not None:
        picked_currency = currency
    vat_rate = rng.choice(VAT_RATES)
    date_style = rng.choice(DATE_STYLES)
    issue_date = date.fromordinal(rng.randint(ISSUE_START.toordinal(), ISSUE_END.toordinal()))
    due_offset = rng.choice((14, 30))
    item_count = rng.randint(1, 4)
    chosen_products = rng.sample(PRODUCTS, item_count)

    line_items: list[LineItem] = []
    for description, unit_price in chosen_products:
        quantity = Decimal(rng.randint(1, 5))
        unit = Decimal(unit_price)
        line_items.append(
            LineItem(
                description=description,
                quantity=quantity,
                unit_price=unit,
                line_total=money(quantity * unit),
            )
        )

    subtotal = money(sum((item.line_total for item in line_items), Decimal("0")))
    vat_amount = money(subtotal * vat_rate)
    total = money(subtotal + vat_amount)
    due_date = issue_date + timedelta(days=due_offset) if document_type == "invoice" else None
    if document_type == "invoice":
        document_number = f"INV-{issue_date.year}-{index:04d}"
    else:
        document_number = f"RCT-{index:05d}"

    fields = ValidatedDocument(
        document_type=document_type,
        vendor=vendor,
        document_number=document_number,
        issue_date=issue_date,
        due_date=due_date,
        currency=picked_currency,  # type: ignore[arg-type]
        subtotal=subtotal,
        vat_rate=vat_rate,
        vat_amount=vat_amount,
        total=total,
        line_items=line_items,
    )
    text = render_text(fields, chosen_layout, date_style)
    doc_id = f"{document_type}_{index:03d}"
    pdf_path, png_path, json_path = _write_files(
        doc_id, chosen_layout, fields, text, Path(dest_dir)
    )
    return GeneratedDocument(
        id=doc_id,
        layout=chosen_layout,
        fields=fields,
        text=text,
        pdf_path=pdf_path,
        png_path=png_path,
        json_path=json_path,
    )


def _write_files(
    doc_id: str,
    layout: str,
    fields: ValidatedDocument,
    text: str,
    dest_dir: Path,
) -> tuple[Path, Path, Path]:
    dest_dir.mkdir(parents=True, exist_ok=True)
    lines = text.splitlines()
    pdf_path = dest_dir / f"{doc_id}.pdf"
    png_path = dest_dir / f"{doc_id}.png"
    json_path = dest_dir / f"{doc_id}.json"
    render_pdf(lines, pdf_path)
    render_png(lines, png_path)
    payload = {"fields": fields.model_dump(mode="json"), "id": doc_id, "layout": layout}
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return pdf_path, png_path, json_path
