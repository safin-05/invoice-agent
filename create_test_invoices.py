"""
Generates four test invoice PDFs in test_invoices/.

Exact total maths (verified before writing):
  invoice_match          subtotal=42,372.88  GST=7,627.12   TOTAL=50,000.00
  invoice_over           subtotal=32,203.39  GST=5,796.61   TOTAL=38,000.00
  invoice_vendor_mismatch subtotal=27,118.64 GST=4,881.36   TOTAL=32,000.00
  invoice_no_po          subtotal=18,220.34  GST=3,279.66   TOTAL=21,500.00
"""
import os
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle,
    Paragraph, Spacer, HRFlowable,
)
from reportlab.lib.styles import ParagraphStyle

os.makedirs("test_invoices", exist_ok=True)

# ── Palette ───────────────────────────────────────────────────────────────────
DARK   = colors.HexColor("#1a1a2e")
ACCENT = colors.HexColor("#2d6a9f")
LGREY  = colors.HexColor("#f5f5f5")
MGREY  = colors.HexColor("#cccccc")

def S(name, size=9, font="Helvetica", color="#333333", **kw):
    return ParagraphStyle(name, fontName=font, fontSize=size,
                          textColor=colors.HexColor(color), **kw)

TITLE = S("title", 22, "Helvetica-Bold", "#1a1a2e", spaceAfter=1)
VNAME = S("vname", 13, "Helvetica-Bold", "#1a1a2e", spaceAfter=2)
SMALL = S("small",  8, color="#666666")
BODY  = S("body",   9)
BOLD  = S("bold",   9, "Helvetica-Bold")
H2    = S("h2",    10, "Helvetica-Bold", "#2d6a9f", spaceBefore=6, spaceAfter=3)


# ── Builder ───────────────────────────────────────────────────────────────────

