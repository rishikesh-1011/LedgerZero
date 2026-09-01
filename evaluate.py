"""
evaluate.py

Scores reconcile.py's output against the hidden ground truth emitted by
generate_data.py (ground_truth.csv).

The Track 04 bar is "throughput plus measured accuracy plus an honest
exception list -- one cherry-picked match proves nothing."  reconcile.py
reports throughput (match rate); this script supplies the other two halves:

  * MEASURED ACCURACY -- precision / recall / F1 of every proposed match,
    checked against the ground truth each row was generated from.
  * EXCEPTION HONESTY  -- verifies the leftover rows are exactly the ones
    that genuinely cannot be matched (decoys, bank fees, orphans) and flags
    any row the pipeline should have matched but didn't.

Usage:
    python evaluate.py

Reads:  bank_statement.csv, company_ledger.csv, ground_truth.csv, matches.csv
Writes: evaluation_summary.json
"""

import argparse
import csv
import json
import os
import sys

NO_TRUTH = ""  # marker for rows with no real transaction behind them (decoys, fees)


def parse_args():
    ap = argparse.ArgumentParser(description="Score reconcile.py output against ground truth")
    ap.add_argument("--bank", default="bank_statement.csv")
    ap.add_argument("--ledger", default="company_ledger.csv")
    ap.add_argument("--ground-truth", default="ground_truth.csv")
    ap.add_argument("--matches", default="matches.csv")
    ap.add_argument("--exceptions", default="exceptions.csv")
    ap.add_argument("--json-out", default="evaluation_summary.json")
    return ap.parse_args()


def load_ground_truth(path):
    if not os.path.exists(path):
        sys.exit(f"{path} not found -- run generate_data.py first.")
    truth = {}
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            truth[(row["source"], int(row["row_index"]))] = (
                row["truth_id"], row.get("scenario", "unknown"))
    return truth


def load_actions(path):
    """Unmatched-row disposition from exceptions.csv (needs_human_review etc.)."""
    actions = {}
    if not os.path.exists(path):
        return actions
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames or "row_index" not in reader.fieldnames:
            return actions
        for row in reader:
            try:
                actions[(row["source"], int(row["row_index"]))] = row.get("recommended_action", "")
            except (ValueError, TypeError):
                continue
    return actions


def load_side(path, source, truth):
    rows = []
    with open(path, newline="") as f:
        for i, row in enumerate(csv.DictReader(f)):
            row["_row"] = i
            tid, scen = truth.get((source, i), (NO_TRUTH, "unknown"))
            row["_truth_id"] = tid
            row["_scenario"] = scen
            rows.append(row)
    return rows


