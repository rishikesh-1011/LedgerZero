"""
generate_data.py

Creates two CSVs representing the SAME underlying set of business transactions,
as seen from two different systems: a bank statement and a company ledger.

Real reconciliation is hard because these two records never perfectly agree.
This script deliberately injects the most common real-world mismatch types:

  - exact matches            (the easy majority)
  - rounding differences     (₹499.50 -> ₹500)
  - date drift               (settlement lands 1-2 days later in one system)
  - missing reference IDs    (one side just doesn't have it)
  - split payments           (one ledger entry = two bank entries)
  - duplicate amounts        (two unrelated transactions with the same amount,
                              which makes naive amount-only matching dangerous)
  - vendor name variations   (typos, abbreviations, suffixes like "Pvt Ltd")
  - orphan rows              (present in only one source, should never "match")

We emit a ground_truth.csv mapping (source, row_index) -> (truth_id,
scenario) for EVERY row so evaluate.py can score accuracy per scenario and
audit the exception list.  Deterministic per --seed: any result is exactly
reproducible.
"""

import argparse
import csv
import random
from datetime import datetime, timedelta


def parse_args():
    ap = argparse.ArgumentParser(
        description="Generate synthetic bank/ledger CSVs plus a ground-truth answer key")
    ap.add_argument("--seed", type=int, default=42, help="RNG seed (default 42)")
    ap.add_argument("--transactions", type=int, default=65,
                    help="number of ground-truth transactions (default 65)")
    return ap.parse_args()


ARGS = parse_args()
random.seed(ARGS.seed)

N_TRANSACTIONS = ARGS.transactions
VENDORS = ["Acme Traders", "BlueOne Logistics", "Kavya Textiles", "Nimbus SaaS",
           "Orbit Freight", "Pixel Studio", "Rane Motors", "Sundar Foods",
           "Tanvi Exports", "Vertex Cloud"]

# Vendor name variation pool -- realistic typos, abbreviations, and suffix changes
# that a fuzzy vendor matcher should handle.
VENDOR_VARIATIONS = {
    "Acme Traders":       ["ACME TRADERS", "Acme Traders Pvt Ltd", "Acme Trdrs"],
    "BlueOne Logistics":  ["Blue One Logistics", "BlueOne Logistics Pvt Ltd", "BLUEONE LOGISTICS"],
    "Kavya Textiles":     ["Kavya Textiles Pvt Ltd", "KAVYA TEXTILES", "Kavya Textiles Ltd"],
    "Nimbus SaaS":        ["Nimbus SAAS", "Nimbus SaaS Inc", "NIMBUS SAAS"],
    "Orbit Freight":      ["Orbit Freight Services", "ORBIT FREIGHT", "Orbit Frieght"],
    "Pixel Studio":       ["Pixel Studio LLP", "PIXEL STUDIO", "Pixel Studios"],
    "Rane Motors":        ["Rane Motors Pvt Ltd", "RANE MOTORS", "Rane Motrs"],
    "Sundar Foods":       ["Sundar Foods Pvt Ltd", "SUNDAR FOODS", "Sundar Food"],
    "Tanvi Exports":      ["Tanvi Exports Pvt Ltd", "TANVI EXPORTS", "Tanvi Export"],
    "Vertex Cloud":       ["Vertex Cloud Services", "VERTEX CLOUD", "Vertex Cld"],
}

start_date = datetime(2026, 7, 1)


def rand_date(offset_days_range=30):
    return start_date + timedelta(days=random.randint(0, offset_days_range))


def make_ref(i):
    return f"TXN{100000 + i}"


def vary_vendor(vendor):
    """Return a plausible variation of the canonical vendor name."""
    variants = VENDOR_VARIATIONS.get(vendor, [])
    if variants:
        return random.choice(variants)
    return vendor


# ---------------------------------------------------------------------------
# 1. Build ground truth
# ---------------------------------------------------------------------------
truth = []
for i in range(N_TRANSACTIONS):
    amount = round(random.uniform(500, 95000), 2)
    truth.append({
        "truth_id": i,
        "amount": amount,
        "date": rand_date(),
        "reference_id": make_ref(i),
        "vendor": random.choice(VENDORS),
    })

bank_rows = []       # list of (row_dict, truth_id_or_None, scenario)
ledger_rows = []

