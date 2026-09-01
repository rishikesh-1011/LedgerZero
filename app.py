"""
app.py

Full-featured Web App & Reconciliation API Server for AI Finance Controller.
Serves the interactive multi-module platform:
  - 5-Stage Multi-Source Reconciliation Engine
  - Settlement Q&A Agent (GPU LLM)
  - Forward Cash Forecaster & Liquidity Risk Engine
  - Tax-Line Matcher & Statutory Withholding Engine (TDS & GST)

Run:
  python app.py
  (Opens http://localhost:8080/dashboard.html)
"""

import base64
import http.server
import json
import os
import socketserver
import sys
from datetime import datetime

import document_parser
import reconcile
from reconcile import (
    stage1_exact, stage2_fuzzy, stage3_split_payments, stage4_escalate
)
import settlement_qa
import cash_forecaster
import tax_matcher

# Interactive uploads should feel instant: default Stage 4 to the
# deterministic heuristic (<1s).  Set APP_USE_LLM=1 to use the GPU LLM
# for ambiguous rows instead (first call loads the model, ~30-60s).
# The Q&A / forecast / tax endpoints keep their own per-request use_llm.
if os.environ.get("APP_USE_LLM", "0").strip().lower() not in ("1", "true", "yes"):
    reconcile.USE_LLM = False

PORT = 8080
DIRECTORY = os.path.dirname(os.path.abspath(__file__))


