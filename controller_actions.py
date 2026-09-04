"""Convert reconciliation exceptions into an actionable finance-operations queue with closed-loop resolution."""

import hashlib
import json
import os
import threading
from datetime import datetime


DEFAULT_REPORT_PATH = "reconciliation_report.json"
RESOLVED_ACTIONS_FILE = "resolved_actions.json"
ACTION_AUDIT_LOG = "controller_action_audit.jsonl"
_STATE_LOCK = threading.RLock()

_ACTION_RULES = {
    "needs_human_review": {
        "priority": "critical",
        "owner": "Finance Controller",
        "sla": "Resolve within 2 hours",
        "next_step": "Verify source documents and approve adjusting entry.",
        "default_treatment": "Approve Adjusting Journal Entry",
    },
    "likely_bank_fee": {
        "priority": "high",
        "owner": "Treasury Operations",
        "sla": "Book or dispute within 1 business day",
        "next_step": "Validate bank tariff and post unrecorded bank fee entry.",
        "default_treatment": "Book Bank Fee to GL 6140",
    },
    "investigate_orphan": {
        "priority": "high",
        "owner": "GL Accountant",
        "sla": "Investigate within 1 business day",
        "next_step": "Find missing counterpart or book timing accrual.",
        "default_treatment": "Post Timing Accrual to GL 2010",
    },
}

_PRIORITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def load_resolved_actions():
    """Load map of resolved action items with hash-linked audit entries."""
    if not os.path.exists(RESOLVED_ACTIONS_FILE):
        return {}
    try:
        with open(RESOLVED_ACTIONS_FILE, "r", encoding="utf-8") as f:
            resolved_actions = json.load(f)
            return resolved_actions if isinstance(resolved_actions, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def save_resolved_actions(resolved_dict):
    """Save map of resolved action items."""
    temporary_path = f"{RESOLVED_ACTIONS_FILE}.tmp"
    try:
        with open(temporary_path, "w", encoding="utf-8") as f:
            json.dump(resolved_dict, f, indent=2)
        os.replace(temporary_path, RESOLVED_ACTIONS_FILE)
    except OSError as error:
        try:
            if os.path.exists(temporary_path):
                os.remove(temporary_path)
        except OSError:
            pass
        raise RuntimeError("Unable to persist the local controller worklist.") from error


def reset_resolved_actions():
    """Reset the resolved actions journal."""
    with _STATE_LOCK:
        save_resolved_actions({})
        _append_audit_event({"event_type": "resolution_state_reset"})


def _read_audit_events():
    if not os.path.exists(ACTION_AUDIT_LOG):
        return [], None
    try:
        with open(ACTION_AUDIT_LOG, "r", encoding="utf-8") as audit_file:
            events = []
            for line_number, line in enumerate(audit_file, start=1):
                if not line.strip():
                    continue
                event = json.loads(line)
                if not isinstance(event, dict):
                    raise ValueError(f"Audit event {line_number} is not an object.")
                events.append(event)
            return events, None
    except (OSError, ValueError, json.JSONDecodeError) as error:
        return [], str(error)


def _load_audit_events():
    events, _ = _read_audit_events()
    return events


def _append_audit_event(event):
    with _STATE_LOCK:
        events = _load_audit_events()
        previous_hash = events[-1].get("event_hash", "GENESIS") if events else "GENESIS"
        audit_event = {
            "recorded_at": datetime.now().isoformat(timespec="seconds"),
            "previous_hash": previous_hash,
            **event,
        }
        payload = json.dumps(audit_event, sort_keys=True, separators=(",", ":"))
        audit_event["event_hash"] = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        with open(ACTION_AUDIT_LOG, "a", encoding="utf-8") as audit_file:
            audit_file.write(json.dumps(audit_event, sort_keys=True) + "\n")
        return audit_event


def verify_audit_chain():
    """Verify the local, hash-linked action audit log without trusting its contents."""
    events, read_error = _read_audit_events()
    if read_error:
        return {
            "is_valid": False,
            "event_count": 0,
            "failed_event": None,
            "last_event_hash": None,
            "reason": "Audit log could not be parsed.",
        }
    expected_previous_hash = "GENESIS"

    for event_index, event in enumerate(events, start=1):
        stored_hash = event.get("event_hash")
        event_payload = {key: value for key, value in event.items() if key != "event_hash"}
        calculated_hash = hashlib.sha256(
            json.dumps(event_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        if event.get("previous_hash") != expected_previous_hash or stored_hash != calculated_hash:
            return {
                "is_valid": False,
                "event_count": len(events),
                "failed_event": event_index,
                "last_event_hash": expected_previous_hash if events else None,
                "reason": "Audit hash chain verification failed.",
            }
        expected_previous_hash = stored_hash

    event_hashes = {event.get("event_hash") for event in events}
    unresolved_audit_entries = [
        action_id
        for action_id, resolution in load_resolved_actions().items()
        if not isinstance(resolution, dict) or resolution.get("audit_hash") not in event_hashes
    ]
    if unresolved_audit_entries:
        return {
            "is_valid": False,
            "event_count": len(events),
            "failed_event": None,
            "last_event_hash": expected_previous_hash if events else None,
            "reason": "A saved resolution is missing its audit event.",
        }

    return {
        "is_valid": True,
        "event_count": len(events),
        "failed_event": None,
        "last_event_hash": expected_previous_hash if events else None,
        "reason": "Audit hash chain verified.",
    }


def _action_id(exception):
    payload = {
        "action": exception.get("recommended_action", "investigate_orphan"),
        "amount": round(float(exception.get("amount") or 0), 2),
        "date": exception.get("date", ""),
        "reference_id": exception.get("reference_id", ""),
        "row_index": exception.get("row_index", ""),
        "source": exception.get("source", "unknown"),
        "vendor": exception.get("vendor", ""),
    }
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()[:10].upper()
    return f"ACT-{digest}"


def _open_action(action_id):
    action_plan = build_action_plan(include_resolved=False)
    for item in action_plan["action_items"]:
        if item["id"] == action_id:
            return item
    raise ValueError("The requested action is not open in the current reconciliation worklist.")


def _posting_accounts(action_item):
    if action_item["recommended_action"] == "likely_bank_fee":
        return "Bank Charges Expense (GL 6140)", "Operating Bank Account (GL 1010)"
    if action_item["source"] == "ledger_only":
        return "Unreconciled Ledger Suspense (GL 2010)", "Accounts Payable Clearing (GL 2100)"
    return "Unapplied Cash Suspense (GL 2010)", "Operating Bank Account (GL 1010)"


def resolve_action(action_id, resolution_type=None, note=None, operator="Finance Controller"):
    """Close the loop on an individual exception by booking an adjusting journal entry."""
    with _STATE_LOCK:
        resolved = load_resolved_actions()
        if action_id in resolved:
            return resolved[action_id]

        action_item = _open_action(action_id)
        resolved_at = datetime.now().isoformat(timespec="seconds")
        journal_seed = hashlib.sha256(action_id.encode("utf-8")).hexdigest()
        je_id = f"JE-{datetime.now().year}-{int(journal_seed[:8], 16) % 9000 + 1000}"
        debit_account, credit_account = _posting_accounts(action_item)

        res_entry = {
            "action_id": action_id,
            "is_resolved": True,
            "journal_entry_id": je_id,
            "resolved_at": resolved_at,
            "operator": operator,
            "resolution_type": resolution_type or "ADJUSTING_JOURNAL_ENTRY",
            "debit_account": debit_account,
            "credit_account": credit_account,
            "note": note or "Controller-approved adjusting entry recorded in the local worklist.",
        }
        audit_event = _append_audit_event({
            "event_type": "controller_resolution_recorded",
            "action_id": action_id,
            "journal_entry_id": je_id,
            "operator": operator,
            "resolution_type": res_entry["resolution_type"],
        })
        res_entry["audit_hash"] = audit_event["event_hash"]
        res_entry["previous_audit_hash"] = audit_event["previous_hash"]
        resolved[action_id] = res_entry
        save_resolved_actions(resolved)
        return res_entry


def auto_resolve_tolerances(max_amount=500.0, operator="Autonomous Policy Engine (Tolerance Rule < ₹500)"):
    """Batch-resolve only policy-approved, low-value bank-fee exceptions."""
    plan = build_action_plan(include_resolved=True)
    resolved_count = 0
    resolved_entries = []

    for item in plan.get("action_items", []):
        if (not item.get("is_resolved")
                and item.get("recommended_action") == "likely_bank_fee"
                and item.get("amount", 0) <= max_amount):
            entry = resolve_action(
                item["id"],
                resolution_type="AUTO_TOLERANCE_SETTLEMENT",
                note=f"Automatic policy settlement: variance ₹{item['amount']} is within ₹{max_amount} de-minimis threshold",
                operator=operator,
            )
            resolved_entries.append(entry)
            resolved_count += 1

    return {
        "resolved_count": resolved_count,
        "entries": resolved_entries,
        "policy": f"De-minimis tolerance threshold <= ₹{max_amount:.2f}",
    }


def load_report(report_path=None):
    """Load the latest reconciliation report when one is available."""
    path = report_path or DEFAULT_REPORT_PATH
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as report_file:
            return json.load(report_file)
    except (OSError, json.JSONDecodeError):
        return None


def build_action_plan(report=None, include_resolved=True):
    """Build a deterministic, auditable worklist with closed-loop resolution state."""
    report = report if report is not None else load_report()
    report = report or {"summary": {}, "exceptions": []}
    summary = report.get("summary", {})
    exceptions = report.get("exceptions", [])
    resolved_map = load_resolved_actions()

    action_items = []
    for exception in exceptions:
        action = exception.get("recommended_action", "investigate_orphan")
        rule = _ACTION_RULES.get(action, _ACTION_RULES["investigate_orphan"])
        reference = exception.get("reference_id") or "No reference"
        vendor = exception.get("vendor") or "Unknown counterparty"
        amount = round(float(exception.get("amount") or 0), 2)
        item_id = _action_id(exception)

        res_data = resolved_map.get(item_id)
        is_resolved = bool(res_data)

        item = {
            "id": item_id,
            "priority": rule["priority"],
            "owner": rule["owner"],
            "sla": rule["sla"],
            "next_step": rule["next_step"],
            "default_treatment": rule.get("default_treatment", "Post Adjusting Journal Entry"),
            "recommended_action": action,
            "amount": amount,
            "source": exception.get("source", "unknown"),
            "vendor": vendor,
            "reference_id": reference,
            "date": exception.get("date", ""),
            "evidence": exception.get("reason", "No matching counterpart found."),
            "is_resolved": is_resolved,
            "resolution": res_data if is_resolved else None,
        }
        action_items.append(item)

    action_items.sort(
        key=lambda item: (
            1 if item["is_resolved"] else 0,
            _PRIORITY_ORDER.get(item["priority"], 99),
            -item["amount"],
        )
    )

    unresolved_items = [item for item in action_items if not item["is_resolved"]]
    resolved_count = len(action_items) - len(unresolved_items)

    total_exposure = round(sum(item["amount"] for item in unresolved_items), 2)
    resolved_exposure = round(sum(item["amount"] for item in action_items if item["is_resolved"]), 2)
    critical_items = sum(item["priority"] == "critical" for item in unresolved_items)
    high_items = sum(item["priority"] == "high" for item in unresolved_items)
    audit_status = verify_audit_chain()

    matched_rows = int(summary.get("matched_bank_rows") or 0) + resolved_count
    total_rows = int(summary.get("total_bank_rows") or 0)
    automation_rate = round((matched_rows / total_rows * 100), 1) if total_rows else 0.0
    if automation_rate > 100.0:
        automation_rate = 100.0

    if critical_items:
        control_status = "attention_required"
        control_message = f"{critical_items} critical exception(s) require controller sign-off before batch close."
    elif unresolved_items:
        control_status = "follow_up_required"
        control_message = f"{len(unresolved_items)} non-critical item(s) pending GL posting."
    else:
        control_status = "ready_to_close"
        control_message = "All items are reconciled and booked. Each resolution has an auditable hash-chain record."

    return {
        "summary": {
            "control_status": control_status,
            "control_message": control_message,
            "automated_resolution_rate": automation_rate,
            "action_item_count": len(action_items),
            "open_action_item_count": len(unresolved_items),
            "total_exceptions_count": len(action_items),
            "resolved_count": resolved_count,
            "resolved_value": resolved_exposure,
            "critical_item_count": critical_items,
            "high_priority_item_count": high_items,
            "unresolved_value": total_exposure,
            "audit_integrity": audit_status,
        },
        "action_items": action_items if include_resolved else unresolved_items,
    }
