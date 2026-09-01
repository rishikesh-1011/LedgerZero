"""
run_sweep.py

Multi-seed evaluation sweep -- the anti-cherry-pick check.

A single seeded run can flatter any matcher.  This script regenerates the
synthetic data across many seeds and runs the full loop per seed:

    generate_data.py --seed S  ->  reconcile.py  ->  evaluate.py

then aggregates precision / recall / F1 / value coverage / honesty across all
runs into sweep_results/sweep_summary.json.  "One cherry-picked match proves
nothing" -- neither does one seed.

Usage:
    python run_sweep.py --seeds 20            # heuristic Stage 4 (fast)
    python run_sweep.py --seeds 5 --llm       # local LLM Stage 4 (slow)
"""

import argparse
import json
import os
import statistics
import subprocess
import sys


def run(cmd):
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        print(proc.stdout)
        print(proc.stderr, file=sys.stderr)
        raise SystemExit(f"command failed: {' '.join(cmd)}")
    return proc.stdout


def main():
    ap = argparse.ArgumentParser(description="Multi-seed reconciliation sweep")
    ap.add_argument("--seeds", type=int, default=20, help="number of seeds to run")
    ap.add_argument("--start-seed", type=int, default=42, help="first seed")
    ap.add_argument("--llm", action="store_true",
                    help="use the local LLM for Stage 4 (slow; heuristic otherwise)")
    ap.add_argument("--outdir", default="sweep_results")
    args = ap.parse_args()

    os.makedirs(args.outdir, exist_ok=True)
    reconcile_cmd = [sys.executable, "reconcile.py"]
    if not args.llm:
        reconcile_cmd.append("--no-llm")

    frac_keys = ("precision", "bank_recall", "ledger_recall", "f1_bank")
    pct_keys = ("bank_value_pct", "ledger_value_pct")
    results = []

    for k in range(args.seeds):
        seed = args.start_seed + k
        print(f"\n===== seed {seed} =====")
        run([sys.executable, "generate_data.py", "--seed", str(seed)])
        run(reconcile_cmd)
        run([sys.executable, "evaluate.py"])

        with open("evaluation_summary.json", encoding="utf-8") as f:
            summary = json.load(f)
        summary["seed"] = seed
        with open(os.path.join(args.outdir, f"seed_{seed}_summary.json"),
                  "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2)
        results.append(summary)
        print(f"  seed {seed}: precision={summary['precision'] * 100:5.1f}%  "
              f"bank_recall={summary['bank_recall'] * 100:5.1f}%  "
              f"f1={summary['f1_bank'] * 100:5.1f}%  "
              f"honest={summary['honest_exception_list']}  "
              f"deferred={summary.get('deferred_review_rows', 0)}")

    def stats(key):
        vals = [r[key] for r in results]
        return {"mean": round(statistics.mean(vals), 4),
                "min": round(min(vals), 4),
                "max": round(max(vals), 4)}

    aggregate = {
        "mode": "llm" if args.llm else "heuristic",
        "runs": len(results),
        "seeds": [r["seed"] for r in results],
        "honest_runs": sum(1 for r in results if r["honest_exception_list"]),
    }
    for key in frac_keys + pct_keys:
        aggregate[key] = stats(key)

    agg_path = os.path.join(args.outdir, "sweep_summary.json")
    with open(agg_path, "w", encoding="utf-8") as f:
        json.dump(aggregate, f, indent=2)

    print("\n" + "=" * 70)
    print(f"SWEEP SUMMARY -- {aggregate['mode']} Stage 4, {aggregate['runs']} seeds "
          f"({args.start_seed}..{args.start_seed + args.seeds - 1})")
    print("=" * 70)
    for key in frac_keys + pct_keys:
        scale = 1 if key in pct_keys else 100
        s = aggregate[key]
        print(f"  {key:18s}: mean {s['mean'] * scale:6.1f}%   "
              f"min {s['min'] * scale:6.1f}%   max {s['max'] * scale:6.1f}%")
    print(f"  honest exception lists: {aggregate['honest_runs']}/{aggregate['runs']} runs")
    print(f"\nWrote {agg_path}")


if __name__ == "__main__":
    main()
