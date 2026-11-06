"""
Data/0_clean_user_behavior.py
=============================
Cleans user_behavior_dataset.csv for the telemetry autoencoder B(u).

Steps
  1. drop exact duplicates
  2. drop rows with missing values
  3. drop rows outside physical or definitional ranges
  4. check the label is binary and that both classes are large enough
  5. add log1p columns for heavy-tailed fields (training uses these, raw kept for reporting)

Outputs (under Data/):
  user_behavior_clean.csv
  user_behavior_clean_report.json
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
RAW = HERE / "user_behavior_dataset.csv"
OUT_CSV = HERE / "user_behavior_clean.csv"
OUT_REPORT = HERE / "user_behavior_clean_report.json"

FEATURES = ["transaction_count", "balance_native", "total_gas_used", "latency_ms",
            "tx_entropy", "packet_drop_ratio", "vote_clustering", "uptime_ratio"]
UNIT_INTERVAL = ["tx_entropy", "packet_drop_ratio", "vote_clustering", "uptime_ratio"]
NONNEG = ["transaction_count", "balance_native", "total_gas_used"]
HEAVY_TAILED = ["transaction_count", "total_gas_used", "latency_ms"]
MIN_CLASS_ROWS = 500

report = {"raw_rows": 0, "steps": []}


def log_step(name, before, after):
    report["steps"].append({"step": name, "rows_before": int(before), "rows_after": int(after),
                            "removed": int(before - after)})
    print(f"[step] {name:45s} {before:>8d} -> {after:>8d}  (removed {before - after})", flush=True)


if not RAW.exists():
    sys.exit(f"[-] ERROR: {RAW.name} not found next to this script")

df = pd.read_csv(RAW)
report["raw_rows"] = len(df)
print(f"[+] loaded {len(df)} rows, {df.shape[1]} columns", flush=True)

required = FEATURES + ["is_bot"]
missing_cols = [c for c in required if c not in df.columns]
if missing_cols:
    sys.exit(f"[-] ERROR: missing columns {missing_cols}")

# 1. Exact duplicates
n0 = len(df)
df = df.drop_duplicates()
log_step("drop exact duplicates", n0, len(df))

# 2. Missing values
n0 = len(df)
report["missing_before_drop"] = df[required].isna().sum().to_dict()
df = df.dropna(subset=required)
log_step("drop rows with missing values", n0, len(df))

# 3. Numeric types
for c in required:
    df[c] = pd.to_numeric(df[c], errors="coerce")
n0 = len(df)
df = df.dropna(subset=required)
log_step("drop non-numeric values", n0, len(df))

# 4. Range checks
n0 = len(df)
mask = pd.Series(True, index=df.index)
for c in UNIT_INTERVAL:
    mask &= df[c].between(0, 1)
for c in NONNEG:
    mask &= df[c] >= 0
mask &= df["latency_ms"] > 0
mask &= df["is_bot"].isin([0, 1])
report["range_violations_by_column"] = {
    c: int((~df[c].between(0, 1)).sum()) for c in UNIT_INTERVAL}
df = df[mask].copy()
log_step("drop out-of-range values", n0, len(df))

# 5. Label balance
df["is_bot"] = df["is_bot"].astype(int)
counts = df["is_bot"].value_counts().to_dict()
report["class_counts"] = {str(k): int(v) for k, v in counts.items()}
print(f"[info] class counts: honest={counts.get(0, 0)}  bot={counts.get(1, 0)}", flush=True)
if counts.get(0, 0) < MIN_CLASS_ROWS or counts.get(1, 0) < MIN_CLASS_ROWS:
    print(f"[!] WARNING: a class has fewer than {MIN_CLASS_ROWS} rows; "
          "the autoencoder needs enough honest rows and the evaluation needs enough bots", flush=True)

# 6. Log transforms for heavy-tailed fields
for c in HEAVY_TAILED:
    df[f"log_{c}"] = np.log1p(df[c])

# 7. Save
keep = FEATURES + ["is_bot"] + [f"log_{c}" for c in HEAVY_TAILED]
df[keep].to_csv(OUT_CSV, index=False)
report["final_rows"] = len(df)
report["output_csv"] = OUT_CSV.name

with open(OUT_REPORT, "w", encoding="utf-8") as f:
    json.dump(report, f, indent=2, ensure_ascii=False, default=str)

print(f"[+] wrote {OUT_CSV.name} ({len(df)} rows)", flush=True)
print(f"[+] wrote {OUT_REPORT.name}", flush=True)