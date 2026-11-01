"""
Data/2_evaluate_test_metrics.py
===============================
Stage 2: Independent Test Evaluation using PyTorch Models.
Evaluates out-of-sample performance, strictly calibrates tau_norm for exact ~1.6% FPR,
and exports Table_3_AI_Validation_Metrics.csv and Figure 7.
"""

import os
import sys
import joblib
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from sklearn.model_selection import train_test_split
from sklearn.metrics import (
    roc_curve,
    roc_auc_score,
    auc,
    brier_score_loss,
    confusion_matrix
)

import torch
import torch.nn as nn

SEED = 42
np.random.seed(SEED)
torch.manual_seed(SEED)
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

plt.style.use("seaborn-v0_8-whitegrid")
plt.rcParams["font.family"] = "sans-serif"

print("=" * 80, flush=True)
print("[STAGE 2] INDEPENDENT HELD-OUT TEST EVALUATION & RIGOROUS CALIBRATION", flush=True)
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

class AnomalyAutoencoder(nn.Module):
    def __init__(self, input_dim=8):
        super(AnomalyAutoencoder, self).__init__()
        self.encoder = nn.Sequential(
            nn.Linear(input_dim, 16),
            nn.ReLU(),
            nn.Linear(16, 4),
            nn.ReLU()
        )
        self.decoder = nn.Sequential(
            nn.Linear(4, 16),
            nn.ReLU(),
            nn.Linear(16, input_dim)
        )

    def forward(self, x):
        latent = self.encoder(x)
        return self.decoder(latent)

scalers = joblib.load("models/scalers.joblib")

risk_model = VentureRiskDNN(input_dim=6, dropout_rate=0.2).to(device)
risk_model.load_state_dict(torch.load("models/venture_risk_dnn.pt", map_location=device))
risk_model.eval()

autoencoder = AnomalyAutoencoder(input_dim=8).to(device)
autoencoder.load_state_dict(torch.load("models/telemetry_autoencoder.pt", map_location=device))
autoencoder.eval()

# 1. EVALUATE VENTURE RISK DNN (R(p))
print("\n[*] Evaluating Venture Risk DNN on 75,000 held-out test records...", flush=True)
df_fin = pd.read_csv("financial_dataset.csv")
X_risk = df_fin[scalers["feature_cols_risk"]].values
y_risk = df_fin["is_successful"].values.astype(np.float32)

_, X_r_temp, _, y_r_temp = train_test_split(
    X_risk, y_risk, test_size=0.30, random_state=SEED, stratify=y_risk
)
_, X_r_test, _, y_r_test = train_test_split(
    X_r_temp, y_r_temp, test_size=0.50, random_state=SEED, stratify=y_r_temp
)

X_r_test_scaled = scalers["scaler_risk"].transform(X_r_test)

with torch.no_grad():
    test_tensor_r = torch.tensor(X_r_test_scaled, dtype=torch.float32).to(device)
    y_r_pred_prob = risk_model(test_tensor_r).cpu().numpy().flatten()

auc_risk = roc_auc_score(y_r_test, y_r_pred_prob)
brier_risk = brier_score_loss(y_r_test, y_r_pred_prob)

y_r_pred_binary = (y_r_pred_prob >= 0.50).astype(int)
tn_r, fp_r, fn_r, tp_r = confusion_matrix(y_r_test, y_r_pred_binary).ravel()
tpr_risk = tp_r / (tp_r + fn_r)
fpr_risk = fp_r / (fp_r + tn_r)

print(f"    [+] Venture Risk AUC:         {auc_risk:.4f}")
print(f"    [+] Brier Calibration Score:  {brier_risk:.4f}")
print(f"    [+] Solvency Detection (TPR): {tpr_risk*100:.2f}%")
print(f"    [+] False Alarm Rate (FPR):   {fpr_risk*100:.2f}%")

# 2. EVALUATE 8D ANOMALY AUTOENCODER (B(u))
print("\n[*] Evaluating Anomaly Autoencoder on 90,000 held-out test traces...", flush=True)
df_user = pd.read_csv("user_behavior_dataset.csv")
X_user = df_user[scalers["feature_cols_anomaly"]].values
y_user = df_user["is_bot"].values.astype(int)

X_u_train, X_u_temp, y_u_train, y_u_temp = train_test_split(
    X_user, y_user, test_size=0.30, random_state=SEED, stratify=y_user
)
X_u_val, X_u_test, y_u_val, y_u_test = train_test_split(
    X_u_temp, y_u_temp, test_size=0.50, random_state=SEED, stratify=y_u_temp
)

X_u_val_scaled = scalers["scaler_user"].transform(X_u_val)
X_u_test_scaled = scalers["scaler_user"].transform(X_u_test)

# Rigorous Statistical Calibration:
# Target FPR = 1.61% at tau_Anomaly = 0.65 requires matching the 98.39th percentile of honest errors
tau_Anomaly = 0.65
with torch.no_grad():
    val_honest_tensor = torch.tensor(X_u_val_scaled[y_u_val == 0], dtype=torch.float32).to(device)
    val_recon = autoencoder(val_honest_tensor).cpu().numpy()
    val_errors = np.mean((X_u_val_scaled[y_u_val == 0] - val_recon) ** 2, axis=1)
    
    honest_target_quantile = float(np.percentile(val_errors, 98.39))
    tau_norm = honest_target_quantile / tau_Anomaly

# Test set evaluation
with torch.no_grad():
    test_tensor_u = torch.tensor(X_u_test_scaled, dtype=torch.float32).to(device)
    test_recon = autoencoder(test_tensor_u).cpu().numpy()
    raw_test_errors = np.mean((X_u_test_scaled - test_recon) ** 2, axis=1)

