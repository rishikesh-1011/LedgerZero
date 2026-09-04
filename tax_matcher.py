"""
tax_matcher.py

Tax-Line Matcher & Statutory Withholding Engine for LedgerZero (Track 04: AI Finance Controller).

Reconciles invoice line items with tax withholdings (TDS) and sales tax (GST):
  - TDS Rules: 1% (194C), 2% (194C/J), 10% (194J/I), 0.1% (194Q)
  - GST Rules: 5%, 12%, 18%, 28%
  - Net-of-tax matching: Bank Net Payment = Ledger Gross Invoice * (1 - TDS%)
  - GST Component matching: Bank Debit = Ledger Base + GST%
  - Discrepancy detection: flags wrong withholding rates, rounding leaks, and unfiled credits
  - GPU LLM reasoning: provides natural language tax audit explanations
"""

import json
import os
from datetime import datetime

DEFAULT_REPORT_PATH = "reconciliation_report.json"

TDS_RATES = [
    {"rate": 0.10, "section": "194J/194I", "label": "10% Professional/Rent TDS"},
    {"rate": 0.02, "section": "194C/194J", "label": "2% Technical/Subcontract TDS"},
    {"rate": 0.01, "section": "194C",      "label": "1% Contractor TDS"},
    {"rate": 0.001, "section": "194Q",     "label": "0.1% Goods Purchase TDS"},
]

GST_RATES = [
    {"rate": 0.18, "label": "18% GST (Standard Services/Software)"},
    {"rate": 0.12, "label": "12% GST (Processed Goods/Logistics)"},
    {"rate": 0.05, "label": "5% GST (Essential Services/Transport)"},
    {"rate": 0.28, "label": "28% GST (Luxury/Automotive)"},
]


def run_tax_line_reconciliation(report=None, use_llm=True):
    """
    Run tax-line matching on matched pairs and exceptions to identify TDS deductions,
    GST components, and tax withholding variances.

    Returns:
        dict with:
          - summary: { total_invoices_audited, tds_detected_count, total_tds_withheld, gst_detected_count, total_gst_component, variance_count }
          - tax_lines: list of audited tax entries
          - audit_commentary: str (LLM generated)
    """
    if report is None and os.path.exists(DEFAULT_REPORT_PATH):
        with open(DEFAULT_REPORT_PATH, "r", encoding="utf-8") as f:
            report = json.load(f)

    matches = report.get("matches", []) if report else []
    exceptions = report.get("exceptions", []) if report else []

    tax_lines = []
    total_tds_withheld = 0.0
    total_gst_amount = 0.0
    tds_count = 0
    gst_count = 0
    variance_count = 0

    # 1. Audit matched entries for tax line structure
    for m in matches:
        ledger_amt = m["ledger_entry"]["amount"]
        bank_amt = sum(b["amount"] for b in m["bank_entries"])
        vendor = m["ledger_entry"]["vendor"]
        ref = m["ledger_entry"]["reference_id"]
        date = m["ledger_entry"]["date"]

        # Check for standard TDS deductions (Bank Net < Ledger Gross)
        matched_tax = None
        for tds in TDS_RATES:
            expected_net = ledger_amt * (1.0 - tds["rate"])
            if abs(bank_amt - expected_net) <= 5.00:
                tds_amt = ledger_amt * tds["rate"]
                total_tds_withheld += tds_amt
                tds_count += 1
                matched_tax = {
                    "type": "TDS_WITHHOLDING",
                    "reference_id": ref,
                    "vendor": vendor,
                    "date": date,
                    "gross_invoice_amount": round(ledger_amt, 2),
                    "bank_net_payment": round(bank_amt, 2),
                    "tax_rate_applied": f"{tds['rate']*100:.1f}%",
                    "tax_section": tds["section"],
                    "tax_withheld": round(tds_amt, 2),
                    "compliance_status": "COMPLIANT",
                    "notes": f"Net bank payment matches gross invoice after {tds['label']}"
                }
                break

        # Check for GST line item addition (Bank Net = Ledger Base + GST)
        if not matched_tax:
            for gst in GST_RATES:
                expected_gross = ledger_amt * (1.0 + gst["rate"])
                if abs(bank_amt - expected_gross) <= 5.00:
                    gst_amt = ledger_amt * gst["rate"]
                    total_gst_amount += gst_amt
                    gst_count += 1
                    matched_tax = {
                        "type": "GST_LINE_COMPONENT",
                        "reference_id": ref,
                        "vendor": vendor,
                        "date": date,
                        "gross_invoice_amount": round(expected_gross, 2),
                        "bank_net_payment": round(bank_amt, 2),
                        "tax_rate_applied": f"{gst['rate']*100:.0f}%",
                        "tax_section": "GST-ITC",
                        "tax_withheld": round(gst_amt, 2),
                        "compliance_status": "COMPLIANT",
                        "notes": f"Gross amount includes {gst['label']}"
                    }
                    break

        if not matched_tax:
            # Check for potential TDS / Tax leakage variance
            delta = abs(bank_amt - ledger_amt)
            if delta > 10.0 and delta < (ledger_amt * 0.35):
                variance_count += 1
                est_rate = delta / ledger_amt if ledger_amt > 0 else 0
                matched_tax = {
                    "type": "TAX_VARIANCE_DISCREPANCY",
                    "reference_id": ref,
                    "vendor": vendor,
                    "date": date,
                    "gross_invoice_amount": round(ledger_amt, 2),
                    "bank_net_payment": round(bank_amt, 2),
                    "tax_rate_applied": f"~{est_rate*100:.1f}% (Unusual)",
                    "tax_section": "AUDIT_REQUIRED",
                    "tax_withheld": round(delta, 2),
                    "compliance_status": "REQUIRES_REVIEW",
                    "notes": f"Payment variance of Rs.{delta:.2f} does not match standard 1%, 2%, or 10% TDS brackets."
                }
            else:
                matched_tax = {
                    "type": "EXACT_INVOICE_MATCH",
                    "reference_id": ref,
                    "vendor": vendor,
                    "date": date,
                    "gross_invoice_amount": round(ledger_amt, 2),
                    "bank_net_payment": round(bank_amt, 2),
                    "tax_rate_applied": "0.0% (Gross Settle)",
                    "tax_section": "N/A",
                    "tax_withheld": 0.0,
                    "compliance_status": "COMPLIANT",
                    "notes": "Full gross settlement without withholding deduction."
                }

        tax_lines.append(matched_tax)

    summary = {
        "total_invoices_audited": len(tax_lines),
        "tds_deductions_detected": tds_count,
        "total_tds_withheld": round(total_tds_withheld, 2),
        "gst_components_detected": gst_count,
        "total_gst_components": round(total_gst_amount, 2),
        "tax_discrepancies": variance_count,
    }

    # Generate LLM commentary for statutory compliance
    commentary = _generate_tax_llm_commentary(summary, tax_lines, use_llm)

    return {
        "summary": summary,
        "tax_lines": tax_lines,
        "audit_commentary": commentary,
    }


