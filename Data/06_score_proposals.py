"""
Data/06_score_proposals.py
==========================
Selects five anonymised proposals from the held-out test split and scores them with R(p).

Selection rule (fixed before scoring; the outcome label is not used)
  For each of the 10th, 30th, 50th, 70th and 90th percentiles of R(p), take the test-split
  proposal with the nearest R(p). IDs P-1 .. P-5 follow ascending R(p).

Outputs (under Data/)
  Table_Proposals_Feature_Profiles.csv   public: IDs, R(p) and the six venture features
  proposal_selection.json                public: rule, targets and provenance hashes
  private/proposal_mapping.csv           PRIVATE: ID -> cohort row, permalink, label.
                                         Never publish this file.
"""

import hashlib
import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import torch
import torch.nn as nn

HERE = Path(__file__).resolve().parent
MODELS = HERE / "models"
COHORT = HERE / "cohorts" / "venture_cohort_primary.csv"
OUT_PROFILE = HERE / "Table_Proposals_Feature_Profiles.csv"
OUT_RULE = HERE / "proposal_selection.json"
PRIVATE_DIR = HERE / "private"
PRIVATE_MAP = PRIVATE_DIR / "proposal_mapping.csv"

QUANTILES = [0.10, 0.30, 0.50, 0.70, 0.90]
R_MIN, R_MAX = 0.02, 0.98   # contract bounds for riskScore (2e16 .. 98e16)


class VentureRiskDNN(nn.Module):
    def __init__(self, input_dim=6, dropout_rate=0.2):
        super().__init__()
        self.fc1 = nn.Linear(input_dim, 32)
        self.relu1 = nn.ReLU()
        self.dropout = nn.Dropout(p=dropout_rate)
        self.fc2 = nn.Linear(32, 16)
        self.relu2 = nn.ReLU()
        self.fc3 = nn.Linear(16, 1)
        self.sigmoid = nn.Sigmoid()

    def forward(self, x):
        h1 = self.relu1(self.fc1(x))
        h2 = self.relu2(self.fc2(self.dropout(h1)))
        return self.sigmoid(self.fc3(h2))


def sha256_file(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


# ------------------------------------------------------------------------------
# 1. Checks
# ------------------------------------------------------------------------------
for p in [COHORT, MODELS / "venture_risk_dnn.pt", MODELS / "scalers.joblib",
          MODELS / "model_hash.json", MODELS / "train_report.json"]:
    if not p.exists():
        sys.exit(f"[-] ERROR: {p} not found. Run 05_train_models.py first.")

model_hash = json.loads((MODELS / "model_hash.json").read_text(encoding="utf-8"))["model_hash"]
train_report = json.loads((MODELS / "train_report.json").read_text(encoding="utf-8"))
if train_report["model_hash"] != model_hash:
    sys.exit("[-] ERROR: model_hash.json and train_report.json disagree. Re-run 05_train_models.py.")

art = joblib.load(MODELS / "scalers.joblib")
FEATS = art["features_risk"]
LOG_COLS = art["risk_log"]

# ------------------------------------------------------------------------------
# 2. Score the test split
# ------------------------------------------------------------------------------
cohort = pd.read_csv(COHORT)
test_rows = cohort.index[cohort["split"] == "test"].to_numpy()
test = cohort.loc[test_rows].reset_index(drop=True)

X = test[FEATS].astype(float).copy()
for c in LOG_COLS:
    X[c] = np.log1p(X[c])
Xs = art["scaler_risk"].transform(X.values)

model = VentureRiskDNN(input_dim=len(FEATS), dropout_rate=0.2)
model.load_state_dict(torch.load(MODELS / "venture_risk_dnn.pt", map_location="cpu"))
model.eval()
with torch.no_grad():
    R = model(torch.tensor(Xs, dtype=torch.float32)).numpy().ravel()

# ------------------------------------------------------------------------------
# 3. Select five proposals by the fixed quantile rule
# ------------------------------------------------------------------------------
targets = np.quantile(R, QUANTILES)
chosen = []
for t in targets:
    j = int(np.argmin(np.abs(R - t)))
    if j in chosen:
        sys.exit("[-] ERROR: two quantile targets map to the same proposal. "
                 "Check the test split size.")
    chosen.append(j)
chosen = sorted(chosen, key=lambda j: R[j])
ids = [f"P-{k + 1}" for k in range(len(chosen))]

out_of_bounds = [(pid, float(R[j])) for pid, j in zip(ids, chosen) if not (R_MIN <= R[j] <= R_MAX)]
if out_of_bounds:
    sys.exit(f"[-] ERROR: R outside contract bounds {out_of_bounds}. "
             "Review the model output; do not clip silently.")

# ------------------------------------------------------------------------------
# 4. Public profile table (no identifiers)
# ------------------------------------------------------------------------------
rows = []
for pid, j in zip(ids, chosen):
    r = test.iloc[j]
    rows.append({
        "Proposal_ID": pid,
        "AI_Risk_Score_R_p": round(float(R[j]), 6),
        "burn_rate": round(float(r["burn_rate"]), 2),
        "requested_amount": round(float(r["requested_amount"]), 2),
        "milestone_count": int(r["milestone_count"]),
        "team_experience": round(float(r["team_experience"]), 4),
        "prev_funding": int(r["prev_funding"]),
        "tam": round(float(r["tam"]), 2),
    })
pd.DataFrame(rows).to_csv(OUT_PROFILE, index=False)

rule = {
    "rule": "nearest test-split proposal to each R(p) quantile",
    "quantiles": QUANTILES,
    "quantile_targets": [round(float(t), 6) for t in targets],
    "selected_R": {pid: round(float(R[j]), 6) for pid, j in zip(ids, chosen)},
    "test_rows": int(len(test)),
    "model_hash": model_hash,
    "cohort_sha256": sha256_file(COHORT),
    "risk_model_sha256": sha256_file(MODELS / "venture_risk_dnn.pt"),
}
with open(OUT_RULE, "w", encoding="utf-8") as f:
    json.dump(rule, f, indent=2, ensure_ascii=False)

# ------------------------------------------------------------------------------
# 5. Private mapping (never published)
# ------------------------------------------------------------------------------
PRIVATE_DIR.mkdir(exist_ok=True)
priv = pd.DataFrame([{
    "Proposal_ID": pid,
    "cohort_row": int(test_rows[j]),
    "permalink": test.iloc[j]["permalink"],
    "label_default": int(test.iloc[j]["label_default"]),
    "R_p": round(float(R[j]), 6),
} for pid, j in zip(ids, chosen)])
priv.to_csv(PRIVATE_MAP, index=False)

print("[+] selected proposals:", flush=True)
print(pd.DataFrame(rows)[["Proposal_ID", "AI_Risk_Score_R_p"]].to_string(index=False), flush=True)
print(f"[+] wrote {OUT_PROFILE.name}, {OUT_RULE.name}, private/{PRIVATE_MAP.name}", flush=True)