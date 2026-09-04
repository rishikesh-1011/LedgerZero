# LedgerZero — AI Finance Controller

**Track 04: AI Finance Controller — Razorpay AI Buildathon 2026**

![CI](https://github.com/rishikesh-1011/LedgerZero/actions/workflows/ci.yml/badge.svg)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![LLM](https://img.shields.io/badge/LLM-local%20%7C%20GPU%20optional-9cf)
**LedgerZero** is an enterprise-grade finance controller that reconciles
transactions across bank feeds and ERP ledgers, reports a measured match rate
against hidden ground truth, and produces an actionable, prioritized exception
worklist with audit evidence.

> 🎬 **Buildathon submission kit:** use [`SUBMISSION.md`](SUBMISSION.md),
> [`SUBMISSION_CHECKLIST.md`](SUBMISSION_CHECKLIST.md),
> [`PITCH_VIDEO.md`](PITCH_VIDEO.md), and
> [`ARCHITECTURE.md`](ARCHITECTURE.md) to prepare the public repository,
> five-minute live demo, and application answers.

> **Zero-dependency core.** The whole pipeline — data generation,
> reconciliation (heuristic Stage 4), evaluation and multi-seed sweeps — is
> pure Python stdlib. `pip install` is only needed for the optional
> local-LLM Stage 4. CI proves the accuracy claims on every push, in
> seconds, with no installs.

## 🚀 Quick Start (fresh clone)

```bash
git clone https://github.com/rishikesh-1011/LedgerZero.git
cd LedgerZero

python generate_data.py            # synthetic data + hidden ground truth (seed 42)
python reconcile.py --no-llm       # 5-stage pipeline, heuristic Stage 4
python evaluate.py                 # precision / recall / F1 + exception audit
python run_sweep.py --seeds 20     # 20-seed sweep: the anti-cherry-pick check

python app.py                      # web dashboard -> http://localhost:8080
# Or on Windows, 1-click launch with:
# .\LedgerZero.exe                  # auto-starts server & opens browser
python test_web_ui.py              # headless smoke test of the web UI
```

For PDF, Word, and Excel uploads, install the optional parsers with
`pip install -r requirements-full.txt`.

## 🏆 Buildathon Submission Package

| Asset | Purpose |
|---|---|
| `SUBMISSION.md` | Project narrative and judge-facing overview |
| `SUBMISSION_CHECKLIST.md` | All 12 application fields with paste-ready answers |
| `PITCH_VIDEO.md` | Timed five-minute live-demo script and recording checklist |
| `ARCHITECTURE.md` | Architecture diagram, LLM boundary, and production caveats |

---

## 🌟 Key Features

1. **Multi-Format Ingestion**:
   - Upload statements in **PDF (.pdf)**, **Word (.docx)**, **Excel (.xlsx, .xls)**, **CSV/TSV/TXT (.csv, .tsv, .txt)**, **XML (.xml)**, and **JSON (.json)**.
   - Smart column mapper auto-detects `Amount`, `Date`, `Reference/UTR`, and `Vendor/Description` across different ERP/bank naming standards.

2. **5-Stage Reconciliation Pipeline**:
   - **Stage 1 (Exact Match)**: Identical reference IDs and exact amounts.
   - **Stage 2 (Fuzzy Match)**: Business suffix normalization (`Pvt Ltd`, `LLP`, `Inc`), SequenceMatcher vendor similarity, and rounding delta tolerance (up to Rs. 5.00).
   - **Stage 3 (Split Payments)**: Detects N bank transactions summing to 1 ledger transaction within settlement windows.
   - **Stage 4 (Optional Local LLM Review)**: Local `Qwen2.5-3B-Instruct` reviews leftover ambiguity only after deterministic rules decline it, with domain guardrails.
   - **Stage 5 (Audit Trail & Exceptions)**: Generates structured matches, honest exception categorizations, and variance analytics.

3. **⚡ Optional Local LLM Acceleration**:
   - The deterministic core requires no model or accelerator. When available,
     the optional Qwen path can run locally on CUDA in FP16.

4. **💬 Settlement Q&A Agent (`settlement_qa.py`)**:
   - Natural language conversational assistant powered directly by **Qwen2.5-3B-Instruct**.
   - Answers inquiries on specific transaction references (e.g. `TXN100018`), vendor settlement drift, unlogged bank fees, and root-cause analysis for exceptions with citations.

5. **📈 Forward Cash Forecaster (`cash_forecaster.py`)**:
   - Quantitative liquidity modeling analyzing vendor lead times, clearing velocity, and pending accruals.
   - Computes 7-day, 14-day, and 30-day forward cash trajectories, detects impending safety-buffer deficit points, and generates executive commentary.

6. **🧾 Tax-Line Matcher & Statutory Withholding (`tax_matcher.py`)**:
   - Reconciles invoice line items against statutory withholdings (TDS under Sec 194C @ 1%/2%, Sec 194J @ 10%, Sec 194Q @ 0.1%) and sales tax (GST @ 5%, 12%, 18%, 28%).
   - Matches net-of-tax bank debits with gross ledger amounts and flags tax leakage/discrepancies.

7. **💻 Interactive Multi-Module Dashboard & Web App (`dashboard.html`)**:
   - 4 integrated tabs: **⚡ Reconciliation Hub**, **💬 Settlement Q&A Agent**, **📈 Forward Cash Forecaster**, and **🧾 Tax-Line Matcher**.
   - Drag-and-Drop statement upload portal (PDF, Word, Excel, CSV, XML, JSON).
   - Real-time pipeline flow diagrams, donut charts, and slide-out variance inspector.
   - Animated SVG match-rate ring, ₹ value-reconciled & review-queue KPI cards.
   - Headless UI smoke test: `python test_web_ui.py` (boots the server and verifies all 7 endpoints over HTTP).

---

## 🎯 Measured Accuracy (evaluate.py)

A match rate alone is throughput, not accuracy — a matcher could hit 100% by
pairing rows at random. `generate_data.py` emits a hidden answer key
(`ground_truth.csv`: truth id **+ scenario type** for every row, never fed to
the matcher) and `evaluate.py` scores the output against it: precision,
recall, F1, value coverage, per-scenario accuracy, and an exception audit.

**The honesty rule:** the heuristic is only a *fallback* for when the LLM is
unavailable. When the LLM runs, any row it declines (or scores below the
confidence threshold) is deferred to a `needs_human_review` queue — never
force-matched afterwards. A deferred row is an honest "I don't know," counted
separately from both matches and true exceptions.

Sample run (seed 42, heuristic Stage 4 — exactly reproducible with `--seed 42`):

```
======================================================================
EVALUATION vs GROUND TRUTH (ground_truth.csv)
======================================================================
Bank statement rows:          77
Ledger rows:                  71
Matches proposed:             68
  correct:                    68
  wrong:                      0
  self-consistency collisions:0

PRECISION:                    100.0%

Matchable bank rows:          69
  correctly matched:          69
BANK RECALL:                  100.0%
F1 (bank side):               100.0%

Matchable ledger rows:        68
  correctly matched:          68
LEDGER RECALL:                100.0%

Value reconciled:
  bank:   Rs.3,412,552.68 of Rs.3,617,777.72 (94.3% of value)
  ledger: Rs.3,412,548.92 of Rs.3,599,254.13 (94.8% of value)

Per-tier accuracy:
  exact          : 54/54 correct
  fuzzy          : 13/13 correct
  split_payment  : 1/1 correct

Per-scenario breakdown (bank side):
  scenario          rows  matchable  matched  review
  bank_fee             3          0        0       0
  date_drift           9          9        9       0
  decoy                4          0        0       0
  exact               40         40       40       0
  missing_ref          1          1        1       0
  rounding             7          7        7       0
  split_payment        2          2        2       0
  tax_line             7          6        6       0
  vendor_variant       4          4        4       0

----------------------------------------------------------------------
EXCEPTION AUDIT (the honest-exception-list test)
----------------------------------------------------------------------
Unmatched bank rows:     8  -> 8 unmatchable by design, 0 missed, 0 deferred to review
Unmatched ledger rows:   3  -> 0 unmatchable by design, 0 missed, 3 deferred to review

HONEST EXCEPTION LIST: YES (3 row(s) honestly deferred to human review)
```

### Multi-seed sweep (the anti-cherry-pick check)

"One cherry-picked match proves nothing" — neither does one seed.
`run_sweep.py` reruns the full loop across 20 seeds and aggregates:

```
SWEEP SUMMARY -- heuristic Stage 4, 20 seeds (42..61)
  precision         : mean  100.0%   min  100.0%   max  100.0%
  bank_recall       : mean  100.0%   min  100.0%   max  100.0%
  ledger_recall     : mean  100.0%   min  100.0%   max  100.0%
  f1_bank           : mean  100.0%   min  100.0%   max  100.0%
  bank_value_pct    : mean   94.3%   min   91.5%   max   97.3%
  ledger_value_pct  : mean   93.8%   min   87.0%   max   98.7%
  honest exception lists: 20/20 runs
```

The harness has already earned its keep: before a conflicting-reference guard
was added to Stage 2, the sweep caught a duplicate-amount decoy being
fuzzy-matched on seed 52 (precision 98.4%, honest list NO) — exactly the
failure mode a single-seed demo would have hidden. The guard now rejects
candidate pairs whose non-empty reference ids disagree.

### Optional local LLM path

The published deterministic benchmark is the baseline evidence. The optional
local Qwen Stage 4 runs only after the deterministic stages decline a row. Its
structured proposals are still checked for row indices, confidence, amount and
date bounds, one-to-one assignment, and conflicting non-empty references. If
the model is unavailable, the core remains usable through the guarded heuristic
fallback. Do not present an LLM score unless it has been evaluated on the
machine used for the demo.

---

## 🚀 Quick Start

### 1. Launch the Web Application
```bash
python app.py
```
Open **http://localhost:8080/dashboard.html** in your browser.

### 2. Upload and Reconcile
- Drag and drop your **Bank Statement** (PDF, Word, Excel, CSV, XML) and **Company Ledger** into the upload zone.
- Enable **"Local LLM reasoning"** only when you want the optional Qwen model to review ambiguous rows and generate narrative commentary; otherwise the dashboard stays instant in deterministic mode.
- Click **"▶ Reconcile & Build Worklist"**.
- Explore matches, inspect variances, and export reports.

### 3. CLI Batch & Evaluation Run
```bash
# Generate synthetic benchmark data (--seed N to vary; default 42)
python generate_data.py

# Run standalone reconciliation pipeline
python reconcile.py --no-llm          # fast, deterministic heuristic Stage 4
python reconcile.py                   # full LLM Stage 4 (GPU when available)
python reconcile.py --tolerance 5 --date-window 3 --confidence 60

# Run ground truth accuracy evaluation
python evaluate.py

# Multi-seed sweep: the anti-cherry-pick check
python run_sweep.py --seeds 20        # heuristic Stage 4 (fast)
python run_sweep.py --seeds 5 --llm   # LLM Stage 4 (slow)

# Intelligence modules (deterministic by default; --llm/USE_LLM=1 for polish)
USE_LLM=0 python settlement_qa.py "What happened to TXN100018?"
python -c "import cash_forecaster; print(cash_forecaster.generate_cash_forecast(use_llm=False))"
python -c "import tax_matcher; print(tax_matcher.run_tax_line_reconciliation(use_llm=False))"
```

LLM calls are greedy-decoded, chunked, retried on parse failure, and disk
cached (`.llm_cache.json`, disable with `LLM_CACHE=0`), so re-runs and seed
sweeps don't re-pay inference latency.

---

## 📁 Architecture

| File | Purpose |
|---|---|
| `app.py` | Web application server and REST API for real-time document upload & reconciliation |
| `document_parser.py` | Universal parser for PDF, Word, Excel, CSV, XML, and JSON statements |
| `dashboard.html` | Interactive frontend dashboard with drag-and-drop upload and variance inspector |
| `reconcile.py` | 5-stage explainable reconciliation engine |
| `llm_resolver.py` | GPU-accelerated local LLM resolver (`Qwen2.5-3B-Instruct`) with domain guardrails |
| `settlement_qa.py` | Settlement Q&A agent — grounded, citation-backed answers (deterministic + optional LLM polish) |
| `cash_forecaster.py` | Forward cash forecaster — 30-day liquidity trajectory, deficit alerts, treasury commentary |
| `tax_matcher.py` | Tax-line matcher — TDS (194C/194J/194Q) & GST revenue/expense verification with leak detection |
| `generate_data.py` | Synthetic financial statement generator with realistic mismatch patterns + hidden ground truth (`--seed` for reproducibility) |
| `evaluate.py` | Benchmark evaluation: precision / recall / F1, value coverage, per-scenario accuracy, exception honesty audit |
| `run_sweep.py` | Multi-seed evaluation sweep — aggregates accuracy and honesty across N seeded datasets |
| `requirements.txt` | Optional deps for the Stage 4 LLM path only (transformers, torch, accelerate) |
| `requirements-full.txt` | Optional LLM plus PDF, Word, and Excel ingestion dependencies |
| `controller_actions.py` | Policy-limited exception worklist with priority, owner, SLA, evidence, and hash-linked audit records |
| `benchmark_engine.py` | Runtime benchmark that strips hidden truth before matching and scores results afterward |
| `SUBMISSION.md` | Judge-ready project narrative |
| `SUBMISSION_CHECKLIST.md` | Application-form completion gate |
| `PITCH_VIDEO.md` | Five-minute live-demo script and recording checklist |
| `ARCHITECTURE.md` | System diagram, decision boundary, reliability controls, and production caveats |

## 📦 Repository notes

- Generated artifacts (`*.csv` outputs, `evaluation_summary.json`,
  `reconciliation_report.json`, `sweep_results/`, `.llm_cache.json`) are
  **gitignored** — everything regenerates deterministically from `--seed`ed
  commands, so the repo can never drift from its own evidence.
- `python app.py` regenerates sample data automatically on first launch if
  missing, so the 1-click dashboard demo works on a fresh clone.
- CI (`.github/workflows/ci.yml`) runs the full loop on Python 3.11 and 3.13
  at every push and **fails if precision, recall or exception honesty
  regress** — the numbers in this README are enforced, not just asserted.
