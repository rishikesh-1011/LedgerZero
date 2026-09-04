"""
llm_resolver.py

Local LLM-based resolver for ambiguous reconciliation rows (Stage 4).

Uses Hugging Face transformers to load a small instruction-tuned model
(Qwen2.5-3B-Instruct by default) directly on GPU (CUDA) or CPU.
The model auto-downloads on first run and is cached locally for subsequent runs.

Design:
  - Single responsibility: take unmatched bank/ledger rows → return proposed
    matches with confidence scores and natural-language reasoning.
  - Graceful degradation: if transformers/torch aren't installed or the model
    can't load, raises ImportError so the caller can fall back to heuristics.
  - Strict output parsing: tries json.loads, then regex extraction, then gives up.
  - Confidence threshold: only returns matches the model is ≥60% sure about.
  - Domain guardrails: validates amount/date proximity to prevent hallucinations.
  - Greedy decoding (temperature 0) so identical input → identical output.
  - Chunked prompts: bank rows are processed in groups of CHUNK_SIZE so one
    big batch can't blow the output budget; proposals are re-indexed and merged.
  - One retry per chunk with a stricter instruction if JSON parsing fails.
  - Disk cache (.llm_cache.json) keyed by model + prompt, so re-runs and seed
    sweeps don't re-pay inference latency (disable with LLM_CACHE=0).
"""

import hashlib
import json
import os
import re
import sys

# ---------------------------------------------------------------------------
# Model configuration
# ---------------------------------------------------------------------------
DEFAULT_MODEL = "Qwen/Qwen2.5-3B-Instruct"
CONFIDENCE_THRESHOLD = 60
MAX_NEW_TOKENS = 1024
TEMPERATURE = 0.0          # 0 = greedy decoding: deterministic structured output
CHUNK_SIZE = 10            # bank rows per prompt
MAX_ATTEMPTS = 2           # generation attempts per chunk before giving up
CACHE_PATH = ".llm_cache.json"

# ---------------------------------------------------------------------------
# Lazy-loaded globals (heavy imports happen only when actually called)
# ---------------------------------------------------------------------------
_pipeline = None
_model_name = None


def _load_model(model_name=None):
    """Load the model pipeline once, cache it globally."""
    global _pipeline, _model_name

    if _pipeline is not None and _model_name == (model_name or DEFAULT_MODEL):
        return _pipeline

    model_name = model_name or DEFAULT_MODEL
    print(f"  [LLM] Loading model: {model_name} ...")
    print(f"  [LLM] (First run downloads ~2-3 GB — subsequent runs use cache)")

    import torch
    from transformers import pipeline as hf_pipeline

    device_str = "cuda" if torch.cuda.is_available() else "cpu"
    torch_dtype = torch.float16 if torch.cuda.is_available() else torch.float32

    print(f"  [LLM] Running on device: {device_str.upper()} (dtype: {torch_dtype})")

    _pipeline = hf_pipeline(
        "text-generation",
        model=model_name,
        dtype=torch_dtype,
        device_map="auto" if torch.cuda.is_available() else None,
    )
    _model_name = model_name
    print(f"  [LLM] Model loaded successfully.")
    return _pipeline


# ---------------------------------------------------------------------------
# Response cache (best-effort; avoids re-paying LLM latency on re-runs)
# ---------------------------------------------------------------------------
def _cache_enabled():
    return os.environ.get("LLM_CACHE", "1").strip().lower() not in ("0", "false", "no")


