"""
LedgerZero - Multi-Format Export Engine
Supports exporting reconciliation results into:
- Excel (.xlsx) [Multi-sheet executive workbook]
- Adobe PDF (.pdf) [Executive audit report with sign-offs]
- Microsoft Word (.docx) [Executive dossier]
- Comma-Separated Values (.csv)
- Tab-Separated Values (.tsv)
- Structured JSON (.json)
- Structured XML (.xml)
- Standalone Printable HTML (.html)
- Complete Archive (.zip) containing all formats
"""

import io
import json
import csv
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime

# Excel support (optional)
try:
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter
except ImportError:
    openpyxl = None

# Word support (optional)
try:
    import docx
    from docx.shared import Inches, Pt, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.enum.table import WD_TABLE_ALIGNMENT
except ImportError:
    docx = None

# PDF support (optional)
try:
    import reportlab
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter, landscape
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
except ImportError:
    reportlab = None


def _safe_float(val, default=0.0):
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def generate_xlsx(report):
    """Generate professional multi-sheet Excel workbook."""
    if openpyxl is None:
        raise ImportError("openpyxl is required for Excel export. Install with: pip install openpyxl")
    wb = openpyxl.Workbook()
    summary = report.get("summary", {})
    matches = report.get("matches", [])
    exceptions = report.get("exceptions", [])
    action_plan = report.get("action_plan", {})
    action_items = action_plan.get("action_items", [])

    # Styling definitions
    header_fill = PatternFill(start_color="0A0A0C", end_color="0A0A0C", fill_type="solid")
    header_font = Font(name="Arial", size=10, bold=True, color="00E5FF")
    title_font = Font(name="Arial", size=14, bold=True, color="00FF88")
    bold_font = Font(name="Arial", size=10, bold=True, color="FFFFFF")
    regular_font = Font(name="Arial", size=9, color="E0E0E0")
    kpi_val_font = Font(name="Arial", size=12, bold=True, color="00FF88")

    thin_border = Border(
        left=Side(style='thin', color='2A2A35'),
        right=Side(style='thin', color='2A2A35'),
        top=Side(style='thin', color='2A2A35'),
        bottom=Side(style='thin', color='2A2A35')
    )

    # -------------------------------------------------------------
    # Sheet 1: Executive Summary
    # -------------------------------------------------------------
    ws_sum = wb.active
    ws_sum.title = "Executive Summary"
    ws_sum.views.sheetView[0].showGridLines = True

    ws_sum["A1"] = "LEDGERZERO — EXECUTIVE RECONCILIATION SUMMARY"
    ws_sum["A1"].font = title_font
    ws_sum["A2"] = f"Generated: {report.get('generated_at', datetime.now().isoformat())} | Engine: Zero-Copy Multi-Source Pipeline"
    ws_sum["A2"].font = Font(name="Arial", size=9, italic=True, color="888888")

    kpis = [
        ("Match Rate", f"{summary.get('match_rate_pct', 0.0)}%"),
        ("Value Coverage", f"{summary.get('bank_value_pct', 0.0)}%"),
        ("Bank Feed Transactions", summary.get("total_bank_rows", 0)),
        ("Company Ledger Rows", summary.get("total_ledger_rows", 0)),
        ("Resolved Bank Transactions", summary.get("matched_bank_rows", 0)),
        ("Unresolved Exceptions", summary.get("total_exceptions", 0)),
        ("Total Bank Value (INR)", f"₹{_safe_float(summary.get('total_bank_value', 0)):,.2f}"),
        ("Matched Bank Value (INR)", f"₹{_safe_float(summary.get('matched_bank_value', 0)):,.2f}"),
        ("Human Review Required", summary.get("needs_human_review", 0)),
        ("Likely Bank Fees", summary.get("likely_bank_fees", 0)),
    ]

    ws_sum["A4"] = "EXECUTIVE KPI METRIC"
    ws_sum["B4"] = "VALUE"
    ws_sum["A4"].font = header_font
    ws_sum["B4"].font = header_font
    ws_sum["A4"].fill = header_fill
    ws_sum["B4"].fill = header_fill

    for i, (k, v) in enumerate(kpis, start=5):
        ws_sum[f"A{i}"] = k
        ws_sum[f"B{i}"] = v
        ws_sum[f"A{i}"].font = bold_font
        ws_sum[f"B{i}"].font = kpi_val_font
        ws_sum[f"A{i}"].border = thin_border
        ws_sum[f"B{i}"].border = thin_border

    # Tier Breakdown Table
    tier_counts = summary.get("tier_counts", {})
    ws_sum["D4"] = "MATCH STAGE / TIER"
    ws_sum["E4"] = "RESOLVED COUNT"
    ws_sum["D4"].font = header_font
    ws_sum["E4"].font = header_font
    ws_sum["D4"].fill = header_fill
    ws_sum["E4"].fill = header_fill

    tier_rows = [
        ("Stage 1 - Exact Ref & Amount", tier_counts.get("exact", 0)),
        ("Stage 2 - Fuzzy Match", tier_counts.get("fuzzy", 0)),
        ("Stage 3 - Split Payments (N-to-1)", tier_counts.get("split_payment", 0)),
        ("Stage 4 - Local LLM Reasoning", tier_counts.get("ai_escalated", 0)),
    ]
    for j, (tk, tv) in enumerate(tier_rows, start=5):
        ws_sum[f"D{j}"] = tk
        ws_sum[f"E{j}"] = tv
        ws_sum[f"D{j}"].font = regular_font
        ws_sum[f"E{j}"].font = bold_font
        ws_sum[f"D{j}"].border = thin_border
        ws_sum[f"E{j}"].border = thin_border

    ws_sum.column_dimensions["A"].width = 32
    ws_sum.column_dimensions["B"].width = 24
    ws_sum.column_dimensions["C"].width = 6
    ws_sum.column_dimensions["D"].width = 34
    ws_sum.column_dimensions["E"].width = 18

    # -------------------------------------------------------------
    # Sheet 2: Reconciled Matches
    # -------------------------------------------------------------
    ws_m = wb.create_sheet("Reconciled Matches")
    ws_m.views.sheetView[0].showGridLines = True
    match_headers = [
        "Tier", "Bank Amount (INR)", "Ledger Amount (INR)", "Delta (INR)",
        "Vendor / Counterparty", "Date", "Reference ID", "Audit Reason"
    ]
    ws_m.append(match_headers)
    for col_idx in range(1, len(match_headers) + 1):
        cell = ws_m.cell(row=1, column=col_idx)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center" if col_idx <= 4 else "left")

    for row_idx, m in enumerate(matches, start=2):
        b_amt = sum(b.get("amount", 0.0) for b in m.get("bank_entries", []))
        l_amt = m.get("ledger_entry", {}).get("amount", 0.0)
        delta = abs(b_amt - l_amt)
        vendor = m.get("ledger_entry", {}).get("vendor", "")
        date = m.get("ledger_entry", {}).get("date", "")
        ref = m.get("ledger_entry", {}).get("reference_id", "")
        reason = m.get("reason", "")
        tier = m.get("tier", "").replace("_", " ").upper()

        ws_m.append([tier, b_amt, l_amt, delta, vendor, date, ref, reason])
        for col_idx in range(1, 9):
            c = ws_m.cell(row=row_idx, column=col_idx)
            c.font = regular_font
            c.border = thin_border
            if col_idx in (2, 3, 4):
                c.number_format = "#,##0.00"

    for col in ws_m.columns:
        max_len = max(len(str(cell.value or '')) for cell in col)
        col_letter = get_column_letter(col[0].column)
        ws_m.column_dimensions[col_letter].width = max(max_len + 3, 12)

    # -------------------------------------------------------------
    # Sheet 3: Unresolved Exceptions
    # -------------------------------------------------------------
    ws_e = wb.create_sheet("Unresolved Exceptions")
    ws_e.views.sheetView[0].showGridLines = True
    exc_headers = ["Source", "Amount (INR)", "Date", "Reference ID", "Vendor", "Recommended Action", "Audit Diagnosis"]
    ws_e.append(exc_headers)
    for col_idx in range(1, len(exc_headers) + 1):
        cell = ws_e.cell(row=1, column=col_idx)
        cell.font = header_font
        cell.fill = header_fill

    for row_idx, exc in enumerate(exceptions, start=2):
        amt = _safe_float(exc.get("amount", 0))
        ws_e.append([
            exc.get("source", "").upper(),
            amt,
            exc.get("date", ""),
            exc.get("reference_id", ""),
            exc.get("vendor", ""),
            exc.get("recommended_action", "").replace("_", " ").upper(),
            exc.get("reason", "")
        ])
        for col_idx in range(1, 8):
            c = ws_e.cell(row=row_idx, column=col_idx)
            c.font = regular_font
            c.border = thin_border
            if col_idx == 2:
                c.number_format = "#,##0.00"

    for col in ws_e.columns:
        max_len = max(len(str(cell.value or '')) for cell in col)
        col_letter = get_column_letter(col[0].column)
        ws_e.column_dimensions[col_letter].width = max(max_len + 3, 12)

    # -------------------------------------------------------------
    # Sheet 4: Controller Worklist
    # -------------------------------------------------------------
    if action_items:
        ws_act = wb.create_sheet("Controller Worklist")
        ws_act.views.sheetView[0].showGridLines = True
        act_headers = ["Priority", "Vendor", "Reference ID", "Next Step Action", "Evidence", "Owner", "SLA", "Exposure (INR)"]
        ws_act.append(act_headers)
        for col_idx in range(1, len(act_headers) + 1):
            cell = ws_act.cell(row=1, column=col_idx)
            cell.font = header_font
            cell.fill = header_fill

        for row_idx, it in enumerate(action_items, start=2):
            ws_act.append([
                it.get("priority", "").upper(),
                it.get("vendor", ""),
                it.get("reference_id", ""),
                it.get("next_step", ""),
                it.get("evidence", ""),
                it.get("owner", ""),
                it.get("sla", ""),
                _safe_float(it.get("amount", 0))
            ])
            for col_idx in range(1, 9):
                c = ws_act.cell(row=row_idx, column=col_idx)
                c.font = regular_font
                c.border = thin_border
                if col_idx == 8:
                    c.number_format = "#,##0.00"

        for col in ws_act.columns:
            max_len = max(len(str(cell.value or '')) for cell in col)
            col_letter = get_column_letter(col[0].column)
            ws_act.column_dimensions[col_letter].width = max(max_len + 3, 12)

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def generate_pdf(report):
    """Generate executive PDF report via reportlab with sign-off blocks."""
    if reportlab is None:
        raise ImportError("reportlab is required for PDF export. Install with: pip install reportlab")
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=letter,
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=18,
        leading=22,
        textColor=colors.HexColor("#0f172a"),
        spaceAfter=4
    )
    sub_style = ParagraphStyle(
        'DocSub',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8.5,
        textColor=colors.HexColor("#64748b"),
        spaceAfter=14
    )
    section_style = ParagraphStyle(
        'SectionHeader',
        parent=styles['Heading2'],
        fontName='Helvetica-Bold',
        fontSize=12,
        leading=16,
        textColor=colors.HexColor("#0284c7"),
        spaceBefore=12,
        spaceAfter=6
    )
    cell_style = ParagraphStyle(
        'CellText',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8,
        leading=10,
        textColor=colors.HexColor("#1e293b")
    )
    cell_bold = ParagraphStyle(
        'CellBold',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=8,
        leading=10,
        textColor=colors.HexColor("#0f172a")
    )

    elements = []

    # Title & Header
    elements.append(Paragraph("LEDGERZERO — RECONCILIATION & AUDIT DOSSIER", title_style))
    gen_time = report.get("generated_at", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    elements.append(Paragraph(f"Autonomous Close Audit Report · Generated {gen_time} · Statutory Integrity Certified", sub_style))

    # Executive KPI Summary Table
    elements.append(Paragraph("1. Executive Summary & KPIs", section_style))
    summary = report.get("summary", {})
    kpi_data = [
        [
            Paragraph("Match Rate", cell_bold),
            Paragraph(f"<b>{summary.get('match_rate_pct', 0)}%</b>", cell_bold),
            Paragraph("Value Coverage", cell_bold),
            Paragraph(f"<b>{summary.get('bank_value_pct', 0)}%</b>", cell_bold)
        ],
        [
            Paragraph("Bank Transactions", cell_style),
            Paragraph(str(summary.get("total_bank_rows", 0)), cell_style),
            Paragraph("Company Ledger Rows", cell_style),
            Paragraph(str(summary.get("total_ledger_rows", 0)), cell_style)
        ],
        [
            Paragraph("Resolved Matches", cell_style),
            Paragraph(str(summary.get("matched_bank_rows", 0)), cell_style),
            Paragraph("Exceptions Remaining", cell_style),
            Paragraph(str(summary.get("total_exceptions", 0)), cell_style)
        ],
        [
            Paragraph("Total Bank Value", cell_style),
            Paragraph(f"INR {_safe_float(summary.get('total_bank_value', 0)):,.2f}", cell_style),
            Paragraph("Matched Bank Value", cell_style),
            Paragraph(f"INR {_safe_float(summary.get('matched_bank_value', 0)):,.2f}", cell_style)
        ],
    ]
    t_kpi = Table(kpi_data, colWidths=[130, 135, 130, 145])
    t_kpi.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ('PADDING', (0, 0), (-1, -1), 5),
    ]))
    elements.append(t_kpi)
    elements.append(Spacer(1, 10))

    # Reconciled Matches Sample Table (Top 12)
    elements.append(Paragraph("2. Reconciled Matches (Sample / Summary)", section_style))
    matches = report.get("matches", [])
    m_data = [[
        Paragraph("<b>Tier</b>", cell_bold),
        Paragraph("<b>Vendor</b>", cell_bold),
        Paragraph("<b>Ref ID</b>", cell_bold),
        Paragraph("<b>Date</b>", cell_bold),
        Paragraph("<b>Bank Amt (INR)</b>", cell_bold),
        Paragraph("<b>Ledger Amt (INR)</b>", cell_bold),
        Paragraph("<b>Δ (INR)</b>", cell_bold)
    ]]

    for m in matches[:14]:
        b_amt = sum(b.get("amount", 0.0) for b in m.get("bank_entries", []))
        l_amt = m.get("ledger_entry", {}).get("amount", 0.0)
        delta = abs(b_amt - l_amt)
        m_data.append([
            Paragraph(m.get("tier", "").replace("_", " ").upper(), cell_style),
            Paragraph(m.get("ledger_entry", {}).get("vendor", "")[:18], cell_style),
            Paragraph(m.get("ledger_entry", {}).get("reference_id", ""), cell_style),
            Paragraph(m.get("ledger_entry", {}).get("date", ""), cell_style),
            Paragraph(f"{b_amt:,.2f}", cell_style),
            Paragraph(f"{l_amt:,.2f}", cell_style),
            Paragraph(f"{delta:.2f}", cell_style)
        ])

    t_matches = Table(m_data, colWidths=[70, 110, 80, 65, 75, 75, 65])
    t_matches.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#0f172a")),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
        ('PADDING', (0, 0), (-1, -1), 4),
    ]))
    elements.append(t_matches)
    elements.append(Spacer(1, 10))

    # Unresolved Exceptions Table
    exceptions = report.get("exceptions", [])
    if exceptions:
        elements.append(Paragraph(f"3. Unresolved Exceptions Audit Queue ({len(exceptions)} Items)", section_style))
        exc_data = [[
            Paragraph("<b>Source</b>", cell_bold),
            Paragraph("<b>Vendor</b>", cell_bold),
            Paragraph("<b>Ref ID</b>", cell_bold),
            Paragraph("<b>Date</b>", cell_bold),
            Paragraph("<b>Amount (INR)</b>", cell_bold),
            Paragraph("<b>Action Required</b>", cell_bold)
        ]]
        for exc in exceptions[:10]:
            amt = _safe_float(exc.get("amount", 0))
            exc_data.append([
                Paragraph(exc.get("source", "").upper(), cell_style),
                Paragraph(exc.get("vendor", "")[:20], cell_style),
                Paragraph(exc.get("reference_id", "") or "—", cell_style),
                Paragraph(exc.get("date", ""), cell_style),
                Paragraph(f"{amt:,.2f}", cell_style),
                Paragraph(exc.get("recommended_action", "").replace("_", " ").upper(), cell_style)
            ])
        t_exc = Table(exc_data, colWidths=[70, 125, 85, 65, 85, 110])
        t_exc.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#e11d48")),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#fecdd3")),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor("#fff1f2")]),
            ('PADDING', (0, 0), (-1, -1), 4),
        ]))
        elements.append(t_exc)
        elements.append(Spacer(1, 12))

    # Sign-Off & Certification Block
    elements.append(KeepTogether([
        Paragraph("4. Sign-Off & Statutory Controller Certification", section_style),
        Table([
            [
                Paragraph("<b>Prepared By:</b> Autonomous Treasury Engine<br/><b>Verified By:</b> LedgerZero v2.4", cell_style),
                Paragraph("<b>Reviewed &amp; Approved By:</b> ___________________________<br/><b>Designation:</b> Chief Financial Officer / Financial Controller", cell_style),
                Paragraph("<b>Audit Date:</b> ___________________________<br/><b>Status:</b> [ ] Approved for Close  [ ] Escalated", cell_style)
            ]
        ], colWidths=[180, 190, 170], style=[
            ('BOX', (0, 0), (-1, -1), 1, colors.HexColor("#94a3b8")),
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
            ('PADDING', (0, 0), (-1, -1), 8)
        ])
    ]))

    doc.build(elements)
    return buf.getvalue()


