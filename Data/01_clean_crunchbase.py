"""
Data/0_clean_crunchbase.py
==========================
Cleans the Crunchbase snapshot (big_startup_secsees_dataset.csv) and builds
the real-data cohort used to calibrate the venture-risk outcome model.

Outputs (under Data/):
  crunchbase_clean.csv          cleaned rows with label and observable features
  crunchbase_split_report.json  counts for every cleaning step and the time split

Label
  acquired, ipo    -> 1 (success)
  closed           -> 0 (failure)
  operating        -> dropped (outcome not yet determined)

LEAKAGE note
  funding_total_usd, funding_rounds and last_funding_at are lifetime totals and can
  partly reflect the outcome. They are reported separately in the paper.
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
RAW = HERE / "big_startup_secsees_dataset.csv"
OUT_CSV = HERE / "crunchbase_clean.csv"
OUT_REPORT = HERE / "crunchbase_split_report.json"

TRAIN_END_YEAR = 2011   # train: <= 2011
VAL_END_YEAR = 2013     # validation: 2012-2013, test: >= 2014
TOP_COUNTRIES = 10
MIN_YEAR, MAX_YEAR = 1950, 2026

report = {"raw_rows": 0, "steps": []}


def log_step(name, before, after):
    report["steps"].append({"step": name, "rows_before": int(before), "rows_after": int(after),
                            "removed": int(before - after)})
    print(f"[step] {name:50s} {before:>7d} -> {after:>7d}  (removed {before - after})", flush=True)


def parse_date_col(series, name):
    """Parse dates in any common format; report values that could not be parsed."""
    raw = series.astype("string").str.strip()
    try:
        parsed = pd.to_datetime(raw, errors="coerce", format="mixed")
    except (TypeError, ValueError):
        parsed = pd.to_datetime(raw, errors="coerce")
    n_bad = int(parsed.isna().sum() - raw.isna().sum())
    report[f"{name}_unparsed"] = n_bad
    if n_bad > 0:
        examples = raw[parsed.isna() & raw.notna()].drop_duplicates().head(10).tolist()
        print(f"[!] {name}: {n_bad} values not parsed. Examples: {examples}", flush=True)
    return parsed


if not RAW.exists():
    sys.exit(f"[-] ERROR: {RAW.name} not found next to this script")

df = pd.read_csv(RAW, dtype=str, keep_default_na=True)
report["raw_rows"] = len(df)
print(f"[+] loaded {len(df)} raw rows, {df.shape[1]} columns", flush=True)
print("[info] sample raw first_funding_at values:",
      df["first_funding_at"].dropna().head(5).tolist(), flush=True)

# 1. Duplicates by permalink
n0 = len(df)
df = df.drop_duplicates(subset=["permalink"], keep="first")
log_step("drop duplicate permalink", n0, len(df))

# 2. Strip whitespace
for col in ["status", "country_code", "category_list"]:
    df[col] = df[col].str.strip()

# 3. Label from status
n0 = len(df)
print("[info] status values:\n" + df["status"].value_counts(dropna=False).to_string(), flush=True)
report["status_counts"] = df["status"].value_counts(dropna=False).to_dict()
label_map = {"acquired": 1, "ipo": 1, "closed": 0}
df["label_success"] = df["status"].str.lower().map(label_map)
df = df[df["label_success"].notna()].copy()
df["label_success"] = df["label_success"].astype(int)
log_step("drop undetermined status (operating / unknown)", n0, len(df))

# 4. Parse dates
for col in ["founded_at", "first_funding_at", "last_funding_at"]:
    df[col] = parse_date_col(df[col], col)

# 5. Require a valid first funding date
n0 = len(df)
df = df[df["first_funding_at"].notna()].copy()
log_step("drop missing/unparsed first_funding_at", n0, len(df))

# 6. Plausible years only
n0 = len(df)
fy = df["first_funding_at"].dt.year
df = df[(fy >= MIN_YEAR) & (fy <= MAX_YEAR)].copy()
log_step("drop implausible first_funding year", n0, len(df))

if len(df) == 0:
    sys.exit("[-] ERROR: no rows left after cleaning. Check the date format printed above; "
             "nothing was written.")

# 7. Funding total
df["funding_total_usd"] = pd.to_numeric(df["funding_total_usd"].replace("-", np.nan), errors="coerce")
n_neg = int((df["funding_total_usd"] < 0).sum())
df.loc[df["funding_total_usd"] < 0, "funding_total_usd"] = np.nan
report["negative_funding_set_to_nan"] = n_neg
df["has_funding_total"] = df["funding_total_usd"].notna().astype(int)

# 8. Funding rounds
df["funding_rounds"] = pd.to_numeric(df["funding_rounds"], errors="coerce")
df.loc[df["funding_rounds"] < 0, "funding_rounds"] = np.nan

# 9. Timing features
age = (df["first_funding_at"] - df["founded_at"]).dt.days / 365.25
bad_age = age < 0
report["negative_age_set_to_nan"] = int(bad_age.sum())
df["age_at_first_funding_yrs"] = age.where(~bad_age)
df["years_to_last_funding"] = (df["last_funding_at"] - df["first_funding_at"]).dt.days / 365.25
df.loc[df["years_to_last_funding"] < 0, "years_to_last_funding"] = np.nan

# 10. Category count
df["n_categories"] = df["category_list"].fillna("").apply(
    lambda s: len([c for c in s.split("|") if c.strip()]) if s else 0)

# 11. Log of funding total
df["log_funding_total"] = np.log1p(df["funding_total_usd"])

# 12. Country grouping
cc = df["country_code"].fillna("UNKNOWN")
top = cc.value_counts().head(TOP_COUNTRIES).index.tolist()
df["country_group"] = cc.where(cc.isin(top), "OTHER")
report["country_groups"] = df["country_group"].value_counts().to_dict()

# 13. Time split
year = df["first_funding_at"].dt.year
df["split"] = np.select([year <= TRAIN_END_YEAR, year <= VAL_END_YEAR], ["train", "val"], default="test")
split_counts = df.groupby("split")["label_success"].agg(["size", "mean"]).rename(
    columns={"size": "n", "mean": "success_rate"})
report["split_counts"] = {k: {"n": int(v["n"]), "success_rate": round(float(v["success_rate"]), 4)}
                          for k, v in split_counts.iterrows()}
print("[info] split counts:\n" + split_counts.to_string(), flush=True)
for s in ["train", "val", "test"]:
    if s not in report["split_counts"] or report["split_counts"][s]["n"] < 200:
        print(f"[!] WARNING: split '{s}' has fewer than 200 rows; adjust cutoffs", flush=True)

# 14. Save
keep = ["permalink", "name", "label_success", "split", "first_funding_at",
        "age_at_first_funding_yrs", "funding_rounds", "log_funding_total",
        "years_to_last_funding", "n_categories", "country_group", "has_funding_total"]
df[keep].to_csv(OUT_CSV, index=False)
report["final_rows"] = len(df)
report["output_csv"] = OUT_CSV.name

with open(OUT_REPORT, "w", encoding="utf-8") as f:
    json.dump(report, f, indent=2, ensure_ascii=False, default=str)

print(f"[+] wrote {OUT_CSV.name} ({len(df)} rows)", flush=True)
print(f"[+] wrote {OUT_REPORT.name}", flush=True)