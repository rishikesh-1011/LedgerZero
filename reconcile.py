"""
reconcile.py

A staged, explainable reconciliation engine for Track 04 (AI Finance Controller).

Design principle: solve everything you can with cheap, deterministic,
100%-explainable rules FIRST. Only escalate the genuinely ambiguous leftovers
to a smarter (optionally LLM-backed) resolver. This keeps the system fast,
auditable, and honest about what it isn't sure of.

Pipeline:
  Stage 1 -- Exact match       (same reference_id AND exact same amount)
  Stage 2 -- Fuzzy match       (reference_id or vendor similarity, amount within
                                 rounding tolerance, date within window)
  Stage 3 -- Split-payment     (N bank rows sum to 1 ledger row)
  Stage 4 -- Escalation        (ambiguous leftovers -> local LLM or heuristic
                                 with strict domain guardrails)
  Stage 5 -- Report            match rate + a reasoned exception list + JSON export

Run:  python reconcile.py
"""

import argparse
import csv
import json
import re
from datetime import datetime
from difflib import SequenceMatcher
from itertools import combinations


def parse_args():
    ap = argparse.ArgumentParser(
        description="Staged, explainable bank-vs-ledger reconciliation engine")
    ap.add_argument("--bank", default="bank_statement.csv", help="bank statement CSV")
    ap.add_argument("--ledger", default="company_ledger.csv", help="company ledger CSV")
    ap.add_argument("--tolerance", type=float, default=5.00,
                    help="Stage 2 amount tolerance in Rs (default 5.00)")
    ap.add_argument("--date-window", type=int, default=3,
                    help="Stage 2/3 date window in days (default 3)")
    ap.add_argument("--confidence", type=int, default=60,
                    help="Stage 4 LLM confidence threshold 0-100 (default 60)")
    ap.add_argument("--no-llm", action="store_true",
                    help="skip the LLM; use the deterministic heuristic for Stage 4")
    ap.add_argument("--model", default=None, help="HuggingFace model id for Stage 4")
    return ap.parse_args()


ARGS = parse_args()

AMOUNT_TOLERANCE = ARGS.tolerance   # rupees (handles rounding to nearest 10)
DATE_WINDOW_DAYS = ARGS.date_window
USE_LLM = not ARGS.no_llm

# Suffixes stripped during vendor name normalization
_VENDOR_SUFFIXES = re.compile(
    r'\b(pvt|private|ltd|limited|llp|inc|incorporated|services|co)\b\.?',
    re.IGNORECASE,
)


def _normalize_vendor(name):
    """Normalize a vendor name for comparison: lowercase, strip common
    business suffixes, collapse whitespace."""
    name = name.lower().strip()
    name = _VENDOR_SUFFIXES.sub('', name)
    name = re.sub(r'\s+', ' ', name).strip()
    return name


def vendor_similarity(a, b):
    """Return a 0-1 similarity score between two vendor names.
    Uses difflib.SequenceMatcher on normalized names."""
    if not a or not b:
        return 0.0
    na, nb = _normalize_vendor(a), _normalize_vendor(b)
    if na == nb:
        return 1.0
    return SequenceMatcher(None, na, nb).ratio()


def load_rows(path):
    rows = []
    with open(path, newline="") as f:
        for i, row in enumerate(csv.DictReader(f)):
            row["amount"] = float(row["amount"])
            row["date"] = datetime.strptime(row["date"], "%Y-%m-%d")
            row["_id"] = f"{path}#{i}"
            row["_row_index"] = i
            rows.append(row)
    return rows


def days_apart(a, b):
    return abs((a - b).days)