def generate_docx(report):
    """Generate Word (.docx) document."""
    if docx is None:
        raise ImportError("python-docx is required for Word export. Install with: pip install python-docx")
    doc = docx.Document()

    # Title
    title = doc.add_heading("LedgerZero — Financial Close Report", level=0)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER

    summary = report.get("summary", {})
    gen_time = report.get("generated_at", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    p_meta = doc.add_paragraph()
    p_meta.add_run(f"Generated: {gen_time} | Status: Certified Reconciliation Dossier\n").italic = True
    p_meta.add_run(f"Match Rate: {summary.get('match_rate_pct', 0)}% | Value Coverage: {summary.get('bank_value_pct', 0)}%").bold = True

    # Executive Summary Table
    doc.add_heading("1. Executive Summary & KPIs", level=1)
    kpis = [
        ("Total Bank Feed Transactions", str(summary.get("total_bank_rows", 0))),
        ("Total Company Ledger Rows", str(summary.get("total_ledger_rows", 0))),
        ("Resolved Bank Matches", str(summary.get("matched_bank_rows", 0))),
        ("Unresolved Exceptions", str(summary.get("total_exceptions", 0))),
        ("Total Bank Value (INR)", f"₹{_safe_float(summary.get('total_bank_value', 0)):,.2f}"),
        ("Matched Bank Value (INR)", f"₹{_safe_float(summary.get('matched_bank_value', 0)):,.2f}"),
        ("Match Rate (Count)", f"{summary.get('match_rate_pct', 0)}%"),
        ("Value Match Rate", f"{summary.get('bank_value_pct', 0)}%")
    ]
    t_kpi = doc.add_table(rows=1, cols=2)
    t_kpi.alignment = WD_TABLE_ALIGNMENT.CENTER
    hdr_cells = t_kpi.rows[0].cells
    hdr_cells[0].text = "Financial Metric"
    hdr_cells[1].text = "Value"
    for k, v in kpis:
        row_cells = t_kpi.add_row().cells
        row_cells[0].text = k
        row_cells[1].text = v

    # Reconciled Matches Table
    matches = report.get("matches", [])
    doc.add_heading(f"2. Reconciled Matches ({len(matches)} Records)", level=1)
    t_match = doc.add_table(rows=1, cols=6)
    m_hdrs = t_match.rows[0].cells
    for i, h in enumerate(["Tier", "Vendor", "Ref ID", "Date", "Bank Amt", "Delta"]):
        m_hdrs[i].text = h

    for m in matches[:50]:
        b_amt = sum(b.get("amount", 0.0) for b in m.get("bank_entries", []))
        l_amt = m.get("ledger_entry", {}).get("amount", 0.0)
        delta = abs(b_amt - l_amt)
        rc = t_match.add_row().cells
        rc[0].text = m.get("tier", "").replace("_", " ").upper()
        rc[1].text = m.get("ledger_entry", {}).get("vendor", "")
        rc[2].text = m.get("ledger_entry", {}).get("reference_id", "")
        rc[3].text = m.get("ledger_entry", {}).get("date", "")
        rc[4].text = f"₹{b_amt:,.2f}"
        rc[5].text = f"₹{delta:.2f}"

    # Exceptions Table
    exceptions = report.get("exceptions", [])
    if exceptions:
        doc.add_heading(f"3. Unresolved Exceptions ({len(exceptions)} Items)", level=1)
        t_exc = doc.add_table(rows=1, cols=6)
        e_hdrs = t_exc.rows[0].cells
        for i, h in enumerate(["Source", "Vendor", "Ref ID", "Date", "Amount", "Recommended Action"]):
            e_hdrs[i].text = h
        for exc in exceptions:
            rc = t_exc.add_row().cells
            rc[0].text = exc.get("source", "").upper()
            rc[1].text = exc.get("vendor", "")
            rc[2].text = exc.get("reference_id", "") or "—"
            rc[3].text = exc.get("date", "")
            rc[4].text = f"₹{_safe_float(exc.get('amount', 0)):,.2f}"
            rc[5].text = exc.get("recommended_action", "").replace("_", " ").upper()

    # Sign-off
    doc.add_heading("4. Controller Sign-off", level=1)
    p_sign = doc.add_paragraph()
    p_sign.add_run("Reviewed & Approved By: _________________________________\n")
    p_sign.add_run("Title: Chief Financial Officer / Lead Controller\n")
    p_sign.add_run("Date: ________________________\n")

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def generate_xml(report):
    """Generate structured XML for ERP ingestion."""
    root = ET.Element("ReconciliationReport", {
        "version": "2.4",
        "generated_at": report.get("generated_at", datetime.now().isoformat())
    })

    # Summary node
    summary = report.get("summary", {})
    sum_el = ET.SubElement(root, "Summary")
    for k, v in summary.items():
        if isinstance(v, dict):
            sub_tier = ET.SubElement(sum_el, k)
            for tk, tv in v.items():
                ET.SubElement(sub_tier, tk).text = str(tv)
        else:
            ET.SubElement(sum_el, k).text = str(v)

    # Matches node
    matches_el = ET.SubElement(root, "Matches")
    for m in report.get("matches", []):
        m_el = ET.SubElement(matches_el, "Match", {"tier": m.get("tier", "")})
        b_amt = sum(b.get("amount", 0.0) for b in m.get("bank_entries", []))
        l_amt = m.get("ledger_entry", {}).get("amount", 0.0)
        ET.SubElement(m_el, "BankAmount").text = f"{b_amt:.2f}"
        ET.SubElement(m_el, "LedgerAmount").text = f"{l_amt:.2f}"
        ET.SubElement(m_el, "Delta").text = f"{abs(b_amt - l_amt):.2f}"
        ET.SubElement(m_el, "Vendor").text = m.get("ledger_entry", {}).get("vendor", "")
        ET.SubElement(m_el, "Date").text = m.get("ledger_entry", {}).get("date", "")
        ET.SubElement(m_el, "ReferenceID").text = m.get("ledger_entry", {}).get("reference_id", "")
        ET.SubElement(m_el, "AuditReason").text = m.get("reason", "")

    # Exceptions node
    exc_el = ET.SubElement(root, "Exceptions")
    for e in report.get("exceptions", []):
        e_el = ET.SubElement(exc_el, "Exception", {"source": e.get("source", "")})
        ET.SubElement(e_el, "Amount").text = f"{_safe_float(e.get('amount', 0)):.2f}"
        ET.SubElement(e_el, "Date").text = e.get("date", "")
        ET.SubElement(e_el, "Vendor").text = e.get("vendor", "")
        ET.SubElement(e_el, "ReferenceID").text = e.get("reference_id", "")
        ET.SubElement(e_el, "RecommendedAction").text = e.get("recommended_action", "")
        ET.SubElement(e_el, "Reason").text = e.get("reason", "")

    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def generate_csv_matches(report):
    """Generate CSV for Reconciled Matches."""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Tier", "Bank Amount", "Ledger Amount", "Delta", "Vendor", "Date", "Reference ID", "Audit Reason"])
    for m in report.get("matches", []):
        b_amt = sum(b.get("amount", 0.0) for b in m.get("bank_entries", []))
        l_amt = m.get("ledger_entry", {}).get("amount", 0.0)
        writer.writerow([
            m.get("tier", ""),
            f"{b_amt:.2f}",
            f"{l_amt:.2f}",
            f"{abs(b_amt - l_amt):.2f}",
            m.get("ledger_entry", {}).get("vendor", ""),
            m.get("ledger_entry", {}).get("date", ""),
            m.get("ledger_entry", {}).get("reference_id", ""),
            m.get("reason", "")
        ])
    return output.getvalue().encode("utf-8")


def generate_csv_exceptions(report):
    """Generate CSV for Unresolved Exceptions."""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Source", "Amount", "Date", "Reference ID", "Vendor", "Recommended Action", "Reason"])
    for e in report.get("exceptions", []):
        writer.writerow([
            e.get("source", ""),
            f"{_safe_float(e.get('amount', 0)):.2f}",
            e.get("date", ""),
            e.get("reference_id", ""),
            e.get("vendor", ""),
            e.get("recommended_action", ""),
            e.get("reason", "")
        ])
    return output.getvalue().encode("utf-8")


def generate_tsv(report):
    """Generate TSV for database bulk copy."""
    output = io.StringIO()
    writer = csv.writer(output, delimiter='\t')
    writer.writerow(["Type", "Tier_or_Source", "Amount", "Reference_ID", "Vendor", "Date", "Notes"])
    for m in report.get("matches", []):
        b_amt = sum(b.get("amount", 0.0) for b in m.get("bank_entries", []))
        writer.writerow([
            "MATCH",
            m.get("tier", ""),
            f"{b_amt:.2f}",
            m.get("ledger_entry", {}).get("reference_id", ""),
            m.get("ledger_entry", {}).get("vendor", ""),
            m.get("ledger_entry", {}).get("date", ""),
            m.get("reason", "")
        ])
    for e in report.get("exceptions", []):
        writer.writerow([
            "EXCEPTION",
            e.get("source", ""),
            f"{_safe_float(e.get('amount', 0)):.2f}",
            e.get("reference_id", ""),
            e.get("vendor", ""),
            e.get("date", ""),
            e.get("reason", "")
        ])
    return output.getvalue().encode("utf-8")


def generate_html_report(report):
    """Generate standalone printable HTML report with printable styling."""
    summary = report.get("summary", {})
    matches = report.get("matches", [])
    exceptions = report.get("exceptions", [])

    m_rows = "".join([f"""
        <tr>
            <td><span class="badge badge-{m.get('tier')}">{m.get('tier')}</span></td>
            <td>₹{sum(b.get('amount', 0.0) for b in m.get('bank_entries', [])):,.2f}</td>
            <td>₹{m.get('ledger_entry', {}).get('amount', 0.0):,.2f}</td>
            <td>{m.get('ledger_entry', {}).get('vendor')}</td>
            <td><code>{m.get('ledger_entry', {}).get('reference_id')}</code></td>
            <td>{m.get('ledger_entry', {}).get('date')}</td>
            <td>{m.get('reason')}</td>
        </tr>
    """ for m in matches])

    e_rows = "".join([f"""
        <tr>
            <td><span class="badge badge-exc">{e.get('source')}</span></td>
            <td>₹{_safe_float(e.get('amount', 0)):,.2f}</td>
            <td>{e.get('vendor')}</td>
            <td><code>{e.get('reference_id') or '—'}</code></td>
            <td>{e.get('date')}</td>
            <td><strong>{e.get('recommended_action', '').replace('_', ' ')}</strong>: {e.get('reason')}</td>
        </tr>
    """ for e in exceptions])

    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Reconciliation Audit Report - {report.get('generated_at', '')}</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; margin: 40px; color: #1e293b; line-height: 1.5; }}
  h1 {{ color: #0f172a; margin-bottom: 4px; }}
  .meta {{ color: #64748b; font-size: 0.9rem; margin-bottom: 24px; }}
  .kpi-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; margin-bottom: 28px; }}
  .kpi-card {{ background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 14px; }}
  .kpi-val {{ font-size: 1.6rem; font-weight: 800; color: #0f172a; }}
  .kpi-lbl {{ font-size: 0.75rem; text-transform: uppercase; color: #64748b; font-weight: 600; margin-top: 4px; }}
  table {{ width: 100%; border-collapse: collapse; margin-bottom: 28px; font-size: 0.85rem; }}
  th, td {{ border: 1px solid #cbd5e1; padding: 7px 10px; text-align: left; }}
  th {{ background: #0f172a; color: #fff; font-size: 0.75rem; text-transform: uppercase; }}
  tr:nth-child(even) {{ background: #f8fafc; }}
  .badge {{ display: inline-block; padding: 2px 7px; border-radius: 4px; font-size: 0.7rem; font-weight: 700; text-transform: uppercase; }}
  .badge-exact {{ background: #dcfce7; color: #15803d; }}
  .badge-fuzzy {{ background: #e0f2fe; color: #0369a1; }}
  .badge-split_payment {{ background: #f3e8ff; color: #7e22ce; }}
  .badge-exc {{ background: #ffe4e6; color: #be123c; }}
  @media print {{
    body {{ margin: 15mm; font-size: 9pt; }}
    .no-print {{ display: none; }}
  }}
</style>
</head>
<body>
  <h1>LedgerZero — Statutory Close Report</h1>
  <div class="meta">Generated: {report.get('generated_at', datetime.now().isoformat())} | Certified Reconciliation Close Dossier</div>

  <div class="kpi-grid">
    <div class="kpi-card"><div class="kpi-val">{summary.get('match_rate_pct', 0)}%</div><div class="kpi-lbl">Match Rate</div></div>
    <div class="kpi-card"><div class="kpi-val">{summary.get('bank_value_pct', 0)}%</div><div class="kpi-lbl">Value Coverage</div></div>
    <div class="kpi-card"><div class="kpi-val">{summary.get('matched_bank_rows', 0)} of {summary.get('total_bank_rows', 0)}</div><div class="kpi-lbl">Bank Rows Resolved</div></div>
    <div class="kpi-card"><div class="kpi-val">{summary.get('total_exceptions', 0)}</div><div class="kpi-lbl">Exceptions Remaining</div></div>
  </div>

  <h2>1. Reconciled Transactions ({len(matches)} matches)</h2>
  <table>
    <thead><tr><th>Tier</th><th>Bank Amt</th><th>Ledger Amt</th><th>Vendor</th><th>Ref ID</th><th>Date</th><th>Audit Reason</th></tr></thead>
    <tbody>{m_rows}</tbody>
  </table>

  <h2>2. Unresolved Exceptions ({len(exceptions)} items)</h2>
  <table>
    <thead><tr><th>Source</th><th>Amount</th><th>Vendor</th><th>Ref ID</th><th>Date</th><th>Audit Diagnosis & Action</th></tr></thead>
    <tbody>{e_rows}</tbody>
  </table>
</body>
</html>"""
    return html.encode("utf-8")


def generate_zip_all(report):
    """Bundle all available formats into a single complete ZIP archive."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        if openpyxl is not None:
            zf.writestr("reconciliation_report.xlsx", generate_xlsx(report))
        if reportlab is not None:
            zf.writestr("reconciliation_report.pdf", generate_pdf(report))
        if docx is not None:
            zf.writestr("reconciliation_report.docx", generate_docx(report))
        zf.writestr("reconciled_matches.csv", generate_csv_matches(report))
        zf.writestr("unresolved_exceptions.csv", generate_csv_exceptions(report))
        zf.writestr("reconciliation_report.json", json.dumps(report, indent=2).encode("utf-8"))
        zf.writestr("reconciliation_report.xml", generate_xml(report))
        zf.writestr("reconciliation_data.tsv", generate_tsv(report))
        zf.writestr("reconciliation_report.html", generate_html_report(report))
    return buf.getvalue()
