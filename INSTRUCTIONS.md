# LedgerZero — Complete Instruction & Operations Manual

**Track 04: AI Finance Controller — Razorpay AI Buildathon 2026**

This document provides a detailed, step-by-step operational guide for setting up, running, testing, benchmarking, and presenting **LedgerZero**.

---

## 📑 Table of Contents

1. [System Overview & Architecture](#-system-overview--architecture)
2. [Prerequisites & Environment Setup](#-prerequisites--environment-setup)
3. [Running the Interactive Web Dashboard](#-running-the-interactive-web-dashboard)
4. [Using the 4 Core Dashboard Modules](#-using-the-4-core-dashboard-modules)
5. [Running the CLI Benchmark Pipeline](#-running-the-cli-benchmark-pipeline)
6. [AI & LLM (Qwen 2.5-3B) Operations](#-ai--llm-qwen-25-3b-operations)
7. [Multi-Format Document Ingestion](#-multi-format-document-ingestion)
8. [Multi-Seed Sweeps & Stress Testing](#-multi-seed-sweeps--stress-testing)
9. [Troubleshooting & FAQs](#-troubleshooting--faqs)

---

## 🧠 System Overview & Architecture

LedgerZero is built as a **Bimodal Hybrid Architecture**:
* **Deterministic Core (Stages 1–3):** 100% mathematical precision with zero hallucinations, 0 token costs, and sub-millisecond execution.
* **Local LLM Layer (Stage 4 & Q&A Copilot):** `Qwen2.5-3B-Instruct` running on-device (CUDA GPU or CPU) for grounded conversational audit investigation, root-cause citation, and executive treasury forecasting.
* **Graceful Degradation:** If no GPU or PyTorch is present, the system automatically falls back to deterministic rule synthesis with **zero errors and zero crashes**.

```
                           ┌───────────────────────────────────────────────┐
                           │      Ingestion: Multi-Format Parser           │
                           │  (PDF, Word .docx, Excel .xlsx, CSV, XML, JSON)│
                           └───────────────────────┬───────────────────────┘
                                                   │
                                                   ▼
┌───────────────────────────────────────────────────────────────────────────────────────────────────┐
│                              5-STAGE RECONCILIATION ENGINE                                        │
│                                                                                                   │
│  Stage 1: Exact Reference Match (O(1) Hash Map) ───────────► Auto-Clear (100% Conf)              │
│  Stage 2: Fuzzy & Business Suffix Inverted Index ─────────► Auto-Clear (90-95% Conf)             │
│  Stage 3: Split-Payment Many-to-One Subset Sum ───────────► Auto-Clear (85-90% Conf)             │
│  Stage 4: Residual Ambiguity Disambiguation ──────────────► Qwen-2.5 3B (GPU) OR Heuristic Engine │
│  Stage 5: Exception & Decoy Classification ───────────────► Actionable Review Queue (0 Halluc.)  │
└──────────────────────────────────────────────────┬────────────────────────────────────────────────┘
                                                   │
                                                   ▼
┌───────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                  AUDIT & TREASURY INTELLIGENCE                                    │
│                                                                                                   │
│  • Autonomous Settlement Q&A Copilot (Grounded Citations via Qwen-2.5 3B)                         │
│  • Forward Cash Forecaster (30-Day Monte Carlo Liquidity Burn + CFO Brief)                       │
│  • Statutory Tax-Line Matcher (TDS Sec 194C/J + GST 2% Withholding)                              │
└───────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## ⚙️ Prerequisites & Environment Setup

LedgerZero runs across all major operating systems (**Windows, macOS, Linux**).

### 1. Python Requirement
* Python **3.10, 3.11, 3.12, 3.13, or 3.14** installed.
* Verify your installation:
  ```bash
  python --version
  ```

### 2. Choose Your Execution Mode:

#### Mode A: Zero-Dependency Lightweight Mode (Default)
Runs 100% out of the box using Python's standard library. Ideal for fast CI checks, laptops without GPUs, or quick evaluation.
```bash
# No external package installation required!
python app.py
```

#### Mode B: Full GPU AI + Multi-Format Ingestion Mode (Recommended for Full Demo)
Installs PyTorch, Transformers, Accelerate (for Qwen LLM on CUDA), plus PDF/Word/Excel parsers:
```bash
pip install -r requirements-full.txt
```

---

## 🖥️ Running the Interactive Web Dashboard

### Starting the Server
From the project root directory, run:
```bash
python app.py
```

* The server starts at: **`http://localhost:8080/dashboard.html`**
* On Windows, you can also launch directly by double-clicking `LedgerZero.exe`.

### Key Server Command-Line Arguments:
```bash
python app.py --port 8080               # Specify custom port
python app.py --host 0.0.0.0            # Bind to all network interfaces
USE_LLM=0 python app.py                 # Force deterministic mode (no LLM)
```

---

## 🔍 Using the 4 Core Dashboard Modules

Open `http://localhost:8080/dashboard.html` in your browser.

### 1. Ingestion & Multi-Source Reconciliation Tab
1. Click **"Load Benchmark Sample"** or drag-and-drop your custom Bank and Ledger files (`.pdf`, `.docx`, `.xlsx`, `.csv`, `.xml`, `.json`).
2. Click **"Execute 5-Stage Reconciliation"**.
3. View instant metrics:
   * Overall Match Rate (%)
   * Reconciled Value vs Unreconciled Variance
   * Breakdown by Tier: Exact (Stage 1), Fuzzy (Stage 2), Split-Payment (Stage 3), AI Resolved (Stage 4).
   * **Honest Human Review Queue:** Unmatched decoys, bank charges, and orphans requiring review.

### 2. Autonomous Settlement & Citation Q&A Agent Tab
1. Ask questions in natural language in the chat input.
2. **Sample Questions to Try:**
   * `"What happened to TXN100018?"` (Direct reference lookup)
   * `"Summarize BlueOne Logistics"` (Vendor-level transaction history)
   * `"Audit all unlogged bank charges"` (Isolates fee debits)
   * `"Explain human review queue"` (Root causes for unresolved exceptions)
   * `"Executive match health summary"` (High-level CFO briefing)
3. Notice that every response quotes grounded transaction IDs, exact rupee amounts (₹), dates, and match tiers.

### 3. Forward Cash Forecaster & Liquidity Risk Tab
1. Set the **Opening Balance** (e.g., `₹5,000,000`) and **Forecast Horizon** (e.g., `30 Days`).
2. Click **"Generate Treasury Forecast"**.
3. Inspect:
   * Predicted End Balance
   * Minimum Projected Cash Trough & Trough Date
   * Liquidity Risk Status (Low / Moderate / High / Critical)
   * CFO Narrative Commentary synthesized by AI.

### 4. Statutory Tax-Line Matcher Tab
1. Automatically isolates tax deduction lines (TDS 194C at 1% / 2%, TDS 194J at 10%, GST TDS at 2%).
2. Matches net bank transfers back to gross ledger entries by reconstructing tax withholdings.

---

## 📊 Running the CLI Benchmark Pipeline

For automated testing, CI/CD, or headless evaluation without the UI:

### Step 1: Generate Synthetic Dataset with Hidden Ground Truth
```bash
python generate_data.py --seed 42 --count 75
```
* Generates `bank_statement.csv`, `company_ledger.csv`, and `ground_truth.csv`.
* Injects realistic financial edge cases: settlement delays (T+1 to T+3), split payments, business suffix variations, rounding errors, tax withholdings, decoys, and unlogged bank charges.

### Step 2: Run the Reconciliation Engine
```bash
# With local Qwen LLM on GPU:
python reconcile.py

# Without LLM (Zero-dependency heuristic fallback):
python reconcile.py --no-llm

# Custom date window and tolerance:
python reconcile.py --tolerance 10.0 --date-window 5 --confidence 60
```
* Outputs: `matches.csv`, `exceptions.csv`, and `reconciliation_report.json`.

### Step 3: Run the Ground Truth Evaluation Benchmark
```bash
python evaluate.py
```
* Compares `matches.csv` against `ground_truth.csv`.
* Evaluates:
  * **Precision:** Percentage of proposed matches that are strictly correct (Target: **100.0%**).
  * **Recall:** Percentage of matchable entries successfully resolved (Target: **100.0%**).
  * **F1-Score:** Harmonic mean of precision and recall.
  * **Honest Exception Test:** Confirms unmatchable decoys and fees were not hallucinated.

---

## 🤖 AI & LLM (Qwen 2.5-3B) Operations

### How Model Loading Works
* **Model Used:** `Qwen/Qwen2.5-3B-Instruct`
* **Weight Storage:** Weights (~3.1 GB `safetensors`) are cached locally in:
  `~/.cache/huggingface/hub/models--Qwen--Qwen2.5-3B-Instruct`
* **Device Acceleration:** Automatically selects **CUDA (float16)** on NVIDIA GPUs; falls back to CPU if no CUDA GPU is detected.

### Pre-warming / Downloading the Model (One-Time)
To pre-cache the model before a demo so there is zero initial download latency:
```bash
python -c "import llm_resolver; llm_resolver._load_model()"
```

### Disabling the LLM
If running in low-resource environments (e.g., CI runners, non-GPU laptops), disable the LLM globally via environment variable:
```bash
# Linux / macOS:
export USE_LLM=0
python app.py

# Windows PowerShell:
$env:USE_LLM="0"
python app.py
```

---

## 📁 Multi-Format Document Ingestion

LedgerZero automatically extracts and normalizes tabular financial data across 7 formats:

| Format | Extension | Parser Engine |
| :--- | :--- | :--- |
| **PDF Statements** | `.pdf` | `pypdf` / `pdfplumber` text & table extractor |
| **Word Documents** | `.docx` | `python-docx` XML table parser |
| **Excel Spreadsheets**| `.xlsx`, `.xls`| `openpyxl` / `xlrd` multi-sheet engine |
| **Comma-Separated** | `.csv`, `.tsv`, `.txt` | Python standard `csv.Sniffer` |
| **Structured Data** | `.json`, `.xml` | `json` / `xml.etree.ElementTree` |

### Column Auto-Mapper Heuristics:
The ingestion engine automatically identifies standard and non-standard column headers:
* **Amount:** `amount`, `amt`, `transaction_amount`, `debit`, `credit`, `total`, `value`
* **Date:** `date`, `txn_date`, `value_date`, `posting_date`, `settlement_date`
* **Reference ID:** `reference_id`, `ref`, `utr`, `txn_id`, `invoice_no`, `chq_no`
* **Vendor / Description:** `vendor`, `party_name`, `narration`, `description`, `beneficiary`

---

## 🧪 Multi-Seed Sweeps & Stress Testing

To verify that accuracy is robust and not cherry-picked on a single random seed:

```bash
# Run a 20-seed sweep across randomized seeds:
python run_sweep.py --seeds 20

# Run a 50-seed stress test:
python run_sweep.py --seeds 50 --count 100
```

The sweep outputs a comprehensive summary table with mean, min, and max Precision, Recall, and F1 across all seeds.

---

## 🛠️ Troubleshooting & FAQs

### 1. Port 8080 is already in use
Specify an alternate port when running `app.py`:
```bash
python app.py --port 8090
```
Then visit `http://localhost:8090/dashboard.html`.

### 2. Unicode / Windows Terminal Encoding issues with ₹ symbol
If running in standard Windows Command Prompt (cmd.exe), enable UTF-8 support:
```cmd
chcp 65001
```
Or run commands in **PowerShell** or **Windows Terminal**.

### 3. GPU Out of Memory (OOM)
`Qwen2.5-3B-Instruct` in float16 requires only **~3.5 GB of VRAM**. If running alongside heavy GPU applications, clear VRAM or switch to CPU mode:
```bash
$env:USE_LLM="0"
python app.py
```

### 4. Running the Smoke Test Suite
To verify that all web endpoints, parsers, and reconciliation logic are functioning:
```bash
python test_web_ui.py
```

---

## 🏆 Key Commands Cheat Sheet

| Action | Command |
| :--- | :--- |
| **Start Web App** | `python app.py` |
| **Generate Benchmark Data** | `python generate_data.py --seed 42` |
| **Run CLI Reconciliation** | `python reconcile.py` |
| **Run Fast No-LLM Reconcile** | `python reconcile.py --no-llm` |
| **Evaluate Ground Truth** | `python evaluate.py` |
| **Run 20-Seed Robustness Sweep**| `python run_sweep.py --seeds 20` |
| **Run Automated UI Smoke Test** | `python test_web_ui.py` |
| **Pre-Cache Qwen 2.5-3B Model** | `python -c "import llm_resolver; llm_resolver._load_model()"` |

---

*LedgerZero — Built with precision for Razorpay Track 04.*