for t in truth:
    scenario = random.random()

    # --- Scenario buckets -------------------------------------------------
    if scenario < 0.50:
        # 50%: clean exact match on both sides
        bank_rows.append((dict(amount=t["amount"], date=t["date"],
                               reference_id=t["reference_id"], vendor=t["vendor"]),
                          t["truth_id"], "exact"))
        ledger_rows.append((dict(amount=t["amount"], date=t["date"],
                                  reference_id=t["reference_id"], vendor=t["vendor"]),
                            t["truth_id"], "exact"))

    elif scenario < 0.63:
        # 13%: rounding difference on the bank side
        rounded = round(t["amount"] / 10) * 10
        bank_rows.append((dict(amount=rounded, date=t["date"],
                               reference_id=t["reference_id"], vendor=t["vendor"]),
                          t["truth_id"], "rounding"))
        ledger_rows.append((dict(amount=t["amount"], date=t["date"],
                                  reference_id=t["reference_id"], vendor=t["vendor"]),
                            t["truth_id"], "rounding"))

    elif scenario < 0.75:
        # 12%: date drift (settlement lands 1-3 days later on the bank side)
        drift = timedelta(days=random.randint(1, 3))
        bank_rows.append((dict(amount=t["amount"], date=t["date"] + drift,
                               reference_id=t["reference_id"], vendor=t["vendor"]),
                          t["truth_id"], "date_drift"))
        ledger_rows.append((dict(amount=t["amount"], date=t["date"],
                                  reference_id=t["reference_id"], vendor=t["vendor"]),
                            t["truth_id"], "date_drift"))

    elif scenario < 0.83:
        # 8%: missing reference ID on the ledger side
        bank_rows.append((dict(amount=t["amount"], date=t["date"],
                               reference_id=t["reference_id"], vendor=t["vendor"]),
                          t["truth_id"], "missing_ref"))
        ledger_rows.append((dict(amount=t["amount"], date=t["date"],
                                  reference_id="", vendor=t["vendor"]),
                            t["truth_id"], "missing_ref"))

    elif scenario < 0.88:
        # 5%: vendor name variation with NO reference id on the ledger side.
        # (A variation that keeps the reference id is matched by Stage 1
        # before the vendor is ever compared -- this variant is what actually
        # exercises vendor-similarity fuzzy matching and the Stage 4 LLM.)
        varied = vary_vendor(t["vendor"])
        bank_rows.append((dict(amount=t["amount"], date=t["date"],
                               reference_id=t["reference_id"], vendor=varied),
                          t["truth_id"], "vendor_variant"))
        ledger_rows.append((dict(amount=t["amount"], date=t["date"],
                                  reference_id="", vendor=t["vendor"]),
                            t["truth_id"], "vendor_variant"))

    elif scenario < 0.94:
        # 6%: split payment -> one ledger entry becomes two bank entries
        part1 = round(t["amount"] * random.uniform(0.3, 0.6), 2)
        part2 = round(t["amount"] - part1, 2)
        bank_rows.append((dict(amount=part1, date=t["date"],
                               reference_id=t["reference_id"] + "-A", vendor=t["vendor"]),
                          t["truth_id"], "split_payment"))
        bank_rows.append((dict(amount=part2, date=t["date"],
                               reference_id=t["reference_id"] + "-B", vendor=t["vendor"]),
                          t["truth_id"], "split_payment"))
        ledger_rows.append((dict(amount=t["amount"], date=t["date"],
                                  reference_id=t["reference_id"], vendor=t["vendor"]),
                            t["truth_id"], "split_payment"))

    else:
        # remainder: orphan row, exists ONLY in the ledger (e.g. an accrual
        # not yet settled) -- should end up as a genuine, correct exception
        ledger_rows.append((dict(amount=t["amount"], date=t["date"],
                                  reference_id=t["reference_id"], vendor=t["vendor"]),
                            t["truth_id"], "orphan_ledger"))

# Inject a few duplicate-amount decoys directly into the bank statement to
# stress-test naive "match on amount alone" logic.
for _ in range(4):
    victim = random.choice(truth)
    decoy_amount = victim["amount"]
    bank_rows.append((dict(amount=decoy_amount, date=rand_date(),
                           reference_id=f"TXN{900000 + random.randint(0,999)}",
                           vendor=random.choice(VENDORS)),
                      None, "decoy"))  # no ground truth -- it's a decoy

