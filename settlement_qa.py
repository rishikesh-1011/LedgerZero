"""
settlement_qa.py

Settlement Q&A Agent powered by local LLM (Qwen2.5-3B-Instruct) on GPU.

Analyzes the full reconciliation state and answers complex questions about:
  - Specific transaction IDs (reasons for matching or being flagged as exceptions)
  - Vendor settlement behavior and timing delays (T+1 to T+3 drift)
  - Bank fees and unexpected charges
  - Root-cause analysis of exceptions and variances
"""

import json
import os
import re
import sys
from datetime import datetime

DEFAULT_REPORT_PATH = "reconciliation_report.json"


def load_report(report_path=None):
    """Load reconciliation report from disk."""
    path = report_path or DEFAULT_REPORT_PATH
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return None


def _build_qa_context(report, question):
    """Build a compact, focused context payload for the LLM based on the user's question."""
    summary = report.get("summary", {})
    matches = report.get("matches", [])
    exceptions = report.get("exceptions", [])

    q = question.lower()

    # Extract any mentioned reference ID
    ref_match = re.search(r"\b(TXN\d+|FEE\d+|REF\d+|INV\d+|[A-Z]{2,4}\d{4,})\b", question, re.IGNORECASE)
    targeted_ref = ref_match.group(1).upper() if ref_match else None

    # Filter relevant matches
    relevant_matches = []
    for m in matches:
        ref = m["ledger_entry"].get("reference_id", "")
        vendor = m["ledger_entry"].get("vendor", "")
        bank_refs = [b.get("reference_id", "") for b in m["bank_entries"]]

        if targeted_ref and (targeted_ref == ref.upper() or any(targeted_ref == br.upper() for br in bank_refs)):
            relevant_matches.append(m)
        elif not targeted_ref and (vendor.lower() in q or len(relevant_matches) < 8):
            relevant_matches.append(m)

    # Filter relevant exceptions
    relevant_exceptions = []
    for e in exceptions:
        ref = e.get("reference_id", "")
        vendor = e.get("vendor", "")
        if targeted_ref and (targeted_ref == ref.upper()):
            relevant_exceptions.append(e)
        elif not targeted_ref and (vendor.lower() in q or "fee" in q or len(relevant_exceptions) < 10):
            relevant_exceptions.append(e)

    context = {
        "summary": summary,
        "targeted_reference": targeted_ref,
        "relevant_matches": relevant_matches,
        "relevant_exceptions": relevant_exceptions,
    }
    return context


def ask_settlement_qa(question, report=None, use_llm=True):
    """
    Query the Settlement Q&A Agent using the local GPU LLM (Qwen2.5-3B-Instruct).
    """
    if report is None:
        report = load_report()

    if not report:
        return {
            "answer": "No reconciliation report is loaded. Please run reconciliation or upload statements first.",
            "citations": [],
            "confidence": 0,
        }

    context = _build_qa_context(report, question)
    context_str = json.dumps(context, indent=2)

    # If LLM is disabled or unavailable, use deterministic fallback
    if not use_llm or os.environ.get("USE_LLM", "1") == "0":
        return _deterministic_fallback(question, report, context)

    try:
        from llm_resolver import _load_model
        pipe = _load_model()

        system_prompt = """You are an AI Financial Controller & Settlement Specialist for Razorpay Track 04.
You will be provided with reconciliation results (matches, variances, settlement dates, fees, and exceptions).

Your task: Provide a clear, precise, and authoritative answer to the user's question.

RULES:
1. Always base your response strictly on the provided context facts.
2. Quote exact transaction reference IDs, amounts in INR (Rs. / ₹), dates, vendors, and match tiers.
3. If explaining an exception, clarify why it could not be automatically matched and recommend the next action.
4. Keep the answer structured, concise, and professional using markdown bullet points.
"""

        user_prompt = f"""RECONCILIATION CONTEXT:
{context_str}

USER QUESTION:
{question}

Provide your financial explanation:"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        output = pipe(
            messages,
            max_new_tokens=512,
            do_sample=False,
            return_full_text=False
        )
        raw_text = output[0]["generated_text"]
        if isinstance(raw_text, list):
            raw_text = raw_text[-1].get("content", str(raw_text[-1]))

        citations = []
        if context.get("targeted_reference"):
            citations.append(f"Reference: {context['targeted_reference']}")
        for m in context["relevant_matches"][:3]:
            citations.append(f"Match [{m['tier']}]: Rs.{m['ledger_entry']['amount']} ({m['ledger_entry']['vendor']})")
        for e in context["relevant_exceptions"][:3]:
            citations.append(f"Exception [{e['source']}]: Rs.{e['amount']} ({e['vendor']})")

        return {
            "answer": raw_text.strip(),
            "citations": citations,
            "confidence": 95,
        }

    except Exception as e:
        return _deterministic_fallback(question, report, context)


def _deterministic_fallback(question, report, context):
    """Fallback when LLM is unavailable."""
    targeted_ref = context.get("targeted_reference")
    summary = report.get("summary", {})

    if targeted_ref:
        for m in context["relevant_matches"]:
            b_amt = sum(b["amount"] for b in m["bank_entries"])
            return {
                "answer": (
                    f"**Transaction {targeted_ref}** is matched under tier **`{m['tier']}`**.\n\n"
                    f"- **Vendor:** {m['ledger_entry']['vendor']}\n"
                    f"- **Ledger:** Rs. {m['ledger_entry']['amount']:,.2f} on {m['ledger_entry']['date']}\n"
                    f"- **Bank:** Rs. {b_amt:,.2f}\n"
                    f"- **Reason:** {m['reason']}"
                ),
                "citations": [f"Match [{m['tier']}]: Rs. {m['ledger_entry']['amount']} ({m['ledger_entry']['vendor']})"],
                "confidence": 100,
            }

        for e in context["relevant_exceptions"]:
            return {
                "answer": (
                    f"**Transaction {targeted_ref}** is an unresolved **{e['source'].replace('_', ' ')}** exception.\n\n"
                    f"- **Amount:** Rs. {e['amount']:,.2f}\n"
                    f"- **Date:** {e['date']}\n"
                    f"- **Vendor:** {e['vendor']}\n"
                    f"- **Action:** {e.get('recommended_action', 'investigate_orphan')}\n"
                    f"- **Reason:** {e.get('reason', 'No matching counterpart found')}"
                ),
                "citations": [f"Exception: Rs. {e['amount']} ({e['vendor']})"],
                "confidence": 100,
            }

    m_rate = summary.get("match_rate_pct", 0)
    return {
        "answer": (
            f"### Executive Settlement Summary\n\n"
            f"- **Overall Match Rate:** **{m_rate}%** ({summary.get('matched_bank_rows', 0)} of {summary.get('total_bank_rows', 0)} bank rows matched)\n"
            f"- **Value Reconciled:** **Rs. {summary.get('matched_bank_value', 0):,.2f}**\n"
            f"- **Exceptions:** **{summary.get('total_exceptions', 0)}** total ({summary.get('needs_human_review', 0)} requiring review)\n\n"
            f"Ask about any specific transaction ID (e.g., `TXN100018`), vendor, or bank fees."
        ),
        "citations": [f"Summary: {m_rate}% match rate"],
        "confidence": 90,
    }


if __name__ == "__main__":
    rep = load_report()
    if rep:
        res = ask_settlement_qa("What happened to TXN100018?", rep, use_llm=False)
        print("Q&A Answer:\n" + res["answer"])