def stage1_exact(bank, ledger):
    """Match on identical, non-empty reference_id AND exact amount.

    Index-based: consumed ledger rows are tracked in a set and both lists
    are rebuilt once at the end (no O(n^2) list.remove / membership scans).
    """
    matches = []
    ledger_by_ref = {}
    for idx, l in enumerate(ledger):
        if l["reference_id"]:
            ledger_by_ref.setdefault(l["reference_id"], []).append(idx)

    used_ledger = set()
    matched_bank = set()
    for bidx, b in enumerate(bank):
        if not b["reference_id"]:
            continue
        for lidx in ledger_by_ref.get(b["reference_id"], []):
            if lidx in used_ledger:
                continue
            l = ledger[lidx]
            if abs(b["amount"] - l["amount"]) < 0.005:
                matches.append({
                    "bank": b, "ledger": l, "tier": "exact",
                    "reason": "identical reference_id and amount",
                })
                used_ledger.add(lidx)
                matched_bank.add(bidx)
                break

    if matches:
        bank[:] = [b for i, b in enumerate(bank) if i not in matched_bank]
        ledger[:] = [l for i, l in enumerate(ledger) if i not in used_ledger]
    return matches


def stage2_fuzzy(bank, ledger):
    """Match on reference ID or vendor similarity with amount within
    rounding tolerance and date within window."""
    matches = []

    # Sub-pass A: identical reference_id with slight amount rounding (<= Rs. 5)
    ledger_by_ref = {}
    for l in ledger:
        if l["reference_id"]:
            ledger_by_ref.setdefault(l["reference_id"], []).append(l)

    for b in list(bank):
        if not b["reference_id"]:
            continue
        candidates = ledger_by_ref.get(b["reference_id"], [])
        for l in candidates:
            if l in ledger and abs(b["amount"] - l["amount"]) <= AMOUNT_TOLERANCE and days_apart(b["date"], l["date"]) <= DATE_WINDOW_DAYS:
                matches.append({
                    "bank": b, "ledger": l, "tier": "fuzzy",
                    "reason": (f"identical ref '{b['reference_id']}', "
                               f"rounding delta Rs.{abs(b['amount'] - l['amount']):.2f}, "
                               f"date within {days_apart(b['date'], l['date'])}d"),
                })
                bank.remove(b)
                ledger.remove(l)
                break

    # Sub-pass B: amount within tolerance + date within window + vendor similarity
    for b in list(bank):
        candidates = [
            l for l in ledger
            if abs(b["amount"] - l["amount"]) <= AMOUNT_TOLERANCE
            and days_apart(b["date"], l["date"]) <= DATE_WINDOW_DAYS
            # Conflicting non-empty reference ids are evidence AGAINST a
            # match: this is what blocks duplicate-amount decoys, which copy
            # a real amount but carry a foreign reference id.
            and not (b["reference_id"] and l["reference_id"]
                     and b["reference_id"] != l["reference_id"])
        ]

        if len(candidates) == 1:
            l = candidates[0]
            vs = vendor_similarity(b["vendor"], l["vendor"])
            if vs >= 0.5:
                matches.append({
                    "bank": b, "ledger": l, "tier": "fuzzy",
                    "reason": (f"amount within Rs.{abs(b['amount'] - l['amount']):.2f}, "
                               f"date within {days_apart(b['date'], l['date'])}d, "
                               f"vendor match ({b['vendor']} ~ {l['vendor']}, sim {vs:.0%})"),
                })
                bank.remove(b)
                ledger.remove(l)

        elif len(candidates) > 1:
            scored = [(vendor_similarity(b["vendor"], c["vendor"]), c) for c in candidates]
            scored.sort(key=lambda x: -x[0])
            best_score, best = scored[0]
            second_score = scored[1][0] if len(scored) > 1 else 0.0

            if best_score >= 0.7 and (best_score - second_score) >= 0.25:
                matches.append({
                    "bank": b, "ledger": best, "tier": "fuzzy",
                    "reason": (f"amount within Rs.{abs(b['amount'] - best['amount']):.2f}, "
                               f"date within {days_apart(b['date'], best['date'])}d, "
                               f"vendor similarity {best_score:.0%} vs next-best {second_score:.0%}"),
                })
                bank.remove(b)
                ledger.remove(best)

    return matches


