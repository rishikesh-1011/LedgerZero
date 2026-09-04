# Razorpay Buildathon Submission Gate

## Form fields from the application

| Form field | Status | What to submit |
|---|---|---|
| Full name | Manual | Your legal/preferred application name. |
| College | Manual | Your college name. |
| Graduation year | Manual | Your graduation year. |
| In-person from September | Manual | Answer yes/no accurately. |
| Six or twelve months | Manual | Choose the term you can honor. |
| Resume file | Manual | Upload the final PDF resume. |
| Track | Ready | `AI Finance Controller — Track 04` |
| Project name | Ready | `LedgerZero — AI Finance Controller` |
| What it solves | Ready | Use the paste-ready answer below. |
| GitHub repo URL, public | Manual | Push this repo publicly and replace the placeholder below. |
| Five-minute pitch video | Manual | Record with `PITCH_VIDEO.md`, upload unlisted, paste the URL. |
| What broke and how you got out | Ready | Use the paste-ready answer below. |

## Paste-ready project answer

**Project name**

`LedgerZero — AI Finance Controller`

**What it solves**

LedgerZero closes the bank-to-ledger reconciliation loop for finance teams.
It ingests common bank and ERP statement formats, reconciles a 50+ record batch
through explainable exact, fuzzy, and split-payment stages, and reports a
measured match rate alongside an honest exception list. Each exception becomes
an assigned controller work item with evidence, SLA, exposure, and a
policy-limited resolution path. An optional local LLM is used only for
unresolved ambiguity; it never performs arithmetic, overrides a conflicting
reference, or turns uncertainty into a forced match.

**What broke, and how you got out**

Two failure modes appeared as the batch became realistic: binary-float amount
comparison could create split-payment boundary drift, and same-amount decoys
could be falsely attractive when reference conflicts were ignored. We moved
Stages 1–3 to cent-normalized comparisons, rejected conflicting non-empty
references across deterministic and LLM paths, and made Stage 4 an optional,
chunked, schema-checked proposal layer. We also rebuilt the benchmark so hidden
truth is stripped before matching and used only for runtime precision, recall,
collision, and exception-honesty scoring. Malformed uploads now fail safely
without exposing an internal traceback.

**Repository and video placeholders**

```text
GitHub: https://github.com/<your-handle>/ledgerzero-ai-finance-controller
Pitch:  https://<unlisted-video-url>
```

## Evidence a reviewer can run

```bash
python generate_data.py --seed 42
python reconcile.py --no-llm
python evaluate.py
python run_sweep.py --seeds 20
python benchmark_engine.py
python test_web_ui.py
```

## Final 15-minute submission sequence

1. Run the commands above and capture clean terminal output.
2. Record and upload the five-minute live pitch using `PITCH_VIDEO.md`.
3. Push the repository to GitHub and make it public.
4. Replace the GitHub and video placeholders with final URLs.
5. Paste the two prepared answers, then fill personal fields and resume.
6. Re-open the public repository in an incognito browser and verify that the
   README, `ARCHITECTURE.md`, `PITCH_VIDEO.md`, and source files render.
