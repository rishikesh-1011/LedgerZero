# LedgerZero — AI Finance Controller

**Razorpay Buildathon 2026 · Track 04: AI Finance Controller**

LedgerZero closes a finance-operations loop instead of stopping at a dashboard:

1. Ingest a bank statement and ERP ledger in common business formats.
2. Reconcile a 50+ record batch through explainable exact, fuzzy, and
   split-payment stages.
3. Measure precision, recall, collisions, and exception honesty against hidden
   synthetic truth.
4. Convert each unresolved row into an assigned controller work item with
   evidence, SLA, owner, and value at risk.
5. Resolve only policy-eligible low-value bank fees and retain a locally
   verifiable hash-linked audit record.

## Why this is a strong Track 04 entry

- **Truth over throughput:** uncertain rows remain exceptions rather than being
  force-matched to make the percentage look better.
- **Measured, reproducible proof:** a seeded generator, hidden-truth evaluator,
  runtime benchmark, and multi-seed sweep make the result repeatable.
- **Correct AI placement:** deterministic rules handle money, references, and
  split arithmetic; the optional local Qwen2.5-3B model only reviews unresolved
  ambiguity and its proposals still pass hard validation.
- **Closed-loop operations:** exceptions carry accountable next steps rather
  than becoming a passive review table.
- **Failure recovery:** cent-normalized money comparisons, reference-conflict
  rejection, bounded uploads, safe client errors, and policy-limited resolution
  are visible in the product and tests.

## Judge assets

- [`ARCHITECTURE.md`](ARCHITECTURE.md) — end-to-end system design, LLM decision
  boundary, reliability controls, and production caveats.
- [`PITCH_VIDEO.md`](PITCH_VIDEO.md) — exact five-minute live-demo storyboard,
  narration, and upload checklist.
- [`SUBMISSION_CHECKLIST.md`](SUBMISSION_CHECKLIST.md) — all twelve application
  fields, paste-ready build answers, and manual submission steps.

## Evidence commands

```bash
python generate_data.py --seed 42
python reconcile.py --no-llm
python evaluate.py
python run_sweep.py --seeds 20
python benchmark_engine.py
python test_web_ui.py
```

The deterministic core and dashboard work without an LLM download. For optional
PDF, Word, and Excel parsing, install `requirements-full.txt`; for optional
local LLM review, install `requirements.txt` and enable **Local LLM reasoning**
in the dashboard only after the model is available.
