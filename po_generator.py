"""Auto-generate the final Purchase Order PDF with ReportLab."""
from __future__ import annotations

import datetime as dt
import io
import zlib
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from models import RFQ, Room

NAVY = colors.HexColor("#0b1f3a")
LIGHT = colors.HexColor("#eef2f8")
LINE = colors.HexColor("#d5dbe5")


def po_number(supplier: str, date: dt.date | None = None) -> str:
    """Stable PO number (same supplier + date -> same number, also across Python runs)."""
    date = date or dt.date.today()
    return f"PO-{date:%Y%m%d}-{zlib.crc32(supplier.encode()) % 9000 + 1000}"


def allocate_lines(rfq: RFQ, total: float) -> list[dict]:
    """Split the agreed package price over the RFQ lines.

    Weights are qty x reference unit price when EVERY line has a reference price, otherwise plain quantity.
    The last line absorbs rounding so the lines always add up to the agreed total exactly.
    """
    use_ref = all(i.ref_unit_price for i in rfq.items)
    weights = [i.quantity * (i.ref_unit_price if use_ref else 1) for i in rfq.items]
    wsum = sum(weights)
    rows, running = [], 0.0
    for n, (it, w) in enumerate(zip(rfq.items, weights)):
        amount = round(total - running, 2) if n == len(rfq.items) - 1 else round(total * w / wsum, 2)
        running += amount
        rows.append({"description": it.description, "quantity": it.quantity, "unit": it.unit,
                     "unit_price": amount / it.quantity, "amount": amount})
    return rows


def generate_po_pdf(rfq: RFQ, room: Room, buyer_company: str | None = None, po_no: str | None = None,
                    approved_by: str = "") -> bytes:
    f = room.final_offer
    assert f is not None, "No agreed deal to turn into a PO"
    buyer_company = buyer_company or rfq.buyer_company or "Acme Manufacturing Ltd."
    today = dt.date.today()
    po_no = po_no or po_number(room.supplier, today)
    delivery_date = today + dt.timedelta(days=f.delivery_days)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm,
                            topMargin=16 * mm, bottomMargin=18 * mm, title=po_no)
    ss = getSampleStyleSheet()
    small = ParagraphStyle("small", parent=ss["Normal"], fontSize=8, textColor=colors.grey)
    h3 = ParagraphStyle("h3", parent=ss["Heading3"], textColor=NAVY, spaceBefore=4, spaceAfter=4)
    white_title = ParagraphStyle("wt", parent=ss["Title"], textColor=colors.white, alignment=0, fontSize=20, leading=24)
    white_sub = ParagraphStyle("ws", parent=ss["Normal"], textColor=colors.HexColor("#c9d6ea"), fontSize=9)
    cell = ParagraphStyle("cell", parent=ss["Normal"], fontSize=9, leading=11)

    banner = Table([[Paragraph("PURCHASE ORDER", white_title),
                     Paragraph(f"<b>{po_no}</b><br/>Issued {today:%d %b %Y}", white_sub)]],
                   colWidths=[110 * mm, 64 * mm])
    banner.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), NAVY), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                                ("ALIGN", (1, 0), (1, 0), "RIGHT"), ("PADDING", (0, 0), (-1, -1), 10)]))
    story = [banner, Spacer(1, 7 * mm)]

    parties = Table([["BUYER", "SUPPLIER"], [buyer_company, room.supplier]], colWidths=[87 * mm, 87 * mm])
    parties.setStyle(TableStyle([("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("FONTSIZE", (0, 0), (-1, 0), 8),
                                 ("BACKGROUND", (0, 0), (-1, 0), LIGHT), ("TEXTCOLOR", (0, 0), (-1, 0), NAVY),
                                 ("BOX", (0, 0), (-1, -1), 0.5, LINE), ("PADDING", (0, 0), (-1, -1), 6)]))
    story += [parties, Spacer(1, 7 * mm)]

    rows = allocate_lines(rfq, f.price)
    data = [["#", "Description", "Qty", "Unit", "Unit price (USD)", "Amount (USD)"]]
    for n, r in enumerate(rows, 1):
        data.append([n, Paragraph(escape(r["description"]), cell), f"{r['quantity']:,}", r["unit"],
                     f"{r['unit_price']:,.2f}", f"{r['amount']:,.2f}"])
    data.append(["", "", "", "", "TOTAL", f"{f.price:,.2f}"])
    lines = Table(data, colWidths=[9 * mm, 68 * mm, 18 * mm, 15 * mm, 33 * mm, 31 * mm], repeatRows=1)
    lines.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), NAVY), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                               ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("FONTSIZE", (0, 0), (-1, -1), 9),
                               ("FONTNAME", (-2, -1), (-1, -1), "Helvetica-Bold"),
                               ("BACKGROUND", (0, -1), (-1, -1), LIGHT),
                               ("ALIGN", (2, 0), (-1, -1), "RIGHT"), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                               ("GRID", (0, 0), (-1, -2), 0.4, LINE), ("PADDING", (0, 0), (-1, -1), 5)]))
    story += [Paragraph("Order Lines", h3), lines]
    if len(rows) > 1:
        story.append(Paragraph("The package was negotiated as one price with a single supplier; line amounts are "
                               "allocated pro rata and add up to the agreed total.", small))
    story.append(Spacer(1, 6 * mm))

    terms = [["Delivery lead time", f"{f.delivery_days} days (by {delivery_date:%d %b %Y})"],
             ["Payment terms", f"Net {f.payment_days} days"],
             ["Negotiation rounds", f"{max(o.round for o in room.offers)} of {rfq.max_rounds}"],
             ["Selection score", f"{room.score}/100"]]
    if approved_by:
        terms.append(["Approved by", approved_by])
    t = Table(terms, colWidths=[50 * mm, 124 * mm])
    t.setStyle(TableStyle([("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"), ("FONTSIZE", (0, 0), (-1, -1), 9),
                           ("LINEBELOW", (0, 0), (-1, -1), 0.25, LINE), ("PADDING", (0, 0), (-1, -1), 5)]))
    story += [Paragraph("Commercial Terms", h3), t, Spacer(1, 6 * mm)]

    hist = [["Rnd", "Party", "Action", "Price (USD)", "Days", "Net"]]
    for o in room.offers:
        hist.append([o.round, o.party.title(), o.action.title(), f"{o.price:,.0f}", o.delivery_days, o.payment_days])
    h = Table(hist, colWidths=[15 * mm, 30 * mm, 30 * mm, 40 * mm, 20 * mm, 20 * mm], repeatRows=1)
    h.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), LIGHT), ("FONTSIZE", (0, 0), (-1, -1), 8),
                           ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("GRID", (0, 0), (-1, -1), 0.25, LINE)]))
    story += [Paragraph("Negotiation Audit Trail", h3), h, Spacer(1, 8 * mm),
              Paragraph("Generated automatically by the Closed-Room B2B Negotiation Hub. "
                        "Private budget and supplier floor margins are not disclosed in this document.", small)]
    doc.build(story)
    return buf.getvalue()