def _generate_tax_llm_commentary(summary, tax_lines, use_llm=True):
    """Generate tax compliance brief using local Qwen2.5-3B LLM on GPU."""
    audited = summary["total_invoices_audited"]
    tds_count = summary["tds_deductions_detected"]
    tds_amt = summary["total_tds_withheld"]
    disc = summary["tax_discrepancies"]

    default_commentary = (
        f"### Statutory Tax & Withholding Audit Brief\n\n"
        f"- **Total Invoices Audited:** {audited}\n"
        f"- **TDS Withholdings Identified:** {tds_count} (Total Tax Withheld: Rs. {tds_amt:,.2f})\n"
        f"- **Tax Variances / Unaligned Deductions:** {disc}\n"
        f"- **Compliance Assessment:** {'[COMPLIANT] Withholdings align with standard statutory brackets.' if disc == 0 else '[ACTION REQUIRED] ' + str(disc) + ' transaction(s) have non-standard withholding deltas.'}\n\n"
        f"**Next Steps:**\n"
        f"- Export TDS deduction ledger for Form 26Q quarterly filing.\n"
        f"- Cross-reference vendor GSTINs on the GST portal for input tax credit eligibility."
    )

    if not use_llm or os.environ.get("USE_LLM", "1") == "0":
        return default_commentary

    try:
        from llm_resolver import _load_model
        pipe = _load_model()

        system_prompt = """You are a Corporate Tax & Statutory Audit Controller.
Analyze the tax-line reconciliation summary (TDS withholdings, GST components, and rate discrepancies).
Write a professional, concise executive tax compliance summary with bullet points."""

        user_prompt = f"""TAX RECONCILIATION DATA:
- Invoices Audited: {audited}
- Identified TDS Deductions: {tds_count} entries (Rs. {tds_amt:,.2f} total)
- Tax Rate Discrepancies: {disc}
- Common Withholding Sections: Sec 194C (1%, 2%), Sec 194J (10%), GST-ITC

Write the tax compliance and statutory filing recommendations:"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        output = pipe(
            messages,
            max_new_tokens=400,
            do_sample=False,
            return_full_text=False
        )
        raw_text = output[0]["generated_text"]
        if isinstance(raw_text, list):
            raw_text = raw_text[-1].get("content", str(raw_text[-1]))

        return raw_text.strip()

    except Exception:
        return default_commentary


if __name__ == "__main__":
    t_res = run_tax_line_reconciliation(use_llm=False)
    print("Tax Audit Summary:", t_res["summary"])
    print("Total Tax Lines:", len(t_res["tax_lines"]))
    print("Commentary:\n" + t_res["audit_commentary"])