def main():
    ARGS = parse_args()
    truth = load_ground_truth(ARGS.ground_truth)
    bank = load_side(ARGS.bank, "bank", truth)
    ledger = load_side(ARGS.ledger, "ledger", truth)
    actions = load_actions(ARGS.exceptions)

    # Which real transactions exist on each side?
    bank_truth = {r["_truth_id"] for r in bank if r["_truth_id"] != NO_TRUTH}
    ledger_truth = {r["_truth_id"] for r in ledger if r["_truth_id"] != NO_TRUTH}

    if not os.path.exists(ARGS.matches):
        sys.exit(f"{ARGS.matches} not found -- run reconcile.py first.")
    matches = []
    with open(ARGS.matches, newline="") as f:
        reader = csv.DictReader(f)
        if not {"bank_row_index", "ledger_row_index"} <= set(reader.fieldnames or []):
            sys.exit("matches.csv lacks *_row_index columns -- re-run reconcile.py "
                     "(an older matches.csv format is in place).")
        for row in reader:
            matches.append({
                "tier": row["tier"],
                "bank_idx": [int(x) for x in row["bank_row_index"].split(";")],
                "ledger_idx": int(row["ledger_row_index"]),
            })

    # ------------------------------------------------------------------
    # 1. PRECISION: is every proposed match the SAME real transaction?
    # ------------------------------------------------------------------
    per_tier = {}
    correct = 0
    wrong = []
    used_bank, used_ledger = set(), set()
    collisions = []

    for m in matches:
        t = per_tier.setdefault(m["tier"], {"total": 0, "correct": 0})
        t["total"] += 1

        for i in m["bank_idx"]:
            if i in used_bank:
                collisions.append(f"bank row {i} consumed by multiple matches")
            used_bank.add(i)
        if m["ledger_idx"] in used_ledger:
            collisions.append(f"ledger row {m['ledger_idx']} consumed by multiple matches")
        used_ledger.add(m["ledger_idx"])

        ledger_tid = ledger[m["ledger_idx"]]["_truth_id"]
        bank_tids = [bank[i]["_truth_id"] for i in m["bank_idx"]]
        if all(b == ledger_tid and b != NO_TRUTH for b in bank_tids):
            correct += 1
            t["correct"] += 1
        else:
            wrong.append({
                "tier": m["tier"],
                "bank_refs": [bank[i]["reference_id"] for i in m["bank_idx"]],
                "ledger_ref": ledger[m["ledger_idx"]]["reference_id"],
                "bank_truth": bank_tids,
                "ledger_truth": ledger_tid,
            })

    precision = correct / len(matches) if matches else 1.0

    # ------------------------------------------------------------------
    # 2. RECALL: of the rows that CAN be matched, how many were?
    #    (decoys / fees / one-side-only orphans are excluded from the
    #     denominator -- they are exceptions by design, not failures)
    # ------------------------------------------------------------------
    matchable_bank = [r for r in bank
                      if r["_truth_id"] != NO_TRUTH and r["_truth_id"] in ledger_truth]
    matchable_ledger = [r for r in ledger
                        if r["_truth_id"] != NO_TRUTH and r["_truth_id"] in bank_truth]

    correct_bank_idx, correct_ledger_idx = set(), set()
    for m in matches:
        ledger_tid = ledger[m["ledger_idx"]]["_truth_id"]
        for i in m["bank_idx"]:
            if bank[i]["_truth_id"] == ledger_tid and ledger_tid != NO_TRUTH:
                correct_bank_idx.add(i)
                correct_ledger_idx.add(m["ledger_idx"])

    recall_bank = (len(correct_bank_idx) / len(matchable_bank)) if matchable_bank else 1.0
    recall_ledger = (len(correct_ledger_idx) / len(matchable_ledger)) if matchable_ledger else 1.0
    f1_bank = (2 * precision * recall_bank / (precision + recall_bank)
               if (precision + recall_bank) else 0.0)

    # Value-based reconciliation: finance teams think in rupees, not rows
    total_bank_value = sum(float(r["amount"]) for r in bank)
    matched_bank_value = sum(float(bank[i]["amount"]) for i in correct_bank_idx)
    total_ledger_value = sum(float(r["amount"]) for r in ledger)
    matched_ledger_value = sum(float(ledger[i]["amount"]) for i in correct_ledger_idx)

    # ------------------------------------------------------------------
    # 3. EXCEPTION HONESTY: are the leftovers exactly the unmatchable rows?
    # ------------------------------------------------------------------
    def classify(row, source, other_truth):
        # A row the matcher deliberately declined is an honest "I don't know",
        # not a miss -- count it separately.
        if actions.get((source, row["_row"]), "") == "needs_human_review":
            return "deferred_review"
        tid = row["_truth_id"]
        if tid == NO_TRUTH:
            return "by_design"        # decoy or bank fee -- nothing to match to
        if tid not in other_truth:
            return "by_design"        # true orphan -- exists on one side only
        return "missed"               # should have matched -- honesty failure

    unmatched_bank = [r for r in bank if r["_row"] not in used_bank]
    unmatched_ledger = [r for r in ledger if r["_row"] not in used_ledger]

    bank_class = {"by_design": [], "missed": [], "deferred_review": []}
    for r in unmatched_bank:
        bank_class[classify(r, "bank_only", ledger_truth)].append(r)
    ledger_class = {"by_design": [], "missed": [], "deferred_review": []}
    for r in unmatched_ledger:
        ledger_class[classify(r, "ledger_only", bank_truth)].append(r)

    bank_misses = bank_class["missed"]
    ledger_misses = ledger_class["missed"]
    bank_review_idx = {r["_row"] for r in bank_class["deferred_review"]}
    ledger_review_idx = {r["_row"] for r in ledger_class["deferred_review"]}

    # ------------------------------------------------------------------
    # Report
    # ------------------------------------------------------------------
    line = "=" * 70
    print(line)
    print("EVALUATION vs GROUND TRUTH (ground_truth.csv)")
    print(line)
    print(f"Bank statement rows:          {len(bank)}")
    print(f"Ledger rows:                  {len(ledger)}")
    print(f"Matches proposed:             {len(matches)}")
    print(f"  correct:                    {correct}")
    print(f"  wrong:                      {len(wrong)}")
    print(f"  self-consistency collisions:{len(collisions)}")
    print()
    print(f"PRECISION:                    {precision * 100:.1f}%")
    print()
    print(f"Matchable bank rows:          {len(matchable_bank)} "
          f"(real transactions with a counterpart on the other side)")
    print(f"  correctly matched:          {len(correct_bank_idx)}")
    print(f"BANK RECALL:                  {recall_bank * 100:.1f}%")
    print(f"F1 (bank side):               {f1_bank * 100:.1f}%")
    print()
    print(f"Matchable ledger rows:        {len(matchable_ledger)}")
    print(f"  correctly matched:          {len(correct_ledger_idx)}")
    print(f"LEDGER RECALL:                {recall_ledger * 100:.1f}%")
    print()
    print("Value reconciled:")
    print(f"  bank:   Rs.{matched_bank_value:>12,.2f} of Rs.{total_bank_value:>12,.2f} "
          f"({matched_bank_value / total_bank_value * 100:.1f}% of value)")
    print(f"  ledger: Rs.{matched_ledger_value:>12,.2f} of Rs.{total_ledger_value:>12,.2f} "
          f"({matched_ledger_value / total_ledger_value * 100:.1f}% of value)")
    print()
    print("Per-tier accuracy:")
    for tier, t in per_tier.items():
        print(f"  {tier:15s}: {t['correct']}/{t['total']} correct")
    print()
    print("Per-scenario breakdown (bank side):")
    print(f"  {'scenario':16s} {'rows':>5s} {'matchable':>10s} {'matched':>8s} {'review':>7s}")
    scenario_names = sorted({r["_scenario"] for r in bank})
    for s in scenario_names:
        rows_s = [r for r in bank if r["_scenario"] == s]
        matchable_s = sum(1 for r in rows_s
                          if r["_truth_id"] != NO_TRUTH and r["_truth_id"] in ledger_truth)
        correct_s = sum(1 for r in rows_s if r["_row"] in correct_bank_idx)
        review_s = sum(1 for r in rows_s if r["_row"] in bank_review_idx)
        print(f"  {s:16s} {len(rows_s):5d} {matchable_s:10d} {correct_s:8d} {review_s:7d}")
    print()
    print("-" * 70)
    print("EXCEPTION AUDIT (the honest-exception-list test)")
    print("-" * 70)
    print(f"Unmatched bank rows:   {len(unmatched_bank):3d}  -> "
          f"{len(bank_class['by_design'])} unmatchable by design, "
          f"{len(bank_misses)} missed, {len(bank_review_idx)} deferred to review")
    print(f"Unmatched ledger rows: {len(unmatched_ledger):3d}  -> "
          f"{len(ledger_class['by_design'])} unmatchable by design, "
          f"{len(ledger_misses)} missed, {len(ledger_review_idx)} deferred to review")
    for r in bank_misses:
        print(f"  [MISSED BANK]   row {r['_row']:3d}  Rs.{float(r['amount']):>10.2f}  "
              f"{r['date']}  ref={r['reference_id']}  vendor={r['vendor']}")
    for r in ledger_misses:
        print(f"  [MISSED LEDGER] row {r['_row']:3d}  Rs.{float(r['amount']):>10.2f}  "
              f"{r['date']}  ref={r['reference_id']}  vendor={r['vendor']}")
    for c in collisions:
        print(f"  [COLLISION] {c}")
    for w in wrong:
        print(f"  [WRONG MATCH] tier={w['tier']} bank={w['bank_refs']} "
              f"ledger={w['ledger_ref']} (truth {w['bank_truth']} != {w['ledger_truth']})")

    # A deferred row is an honest "I don't know" -- it does not break honesty.
    honest = not (bank_misses or ledger_misses or wrong or collisions)
    deferred = len(bank_review_idx) + len(ledger_review_idx)
    print()
    if honest:
        verdict = "YES" + (f" ({deferred} row(s) honestly deferred to human review)"
                           if deferred else "")
        print(f"HONEST EXCEPTION LIST: {verdict}")
    else:
        print("HONEST EXCEPTION LIST: NO -- see flags above")

    # Machine-readable summary for the demo/appendix
    scenario_breakdown = {}
    for s in scenario_names:
        rows_s = [r for r in bank if r["_scenario"] == s]
        scenario_breakdown[s] = {
            "bank_rows": len(rows_s),
            "matchable": sum(1 for r in rows_s if r["_truth_id"] != NO_TRUTH
                             and r["_truth_id"] in ledger_truth),
            "matched": sum(1 for r in rows_s if r["_row"] in correct_bank_idx),
            "deferred_review": sum(1 for r in rows_s if r["_row"] in bank_review_idx),
        }

    summary = {
        "bank_rows": len(bank),
        "ledger_rows": len(ledger),
        "matches_proposed": len(matches),
        "matches_correct": correct,
        "matches_wrong": len(wrong),
        "self_consistency_collisions": len(collisions),
        "precision": round(precision, 4),
        "matchable_bank_rows": len(matchable_bank),
        "bank_recall": round(recall_bank, 4),
        "f1_bank": round(f1_bank, 4),
        "matchable_ledger_rows": len(matchable_ledger),
        "ledger_recall": round(recall_ledger, 4),
        "total_bank_value": round(total_bank_value, 2),
        "matched_bank_value": round(matched_bank_value, 2),
        "bank_value_pct": round(matched_bank_value / total_bank_value * 100, 2)
                          if total_bank_value else 100.0,
        "total_ledger_value": round(total_ledger_value, 2),
        "matched_ledger_value": round(matched_ledger_value, 2),
        "ledger_value_pct": round(matched_ledger_value / total_ledger_value * 100, 2)
                            if total_ledger_value else 100.0,
        "per_tier": per_tier,
        "scenario_breakdown": scenario_breakdown,
        "wrong_matches": wrong,
        "missed_bank_rows": [{"row": r["_row"], "reference_id": r["reference_id"]}
                             for r in bank_misses],
        "missed_ledger_rows": [{"row": r["_row"], "reference_id": r["reference_id"]}
                               for r in ledger_misses],
        "deferred_review_rows": deferred,
        "honest_exception_list": honest,
    }
    with open(ARGS.json_out, "w") as f:
        json.dump(summary, f, indent=2)
    print()
    print(f"Wrote {ARGS.json_out}")


if __name__ == "__main__":
    main()
