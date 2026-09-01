"""
cash_forecaster.py

Forward Cash Forecaster powered by quantitative liquidity modeling & local LLM reasoning.

Capabilities:
  - Models historical settlement drift & velocity from reconciled pairs
  - Computes 7-day, 14-day, and 30-day forward cash balance trajectories
  - Detects impending liquidity deficit points below safety reserve thresholds
  - Generates executive cash runway insights using local Qwen2.5-3B LLM
"""

import json
import os
from datetime import datetime, timedelta

DEFAULT_REPORT_PATH = "reconciliation_report.json"
DEFAULT_OPENING_BALANCE = 5000000.00  # Rs. 50 Lakhs default starting liquidity
SAFETY_BUFFER = 1000000.00            # Rs. 10 Lakhs safety buffer


def generate_cash_forecast(report=None, opening_balance=DEFAULT_OPENING_BALANCE, days_horizon=30, use_llm=True):
    """
    Generate forward daily cash balance trajectory and LLM risk assessment.

    Args:
        report: parsed reconciliation report dict (or None to load from disk)
        opening_balance: starting bank cash position in INR
        days_horizon: number of days to project forward (7, 14, 30)
        use_llm: whether to generate LLM executive commentary

    Returns:
        dict with:
          - opening_balance
          - current_burn_rate_daily
          - projected_30d_balance
          - deficit_detected: bool
          - deficit_date: str or None
          - daily_trajectory: list of { date, balance, net_flow, inflows, outflows }
          - executive_summary: str (LLM generated)
    """
    if report is None and os.path.exists(DEFAULT_REPORT_PATH):
        with open(DEFAULT_REPORT_PATH, "r", encoding="utf-8") as f:
            report = json.load(f)

    matches = report.get("matches", []) if report else []
    exceptions = report.get("exceptions", []) if report else []

    # Calculate historical daily flow velocity
    dates = []
    total_inflows = 0.0
    total_outflows = 0.0
    daily_flows = {}

    for m in matches:
        amt = m["ledger_entry"]["amount"]
        dt_str = m["ledger_entry"]["date"]
        try:
            dt = datetime.strptime(dt_str, "%Y-%m-%d")
            dates.append(dt)
            # Standard outflow assumption for vendor payments
            daily_flows[dt.date()] = daily_flows.get(dt.date(), 0.0) + amt
            total_outflows += amt
        except ValueError:
            pass

    # Determine base daily burn rate
    n_days = max(1, (max(dates) - min(dates)).days) if dates else 30
    avg_daily_outflow = total_outflows / n_days if n_days > 0 else 50000.0

    # Project forward daily trajectory starting from latest date
    start_date = max(dates) if dates else datetime.now()
    current_bal = float(opening_balance)
    trajectory = []
    deficit_detected = False
    deficit_date = None

    # Pending un-reconciled ledger items will clear over the next 1-7 days (drift)
    pending_ledger_amounts = [e["amount"] for e in exceptions if e.get("source") == "ledger_only"]
    pending_per_day = sum(pending_ledger_amounts) / min(7, days_horizon) if pending_ledger_amounts else 0.0

    for i in range(1, days_horizon + 1):
        proj_date = start_date + timedelta(days=i)
        date_str = proj_date.strftime("%Y-%m-%d")

        # Inflows (e.g. customer collections model: cyclical every 5 days)
        inflow = (avg_daily_outflow * 1.25) if (i % 5 == 0) else (avg_daily_outflow * 0.15)

        # Outflows (recurring vendor runs + pending uncleared ledger payments)
        outflow = avg_daily_outflow + (pending_per_day if i <= 7 else 0.0)
        net_flow = inflow - outflow

        current_bal += net_flow

        if current_bal < SAFETY_BUFFER and not deficit_detected:
            deficit_detected = True
            deficit_date = date_str

        trajectory.append({
            "day": i,
            "date": date_str,
            "balance": round(current_bal, 2),
            "net_flow": round(net_flow, 2),
            "inflows": round(inflow, 2),
            "outflows": round(outflow, 2),
        })

    end_balance = trajectory[-1]["balance"] if trajectory else current_bal

    forecast_data = {
        "opening_balance": round(opening_balance, 2),
        "avg_daily_burn": round(avg_daily_outflow, 2),
        "projected_end_balance": round(end_balance, 2),
        "horizon_days": days_horizon,
        "deficit_detected": deficit_detected,
        "deficit_date": deficit_date,
        "safety_buffer": SAFETY_BUFFER,
        "daily_trajectory": trajectory,
    }

    # Generate LLM executive liquidity report
    commentary = _generate_forecast_llm_commentary(forecast_data, use_llm)
    forecast_data["executive_summary"] = commentary

    return forecast_data


def _generate_forecast_llm_commentary(forecast_data, use_llm=True):
    """Generate executive liquidity commentary using Qwen2.5-3B on GPU."""
    op = forecast_data["opening_balance"]
    end_bal = forecast_data["projected_end_balance"]
    burn = forecast_data["avg_daily_burn"]
    deficit = forecast_data["deficit_detected"]
    def_date = forecast_data["deficit_date"]

    default_commentary = (
        f"### 30-Day Liquidity Outlook\n\n"
        f"- **Starting Cash:** Rs. {op:,.2f}\n"
        f"- **Projected Ending Cash:** Rs. {end_bal:,.2f}\n"
        f"- **Average Daily Outflow:** Rs. {burn:,.2f}\n"
        f"- **Liquidity Status:** {'[WARNING] Deficit warning triggered on ' + str(def_date) + ' (falls below Rs. 10L reserve)' if deficit else '[HEALTHY] Liquidity runway with no projected deficits.'}\n\n"
        f"**Recommendations:**\n"
        f"- Prioritize collection follow-ups before day 15 to maintain the liquidity buffer.\n"
        f"- Settle uncleared ledger accruals in scheduled batches."
    )

    if not use_llm or os.environ.get("USE_LLM", "1") == "0":
        return default_commentary

    try:
        from llm_resolver import _load_model
        pipe = _load_model()

        system_prompt = """You are a Chief Financial Officer & Cash Flow Strategist.
Analyze the provided forward cash forecast metrics and write a concise, high-impact executive liquidity brief.
Highlight opening cash, projected trajectory, runway risk points, and 2 actionable treasury recommendations.
Format using clean markdown with bullet points."""

        user_prompt = f"""FORECAST METRICS:
- Opening Cash Position: Rs. {op:,.2f}
- Projected Ending Cash ({forecast_data['horizon_days']} days): Rs. {end_bal:,.2f}
- Daily Operating Burn Rate: Rs. {burn:,.2f}
- Deficit Warning Triggered: {deficit} (Trigger Date: {def_date or 'None'})
- Safety Buffer Threshold: Rs. {SAFETY_BUFFER:,.2f}

Write the executive liquidity analysis:"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        output = pipe(
            messages,
            max_new_tokens=400,
            do_sample=False,
            return_full_text=False
        )
        raw_text = output[0]["generated_text"]
        if isinstance(raw_text, list):
            raw_text = raw_text[-1].get("content", str(raw_text[-1]))

        return raw_text.strip()

    except Exception:
        return default_commentary


if __name__ == "__main__":
    fc = generate_cash_forecast(use_llm=False)
    print("Cash Forecast Opening:", fc["opening_balance"])
    print("Projected End Balance:", fc["projected_end_balance"])
    print("Trajectory Days:", len(fc["daily_trajectory"]))
    print("Summary:\n", fc["executive_summary"])
