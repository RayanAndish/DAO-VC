"""
Data/2_evaluate_test_metrics.py
===============================
Stage 2: held-out test evaluation of R(p) and B(u), threshold calibration on the
validation split, Table 3 and Figure 7.

Revision notes
- Paths are relative to this file. Split sizes are computed from the data, not typed in.
- The calibration is unchanged numerically: tau_norm = q_val(98.39%) / 0.65, so
  B(u) >= 0.65 <=> raw error >= q_val(98.39%). The threshold is chosen on validation only.
  The file calibration.json records this so the paper can state it plainly (S3).
"""

import json
import sys
from pathlib import Path

import joblib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from sklearn.metrics import auc, brier_score_loss, confusion_matrix, roc_auc_score, roc_curve
from sklearn.model_selection import train_test_split

HERE = Path(__file__).resolve().parent
MODELS = HERE / "models"
SEED = 42
np.random.seed(SEED)
torch.manual_seed(SEED)
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

plt.style.use("seaborn-v0_8-whitegrid")
plt.rcParams["font.family"] = "sans-serif"

TAU_ANOMALY = 0.65
TARGET_PERCENTILE = 98.39     # validation honest errors -> FPR ~ 1.61%


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


class AnomalyAutoencoder(nn.Module):
    def __init__(self, input_dim=8):
        super().__init__()
        self.encoder = nn.Sequential(nn.Linear(input_dim, 16), nn.ReLU(), nn.Linear(16, 4), nn.ReLU())
        self.decoder = nn.Sequential(nn.Linear(4, 16), nn.ReLU(), nn.Linear(16, input_dim))

    def forward(self, x):
        return self.decoder(self.encoder(x))


def load_inputs():
    scalers_path = MODELS / "scalers.joblib"
    for p in [scalers_path, MODELS / "venture_risk_dnn.pt", MODELS / "telemetry_autoencoder.pt"]:
        if not p.exists():
            sys.exit(f"[-] ERROR: {p} missing. Run 1_train_models.py first.")
    return joblib.load(scalers_path)


scalers = load_inputs()

risk_model = VentureRiskDNN().to(device)
risk_model.load_state_dict(torch.load(MODELS / "venture_risk_dnn.pt", map_location=device))
risk_model.eval()

autoencoder = AnomalyAutoencoder().to(device)
autoencoder.load_state_dict(torch.load(MODELS / "telemetry_autoencoder.pt", map_location=device))
autoencoder.eval()

# ------------------------------------------------------------------------------
# 1. VENTURE RISK DNN R(p)
# ------------------------------------------------------------------------------
df_fin = pd.read_csv(HERE / "financial_dataset.csv")
X_risk = df_fin[scalers["feature_cols_risk"]].values
y_risk = df_fin["is_successful"].values.astype(np.float32)

_, X_r_temp, _, y_r_temp = train_test_split(X_risk, y_risk, test_size=0.30, random_state=SEED, stratify=y_risk)
X_r_train, _, y_r_train, _ = train_test_split(X_risk, y_risk, test_size=0.30, random_state=SEED, stratify=y_risk)
X_r_val, X_r_test, y_r_val, y_r_test = train_test_split(
    X_r_temp, y_r_temp, test_size=0.50, random_state=SEED, stratify=y_r_temp)

with torch.no_grad():
    p_risk = risk_model(torch.tensor(scalers["scaler_risk"].transform(X_r_test), dtype=torch.float32)
                        .to(device)).cpu().numpy().flatten()

auc_risk = roc_auc_score(y_r_test, p_risk)
brier_risk = brier_score_loss(y_r_test, p_risk)
tn, fp, fn, tp = confusion_matrix(y_r_test, (p_risk >= 0.5).astype(int)).ravel()
tpr_risk, fpr_risk = tp / (tp + fn), fp / (fp + tn)

# ------------------------------------------------------------------------------
# 2. EIGHT-DIMENSIONAL AUTOENCODER B(u)
# ------------------------------------------------------------------------------
df_user = pd.read_csv(HERE / "user_behavior_dataset.csv")
X_user = df_user[scalers["feature_cols_anomaly"]].values
y_user = df_user["is_bot"].values.astype(int)

X_u_train, X_u_temp, y_u_train, y_u_temp = train_test_split(
    X_user, y_user, test_size=0.30, random_state=SEED, stratify=y_user)
X_u_val, X_u_test, y_u_val, y_u_test = train_test_split(
    X_u_temp, y_u_temp, test_size=0.50, random_state=SEED, stratify=y_u_temp)

X_u_val_s = scalers["scaler_user"].transform(X_u_val)
X_u_test_s = scalers["scaler_user"].transform(X_u_test)

with torch.no_grad():
    honest_val = X_u_val_s[y_u_val == 0]
    val_recon = autoencoder(torch.tensor(honest_val, dtype=torch.float32).to(device)).cpu().numpy()
    val_errors = np.mean((honest_val - val_recon) ** 2, axis=1)
    q_val = float(np.percentile(val_errors, TARGET_PERCENTILE))
    tau_norm = q_val / TAU_ANOMALY          # validation-only calibration

    test_recon = autoencoder(torch.tensor(X_u_test_s, dtype=torch.float32).to(device)).cpu().numpy()
    raw_test_errors = np.mean((X_u_test_s - test_recon) ** 2, axis=1)

b_u_scores = np.clip(raw_test_errors / max(tau_norm, 1e-7), 0.0, 1.0)

fpr_a, tpr_a, _ = roc_curve(y_u_test, raw_test_errors)
auc_anomaly = auc(fpr_a, tpr_a)