def _cache_key(model_name, system_prompt, user_prompt):
    payload = json.dumps({"model": model_name,
                          "system": system_prompt,
                          "user": user_prompt}, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _cache_get(key):
    if not _cache_enabled() or not os.path.exists(CACHE_PATH):
        return None
    try:
        with open(CACHE_PATH, encoding="utf-8") as f:
            return json.load(f).get(key)
    except (OSError, json.JSONDecodeError):
        return None


def _cache_put(key, proposals):
    if not _cache_enabled():
        return
    try:
        data = {}
        if os.path.exists(CACHE_PATH):
            with open(CACHE_PATH, encoding="utf-8") as f:
                data = json.load(f)
        data[key] = proposals
        with open(CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f)
    except (OSError, json.JSONDecodeError):
        pass  # cache is best-effort; never fail the pipeline over it


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------
def _build_prompt(bank_rows, ledger_rows):
    """Build a structured prompt for the LLM to propose matches."""

    bank_data = []
    for i, b in enumerate(bank_rows):
        bank_data.append({
            "bank_id": f"B{i}",
            "amount": round(b["amount"], 2),
            "date": b["date"].strftime("%Y-%m-%d"),
            "reference_id": b.get("reference_id", ""),
            "vendor": b.get("vendor", ""),
        })

    ledger_data = []
    for i, l in enumerate(ledger_rows):
        ledger_data.append({
            "ledger_id": f"L{i}",
            "amount": round(l["amount"], 2),
            "date": l["date"].strftime("%Y-%m-%d"),
            "reference_id": l.get("reference_id", ""),
            "vendor": l.get("vendor", ""),
        })

    system_prompt = """You are a financial reconciliation expert. You will be given unmatched bank statement rows and ledger rows that could not be matched by automated rules.

Your task: propose which bank row matches which ledger row, if any reasonable match exists.

RULES:
1. A match means the bank row and ledger row represent the SAME real-world transaction.
2. Consider:
   - Amounts must be close (small rounding differences of +/-5 to 10 rupees are normal, but amounts with completely different orders of magnitude are NOT matches).
   - Dates must be close (1-5 days settlement delays are normal).
   - Vendor names should match or be variations/abbreviations/typos of each other.
3. Bank fees, decoys, or unmatched orphans must NOT be matched to unrelated transactions. Set ledger_id to null.
4. Each bank row can match AT MOST one ledger row, and vice versa.
5. Assign a confidence score from 0 to 100 for each proposed match.

RESPOND WITH ONLY a valid JSON array. Each element must have exactly these fields:
[
  {
    "bank_id": "B0",
    "ledger_id": "L0",
    "confidence": 90,
    "reason": "<short explanation>"
  }
]

Do NOT include any text outside the JSON array. No markdown, no explanation, just the JSON."""

    user_prompt = f"""Here are the unmatched rows:

BANK ROWS:
{json.dumps(bank_data, indent=2)}

LEDGER ROWS:
{json.dumps(ledger_data, indent=2)}

Propose matches as a JSON array:"""

    return system_prompt, user_prompt


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------
def _parse_llm_response(raw_text):
    """Extract structured match proposals from LLM output."""
    raw_text = raw_text.strip()

    # Strip markdown code blocks if present
    if raw_text.startswith("```"):
        raw_text = re.sub(r"^```(?:json)?\s*", "", raw_text)
        raw_text = re.sub(r"\s*```$", "", raw_text)
        raw_text = raw_text.strip()

    # Strategy 1: direct parse
    try:
        result = json.loads(raw_text)
        if isinstance(result, list):
            return result
    except json.JSONDecodeError:
        pass

    # Strategy 2: regex extract the first JSON array
    match = re.search(r'\[[\s\S]*?\](?=\s*$|\s*[^,\]\}])', raw_text)
    if not match:
        match = re.search(r'\[.*\]', raw_text, re.DOTALL)
    if match:
        try:
            result = json.loads(match.group())
            if isinstance(result, list):
                return result
        except json.JSONDecodeError:
            pass

    raise ValueError(f"Could not parse LLM response as JSON array. Raw: {raw_text[:500]}")


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------
def _generate_chunk(pipe, bank_chunk, ledger_rows, model_name):
    """Run one bank-row chunk through the model, with retry on parse failure.

    Returns the parsed proposal list; bank ids inside are chunk-local
    ("B0" refers to the first row of THIS chunk).
    """
    system_prompt, user_prompt = _build_prompt(bank_chunk, ledger_rows)
    key = _cache_key(model_name, system_prompt, user_prompt)

    cached = _cache_get(key)
    if cached is not None:
        print(f"  [LLM] cache hit for chunk of {len(bank_chunk)} bank row(s)")
        return cached

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    print(f"  [LLM] Sending {len(bank_chunk)} bank + {len(ledger_rows)} ledger rows to model ...")

    # Greedy decoding when TEMPERATURE == 0: same input, same structured output.
    gen_kwargs = {"max_new_tokens": MAX_NEW_TOKENS,
                  "do_sample": TEMPERATURE > 0,
                  "return_full_text": False}
    if TEMPERATURE > 0:
        gen_kwargs["temperature"] = TEMPERATURE

    last_err = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        output = pipe(messages, **gen_kwargs)

        raw_text = output[0]["generated_text"]
        if isinstance(raw_text, list):
            raw_text = raw_text[-1].get("content", str(raw_text[-1]))

        print(f"  [LLM] Got response ({len(raw_text)} chars), parsing ...")
        try:
            proposals = _parse_llm_response(raw_text)
            _cache_put(key, proposals)
            return proposals
        except ValueError as e:
            last_err = e
            if attempt < MAX_ATTEMPTS:
                print("  [LLM] unparseable response — retrying with stricter instruction ...")
                messages = messages + [
                    {"role": "assistant", "content": raw_text[:500]},
                    {"role": "user", "content":
                     "That was not a valid JSON array. Respond with ONLY the "
                     "JSON array, no other text."},
                ]

    raise last_err


def resolve_ambiguous(bank_rows, ledger_rows, model_name=None, confidence_threshold=None):
    """
    Ask a local LLM to propose matches for ambiguous leftover rows.

    Args:
        bank_rows:   list of unmatched bank dicts (with 'amount', 'date',
                     'reference_id', 'vendor' keys)
        ledger_rows: list of unmatched ledger dicts (same keys)
        model_name:  HuggingFace model ID (default: Qwen2.5-3B-Instruct)
        confidence_threshold: 0-100; defaults to CONFIDENCE_THRESHOLD

    Returns:
        list of dicts, each with:
          - bank_index: int
          - ledger_index: int or None
          - confidence: int (0-100)
          - reason: str
    """
    if not bank_rows or not ledger_rows:
        return []

    threshold = (CONFIDENCE_THRESHOLD if confidence_threshold is None
                 else int(confidence_threshold))
    pipe = _load_model(model_name)
    model_name = model_name or DEFAULT_MODEL

    # Chunked prompts keep each response well inside the token budget;
    # chunk-local bank ids (B0, B1, ...) are re-offset to the full list here.
    proposals = []
    for start in range(0, len(bank_rows), CHUNK_SIZE):
        chunk = bank_rows[start:start + CHUNK_SIZE]
        chunk_proposals = _generate_chunk(pipe, chunk, ledger_rows, model_name)
        for p in chunk_proposals:
            raw_bi = p.get("bank_id", p.get("bank_index"))
            try:
                n = int(str(raw_bi)[1:]) if str(raw_bi).startswith("B") else int(raw_bi)
                p["bank_id"] = f"B{n + start}"
            except (ValueError, TypeError):
                p["bank_id"] = "B-1"
        proposals.extend(chunk_proposals)

    # Filter by confidence threshold and validate indices & domain constraints
    valid = []
    for p in proposals:
        try:
            # Parse bank index (supports "B0" or 0)
            raw_bi = p.get("bank_id", p.get("bank_index"))
            if isinstance(raw_bi, str) and raw_bi.startswith("B"):
                bi = int(raw_bi[1:])
            else:
                bi = int(raw_bi)

            raw_li = p.get("ledger_id", p.get("ledger_index"))
            if raw_li is None or str(raw_li).lower() in ("null", "none", ""):
                continue

            if isinstance(raw_li, str) and raw_li.startswith("L"):
                li = int(raw_li[1:])
            else:
                li = int(raw_li)

            conf = int(p.get("confidence", 0))
            reason = str(p.get("reason", "LLM proposed match"))

            if bi < 0 or bi >= len(bank_rows) or li < 0 or li >= len(ledger_rows):
                continue

            b = bank_rows[bi]
            l = ledger_rows[li]

            if (b.get("reference_id") and l.get("reference_id")
                    and b["reference_id"] != l["reference_id"]):
                print(f"  [LLM Guardrail] Rejected bank[{bi}] ↔ ledger[{li}]: conflicting reference ids")
                continue

            # Domain guardrail: prevent hallucinations between wildly different transactions
            amount_diff = abs(b["amount"] - l["amount"])
            date_diff = abs((b["date"] - l["date"]).days)

            # Amount difference must be within reasonable rounding/fee tolerance (Rs. 10.0 or 1%)
            max_allowed_diff = max(10.0, l["amount"] * 0.02)
            if amount_diff > max_allowed_diff:
                print(f"  [LLM Guardrail] Rejected bank[{bi}] (Rs.{b['amount']}) ↔ ledger[{li}] (Rs.{l['amount']}): amount diff {amount_diff:.2f} > {max_allowed_diff:.2f}")
                continue

            if date_diff > 7:
                print(f"  [LLM Guardrail] Rejected bank[{bi}] ↔ ledger[{li}]: date diff {date_diff}d > 7d")
                continue

            if conf < threshold:
                print(f"  [LLM] Skipping bank[{bi}]↔ledger[{li}]: confidence {conf}% < {threshold}% threshold")
                continue

            valid.append({
                "bank_index": bi,
                "ledger_index": li,
                "confidence": conf,
                "reason": reason,
            })
        except (ValueError, TypeError, KeyError):
            continue

    # Deduplicate: keep highest confidence
    used_bank = {}
    used_ledger = {}
    valid.sort(key=lambda x: -x["confidence"])
    deduped = []
    for v in valid:
        if v["bank_index"] not in used_bank and v["ledger_index"] not in used_ledger:
            deduped.append(v)
            used_bank[v["bank_index"]] = True
            used_ledger[v["ledger_index"]] = True

    print(f"  [LLM] {len(deduped)} match(es) accepted after guardrail validation "
          f"(threshold {threshold}%)")
    return deduped