def stage3_split_payments(bank, ledger, max_parts=3):
    """Detect N bank rows summing to one ledger row (split payment pattern)."""
    matches = []
    for l in list(ledger):
        # Prune first: only bank rows inside the date window, each smaller
        # than the target amount, can participate in a split.  This keeps the
        # combinatorial search tiny even on large statements.
        near = [c for c in bank
                if c["amount"] < l["amount"]
                and days_apart(c["date"], l["date"]) <= DATE_WINDOW_DAYS]
        found = None
        for n in range(2, max_parts + 1):
            if len(near) < n:
                break
            for combo in combinations(near, n):
                if abs(sum(c["amount"] for c in combo) - l["amount"]) < 0.02:
                    found = combo
                    break
            if found:
                break
        if found:
            matches.append({
                "bank": list(found), "ledger": l, "tier": "split_payment",
                "reason": f"{len(found)} bank rows sum to ledger amount within Rs.0.02",
            })
            for c in found:
                bank.remove(c)
            ledger.remove(l)
    return matches


def _stage4_heuristic_fallback(bank, ledger):
    """Scoring heuristic with vendor fuzzy matching — used as fallback ONLY
    when the LLM is unavailable.

    Returns (resolved, deferred): rows the scorer deemed 'too close to call'
    are deferred for human review rather than force-matched.
    """
    resolved = []
    deferred = []
    for b in list(bank):
        scored = []
        for l in ledger:
            amount_gap = abs(b["amount"] - l["amount"])
            date_gap = days_apart(b["date"], l["date"])
            vs = vendor_similarity(b["vendor"], l["vendor"])

            # Require strong vendor similarity or small gap to prevent spurious decoy matches
            if vs >= 0.6 and amount_gap <= AMOUNT_TOLERANCE and date_gap <= DATE_WINDOW_DAYS:
                score = -(amount_gap) - (date_gap * 1.5) + (vs * 10)
                scored.append((score, l, amount_gap, date_gap, vs))

        scored.sort(key=lambda x: -x[0])
        if len(scored) >= 2 and abs(scored[0][0] - scored[1][0]) < 1.0:
            deferred.append(b)  # too close to call -- needs human review
            continue

        if scored:
            best = scored[0]
            resolved.append({
                "bank": b, "ledger": best[1], "tier": "ai_escalated",
                "reason": (f"[heuristic] match (Rs.{best[2]:.2f} delta, "
                           f"{best[3]}d apart, vendor sim {best[4]:.0%})"),
            })
            bank.remove(b)
            ledger.remove(best[1])

    return resolved, deferred + list(ledger)


def stage4_escalate(bank, ledger):
    """
    Stage 4: LLM reasoning with Qwen2.5-3B-Instruct (GPU-accelerated),
    with graceful fallback to the heuristic resolver when the LLM is
    unavailable.

    Returns (resolved_matches, needs_review_rows).

    THE HONESTY RULE: the heuristic is only a fallback.  When the LLM runs,
    any row it declines (or scores below the confidence threshold) is
    deferred to the human-review queue -- never force-matched by the
    heuristic afterwards.  A deferred row is an honest "I don't know".
    """
    if not bank or not ledger:
        return [], []

    if not USE_LLM:
        print("\n  Stage 4: LLM disabled (--no-llm) — using heuristic fallback")
        return _stage4_heuristic_fallback(bank, ledger)

    try:
        from llm_resolver import resolve_ambiguous

        print(f"\n  Stage 4: attempting local LLM resolution "
              f"({len(bank)} bank × {len(ledger)} ledger rows) ...")

        proposals = resolve_ambiguous(bank, ledger, model_name=ARGS.model,
                                      confidence_threshold=ARGS.confidence)

        resolved = []
        proposals.sort(key=lambda p: -p["confidence"])
        for p in proposals:
            b = bank[p["bank_index"]] if p["bank_index"] < len(bank) else None
            l = ledger[p["ledger_index"]] if p["ledger_index"] < len(ledger) else None
            if b is None or l is None:
                continue
            if b not in bank or l not in ledger:
                continue

            resolved.append({
                "bank": b, "ledger": l, "tier": "ai_escalated",
                "reason": (f"[LLM {p['confidence']}% confidence] {p['reason']}"),
            })
            bank.remove(b)
            ledger.remove(l)

        print(f"  Stage 4: LLM resolved {len(resolved)} match(es)")

        # HONESTY RULE: rows the LLM declined (or scored below threshold) are
        # NOT re-matched by the heuristic -- they go to the human-review queue.
        leftovers = list(bank) + list(ledger)
        if leftovers:
            print(f"  Stage 4: {len(leftovers)} row(s) deferred to human review "
                  f"(LLM declined or below {ARGS.confidence}% confidence)")

        return resolved, leftovers

    except ImportError:
        print("\n  Stage 4: transformers/torch not installed — using heuristic fallback")
        return _stage4_heuristic_fallback(bank, ledger)

    except Exception as e:
        print(f"\n  Stage 4: LLM failed ({type(e).__name__}: {e}) — using heuristic fallback")
        return _stage4_heuristic_fallback(bank, ledger)