tn_a, fp_a, fn_a, tp_a = confusion_matrix(y_u_test, (b_u_scores >= TAU_ANOMALY).astype(int)).ravel()
tpr_anomaly, fpr_anomaly = tp_a / (tp_a + fn_a), fp_a / (fp_a + tn_a)

calibration = {
    "tau_anomaly": TAU_ANOMALY,
    "target_percentile_validation": TARGET_PERCENTILE,
    "q_val_raw_mse": q_val,
    "tau_norm": tau_norm,
    "note": "threshold chosen on validation honest errors; equivalent to raw MSE >= q_val",
}
with open(MODELS / "calibration.json", "w", encoding="utf-8") as f:
    json.dump(calibration, f, indent=4)

print(f"[+] Risk AUC {auc_risk:.4f} | Brier {brier_risk:.4f} | TPR {tpr_risk*100:.2f}% | FPR {fpr_risk*100:.2f}%")
print(f"[+] Anomaly AUC {auc_anomaly:.4f} | tau_norm {tau_norm:.6f} | TPR {tpr_anomaly*100:.2f}% | FPR {fpr_anomaly*100:.2f}%")

# ------------------------------------------------------------------------------
# 3. TABLE 3 (split sizes computed from the data)
# ------------------------------------------------------------------------------
def split_text(n_total, parts):
    return " / ".join(f"{n:,}" for n in parts)


n_fin = len(df_fin)
n_user = len(df_user)
df_table3 = pd.DataFrame([
    {
        "Model Component": "Validator Anomaly Autoencoder (B(u))",
        "Ground-Truth Target": "is_bot (0: Honest, 1: Sybil / Malicious)",
        "Input Dimension": "8 Telemetry Features",
        "Train / Val / Test Split": split_text(n_user, [len(X_u_train), len(X_u_val), len(X_u_test)]) + " traces",
        "Test ROC-AUC": round(auc_anomaly, 4),
        "Detection Rate (TPR)": f"{tpr_anomaly*100:.2f}%",
        "False Alarm Rate (FPR)": f"{fpr_anomaly*100:.2f}%",
        "Calibration / Loss Metric": f"tau_norm = {tau_norm:.6f} (val q98.39 = {q_val:.6f})",
    },
    {
        "Model Component": "Venture Risk DNN (R(p))",
        "Ground-Truth Target": "is_successful (1: Solvent, 0: Defaulted)",
        "Input Dimension": "6 Financial Indicators",
        "Train / Val / Test Split": split_text(n_fin, [len(X_r_train), len(X_r_val), len(X_r_test)]) + " samples",
        "Test ROC-AUC": round(auc_risk, 4),
        "Detection Rate (TPR)": f"{tpr_risk*100:.2f}%",
        "False Alarm Rate (FPR)": f"{fpr_risk*100:.2f}%",
        "Calibration / Loss Metric": f"Brier Score = {brier_risk:.4f} (sigmoid output)",
    },
])
df_table3.to_csv(HERE / "Table_3_AI_Validation_Metrics.csv", index=False)
print("[+] Table_3_AI_Validation_Metrics.csv written", flush=True)

# ------------------------------------------------------------------------------
# 4. FIGURE 7
# ------------------------------------------------------------------------------
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))

ax1.plot([0, 1], [0, 1], "k--", alpha=0.5, label="Random guessing (AUC = 0.50)")
ax1.plot(fpr_a, tpr_a, color="#1f77b4", linewidth=2.8, label=f"8D autoencoder B(u) (AUC = {auc_anomaly:.3f})")
ax1.scatter([fpr_anomaly], [tpr_anomaly], color="red", s=90, zorder=5, edgecolor="black",
            label=f"Cutoff tau=0.65 (FPR={fpr_anomaly*100:.1f}%, TPR={tpr_anomaly*100:.1f}%)")
ax1.set_title("A. Validator telemetry anomaly detection (8-D)", fontsize=12, fontweight="bold", pad=12)

fpr_r, tpr_r, _ = roc_curve(y_r_test, p_risk)
ax2.plot([0, 1], [0, 1], "k--", alpha=0.5, label="Random guessing (AUC = 0.50)")
ax2.plot(fpr_r, tpr_r, color="#2ca02c", linewidth=2.8, label=f"Venture risk DNN R(p) (AUC = {auc_risk:.3f})")
ax2.scatter([fpr_risk], [tpr_risk], color="red", s=90, zorder=5, edgecolor="black",
            label=f"Operating point at 0.5 (FPR={fpr_risk*100:.1f}%, TPR={tpr_risk*100:.1f}%)")
ax2.set_title("B. Venture solvency classification (6-D)", fontsize=12, fontweight="bold", pad=12)

for ax in (ax1, ax2):
    ax.set_xlabel("False positive rate (FPR)", fontsize=11)
    ax.set_ylabel("True positive rate (TPR)", fontsize=11)
    ax.set_xlim([-0.02, 1.02])
    ax.set_ylim([-0.02, 1.02])
    ax.legend(loc="lower right", fontsize=10, frameon=True)
    ax.grid(True, linestyle=":", alpha=0.5)

plt.suptitle("Figure 7 | Empirical ROC of the off-chain AI meta-layer", fontsize=13, fontweight="bold", y=1.02)
plt.tight_layout()
plt.savefig(HERE / "Figure_7_AI_Anomaly_and_Risk_ROC.png", dpi=300, bbox_inches="tight")
print("[+] Figure_7_AI_Anomaly_and_Risk_ROC.png saved", flush=True)
