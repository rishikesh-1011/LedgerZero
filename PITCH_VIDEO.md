# Five-Minute Pitch Video Plan

## Submission standard

Record a **4:45–5:00 live screen walkthrough** of the running app and upload
it as an unlisted video. The local `pitch_video.mp4` is a 2:10.98 product
teaser, so it is not the submission video for a form that asks for five
minutes. Use it only as visual reference, not as the final evidence.

The pitch must demonstrate the working product, measured evidence, the LLM
decision boundary, and a real failure recovery. A polished animation alone is
not enough for this rubric.

## Recording preflight

1. Run `python generate_data.py --seed 42`, then `python app.py`.
2. Open `http://localhost:8080/dashboard.html` at 100% browser zoom.
3. Click **Reset** in the Controller Close Worklist, then **Load Sample Data**.
   Loading the sample automatically runs the reconciliation and builds its
   worklist.
4. Keep **Local LLM reasoning** off for the primary reconciliation. Turn it on
   only if the local model is already installed and warm; the deterministic
   path is the reliable demo path.
5. Open one exact match, one split-payment match, one exception, the
   Controller Close Worklist, and the Benchmark Suite before recording.
6. Record a 1920×1080 screen with clear microphone audio. Hide terminals,
   local paths, notifications, credentials, and browser extensions.
7. End on the proof commands, not a logo animation. Upload the final MP4 as
   unlisted and paste the resulting URL into the application form.

## Timed talk track

### 00:00–00:25 — Problem and promise

**Screen:** Dashboard landing view.

> Finance close teams still spend days proving that bank statements, ERP
> ledgers, and tax records agree. LedgerZero is an AI Finance Controller for
> that verification loop. It ingests finance feeds, reconciles only what it
> can prove, leaves uncertainty visible, and turns every unresolved item into
> an accountable next action.

### 00:25–00:55 — Real batch, not a cherry-picked pair

**Screen:** Click **Load Sample Data**, then show both source cards and the
completed reconciliation.

> This is a seeded batch with more than fifty records and deliberately mixed
> cases: exact payments, amount and date drift, vendor variants, split
> settlements, fees, missing counterparts, and conflicting-reference decoys.
> We accept common statement formats and normalize the amount, date,
> reference, and vendor fields before matching. The useful metric is not a
> pretty match rate; it is a match rate with evidence and an honest exception
> list.

### 00:55–01:35 — Explain the deterministic core

**Screen:** Reconciliation funnel and then an exact match detail drawer.

> The core is a five-stage, explainable funnel. Stage one requires the same
> non-empty reference and cent-normalized amount. Stage two applies a bounded
> vendor, date, and amount window. Stage three searches only two- or
> three-payment combinations for a split settlement. These decisions are
> deterministic on purpose: an LLM should not calculate money or decide an
> exact reference. Every accepted row exposes the rule and source evidence
> that produced it.

### 01:35–02:05 — Show the system refusing to guess

**Screen:** Open an exception, especially a conflicting reference or bank fee.

> This is the behavior that makes the controller safe. A bank fee without a
> ledger counterpart remains a bank fee. A conflicting non-empty reference is
> rejected even when its amount and vendor look tempting. We do not force a
> pair just to improve the dashboard percentage. The result is an exception
> queue with a reason, source, owner, value, and next step.

### 02:05–02:45 — Close the finance-operations loop

**Screen:** Scroll to **Controller Close Worklist**. Resolve one eligible bank
fee, then show its audit entry.

> Reconciliation is not useful if it ends in a spreadsheet. Here each
> exception becomes a controller work item with priority, SLA, owner, evidence,
> and financial exposure. Automation is deliberately narrow: only an eligible
> low-value bank fee below the configured ₹500 policy limit can be batch-booked.
> Critical review cases cannot be auto-resolved. A resolution gets a stable
> action ID, journal reference, and locally verifiable hash-chain audit event.

### 02:45–03:20 — Prove the metric live

**Screen:** Open **Benchmark Suite (500+ Txns)** and click **Re-Run Benchmark
Stress Test**.

> This benchmark is generated at runtime. Its truth labels are retained only
> by the scorer; the matcher never receives them. The modal reports measured
> throughput, precision, recall, false-positive rate, collisions, and the
> exception categories for this run. That protects us from a screenshot with
> hard-coded claims and lets a reviewer repeat the evidence on the same seed.

### 03:20–03:50 — Explain exactly where the LLM belongs

**Screen:** Open a Stage 4 detail or point to the Local LLM toggle.

> Yes, this project uses an LLM, but only where language helps. The optional
> local Qwen 2.5 3B path sees unresolved rows after deterministic rules have
> declined them. It returns structured proposals that still must pass a
> confidence threshold, amount and date bounds, one-to-one deduplication, and
> the conflicting-reference guardrail. If that proof is missing, the item stays
> in human review.

### 03:50–04:20 — Show downstream value briefly

**Screen:** Settlement Q&A, then Forecast or Tax Controls.

> The same audited reconciliation state powers the Settlement Q&A, forward cash
> forecast, and tax-line controls. These are not separate demo datasets: they
> answer finance questions from the report the controller just produced. The
> core win remains verification and exception control; the supporting modules
> make that verified state useful for treasury and finance operations.

### 04:20–04:45 — Answer “what broke, and how did you get out?”

**Screen:** Open the **Buildathon Dossier** modal.

> Two issues forced an architectural change. Binary float comparison can create
> split-payment boundary drift, and same-amount decoys can be falsely attractive
> if reference conflicts are ignored. We moved money comparisons to integer
> paise, hard-blocked conflicting non-empty references, chunked the optional
> LLM path, and rebuilt the benchmark around hidden truth with runtime scoring.
> Bad uploads also fail safely with a clear error rather than an internal stack
> trace.

### 04:45–05:00 — Close with reproducibility

**Screen:** Terminal or repository README with the commands visible.

> LedgerZero is not asking you to trust a single demo match. Run the seeded
> reconciliation, evaluation, multi-seed sweep, and web smoke test yourself.
> It is a finance controller that prefers an honest exception over an invented
> answer. That is the standard we would trust at close.

## Upload checklist

- [ ] Duration is between 4:45 and 5:00.
- [ ] Voice is intelligible without background music.
- [ ] The video shows the live dashboard, not only slides.
- [ ] The benchmark is run live and its values are not narrated as fixed.
- [ ] The LLM is described as optional and guarded.
- [ ] The failure-recovery story is shown in the dossier and stated clearly.
- [ ] No secret, personal data, proprietary data, or local path is visible.
- [ ] Video is uploaded as unlisted and the URL is pasted into the form.