def build_invoice(
    filename,
    vendor_name, vendor_address, vendor_gstin,
    invoice_number, invoice_date, due_date, po_number,
    buyer_name, buyer_address, buyer_gstin,
    line_items,   # list of dicts: {desc, qty, unit}
    notes="",
):
    """
    Writes one invoice PDF.
    po_number=None → the PO Number row is omitted entirely from the document,
    so the agent's regex cannot find it.
    """
    for item in line_items:
        item["amount"] = round(item["qty"] * item["unit"], 2)

    subtotal = round(sum(i["amount"] for i in line_items), 2)
    gst      = round(subtotal * 0.18, 2)
    total    = round(subtotal + gst, 2)

    filepath = os.path.join("test_invoices", filename)
    doc = SimpleDocTemplate(
        filepath, pagesize=A4,
        rightMargin=20*mm, leftMargin=20*mm,
        topMargin=15*mm, bottomMargin=15*mm,
    )
    story = []

    # ── Vendor header ─────────────────────────────────────────────────────────
    story.append(Paragraph("INVOICE", TITLE))
    story.append(Paragraph(f"<b>{vendor_name}</b>", VNAME))
    story.append(Paragraph(vendor_address, SMALL))
    if vendor_gstin:
        story.append(Paragraph(f"GSTIN: {vendor_gstin}", SMALL))
    story.append(Spacer(1, 5*mm))

    # ── Bill-To + invoice meta (two-column) ───────────────────────────────────
    bill_to_html = (
        f"<b>Bill To:</b><br/>{buyer_name}<br/>{buyer_address}"
        + (f"<br/>GSTIN: {buyer_gstin}" if buyer_gstin else "")
    )

    meta_rows = [
        ["Invoice Number:", invoice_number],
        ["Invoice Date:",   invoice_date],
        ["Due Date:",       due_date],
        ["Payment Terms:",  "Net 30"],
        ["Currency:",       "INR"],
    ]
    if po_number:                          # omit row entirely when po_number is None
        meta_rows.insert(2, ["PO Number:", po_number])

    meta_inner = Table(
        meta_rows,
        colWidths=[38*mm, 55*mm],
        style=TableStyle([
            ("FONTNAME",      (0, 0), (-1, -1), "Helvetica"),
            ("FONTNAME",      (0, 0), (0,  -1), "Helvetica-Bold"),
            ("FONTSIZE",      (0, 0), (-1, -1), 9),
            ("TEXTCOLOR",     (0, 0), (-1, -1), colors.HexColor("#333333")),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]),
    )

    header_table = Table(
        [[Paragraph(bill_to_html, BODY), meta_inner]],
        colWidths=[90*mm, 98*mm],
        style=TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]),
    )
    story.append(header_table)
    story.append(Spacer(1, 6*mm))

    # ── Line items ────────────────────────────────────────────────────────────
    story.append(Paragraph("Line Items", H2))

    rows = [["#", "Description", "Qty", "Unit Price (Rs.)", "Amount (Rs.)"]]
    for i, item in enumerate(line_items):
        rows.append([
            str(i + 1),
            item["desc"],
            str(item["qty"]),
            f"{item['unit']:,.2f}",
            f"{item['amount']:,.2f}",
        ])

    items_table = Table(
        rows,
        colWidths=[10*mm, 87*mm, 18*mm, 33*mm, 33*mm],
        style=TableStyle([
            ("BACKGROUND",    (0, 0), (-1, 0),  ACCENT),
            ("TEXTCOLOR",     (0, 0), (-1, 0),  colors.white),
            ("FONTNAME",      (0, 0), (-1, 0),  "Helvetica-Bold"),
            ("FONTNAME",      (0, 1), (-1, -1), "Helvetica"),
            ("FONTSIZE",      (0, 0), (-1, -1), 9),
            ("ROWBACKGROUNDS",(0, 1), (-1, -1), [colors.white, LGREY]),
            ("ALIGN",         (2, 0), (-1, -1), "RIGHT"),
            ("ALIGN",         (0, 0), (1,  -1), "LEFT"),
            ("GRID",          (0, 0), (-1, -1), 0.5, MGREY),
            ("TOPPADDING",    (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LEFTPADDING",   (0, 0), (-1, -1), 6),
        ]),
    )
    story.append(items_table)
    story.append(Spacer(1, 4*mm))

    # ── Totals ────────────────────────────────────────────────────────────────
    totals = Table(
        [
            ["", "Subtotal:",  f"Rs. {subtotal:,.2f}"],
            ["", "GST (18%):", f"Rs. {gst:,.2f}"],
            ["", "TOTAL DUE:", f"Rs. {total:,.2f}"],
        ],
        colWidths=[100*mm, 44*mm, 38*mm],
        style=TableStyle([
            ("FONTNAME",      (0, 0), (-1, -1), "Helvetica"),
            ("FONTSIZE",      (0, 0), (-1, -1), 9),
            ("FONTNAME",      (1, 2), (-1,  2), "Helvetica-Bold"),
            ("FONTSIZE",      (1, 2), (-1,  2), 11),
            ("ALIGN",         (1, 0), (-1, -1), "RIGHT"),
            ("LINEABOVE",     (1, 2), (-1,  2), 1, DARK),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]),
    )
    story.append(totals)

    if notes:
        story.append(Spacer(1, 6*mm))
        story.append(HRFlowable(width="100%", thickness=0.5, color=MGREY))
        story.append(Spacer(1, 3*mm))
        story.append(Paragraph("<b>Notes</b>", BOLD))
        story.append(Paragraph(notes, SMALL))

    doc.build(story)
    print(f"  {filename:<40}  subtotal={subtotal:>10,.2f}  GST={gst:>8,.2f}  TOTAL={total:>10,.2f}")


# ── Invoice 1: Perfect match ──────────────────────────────────────────────────
# Acme Supplies, PO-1001 (approved Rs.50,000). Invoice total = 50,000.
# Math: 42,372.88 * 1.18 = 42,372.88 + 7,627.12 = 50,000.00
print("\nGenerating invoices...")
build_invoice(
    filename       = "invoice_match.pdf",
    vendor_name    = "Acme Supplies Pvt. Ltd.",
    vendor_address = "42 Industrial Estate, Whitefield, Bengaluru - 560066  |  contact@acmesupplies.in",
    vendor_gstin   = "29AABCA1234A1Z5",
    invoice_number = "INV-2026-0892",
    invoice_date   = "25 June 2026",
    due_date       = "25 July 2026",
    po_number      = "PO-1001",
    buyer_name     = "Tone Garage Technologies Pvt. Ltd.",
    buyer_address  = "91 Koramangala 5th Block, Bengaluru - 560095",
    buyer_gstin    = "29AADCT5678B1ZK",
    line_items     = [
        {"desc": "Industrial Resistance Bands (Set of 5)", "qty": 100, "unit": 180.00},
        {"desc": "Foam Rollers - High Density",            "qty":  60, "unit": 180.00},
        {"desc": "Gym Chalk Block (200 g)",                "qty": 200, "unit":  65.00},
        {"desc": "Handling & Freight Charges",             "qty":   1, "unit": 572.88},
    ],
    notes="Payment via NEFT/RTGS to HDFC Bank. A/C 5020012345678, IFSC HDFC0001234. Quote INV-2026-0892.",
)

# ── Invoice 2: Amount exceeds PO limit ───────────────────────────────────────
# Bright Logistics, PO-1002 (approved Rs.30,000). Invoice total = 38,000 — over by 8,000.
# Math: 32,203.39 * 1.18 = 32,203.39 + 5,796.61 = 38,000.00
build_invoice(
    filename       = "invoice_over.pdf",
    vendor_name    = "Bright Logistics Pvt. Ltd.",
    vendor_address = "14 Peenya Industrial Area, Bengaluru - 560058  |  ops@brightlogistics.in",
    vendor_gstin   = "29AABCB5678B1Z3",
    invoice_number = "BL-2026-0044",
    invoice_date   = "28 June 2026",
    due_date       = "28 July 2026",
    po_number      = "PO-1002",
    buyer_name     = "Tone Garage Technologies Pvt. Ltd.",
    buyer_address  = "91 Koramangala 5th Block, Bengaluru - 560095",
    buyer_gstin    = "29AADCT5678B1ZK",
    line_items     = [
        {"desc": "Freight Services, Mumbai-Bengaluru (LTL)", "qty":  5, "unit": 3000.00},
        {"desc": "Warehousing Charges (per day)",            "qty": 30, "unit":  250.00},
        {"desc": "Packing & Crating Materials",              "qty":100, "unit":   95.00},
        {"desc": "Express Delivery Surcharge",               "qty":  1, "unit":  203.39},
    ],
    notes="Payment via NEFT to Axis Bank. A/C 9180034567890, IFSC UTIB0002345. Quote BL-2026-0044.",
)

# ── Invoice 3: Vendor name mismatch ──────────────────────────────────────────
# PO-1002 belongs to Bright Logistics. This invoice claims vendor = Shady Corp.
# Agent should detect the name mismatch regardless of the amount.
# Math: 27,118.64 * 1.18 = 27,118.64 + 4,881.36 = 32,000.00
build_invoice(
    filename       = "invoice_vendor_mismatch.pdf",
    vendor_name    = "Shady Corp Pvt. Ltd.",
    vendor_address = "Plot 99, Unknown Industrial Estate, Bengaluru - 560000",
    vendor_gstin   = "29XXXXX0000X0X0",
    invoice_number = "SC-2026-0001",
    invoice_date   = "30 June 2026",
    due_date       = "30 July 2026",
    po_number      = "PO-1002",
    buyer_name     = "Tone Garage Technologies Pvt. Ltd.",
    buyer_address  = "91 Koramangala 5th Block, Bengaluru - 560095",
    buyer_gstin    = "29AADCT5678B1ZK",
    line_items     = [
        {"desc": "Logistics Consulting Services",        "qty": 10, "unit": 2000.00},
        {"desc": "Route Optimisation Software Licence",  "qty":  1, "unit": 5000.00},
        {"desc": "Post-Sales Technical Support (hourly)","qty":  8, "unit":  264.83},
    ],
    notes="Please process urgently. Wire to SBIN0000001, A/C 0000099999.",
)

# ── Invoice 4: No PO number anywhere ─────────────────────────────────────────
# The PO Number row is absent from the PDF — the agent cannot look anything up.
# Math: 18,220.34 * 1.18 = 18,220.34 + 3,279.66 = 21,500.00
build_invoice(
    filename       = "invoice_no_po.pdf",
    vendor_name    = "Horizon Tech Supplies",
    vendor_address = "8 Commercial Street, MG Road, Bengaluru - 560001  |  sales@horizontech.in",
    vendor_gstin   = "29AADCH9012C1Z7",
    invoice_number = "HTS-2026-0227",
    invoice_date   = "01 July 2026",
    due_date       = "31 July 2026",
    po_number      = None,
    buyer_name     = "Tone Garage Technologies Pvt. Ltd.",
    buyer_address  = "91 Koramangala 5th Block, Bengaluru - 560095",
    buyer_gstin    = "29AADCT5678B1ZK",
    line_items     = [
        {"desc": "A4 Paper Reams (500 sheets, 80 gsm)", "qty": 50, "unit": 200.00},
        {"desc": "Laser Printer Cartridges (Black)",     "qty": 10, "unit": 800.00},
        {"desc": "Desk Organiser & Stationery Kit",      "qty":  1, "unit": 220.34},
    ],
    notes="Payment via cheque or NEFT to ICICI Bank. A/C 6070081234567, IFSC ICIC0006070.",
)

print("\nAll invoices written to test_invoices/")