def reconcile_records(bank_rows, ledger_rows):
    """Run the 5-stage reconciliation pipeline on in-memory row lists."""
    total_bank, total_ledger = len(bank_rows), len(ledger_rows)

    bank = [dict(r) for r in bank_rows]
    ledger = [dict(r) for r in ledger_rows]

    all_matches = []
    all_matches += stage1_exact(bank, ledger)
    all_matches += stage2_fuzzy(bank, ledger)
    all_matches += stage3_split_payments(bank, ledger)
    s4_matches, review_rows = stage4_escalate(bank, ledger)
    all_matches += s4_matches
    review_ids = {id(r) for r in review_rows}

    def action_for(row):
        if id(row) in review_ids:
            return "needs_human_review"
        if row.get("vendor") == "Bank Charges":
            return "likely_bank_fee"
        return "investigate_orphan"

    def reason_for(row):
        if id(row) in review_ids:
            return "matcher declined to guess (ambiguous; needs human review)"
        if row.get("vendor") == "Bank Charges":
            return "bank charge with no ledger counterpart"
        return "no confident match found in the other system"

    tier_counts = {}
    for m in all_matches:
        tier_counts[m["tier"]] = tier_counts.get(m["tier"], 0) + 1

    matched_bank_rows = sum(
        (len(m["bank"]) if isinstance(m["bank"], list) else 1) for m in all_matches
    )
    match_rate = (matched_bank_rows / total_bank * 100) if total_bank > 0 else 0.0

    total_bank_value = sum(float(r.get("amount") or 0) for r in bank_rows)
    total_ledger_value = sum(float(r.get("amount") or 0) for r in ledger_rows)
    matched_bank_value = sum(
        sum(x["amount"] for x in (m["bank"] if isinstance(m["bank"], list) else [m["bank"]]))
        for m in all_matches
    )
    matched_ledger_value = sum(m["ledger"]["amount"] for m in all_matches)
    bank_value_pct = (matched_bank_value / total_bank_value * 100) if total_bank_value else 0.0

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
            "bank_value_pct": round(bank_value_pct, 1),
            "total_ledger_value": round(total_ledger_value, 2),
            "matched_ledger_value": round(matched_ledger_value, 2),
            "ledger_value_pct": round(matched_ledger_value / total_ledger_value * 100, 1)
                               if total_ledger_value else 0.0,
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
                "date": x["date"].strftime("%Y-%m-%d") if isinstance(x["date"], datetime) else str(x["date"]),
                "reference_id": x.get("reference_id", ""),
                "vendor": x.get("vendor", ""),
                "row_index": x.get("_row_index", 0),
            } for x in bank_part],
            "ledger_entry": {
                "amount": m["ledger"]["amount"],
                "date": m["ledger"]["date"].strftime("%Y-%m-%d") if isinstance(m["ledger"]["date"], datetime) else str(m["ledger"]["date"]),
                "reference_id": m["ledger"].get("reference_id", ""),
                "vendor": m["ledger"].get("vendor", ""),
                "row_index": m["ledger"].get("_row_index", 0),
            },
            "reason": m["reason"],
        }
        report["matches"].append(entry)

    for b in bank:
        report["exceptions"].append({
            "source": "bank_only",
            "amount": b["amount"],
            "date": b["date"].strftime("%Y-%m-%d") if isinstance(b["date"], datetime) else str(b["date"]),
            "reference_id": b.get("reference_id", ""),
            "vendor": b.get("vendor", ""),
            "row_index": b.get("_row_index", 0),
            "recommended_action": action_for(b),
            "reason": reason_for(b),
        })
    for l in ledger:
        report["exceptions"].append({
            "source": "ledger_only",
            "amount": l["amount"],
            "date": l["date"].strftime("%Y-%m-%d") if isinstance(l["date"], datetime) else str(l["date"]),
            "reference_id": l.get("reference_id", ""),
            "vendor": l.get("vendor", ""),
            "row_index": l.get("_row_index", 0),
            "recommended_action": action_for(l),
            "reason": reason_for(l),
        })

    # Save to disk as well
    with open(os.path.join(DIRECTORY, "reconciliation_report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    return report


class ReconciliationRequestHandler(http.server.SimpleHTTPRequestHandler):
    """Custom request handler supporting static dashboard serving & REST API endpoints."""
    protocol_version = "HTTP/1.1"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIRECTORY, **kwargs)

    def handle(self):
        try:
            super().handle()
        except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError, OSError):
            pass

    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Connection", "close")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

    def do_GET(self):
        if self.path == "/" or self.path == "":
            self.send_response(302)
            self.send_header("Location", "/dashboard.html")
            self.end_headers()
            return

        if self.path.startswith("/api/status"):
            try:
                import torch
                device = torch.cuda.get_device_name(0) if torch.cuda.is_available() else "CPU"
                cuda_available = torch.cuda.is_available()
            except ImportError:
                device = "CPU (heuristic mode — install requirements.txt for GPU LLM)"
                cuda_available = False
            payload = {
                "status": "online",
                "device": device,
                "cuda_available": cuda_available,
                "supported_formats": [".csv", ".xlsx", ".xls", ".docx", ".pdf", ".xml", ".json", ".tsv", ".txt"],
                "modules": ["reconciliation", "settlement_qa", "cash_forecast", "tax_matcher"]
            }
            self._send_json(payload)
            return

        if self.path.startswith("/api/forecast"):
            # Instant GET forecast using current report (deterministic by
            # default; the POST endpoint carries an explicit use_llm flag).
            res = cash_forecaster.generate_cash_forecast(use_llm=False)
            self._send_json(res)
            return

        if self.path.startswith("/api/tax-match"):
            # Instant GET audit using current report (deterministic by default).
            res = tax_matcher.run_tax_line_reconciliation(use_llm=False)
            self._send_json(res)
            return

        super().do_GET()

    def do_POST(self):
        content_type = self.headers.get("Content-Type", "")
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)

        # 1. Reconciliation Endpoint
        if self.path.startswith("/api/reconcile"):
            try:
                if "application/json" in content_type:
                    data = json.loads(body.decode("utf-8"))
                    bank_raw = data.get("bank_content", "")
                    bank_name = data.get("bank_filename", "bank.csv")
                    ledger_raw = data.get("ledger_content", "")
                    ledger_name = data.get("ledger_filename", "ledger.csv")

                    if data.get("is_base64"):
                        bank_bytes = base64.b64decode(bank_raw) if bank_raw else b""
                        ledger_bytes = base64.b64decode(ledger_raw) if ledger_raw else b""
                    else:
                        bank_bytes = bank_raw.encode("utf-8") if isinstance(bank_raw, str) else bank_raw
                        ledger_bytes = ledger_raw.encode("utf-8") if isinstance(ledger_raw, str) else ledger_raw

                    bank_rows = document_parser.parse_document(bank_bytes, bank_name)
                    ledger_rows = document_parser.parse_document(ledger_bytes, ledger_name)

                else:
                    self.send_error(400, "Unsupported Content-Type. Use JSON payload.")
                    return

                if not bank_rows and not ledger_rows:
                    self.send_error(400, "No transactions could be parsed from the uploaded files.")
                    return

                print(f"[API] Reconciling {len(bank_rows)} bank rows vs {len(ledger_rows)} ledger rows...")
                report = reconcile_records(bank_rows, ledger_rows)
                self._send_json(report)

            except Exception as e:
                import traceback
                traceback.print_exc()
                self._send_json({"error": str(e), "traceback": traceback.format_exc()}, status=500)
            return

        # 2. Settlement Q&A Endpoint
        if self.path.startswith("/api/qa"):
            try:
                data = json.loads(body.decode("utf-8"))
                question = data.get("question", "").strip()
                use_llm = data.get("use_llm", True)

                if not question:
                    self.send_error(400, "Missing 'question' parameter.")
                    return

                res = settlement_qa.ask_settlement_qa(question, use_llm=use_llm)
                self._send_json(res)
            except Exception as e:
                import traceback
                traceback.print_exc()
                self._send_json({"error": str(e)}, status=500)
            return

        # 3. Cash Forecaster Endpoint
        if self.path.startswith("/api/forecast"):
            try:
                data = json.loads(body.decode("utf-8")) if body else {}
                opening_bal = float(data.get("opening_balance", cash_forecaster.DEFAULT_OPENING_BALANCE))
                days = int(data.get("days_horizon", 30))
                use_llm = data.get("use_llm", True)

                res = cash_forecaster.generate_cash_forecast(opening_balance=opening_bal, days_horizon=days, use_llm=use_llm)
                self._send_json(res)
            except Exception as e:
                import traceback
                traceback.print_exc()
                self._send_json({"error": str(e)}, status=500)
            return

        # 4. Tax-Line Matcher Endpoint
        if self.path.startswith("/api/tax-match"):
            try:
                data = json.loads(body.decode("utf-8")) if body else {}
                use_llm = data.get("use_llm", True)
                res = tax_matcher.run_tax_line_reconciliation(use_llm=use_llm)
                self._send_json(res)
            except Exception as e:
                import traceback
                traceback.print_exc()
                self._send_json({"error": str(e)}, status=500)
            return

        self.send_error(404, "Endpoint not found")

    def _send_json(self, data, status=200):
        body = json.dumps(data, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class ThreadingServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def handle_error(self, request, client_address):
        # Ignore client disconnect / connection reset errors cleanly
        pass


def ensure_sample_data():
    """Fresh-clone safety: regenerate sample CSVs if missing."""
    missing = [f for f in ("bank_statement.csv", "company_ledger.csv")
               if not os.path.exists(os.path.join(DIRECTORY, f))]
    if missing:
        print(f"[SERVER] Sample data missing ({', '.join(missing)}) — generating ...")
        import subprocess
        subprocess.run([sys.executable, os.path.join(DIRECTORY, "generate_data.py")],
                       check=True, cwd=DIRECTORY)


def main():
    ensure_sample_data()
    httpd = ThreadingServer(("", PORT), ReconciliationRequestHandler)
    print("=" * 70)
    print(f"[SERVER] AI Finance Controller Web App running at:")
    print(f"   http://localhost:{PORT}/dashboard.html")
    print("=" * 70)
    print("Modules Active:")
    print("   1. Multi-Source Reconciliation Engine (5-Stage + GPU LLM)")
    print("   2. Settlement Q&A Agent (GPU LLM)")
    print("   3. Forward Cash Forecaster & Liquidity Risk Engine")
    print("   4. Tax-Line Matcher (TDS & GST Statutory Withholding)")
    print()
    print("Supported Upload Formats: PDF, Word (.docx), Excel (.xlsx), CSV, XML, JSON")
    print()
    print("Press Ctrl+C to stop the server.")

    while True:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down server.")
            break
        except Exception as e:
            import time
            time.sleep(0.2)


if __name__ == "__main__":
    main()
