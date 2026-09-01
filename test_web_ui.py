"""
test_web_ui.py

Smoke test for the web dashboard (app.py + dashboard.html).

Starts the server on localhost:8080, then verifies:
  1. GET  /dashboard.html   -> 200, page served
  2. GET  /api/status       -> JSON with device info (works without torch too)
  3. GET  /                 -> redirects to the dashboard
  4. POST /api/reconcile    -> end-to-end match on a tiny 2-row CSV pair

Run:
    python test_web_ui.py

Exits 0 on success, 1 on failure.  Any pre-existing server on port 8080 is
stopped first so the test always exercises a fresh instance.
"""

import json
import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request

PORT = 8080
BASE = f"http://localhost:{PORT}"
HERE = os.path.dirname(os.path.abspath(__file__))


def kill_port_owners():
    """Stop anything already listening on PORT (best effort, Windows/Linux)."""
    try:
        out = subprocess.run(["netstat", "-ano"], capture_output=True, text=True).stdout
    except OSError:
        return
    pids = set()
    for line in out.splitlines():
        if f":{PORT}" in line and "LISTENING" in line.upper():
            parts = line.split()
            if parts and parts[-1].isdigit():
                pids.add(parts[-1])
    for pid in pids:
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/F", "/PID", pid], capture_output=True)
        else:
            try:
                os.kill(int(pid), signal.SIGTERM)
            except (ProcessLookupError, ValueError):
                pass


def request(path, payload=None, timeout=30):
    url = BASE + path
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json"} if data else {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def main():
    print("=" * 60)
    print("WEB UI SMOKE TEST (app.py + dashboard.html)")
    print("=" * 60)

    kill_port_owners()
    proc = subprocess.Popen([sys.executable, "app.py"], cwd=HERE,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        # 0. wait for the server to accept connections
        deadline = time.time() + 15
        while True:
            try:
                request("/api/status", timeout=2)
                break
            except (urllib.error.URLError, ConnectionError, OSError):
                if time.time() > deadline or proc.poll() is not None:
                    raise SystemExit("FAIL: server did not start on port 8080")
                time.sleep(0.5)
        print("PASS  server started on port 8080")

        # 1. dashboard page
        status, body = request("/dashboard.html")
        assert status == 200 and b"dashboard" in body.lower(), f"dashboard.html -> {status}"
        print(f"PASS  GET /dashboard.html -> 200 ({len(body) // 1024} KB served)")

        # 2. status endpoint (must also work with NO torch installed)
        status, body = request("/api/status")
        info = json.loads(body)
        assert status == 200 and "device" in info, f"/api/status -> {status}"
        print(f"PASS  GET /api/status -> device: {info['device']}")

        # 3. root redirects to the dashboard
        status, _ = request("/")
        assert status in (200, 302), f"/ -> {status}"
        print(f"PASS  GET / -> {status} (dashboard)")

        # 4. end-to-end reconciliation over HTTP
        nl = "\n"
        payload = {
            "bank_content": ("amount,date,reference_id,vendor" + nl
                             + "100.00,2026-01-01,T1,Acme" + nl
                             + "50.00,2026-01-02,T2,Acme"),
            "bank_filename": "bank.csv",
            "ledger_content": ("amount,date,reference_id,vendor" + nl
                               + "100.00,2026-01-01,T1,Acme" + nl
                               + "75.00,2026-01-02,T3,Beta"),
            "ledger_filename": "ledger.csv",
        }
        status, body = request("/api/reconcile", payload)
        assert status == 200, f"/api/reconcile -> {status}: {body[:200]}"
        summary = json.loads(body)["summary"]
        assert summary["total_bank_rows"] == 2, "bank rows not parsed"
        assert summary["matched_bank_rows"] == 1, "T1 should match exactly"
        assert summary["match_rate_pct"] == 50.0, "expected 1/2 matched"
        print(f"PASS  POST /api/reconcile -> {summary['matched_bank_rows']}/"
              f"{summary['total_bank_rows']} matched ({summary['match_rate_pct']}%), "
              f"{summary['total_exceptions']} exception(s)")

        print("-" * 60)
        print("ALL CHECKS PASSED — run `python app.py` and open "
              "http://localhost:8080/dashboard.html to use the UI")
        return 0
    except AssertionError as e:
        print(f"FAIL: {e}")
        return 1
    except Exception as e:
        print(f"FAIL: {type(e).__name__}: {e}")
        return 1
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


if __name__ == "__main__":
    sys.exit(main())