def main():
    bank = load_rows(ARGS.bank)
    ledger = load_rows(ARGS.ledger)
    total_bank, total_ledger = len(bank), len(ledger)
    total_bank_value = sum(b["amount"] for b in bank)
    total_ledger_value = sum(l["amount"] for l in ledger)

    all_matches = []
    all_matches += stage1_exact(bank, ledger)
    all_matches += stage2_fuzzy(bank, ledger)
    all_matches += stage3_split_payments(bank, ledger)
    s4_matches, review_rows = stage4_escalate(bank, ledger)
    all_matches += s4_matches
    review_ids = {id(r) for r in review_rows}

    tier_counts = {}
    for m in all_matches:
        tier_counts[m["tier"]] = tier_counts.get(m["tier"], 0) + 1

    matched_bank_rows = sum(
        (len(m["bank"]) if isinstance(m["bank"], list) else 1) for m in all_matches
    )

    print("=" * 70)
    print("RECONCILIATION REPORT")
    print("=" * 70)
    print(f"Bank statement rows:  {total_bank}")
    print(f"Ledger rows:          {total_ledger}")
    print()
    print("Matched by tier:")
    for tier, count in tier_counts.items():
        print(f"  {tier:15s}: {count}")
    print()
    match_rate = matched_bank_rows / total_bank * 100
    print(f"MATCH RATE (bank rows resolved): {matched_bank_rows}/{total_bank} = {match_rate:.1f}%")
    print()
    matched_bank_value = sum(
        (sum(x["amount"] for x in m["bank"]) if isinstance(m["bank"], list)
         else m["bank"]["amount"])
        for m in all_matches
    )
    matched_ledger_value = sum(m["ledger"]["amount"] for m in all_matches)
    print("Value reconciled:")
    print(f"  bank:   Rs.{matched_bank_value:>12,.2f} of Rs.{total_bank_value:>12,.2f} "
          f"({matched_bank_value / total_bank_value * 100:.1f}% of value)")
    print(f"  ledger: Rs.{matched_ledger_value:>12,.2f} of Rs.{total_ledger_value:>12,.2f} "
          f"({matched_ledger_value / total_ledger_value * 100:.1f}% of value)")
    print()

    print("-" * 70)
    print(f"UNRESOLVED EXCEPTIONS -- {len(bank) + len(ledger)} rows could not be confidently matched")
    print("-" * 70)
    for b in bank:
        is_review = id(b) in review_ids
        tag = "[REVIEW]     " if is_review else "[BANK ONLY]  "
        reason = ("matcher declined to guess -- needs human review"
                  if is_review else
                  "no candidate in ledger within tolerance, or tied confidence")
        print(f"  {tag} Rs.{b['amount']:>10.2f}  {b['date'].date()}  "
              f"ref={b['reference_id'] or '(none)':12s} vendor={b['vendor']:18s} "
              f"-> {reason}")
    for l in ledger:
        is_review = id(l) in review_ids
        tag = "[REVIEW]     " if is_review else "[LEDGER ONLY]"
        reason = ("matcher declined to guess -- needs human review"
                  if is_review else
                  "no candidate in bank statement within tolerance, or tied confidence")
        print(f"  {tag} Rs.{l['amount']:>10.2f}  {l['date'].date()}  "
              f"ref={l['reference_id'] or '(none)':12s} vendor={l['vendor']:18s} "
              f"-> {reason}")

    # -- Write machine-readable outputs -----------------------------------

    # matches.csv (with row indices for evaluate.py)
    with open("matches.csv", "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["tier", "bank_amount", "ledger_amount", "reference_id",
                         "bank_row_index", "ledger_row_index", "reason"])
        for m in all_matches:
            bank_part = m["bank"] if isinstance(m["bank"], list) else [m["bank"]]
            bank_amt = "+".join(f"{x['amount']:.2f}" for x in bank_part)
            bank_idx = ";".join(str(x["_row_index"]) for x in bank_part)
            writer.writerow([m["tier"], bank_amt, m["ledger"]["amount"],
                              m["ledger"]["reference_id"],
                              bank_idx, m["ledger"]["_row_index"],
                              m["reason"]])

    # exceptions.csv -- with row indices and a recommended_action column so
    # the exception list doubles as a human-review queue.
    def action_for(row):
        if id(row) in review_ids:
            return "needs_human_review"
        if row.get("vendor") == "Bank Charges":
            return "likely_bank_fee"
        return "investigate_orphan"

    def reason_for(row):
        if id(row) in review_ids:
            return "matcher declined to guess (ambiguous; below confidence)"
        if row.get("vendor") == "Bank Charges":
            return "bank charge with no ledger counterpart"
        return "no confident match found in the other system"

    with open("exceptions.csv", "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["source", "row_index", "amount", "date", "reference_id",
                         "vendor", "recommended_action", "reason"])
        for b in bank:
            writer.writerow(["bank_only", b["_row_index"], b["amount"], b["date"].date(),
                              b["reference_id"], b["vendor"], action_for(b), reason_for(b)])
        for l in ledger:
            writer.writerow(["ledger_only", l["_row_index"], l["amount"], l["date"].date(),
                              l["reference_id"], l["vendor"], action_for(l), reason_for(l)])

    # reconciliation_report.json (for the dashboard)
    report = {
        "generated_at": datetime.now().isoformat(),
        "summary": {
            "total_bank_rows": total_bank,
            "total_ledger_rows": total_ledger,
            "matched_bank_rows": matched_bank_rows,
            "match_rate_pct": round(match_rate, 1),
            "total_exceptions": len(bank) + len(ledger),
            "needs_human_review": sum(1 for r in list(bank) + list(ledger)
                                      if id(r) in review_ids),
            "total_bank_value": round(total_bank_value, 2),
            "matched_bank_value": round(matched_bank_value, 2),
            "tier_counts": tier_counts,
        },
        "matches": [],
        "exceptions": [],
    }

    for m in all_matches:
        bank_part = m["bank"] if isinstance(m["bank"], list) else [m["bank"]]
        entry = {
            "tier": m["tier"],
            "bank_entries": [{
                "amount": x["amount"],
                "date": x["date"].strftime("%Y-%m-%d"),
                "reference_id": x["reference_id"],
                "vendor": x["vendor"],
                "row_index": x["_row_index"],
            } for x in bank_part],
            "ledger_entry": {
                "amount": m["ledger"]["amount"],
                "date": m["ledger"]["date"].strftime("%Y-%m-%d"),
                "reference_id": m["ledger"]["reference_id"],
                "vendor": m["ledger"]["vendor"],
                "row_index": m["ledger"]["_row_index"],
            },
            "reason": m["reason"],
        }
        report["matches"].append(entry)

    for b in bank:
        report["exceptions"].append({
            "source": "bank_only",
            "amount": b["amount"],
            "date": b["date"].strftime("%Y-%m-%d"),
            "reference_id": b["reference_id"],
            "vendor": b["vendor"],
            "row_index": b["_row_index"],
            "recommended_action": action_for(b),
            "reason": reason_for(b),
        })
    for l in ledger:
        report["exceptions"].append({
            "source": "ledger_only",
            "amount": l["amount"],
            "date": l["date"].strftime("%Y-%m-%d"),
            "reference_id": l["reference_id"],
            "vendor": l["vendor"],
            "row_index": l["_row_index"],
            "recommended_action": action_for(l),
            "reason": reason_for(l),
        })

    with open("reconciliation_report.json", "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    print()
    print("Wrote matches.csv, exceptions.csv, reconciliation_report.json")


if __name__ == "__main__":
    main()