# Inject a couple of bank-only orphans too (e.g. a bank fee never logged yet)
for _ in range(3):
    bank_rows.append((dict(amount=round(random.uniform(50, 500), 2), date=rand_date(),
                           reference_id=f"FEE{random.randint(1000,9999)}",
                           vendor="Bank Charges"),
                      None, "bank_fee"))  # no ground truth

# Tax lines: GST + TDS settlement pairs on BOTH sides (identical refs/amounts
# -> Stage 1 exact match), one small round-off TDS pair (within Rs tolerance,
# exercises fuzzy matching), and one bank-only GST credit (a genuine open tax
# item for the tax-line matcher).
for i in range(4):
    amt = round(random.uniform(500, 20000), 2)
    ref = f"GST{250000 + random.randint(1000, 9999)}"
    date = rand_date()
    bank_rows.append((dict(amount=amt, date=date, reference_id=ref,
                           vendor="GST Payment"),
                      f"tax-gst-{i}", "tax_line"))
    ledger_rows.append((dict(amount=amt, date=date, reference_id=ref,
                             vendor="GST Payment"),
                        f"tax-gst-{i}", "tax_line"))

tds_amt = round(random.uniform(300, 8000), 2)
tds_ref = f"TDS{260000 + random.randint(1000, 9999)}"
tds_vendor = random.choice(VENDORS) + " TDS"
tds_date = rand_date()
bank_rows.append((dict(amount=tds_amt, date=tds_date, reference_id=tds_ref,
                       vendor=tds_vendor),
                  "tax-tds-0", "tax_line"))
ledger_rows.append((dict(amount=tds_amt, date=tds_date, reference_id=tds_ref,
                         vendor=tds_vendor),
                    "tax-tds-0", "tax_line"))

tds2_amt = round(random.uniform(300, 8000), 2)
tds2_ref = f"TDS{270000 + random.randint(1000, 9999)}"
tds2_vendor = random.choice(VENDORS) + " TDS"
tds2_date = rand_date()
bank_rows.append((dict(amount=round(tds2_amt - 2.5, 2), date=tds2_date,
                       reference_id=tds2_ref, vendor=tds2_vendor),
                  "tax-tds-1", "tax_line"))
ledger_rows.append((dict(amount=tds2_amt, date=tds2_date, reference_id=tds2_ref,
                         vendor=tds2_vendor),
                    "tax-tds-1", "tax_line"))

bank_rows.append((dict(amount=round(random.uniform(500, 3000), 2), date=rand_date(),
                       reference_id=f"GST{240000 + random.randint(1000, 9999)}",
                       vendor="GST Input Credit"),
                  None, "tax_line"))  # open tax item -- bank only

random.shuffle(bank_rows)
random.shuffle(ledger_rows)


def write_csv(path, rows):
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["amount", "date", "reference_id", "vendor"])
        writer.writeheader()
        for r, _, _ in rows:
            row = dict(r)
            row["date"] = row["date"].strftime("%Y-%m-%d")
            writer.writerow(row)


def write_ground_truth(bank_rows, ledger_rows):
    """Write ground_truth.csv: (source, row_index) -> truth_id + scenario.

    Written for EVERY row -- truth_id is empty for rows with no real
    transaction behind them (decoys, bank fees) -- so evaluate.py can score
    matches AND label exceptions by type.  The matcher never sees this file.
    """
    with open("ground_truth.csv", "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["source", "row_index", "truth_id", "scenario"])
        for source, rows in (("bank", bank_rows), ("ledger", ledger_rows)):
            for i, (_, tid, scen) in enumerate(rows):
                writer.writerow([source, i, "" if tid is None else tid, scen])


write_csv("bank_statement.csv", bank_rows)
write_csv("company_ledger.csv", ledger_rows)
write_ground_truth(bank_rows, ledger_rows)

print(f"Generated {len(bank_rows)} bank_statement.csv rows")
print(f"Generated {len(ledger_rows)} company_ledger.csv rows")
print(f"Underlying ground-truth transactions: {N_TRANSACTIONS} (seed {ARGS.seed})")
print("Wrote ground_truth.csv (truth ids + scenario labels) for evaluate.py")
