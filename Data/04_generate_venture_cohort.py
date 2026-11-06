"""
Data/2_generate_venture_cohort.py
=================================
Generates the venture cohort for R(p) (probability of default).

Design
  * Venture features are generated from observables known at proposal time
    (age at first funding, number of categories, country). Lifetime totals are
    not used, so the generator does not leak the outcome.
  * requested_amount = burn_rate * runway with a continuous runway, so it is
    not an integer multiple of burn_rate.
  * success logit = logit(P_observable) + gamma * venture_score + noise + shift.
    P_observable is the Crunchbase calibration model. The shift is solved so the
    cohort success rate equals the target base rate.
  * Label = default = 1 - success.
  * Ground truth p_default_true is saved for diagnostics only and is never a model input.

Grid: 3 base success rates x 3 noise levels = 9 scenarios.
Primary scenario: base 0.46, noise 0.7.

PARAMS are fixed before any model is trained. Nothing is tuned to a target AUC.
"""

import hashlib
import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

HERE = Path(__file__).resolve().parent
SRC = HERE / "crunchbase_clean.csv"
ART = HERE / "models" / "crunchbase_outcome_logit.joblib"
OUT_DIR = HERE / "cohorts"
OUT_DIR.mkdir(exist_ok=True)
REPORT = OUT_DIR / "generator_report.json"

SEED = 42
BASE_SUCCESS_RATES = [0.27, 0.46, 0.60]
NOISE_SD = [0.3, 0.7, 1.2]
PRIMARY = (0.46, 0.7)

PARAMS = {
    "gamma_venture_effect": 0.5,
    "burn_base_usd": 12000.0,
    "burn_age_coef": 0.25,
    "burn_ncat_coef": 0.2,
    "burn_log_sigma": 0.6,
    "runway_median_months": 9.0,
    "runway_log_sigma": 0.5,
    "team_age_coef": 0.6,
    "team_gamma_shape": 2.0,
    "team_gamma_scale": 1.5,
    "milestone_lambda_base": 3.0,
    "milestone_ncat_coef": 0.2,
    "milestone_age_coef": 0.1,
    "milestone_min": 1,
    "milestone_max": 12,
    "prev_funding_intercept": -0.3,
    "prev_funding_age_coef": 0.5,
    "tam_median_usd": 1e9,
    "tam_ncat_coef": 0.2,
    "tam_log_sigma": 1.0,
    "score_weights": {
        "z_log_burn": -0.6,
        "z_log_requested": -0.4,
        "z_team": 0.4,
        "prev_funding": 0.2,
        "z_log_tam": 0.1,
        "z_log_burn_x_z_team": -0.3,
    },
}

if not SRC.exists() or not ART.exists():
    sys.exit("[-] ERROR: run 0_clean_crunchbase.py and 1_calibrate_crunchbase_outcome.py first.")

art = joblib.load(ART)
df = pd.read_csv(SRC)
df["age_missing"] = df["age_at_first_funding_yrs"].isna().astype(int)
df["has_funding_total"] = df["has_funding_total"].fillna(0).astype(int)


def build_X(frame):
    X = pd.DataFrame(index=frame.index)
    for c in art["numeric_cols"]:
        X[c] = frame[c].fillna(art["medians"].get(c, 0.0)).astype(float)
    for k in art["countries"]:
        X[f"country_{k}"] = (frame["country_group"] == k).astype(float)
    return X


P_OBS = art["model"].predict_proba(art["scaler"].transform(build_X(df)))[:, 1]
P_OBS = np.clip(P_OBS, 1e-6, 1 - 1e-6)
LOGIT_OBS = np.log(P_OBS / (1 - P_OBS))

AGE = df["age_at_first_funding_yrs"].fillna(df["age_at_first_funding_yrs"].median()).values
NCAT = df["n_categories"].values.astype(float)
SPLIT = df["split"].values
PERMALINK = df["permalink"].values


def z(x):
    x = np.asarray(x, dtype=float)
    s = x.std()
    return (x - x.mean()) / (s if s > 0 else 1.0)


def sigmoid(x):
    return 1.0 / (1.0 + np.exp(-x))