# Scaled continuous metric B(u) in [0, 1] (Eq. 5)
b_u_scores = np.clip(raw_test_errors / max(tau_norm, 1e-7), 0.0, 1.0)

fpr_a, tpr_a, _ = roc_curve(y_u_test, raw_test_errors)
auc_anomaly = auc(fpr_a, tpr_a)

y_u_pred_anomaly = (b_u_scores >= tau_Anomaly).astype(int)
tn_a, fp_a, fn_a, tp_a = confusion_matrix(y_u_test, y_u_pred_anomaly).ravel()
tpr_anomaly = tp_a / (tp_a + fn_a)
fpr_anomaly = fp_a / (fp_a + tn_a)

print(f"    [+] Anomaly Detection AUC:   {auc_anomaly:.4f}")
print(f"    [+] Calibrated tau_norm:     {tau_norm:.6f}")
print(f"    [+] True Positive (TPR):     {tpr_anomaly*100:.2f}% (at tau=0.65)")
print(f"    [+] False Alarm Rate (FPR):  {fpr_anomaly*100:.2f}% (at tau=0.65)")

# 3. EXPORT VERIFIED TABLE 3 CSV
df_table3 = pd.DataFrame([
    {
        "Model Component": "Validator Anomaly Autoencoder (B(u))",
        "Ground-Truth Target": "is_bot (0: Honest, 1: Sybil / Malicious)",
        "Input Dimension": "8 Telemetry Features",
        "Train / Val / Test Split": "420,000 / 90,000 / 90,000 traces (70/15/15)",
        "Test ROC-AUC": round(auc_anomaly, 4),
        "Detection Rate (TPR)": f"{tpr_anomaly*100:.2f}%",
        "False Alarm Rate (FPR)": f"{fpr_anomaly*100:.2f}%",
        "Calibration / Loss Metric": f"tau_norm = {tau_norm:.6f} (MSE = {val_errors.mean():.6f})"
    },
    {
        "Model Component": "Venture Risk DNN (R(p))",
        "Ground-Truth Target": "is_successful (1: Solvent, 0: Defaulted)",
        "Input Dimension": "6 Financial Indicators",
        "Train / Val / Test Split": "350,000 / 75,000 / 75,000 samples (70/15/15)",
        "Test ROC-AUC": round(auc_risk, 4),
        "Detection Rate (TPR)": f"{tpr_risk*100:.2f}%",
        "False Alarm Rate (FPR)": f"{fpr_risk*100:.2f}%",
        "Calibration / Loss Metric": f"Brier Score = {brier_risk:.4f} (Sigmoid calibrated)"
    }
])
df_table3.to_csv("Table_3_AI_Validation_Metrics.csv", index=False)
print("\n[+] Table_3_AI_Validation_Metrics.csv exported successfully.", flush=True)

# 4. GENERATE PUBLICATION FIGURE 7
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))

ax1.plot([0, 1], [0, 1], "k--", alpha=0.5, label="Random Guessing (AUC = 0.50)")
ax1.plot(fpr_a, tpr_a, color="#1f77b4", linewidth=2.8, label=f"8D Autoencoder B(u) (AUC = {auc_anomaly:.3f})")
ax1.scatter([fpr_anomaly], [tpr_anomaly], color="red", s=90, zorder=5, edgecolor="black", linewidth=1.2,
            label=f"Cutoff tau=0.65 (FPR={fpr_anomaly*100:.1f}%, TPR={tpr_anomaly*100:.1f}%)")
ax1.set_title("A. Validator Telemetry Anomaly Detection (8-Dimensional)", fontsize=12, fontweight="bold", pad=12)
ax1.set_xlabel("False Positive Rate (FPR)", fontsize=11)
ax1.set_ylabel("True Positive Rate (TPR / Recall)", fontsize=11)
ax1.set_xlim([-0.02, 1.02])
ax1.set_ylim([-0.02, 1.02])
ax1.legend(loc="lower right", fontsize=10, shadow=True, frameon=True)
ax1.grid(True, linestyle=":", alpha=0.5)

fpr_r, tpr_r, _ = roc_curve(y_r_test, y_r_pred_prob)
ax2.plot([0, 1], [0, 1], "k--", alpha=0.5, label="Random Guessing (AUC = 0.50)")
ax2.plot(fpr_r, tpr_r, color="#2ca02c", linewidth=2.8, label=f"Venture Risk DNN R(p) (AUC = {auc_risk:.3f})")
ax2.scatter([fpr_risk], [tpr_risk], color="red", s=90, zorder=5, edgecolor="black", linewidth=1.2,
            label=f"Operating Cutoff (FPR={fpr_risk*100:.1f}%, TPR={tpr_risk*100:.1f}%)")
ax2.set_title("B. Predictive Venture Solvency Classification (6-Dimensional)", fontsize=12, fontweight="bold", pad=12)
ax2.set_xlabel("False Positive Rate (FPR)", fontsize=11)
ax2.set_ylabel("True Positive Rate (TPR / Recall)", fontsize=11)
ax2.set_xlim([-0.02, 1.02])
ax2.set_ylim([-0.02, 1.02])
ax2.legend(loc="lower right", fontsize=10, shadow=True, frameon=True)
ax2.grid(True, linestyle=":", alpha=0.5)

plt.suptitle("Figure 7 | Empirical Receiver Operating Characteristic (ROC) of Off-Chain AI Meta-Layer",
             fontsize=13, fontweight="bold", y=1.02)
plt.tight_layout()
plt.savefig("Figure_7_AI_Anomaly_and_Risk_ROC.png", dpi=300, bbox_inches="tight")
print("[+] Figure_7_AI_Anomaly_and_Risk_ROC.png saved successfully.", flush=True)
print("=" * 80, flush=True)