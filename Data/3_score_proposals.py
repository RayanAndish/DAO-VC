"""
Data/3_score_proposals.py
=========================
Stage 3: extract five benchmark proposals from the held-out test split (15%) of
financial_dataset.csv and score them with R(p).

Revision notes
- Single output location: Data/Table_Proposals_Feature_Profiles.csv. The copy to the
  project root is removed, so no stale root copy can be read later.
- No silent exception handling. Missing strata fall back only with a printed warning.
- The clip R in [0.02, 0.98] is kept (it is what the paper uses), but every clipped
  proposal is reported, together with the unclipped R, so the effect is visible.
- Stratum bounds are declared once, so they can be cited in the paper.
"""

import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from sklearn.model_selection import train_test_split

HERE = Path(__file__).resolve().parent
MODELS = HERE / "models"
SEED = 42
np.random.seed(SEED)
torch.manual_seed(SEED)
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

R_FLOOR, R_CEIL = 0.02, 0.98

# (proposal id, R lower bound, R upper bound, random_state)
STRATA = [
    ("P-3", 0.00, 0.15, SEED),      # sound venture
    ("P-5", 0.32, 0.40, SEED),
    ("P-1", 0.35, 0.43, SEED + 1),
    ("P-4", 0.43, 0.48, SEED),
    ("P-2", 0.48, 0.55, SEED),      # hyped venture
]


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


scalers_path = MODELS / "scalers.joblib"
model_path = MODELS / "venture_risk_dnn.pt"
for p in (scalers_path, model_path):
    if not p.exists():
        sys.exit(f"[-] ERROR: {p} missing. Run 1_train_models.py first.")

scalers = joblib.load(scalers_path)
feature_cols = scalers["feature_cols_risk"]

risk_model = VentureRiskDNN(input_dim=6, dropout_rate=0.2).to(device)
risk_model.load_state_dict(torch.load(model_path, map_location=device))
risk_model.eval()

df_fin = pd.read_csv(HERE / "financial_dataset.csv")
_, df_temp = train_test_split(df_fin, test_size=0.30, random_state=SEED, stratify=df_fin["is_successful"])
_, df_test = train_test_split(df_temp, test_size=0.50, random_state=SEED, stratify=df_temp["is_successful"])
print(f"[*] Held-out test pool: {len(df_test):,} records", flush=True)

pool = df_test.sample(n=min(20000, len(df_test)), random_state=SEED).copy()
X_pool_s = scalers["scaler_risk"].transform(pool[feature_cols].values)
with torch.no_grad():
    p_solv = risk_model(torch.tensor(X_pool_s, dtype=torch.float32).to(device)).cpu().numpy().flatten()

pool["P_Solvency"] = p_solv
pool["R_p_raw"] = 1.0 - p_solv
pool["R_p"] = np.clip(pool["R_p_raw"], R_FLOOR, R_CEIL)

selected = []
for pid, lo, hi, rs in STRATA:
    cand = pool[(pool["R_p"] >= lo) & (pool["R_p"] <= hi)]
    if pid == "P-3":
        cand = pool[pool["R_p"] <= hi]
    if len(cand) == 0:
        sys.exit(f"[-] ERROR: no candidate for {pid} in R in [{lo}, {hi}]; widen the stratum and document it")
    row = cand.sample(n=1, random_state=rs).copy()
    row["Proposal_ID"] = pid
    selected.append(row)

df_prop = pd.concat(selected).reset_index(drop=True)

clipped = df_prop[df_prop["R_p_raw"] != df_prop["R_p"]]
for _, r in clipped.iterrows():
    print(f"[!] {r['Proposal_ID']}: R unclipped {r['R_p_raw']:.4f} -> clipped to {r['R_p']:.2f}", flush=True)

df_prop["P_Solvency"] = df_prop["P_Solvency"].round(4)
df_prop["AI_Risk_Score_R_p"] = df_prop["R_p"].round(4)
df_prop["Bayesian_Odds_Ratio"] = ((1.0 - df_prop["AI_Risk_Score_R_p"]) / df_prop["AI_Risk_Score_R_p"]).round(4)

export_cols = ["Proposal_ID", "tam", "burn_rate", "requested_amount", "milestone_count",
               "team_experience", "prev_funding", "P_Solvency", "AI_Risk_Score_R_p", "Bayesian_Odds_Ratio"]
df_out = df_prop[export_cols].sort_values("Proposal_ID").reset_index(drop=True)

out_path = HERE / "Table_Proposals_Feature_Profiles.csv"
df_out.to_csv(out_path, index=False)
print(f"[+] {out_path} written", flush=True)
print(df_out[["Proposal_ID", "AI_Risk_Score_R_p", "Bayesian_Odds_Ratio", "P_Solvency"]].to_string(index=False))