def solve_shift(logit, target_success):
    lo, hi = -30.0, 30.0
    for _ in range(200):
        mid = (lo + hi) / 2
        if sigmoid(logit + mid).mean() < target_success:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def generate(rng, base_success, noise_sd):
    P = PARAMS
    n = len(AGE)
    age_z = z(AGE)
    ncat_z = z(NCAT)

    burn = np.exp(np.log(P["burn_base_usd"]) + P["burn_age_coef"] * age_z
                  + P["burn_ncat_coef"] * ncat_z + rng.normal(0, P["burn_log_sigma"], n))
    runway = np.exp(np.log(P["runway_median_months"]) + rng.normal(0, P["runway_log_sigma"], n))
    requested = burn * runway
    team = np.maximum(0.0, P["team_age_coef"] * AGE + rng.gamma(P["team_gamma_shape"],
                                                                 P["team_gamma_scale"], n))
    lam = np.exp(np.log(P["milestone_lambda_base"]) + P["milestone_ncat_coef"] * ncat_z
                 + P["milestone_age_coef"] * age_z)
    milestone = np.clip(rng.poisson(lam), P["milestone_min"], P["milestone_max"])
    p_prev = sigmoid(P["prev_funding_intercept"] + P["prev_funding_age_coef"] * age_z)
    prev = rng.binomial(1, p_prev)
    tam = np.exp(np.log(P["tam_median_usd"]) + P["tam_ncat_coef"] * ncat_z
                 + rng.normal(0, P["tam_log_sigma"], n))

    w = P["score_weights"]
    zb = z(np.log(burn))
    zr = z(np.log(requested))
    zt = z(team)
    score = (w["z_log_burn"] * zb + w["z_log_requested"] * zr + w["z_team"] * zt
             + w["prev_funding"] * prev + w["z_log_tam"] * z(np.log(tam))
             + w["z_log_burn_x_z_team"] * zb * zt)

    eta = rng.normal(0, noise_sd, n)
    base_logit = LOGIT_OBS + P["gamma_venture_effect"] * score + eta
    shift = solve_shift(base_logit, base_success)
    p_success = sigmoid(base_logit + shift)
    p_default = 1.0 - p_success
    label_default = rng.binomial(1, p_default)

    out = pd.DataFrame({
        "permalink": PERMALINK,
        "split": SPLIT,
        "label_default": label_default,
        "p_default_true": p_default,
        "burn_rate": burn,
        "requested_amount": requested,
        "milestone_count": milestone,
        "team_experience": team,
        "prev_funding": prev,
        "tam": tam,
    })
    diag = {"shift": float(shift), "success_rate_achieved": float(p_success.mean())}
    return out, diag


def summarize(out, base_success, noise_sd, name, path):
    feats = ["burn_rate", "requested_amount", "milestone_count", "team_experience", "prev_funding", "tam"]
    y = out["label_default"].values
    p = out["p_default_true"].values
    oracle_by_split = {}
    for s in ["train", "val", "test"]:
        m = out["split"].values == s
        oracle_by_split[s] = round(float(roc_auc_score(y[m], p[m])), 4)
    obs_default = 1.0 - P_OBS
    ratio = out["requested_amount"] / out["burn_rate"]
    integer_share = float(np.isclose(ratio, np.round(ratio), atol=1e-6).mean())
    stats = {c: {"min": round(float(out[c].min()), 4), "median": round(float(out[c].median()), 4),
                 "max": round(float(out[c].max()), 4)} for c in feats}
    corr = {c: round(float(np.corrcoef(out[c].values, y)[0, 1]), 4) for c in feats}
    return {
        "name": name,
        "base_success_target": base_success,
        "noise_sd": noise_sd,
        "default_rate": round(float(y.mean()), 4),
        "oracle_auc_all": round(float(roc_auc_score(y, p)), 4),
        "oracle_auc_by_split": oracle_by_split,
        "observable_only_auc": round(float(roc_auc_score(y, obs_default)), 4),
        "requested_integer_multiple_share": round(integer_share, 6),
        "feature_stats": stats,
        "label_correlations": corr,
        "file": path.name,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


results = []
for i, base in enumerate(BASE_SUCCESS_RATES):
    for j, sd in enumerate(NOISE_SD):
        rng = np.random.default_rng(SEED + 10 * i + j)
        out, diag = generate(rng, base, sd)
        name = f"b{int(base*100):02d}_n{int(sd*10):02d}"
        path = OUT_DIR / f"venture_cohort_{name}.csv"
        out.to_csv(path, index=False)
        summary = summarize(out, base, sd, name, path)
        summary.update(diag)
        summary["primary"] = (abs(base - PRIMARY[0]) < 1e-9 and abs(sd - PRIMARY[1]) < 1e-9)
        results.append(summary)
        print(f"[+] {name}: default={summary['default_rate']}  oracle AUC={summary['oracle_auc_all']}  "
              f"observable-only AUC={summary['observable_only_auc']}  "
              f"integer-multiple share={summary['requested_integer_multiple_share']}", flush=True)

primary = [r for r in results if r["primary"]][0]
(OUT_DIR / "venture_cohort_primary.csv").write_bytes((OUT_DIR / primary["file"]).read_bytes())

with open(REPORT, "w", encoding="utf-8") as f:
    json.dump({"seed": SEED, "params": PARAMS, "primary": primary["name"],
               "scenarios": results}, f, indent=2, ensure_ascii=False)

print(f"[+] primary scenario: {primary['name']} -> cohorts/venture_cohort_primary.csv", flush=True)
print(f"[+] wrote {REPORT.name}", flush=True)