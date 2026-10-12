"""Lightweight PDF/document generation for receipts, pay stubs, and invoices.

Produces minimal but valid PDFs without external dependencies. This keeps the
backend runnable with zero extra system packages; swap for a richer renderer
(WeasyPrint/ReportLab) in production if desired.
"""

from __future__ import annotations



def _escape(text: str) -> str:
    text = text.encode("latin-1", "replace").decode("latin-1")
    return text.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


def _build_pdf(objects: list[bytes]) -> bytes:
    pdf = b"%PDF-1.4\n"
    offsets: list[int] = []
    for i, obj in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf += b"%d 0 obj\n" % i + obj + b"\nendobj\n"
    xref_pos = len(pdf)
    pdf += b"xref\n0 %d\n" % (len(objects) + 1)
    pdf += b"0000000000 65535 f \n"
    for off in offsets:
        pdf += b"%010d 00000 n \n" % off
    pdf += b"trailer\n<< /Size %d /Root 1 0 R >>\n" % (len(objects) + 1)
    pdf += b"startxref\n%d\n%%%%EOF" % xref_pos
    return pdf


def render_simple_pdf(title: str, lines: list[str]) -> bytes:
    """Render a single-page PDF with a title and body lines. Returns bytes."""
    body_lines = [title, ""] + lines
    text_ops = ["BT", "/F1 14 Tf", "72 760 Td", "16 TL"]
    for i, line in enumerate(body_lines):
        text_ops.append(f"({_escape(line)}) Tj" if i == 0 else f"T* ({_escape(line)}) Tj")
    text_ops.append("ET")
    content = "\n".join(text_ops).encode("latin-1", "replace")

    objects: list[bytes] = []
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objects.append(b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>")
    objects.append(
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>"
    )
    objects.append(b"<< /Length %d >>\nstream\n%s\nendstream" % (len(content), content))
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    return _build_pdf(objects)


# ─── Invoice PDF ──────────────────────────────────────────────────────────

_MARGIN_LEFT = 72
_MARGIN_RIGHT = 72
_PAGE_WIDTH = 612
_COL_RIGHT = _PAGE_WIDTH - _MARGIN_RIGHT


def _text_at(x: float, y: float, text: str, font: str = "/F1", size: int = 10) -> str:
    return f"BT {font} {size} Tf {x:.0f} {y:.0f} Td ({_escape(text)}) Tj ET"


def _line(y: float, x1: float = 72, x2: float = 540) -> str:
    return f"BT /F1 1 Tf {x1:.0f} {y:.0f} Td (\u00a0) Tj ET 1 w {x1:.0f} {(y+3):.0f} m {x2:.0f} {(y+3):.0f} l S"


def _right_text(y: float, text: str, size: int = 10, font: str = "/F1") -> str:
    tw = len(text) * size * 0.55
    x = min(max(_COL_RIGHT - tw, _MARGIN_LEFT), _COL_RIGHT)
    return _text_at(x, y, text, font=font, size=size)


def render_invoice_pdf(
    gym_name: str,
    gym_address: str | None,
    invoice_id: str,
    invoice_date: str,
    status: str,
    description: str,
    subtotal: float,
    tax: float,
    total: float,
    currency: str = "USD",
) -> bytes:
    """Render a professional single-page invoice PDF."""
    lines: list[str] = []
    y = 740

    lines.append(_text_at(72, y, gym_name, font="/F2", size=18))
    y -= 16
    if gym_address:
        lines.append(_text_at(72, y, gym_address, size=9))
        y -= 14

    y -= 20
    lines.append(_text_at(72, y, "INVOICE", font="/F2", size=16))
    y -= 18
    lines.append(_text_at(72, y, f"#{invoice_id}", size=10))
    y -= 14
    lines.append(_text_at(72, y, f"Date: {invoice_date}", size=10))
    y -= 14
    lines.append(_text_at(72, y, f"Status: {status.upper()}", size=10))

    y -= 24
    lines.append(_line(y))
    y -= 20

    lines.append(_text_at(72, y, "Description", font="/F2", size=10))
    lines.append(_right_text(y, "Amount", size=10, font="/F2"))
    y -= 18
    lines.append(_line(y))
    y -= 16

    lines.append(_text_at(72, y, description, size=10))
    lines.append(_right_text(y, f"{currency} {subtotal:.2f}", size=10))
    y -= 18

    lines.append(_text_at(72, y, "Tax", size=10))
    lines.append(_right_text(y, f"{currency} {tax:.2f}", size=10))
    y -= 18

    lines.append(_line(y))
    y -= 20

    lines.append(_text_at(72, y, "Total", font="/F2", size=12))
    lines.append(_right_text(y, f"{currency} {total:.2f}", size=12, font="/F2"))
    y -= 40

    lines.append(_text_at(72, y, "Thank you for your business!", size=10))
    y -= 14
    lines.append(_text_at(72, y, "Gym Operations Platform", size=8))

    content_parts = "\n".join(lines)
    content = content_parts.encode("latin-1", "replace")

    objects: list[bytes] = []
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objects.append(b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>")
    objects.append(
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 4 0 R /F2 5 0 R >> >> /Contents 6 0 R >>"
    )
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>")
    objects.append(b"<< /Length %d >>\nstream\n%s\nendstream" % (len(content), content))
    return _build_pdf(objects)


# ─── Cash / offline payment receipt PDF ───────────────────────────────────


def render_receipt_pdf(
    *,
    gym_name: str,
    gym_address: str | None,
    receipt_no: str,
    paid_at: str,
    member_name: str,
    member_email: str,
    plan_name: str,
    amount: float,
    currency: str,
    method: str,
    logged_by: str,
    plan_price: float | None = None,
    joining_fee: float = 0,
    discount: float = 0,
    tax: float = 0,
    promo_code: str | None = None,
    valid_until: str | None = None,
    note: str | None = None,
) -> bytes:
    """Render the proof-of-payment receipt handed to a member (Section 11.1)."""

    lines: list[str] = []
    y = 740

    lines.append(_text_at(72, y, gym_name, font="/F2", size=18))
    y -= 16
    if gym_address:
        lines.append(_text_at(72, y, gym_address, size=9))
        y -= 14

    y -= 20
    lines.append(_text_at(72, y, "PAYMENT RECEIPT", font="/F2", size=16))
    lines.append(_right_text(y, "PAID", size=12, font="/F2"))
    y -= 18
    lines.append(_text_at(72, y, f"Receipt #{receipt_no}", size=10))
    y -= 14
    lines.append(_text_at(72, y, f"Date: {paid_at}", size=10))

    y -= 24
    lines.append(_line(y))
    y -= 20

    lines.append(_text_at(72, y, "Received from", font="/F2", size=10))
    y -= 16
    lines.append(_text_at(72, y, member_name, size=10))
    y -= 14
    lines.append(_text_at(72, y, member_email, size=9))

    y -= 24
    lines.append(_line(y))
    y -= 20

    lines.append(_text_at(72, y, "Description", font="/F2", size=10))
    lines.append(_right_text(y, "Amount", size=10, font="/F2"))
    y -= 18
    lines.append(_line(y))
    y -= 16

    lines.append(_text_at(72, y, plan_name, size=10))
    lines.append(_right_text(y, f"{currency} {(plan_price if plan_price is not None else amount):.2f}", size=10))
    y -= 18

    for label, value in (
        ("Joining fee", joining_fee),
        (f"Promo {promo_code}" if promo_code else "Discount", -discount),
        ("Tax", tax),
    ):
        if value:
            lines.append(_text_at(72, y, label, size=10))
            lines.append(_right_text(y, f"{currency} {value:.2f}", size=10))
            y -= 18

    lines.append(_text_at(72, y, f"Payment method: {method}", size=10))
    y -= 18

    lines.append(_line(y))
    y -= 20

    lines.append(_text_at(72, y, "Total paid", font="/F2", size=12))
    lines.append(_right_text(y, f"{currency} {amount:.2f}", size=12, font="/F2"))
    y -= 30

    if valid_until:
        lines.append(_text_at(72, y, f"Membership active until: {valid_until}", size=10))
        y -= 16
    if note:
        lines.append(_text_at(72, y, f"Note: {note}", size=9))
        y -= 16

    y -= 14
    lines.append(_text_at(72, y, f"Recorded by: {logged_by}", size=9))
    y -= 14
    lines.append(_text_at(72, y, "Keep this receipt as proof of payment.", size=9))
    y -= 14
    lines.append(_text_at(72, y, "Gym Operations Platform", size=8))

    content = "\n".join(lines).encode("latin-1", "replace")

    objects: list[bytes] = []
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objects.append(b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>")
    objects.append(
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 4 0 R /F2 5 0 R >> >> /Contents 6 0 R >>"
    )
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>")
    objects.append(b"<< /Length %d >>\nstream\n%s\nendstream" % (len(content), content))
    return _build_pdf(objects)
