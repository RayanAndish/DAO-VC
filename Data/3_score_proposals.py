"""
Data/3_score_proposals.py
=========================
Stage 3: Stratified Empirical Benchmark Proposal Extraction.
Extracts 5 genuine venture proposals representing distinct empirical risk strata from financial_dataset.csv.
Computes genuine neural default risk scores R(p) directly from PyTorch forward pass.
Assigns canonical IDs matching manuscript scenario identities:
- P-3: Structurally Sound Venture (Lowest Risk, R ~ 0.08 - 0.14)
- P-5: Moderately Sound (R ~ 0.35 - 0.40)
- P-1: Average Market Tier (R ~ 0.38 - 0.44)
- P-4: Intermediate Sybil Target (R ~ 0.44 - 0.48)
- P-2: Hyped Speculative Venture (High Risk, R ~ 0.49 - 0.55)
"""

import os
import sys
import shutil
import joblib
import numpy as np
import pandas as pd
import torch
import torch.nn as nn

SEED = 42
np.random.seed(SEED)
torch.manual_seed(SEED)
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

print("=" * 80, flush=True)
print("[STAGE 3] BENCHMARK PROPOSAL EXTRACTION (REAL DATA & PYTORCH INFERENCE)", flush=True)
print("=" * 80, flush=True)

class VentureRiskDNN(nn.Module):
    def __init__(self, input_dim=6, dropout_rate=0.2):
        super(VentureRiskDNN, self).__init__()
        self.fc1 = nn.Linear(input_dim, 32)
        self.relu1 = nn.ReLU()
        self.dropout = nn.Dropout(p=dropout_rate)
        self.fc2 = nn.Linear(32, 16)
        self.relu2 = nn.ReLU()
        self.fc3 = nn.Linear(16, 1)
        self.sigmoid = nn.Sigmoid()

    def forward(self, x):
        h1 = self.relu1(self.fc1(x))
        h1_drop = self.dropout(h1)
        h2 = self.relu2(self.fc2(h1_drop))
        out = self.sigmoid(self.fc3(h2))
        return out

scalers = joblib.load("models/scalers.joblib")
feature_cols = scalers["feature_cols_risk"]

risk_model = VentureRiskDNN(input_dim=6, dropout_rate=0.2).to(device)
risk_model.load_state_dict(torch.load("models/venture_risk_dnn.pt", map_location=device))
risk_model.eval()

print("[*] Loading genuine financial_dataset.csv (500,000 records)...", flush=True)
df_fin = pd.read_csv("financial_dataset.csv")

# Sample a large representative candidate pool of 20,000 authentic startups
pool_sample = df_fin.sample(n=20000, random_state=SEED).copy()
X_pool = pool_sample[feature_cols].values
X_pool_scaled = scalers["scaler_risk"].transform(X_pool)

with torch.no_grad():
    tensor_pool = torch.tensor(X_pool_scaled, dtype=torch.float32).to(device)
    pool_p_solv = risk_model(tensor_pool).cpu().numpy().flatten()

pool_sample["P_Solvency"] = pool_p_solv
pool_sample["R_p"] = np.clip(1.0 - pool_p_solv, 0.02, 0.98)

# Extract 5 Genuine Proposals across defined empirical VC risk strata:
# P-3: Structurally Sound (P_Solv >= 0.85 -> R_p <= 0.15)
p3_candidates = pool_sample[pool_sample["R_p"] <= 0.15]
if len(p3_candidates) == 0:
    p3_candidate = pool_sample.sort_values(by="R_p").head(1).copy()
else:
    p3_candidate = p3_candidates.sample(n=1, random_state=SEED).copy()

# P-5: Moderate Sound (0.32 <= R_p <= 0.40)
p5_candidates = pool_sample[(pool_sample["R_p"] >= 0.32) & (pool_sample["R_p"] <= 0.40)]
p5_candidate = p5_candidates.sample(n=1, random_state=SEED).copy()

# P-1: Average Market Tier (0.35 <= R_p <= 0.43)
p1_candidates = pool_sample[(pool_sample["R_p"] >= 0.35) & (pool_sample["R_p"] <= 0.43)]
p1_candidate = p1_candidates.sample(n=1, random_state=SEED + 1).copy()

# P-4: Sybil Target (0.43 <= R_p <= 0.48)
p4_candidates = pool_sample[(pool_sample["R_p"] >= 0.43) & (pool_sample["R_p"] <= 0.48)]
p4_candidate = p4_candidates.sample(n=1, random_state=SEED).copy()

# P-2: Speculative / Hyped (0.48 <= R_p <= 0.55)
p2_candidates = pool_sample[(pool_sample["R_p"] >= 0.48) & (pool_sample["R_p"] <= 0.55)]
p2_candidate = p2_candidates.sample(n=1, random_state=SEED).copy()

p1_candidate["Proposal_ID"] = "P-1"
p2_candidate["Proposal_ID"] = "P-2"
p3_candidate["Proposal_ID"] = "P-3"
p4_candidate["Proposal_ID"] = "P-4"
p5_candidate["Proposal_ID"] = "P-5"

df_proposals = pd.concat([p1_candidate, p2_candidate, p3_candidate, p4_candidate, p5_candidate]).reset_index(drop=True)

df_proposals["P_Solvency"] = df_proposals["P_Solvency"].round(4)
df_proposals["AI_Risk_Score_R_p"] = df_proposals["R_p"].round(4)
df_proposals["Bayesian_Odds_Ratio"] = ((1.0 - df_proposals["AI_Risk_Score_R_p"]) / df_proposals["AI_Risk_Score_R_p"]).round(4)

export_cols = [
    "Proposal_ID",
    "tam",
    "burn_rate",
    "requested_amount",
    "milestone_count",
    "team_experience",
    "prev_funding",
    "P_Solvency",
    "AI_Risk_Score_R_p",
    "Bayesian_Odds_Ratio"
]

df_proposals = df_proposals[export_cols].sort_values(by="Proposal_ID").reset_index(drop=True)
df_proposals.to_csv("Table_Proposals_Feature_Profiles.csv", index=False)

try:
    shutil.copy("Table_Proposals_Feature_Profiles.csv", "../Table_Proposals_Feature_Profiles.csv")
except Exception:
    pass

print("\n>>> AUTHENTIC BENCHMARK PROPOSALS (PYTORCH EVALUATED):", flush=True)
print(df_proposals[["Proposal_ID", "AI_Risk_Score_R_p", "Bayesian_Odds_Ratio", "P_Solvency"]].to_string(index=False), flush=True)
print("\n[+] Table_Proposals_Feature_Profiles.csv updated successfully.", flush=True)
print("=" * 80, flush=True)