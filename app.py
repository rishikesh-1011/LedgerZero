"""
app.py

Full-featured Web App & Reconciliation API Server for AI Finance Controller.
Serves the interactive dashboard and handles real-time multi-format statement
uploads (CSV, Excel .xlsx/.xls, Word .docx, PDF .pdf, XML .xml, JSON .json).

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

# Interactive uploads should feel instant: default Stage 4 to the
# deterministic heuristic (<1s).  Set APP_USE_LLM=1 to use the GPU LLM
# for ambiguous rows instead (first call loads the model, ~30-60s).
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

    tier_counts = {}
    for m in all_matches:
        tier_counts[m["tier"]] = tier_counts.get(m["tier"], 0) + 1

    matched_bank_rows = sum(
        (len(m["bank"]) if isinstance(m["bank"], list) else 1) for m in all_matches
    )
    match_rate = (matched_bank_rows / total_bank * 100) if total_bank > 0 else 0.0

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
            "reason": "no confident match found in ledger",
        })
    for l in ledger:
        report["exceptions"].append({
            "source": "ledger_only",
            "amount": l["amount"],
            "date": l["date"].strftime("%Y-%m-%d") if isinstance(l["date"], datetime) else str(l["date"]),
            "reference_id": l.get("reference_id", ""),
            "vendor": l.get("vendor", ""),
            "row_index": l.get("_row_index", 0),
            "reason": "no confident match found in bank statement",
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

    def end_headers(self):
        # Enable CORS and disable caching for API responses
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
                # LLM deps not installed — the pipeline still works end to end
                # with the deterministic heuristic fallback for Stage 4.
                device = "CPU (heuristic mode — install requirements.txt for the GPU LLM)"
                cuda_available = False
            payload = {
                "status": "online",
                "device": device,
                "cuda_available": cuda_available,
                "supported_formats": [".csv", ".xlsx", ".xls", ".docx", ".pdf", ".xml", ".json", ".tsv", ".txt"],
            }
            self._send_json(payload)
            return

        super().do_GET()

    def do_POST(self):
        if self.path.startswith("/api/reconcile"):
            content_type = self.headers.get("Content-Type", "")
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)

            try:
                bank_rows = []
                ledger_rows = []

                if "application/json" in content_type:
                    data = json.loads(body.decode("utf-8"))
                    bank_raw = data.get("bank_content", "")
                    bank_name = data.get("bank_filename", "bank.csv")
                    ledger_raw = data.get("ledger_content", "")
                    ledger_name = data.get("ledger_filename", "ledger.csv")

                    # Handle base64 encoded binary files (e.g. PDF, Word, Excel)
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

        self.send_error(404, "Endpoint not found")

    def _send_json(self, data, status=200):
        body = json.dumps(data, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def ensure_sample_data():
    """Fresh-clone safety: the dashboard's 1-click sample loader fetches
    bank_statement.csv / company_ledger.csv, which are gitignored generated
    artifacts.  Regenerate them from the seeded generator if missing."""
    missing = [f for f in ("bank_statement.csv", "company_ledger.csv")
               if not os.path.exists(os.path.join(DIRECTORY, f))]
    if missing:
        print(f"[SERVER] Sample data missing ({', '.join(missing)}) — generating ...")
        import subprocess
        subprocess.run([sys.executable, os.path.join(DIRECTORY, "generate_data.py")],
                       check=True, cwd=DIRECTORY)


def main():
    ensure_sample_data()
    socketserver.ThreadingTCPServer.allow_reuse_address = True
    with socketserver.ThreadingTCPServer(("", PORT), ReconciliationRequestHandler) as httpd:
        print("=" * 70)
        print(f"[SERVER] AI Finance Controller Web App running at:")
        print(f"   http://localhost:{PORT}/dashboard.html")
        print("=" * 70)
        print(f"Supported Upload Formats:")
        print(f"   - PDF Statements    (.pdf)")
        print(f"   - Word Documents    (.docx, .doc)")
        print(f"   - Excel Sheets      (.xlsx, .xls)")
        print(f"   - CSV / TSV / Text  (.csv, .tsv, .txt)")
        print(f"   - XML Statements    (.xml)")
        print(f"   - JSON              (.json)")
        print()
        print("Press Ctrl+C to stop the server.")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down server.")


if __name__ == "__main__":
    main()
