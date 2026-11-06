"""
Data/1_calibrate_crunchbase_outcome.py
======================================
Fits the real-data outcome model P(failure | observable features) on Crunchbase.

Main model (leakage-free): company age at first funding, missing-age flag,
number of categories, country group.

Sensitivity model: adds lifetime totals (funding_rounds, log_funding_total,
years_to_last_funding, has_funding_total). These may partly reflect the outcome,
so they are reported only to quantify the leakage gap.

Medians and the country list come from the training split only.
Output: Data/models/crunchbase_outcome_logit.joblib and crunchbase_calibration.json
"""

import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, roc_auc_score
from sklearn.preprocessing import StandardScaler

HERE = Path(__file__).resolve().parent
SRC = HERE / "crunchbase_clean.csv"
MODELS = HERE / "models"
MODELS.mkdir(exist_ok=True)
OUT_JSON = MODELS / "crunchbase_calibration.json"
OUT_PKL = MODELS / "crunchbase_outcome_logit.joblib"
SEED = 42

MAIN_COLS = ["age_at_first_funding_yrs", "age_missing", "n_categories"]
LIFETIME_COLS = ["funding_rounds", "log_funding_total", "years_to_last_funding", "has_funding_total"]

if not SRC.exists():
    sys.exit(f"[-] ERROR: {SRC.name} not found. Run 0_clean_crunchbase.py first.")

df = pd.read_csv(SRC)
df["age_missing"] = df["age_at_first_funding_yrs"].isna().astype(int)
df["has_funding_total"] = df["has_funding_total"].fillna(0).astype(int)

train = df[df["split"] == "train"].copy()
val = df[df["split"] == "val"].copy()
test = df[df["split"] == "test"].copy()
for name, part in [("train", train), ("val", val), ("test", test)]:
    if len(part) < 200 or part["label_success"].nunique() < 2:
        sys.exit(f"[-] ERROR: split '{name}' is too small or has one class. Adjust cutoffs.")

base_rate_train = float(train["label_success"].mean())


def fit_eval(numeric_cols, tag):
    medians = {c: float(train[c].median()) for c in numeric_cols if train[c].isna().any()}
    countries = sorted(train["country_group"].unique().tolist())

    def matrix(frame):
        X = pd.DataFrame(index=frame.index)
        for c in numeric_cols:
            X[c] = frame[c].fillna(medians.get(c, 0.0)).astype(float)
        for k in countries:
            X[f"country_{k}"] = (frame["country_group"] == k).astype(float)
        return X

    Xtr, Xva, Xte = matrix(train), matrix(val), matrix(test)
    scaler = StandardScaler().fit(Xtr)
    model = LogisticRegression(C=1.0, max_iter=5000, random_state=SEED)
    model.fit(scaler.transform(Xtr), train["label_success"].values)

    def evaluate(frame, X):
        y = frame["label_success"].values
        p = model.predict_proba(scaler.transform(X))[:, 1]
        base = np.full(len(y), base_rate_train)
        return {
            "n": int(len(y)),
            "success_rate": round(float(y.mean()), 4),
            "auc": round(float(roc_auc_score(y, p)), 4),
            "brier": round(float(brier_score_loss(y, p)), 4),
            "brier_baseline_train_mean": round(float(brier_score_loss(y, base)), 4),
        }, p

    m_val, _ = evaluate(val, Xva)
    m_test, p_test = evaluate(test, Xte)

    bins = pd.qcut(pd.Series(p_test), 10, duplicates="drop")
    cal = (pd.DataFrame({"pred": p_test, "obs": test["label_success"].values, "bin": bins})
           .groupby("bin", observed=True)
           .agg(mean_pred=("pred", "mean"), obs_rate=("obs", "mean"), n=("obs", "size"))
           .reset_index(drop=True))
    calibration = [{k: round(float(v), 4) if k != "n" else int(v) for k, v in row.items()}
                   for row in cal.to_dict(orient="records")]

    coef = dict(zip(Xtr.columns.tolist(), [round(float(c), 4) for c in model.coef_[0]]))
    artifact = {"model": model, "scaler": scaler, "medians": medians,
                "countries": countries, "numeric_cols": numeric_cols, "seed": SEED}
    return {
        "tag": tag,
        "feature_cols": Xtr.columns.tolist(),
        "standardized_coefficients": coef,
        "intercept_standardized": round(float(model.intercept_[0]), 4),
        "validation": m_val,
        "test": m_test,
        "test_calibration_deciles": calibration,
    }, artifact


main_result, main_artifact = fit_eval(MAIN_COLS, "main_leakage_free")
sens_result, _ = fit_eval(MAIN_COLS + LIFETIME_COLS, "sensitivity_with_lifetime_totals")

joblib.dump(main_artifact, OUT_PKL)

summary = {
    "source": SRC.name,
    "seed": SEED,
    "split_success_rates": {
        "train": round(base_rate_train, 4),
        "val": round(float(val["label_success"].mean()), 4),
        "test": round(float(test["label_success"].mean()), 4),
    },
    "main": main_result,
    "sensitivity": sens_result,
    "leakage_gap_test_auc": round(sens_result["test"]["auc"] - main_result["test"]["auc"], 4),
    "artifact": OUT_PKL.name,
}
with open(OUT_JSON, "w", encoding="utf-8") as f:
    json.dump(summary, f, indent=2, ensure_ascii=False)

print("[+] split success rates:", summary["split_success_rates"], flush=True)
print(f"[+] MAIN (leakage-free)  test AUC={main_result['test']['auc']}  "
      f"Brier={main_result['test']['brier']} (baseline {main_result['test']['brier_baseline_train_mean']})",
      flush=True)
print(f"[+] SENSITIVITY (+lifetime) test AUC={sens_result['test']['auc']}  "
      f"Brier={sens_result['test']['brier']}", flush=True)
print(f"[+] leakage gap in test AUC: {summary['leakage_gap_test_auc']}", flush=True)
print(f"[+] wrote {OUT_PKL.name} and {OUT_JSON.name}", flush=True)