"""
2_evaluate_test_metrics.py
==========================
Stage 2: Independent Test Evaluation.
Loads serialized models from models/, benchmarks out-of-sample performance,
exports Table_2b_AI_Validation_Metrics.csv, and plots publication Figure 7.
"""

import joblib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.metrics import (
    auc,
    brier_score_loss,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
    roc_curve,
)
from sklearn.model_selection import train_test_split

plt.style.use("seaborn-v0_8-whitegrid")
plt.rcParams["font.family"] = "sans-serif"

print("=" * 80)
print("STAGE 2: EVALUATING OUT-OF-SAMPLE TEST METRICS FROM SERIALIZED MODELS")
print("=" * 80)

# Load Models and Scalers
scalers = joblib.load("models/scalers.joblib")
risk_dnn = joblib.load("models/venture_risk_dnn.joblib")
autoencoder = joblib.load("models/telemetry_autoencoder.joblib")

# ------------------------------------------------------------------------------
# 1. EVALUATE VENTURE RISK DNN (Test Split = 15%)
# ------------------------------------------------------------------------------
print("\n[*] Evaluating Venture Risk DNN on independent test set...")
df_fin = pd.read_csv("financial_dataset.csv")
X_risk = df_fin[scalers["feature_cols_risk"]].copy()
y_risk = df_fin["is_successful"].values

_, X_r_temp, _, y_r_temp = train_test_split(
    X_risk, y_risk, test_size=0.30, random_state=42, stratify=y_risk
)
X_r_val, X_r_test, y_r_val, y_r_test = train_test_split(
    X_r_temp, y_r_temp, test_size=0.50, random_state=42, stratify=y_r_temp
)

X_r_test_scaled = scalers["scaler_risk"].transform(X_r_test)
y_r_pred_prob = risk_dnn.predict_proba(X_r_test_scaled)[:, 1]
y_r_pred = risk_dnn.predict(X_r_test_scaled)

auc_risk = roc_auc_score(y_r_test, y_r_pred_prob)
brier_risk = brier_score_loss(y_r_test, y_r_pred_prob)
prec_risk = precision_score(y_r_test, y_r_pred)
rec_risk = recall_score(y_r_test, y_r_pred)

print(f"  [+] Held-Out Test ROC-AUC: {auc_risk:.4f}")
print(f"  [+] Brier Calibration Score: {brier_risk:.4f}")
print(f"  [+] Precision: {prec_risk*100:.2f}% | Recall: {rec_risk*100:.2f}%")

# ------------------------------------------------------------------------------
# 2. EVALUATE ANOMALY AUTOENCODER (Test Split = 15%)
# ------------------------------------------------------------------------------
print("\n[*] Evaluating Anomaly Autoencoder on independent test set...")
df_user = pd.read_csv("user_behavior_dataset.csv")
X_user = df_user[scalers["feature_cols_anomaly"]].copy()
y_user = df_user["is_bot"].values

_, X_u_temp, _, y_u_temp = train_test_split(
    X_user, y_user, test_size=0.30, random_state=42, stratify=y_user
)
X_u_val, X_u_test, y_u_val, y_u_test = train_test_split(
    X_u_temp, y_u_temp, test_size=0.50, random_state=42, stratify=y_u_temp
)

X_u_val_scaled = scalers["scaler_user"].transform(X_u_val)
X_u_test_scaled = scalers["scaler_user"].transform(X_u_test)

# Calibrate tau_norm on validation honest nodes
val_honest = X_u_val_scaled[y_u_val == 0]
val_recon = autoencoder.predict(val_honest)
val_errors = np.mean((val_honest - val_recon) ** 2, axis=1)
tau_norm = float(np.percentile(val_errors, 95))

# Test reconstruction
test_recon = autoencoder.predict(X_u_test_scaled)
test_errors = np.mean((X_u_test_scaled - test_recon) ** 2, axis=1)
b_u_scores = np.clip(test_errors / max(tau_norm, 1e-6), 0.0, 1.0)

auc_anomaly = roc_auc_score(y_u_test, b_u_scores)
tau_Anomaly = 0.65
y_u_pred_anomaly = (b_u_scores >= tau_Anomaly).astype(int)

tn, fp, fn, tp = confusion_matrix(y_u_test, y_u_pred_anomaly).ravel()
tpr_anomaly = tp / (tp + fn)
fpr_anomaly = fp / (fp + tn)

print(f"  [+] Calibrated tau_norm threshold: {tau_norm:.6f}")
print(f"  [+] Held-Out Test ROC-AUC: {auc_anomaly:.4f}")
print(
    f"  [+] At tau_Anomaly = {tau_Anomaly:.2f} -> Detection Rate (TPR):"
    f" {tpr_anomaly*100:.2f}% | FPR: {fpr_anomaly*100:.2f}%"
)

# ------------------------------------------------------------------------------
# 3. EXPORT TABLE 2b AND FIGURE 7
# ------------------------------------------------------------------------------
df_table2b = pd.DataFrame(
    [
        {
            "Model Component": "Validator Anomaly Autoencoder (B(u))",
            "Ground-Truth Target": "is_bot (0: Honest, 1: Sybil / Malicious)",
            "Input Dimension": "3 Telemetry Features",
            "Train / Val / Test Split": (
                "420,000 / 90,000 / 90,000 traces (70/15/15)"
            ),
            "Test ROC-AUC": round(auc_anomaly, 4),
            "Detection Rate (TPR)": f"{tpr_anomaly*100:.2f}%",
            "False Alarm Rate (FPR)": f"{fpr_anomaly*100:.2f}%",
            "Calibration / Loss Metric": (
                f"tau_norm = {tau_norm:.6f} (MSE ="
                f" {val_errors.mean():.6f})"
            ),
        },
        {
            "Model Component": "Venture Risk DNN (R(p))",
            "Ground-Truth Target": "is_successful (1: Solvent, 0: Defaulted)",
            "Input Dimension": "6 Financial Indicators",
            "Train / Val / Test Split": (
                "350,000 / 75,000 / 75,000 samples (70/15/15)"
            ),
            "Test ROC-AUC": round(auc_risk, 4),
            "Detection Rate (TPR)": f"{rec_risk*100:.2f}%",
            "False Alarm Rate (FPR)": f"{(1.0-prec_risk)*100:.2f}%",
            "Calibration / Loss Metric": (
                f"Brier Score = {brier_risk:.4f} (Sigmoid)"
            ),
        },
    ]
)
df_table2b.to_csv("Table_2b_AI_Validation_Metrics.csv", index=False)
print("\n[+] Table 2b saved as Table_2b_AI_Validation_Metrics.csv")

# Plot Figure 7
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))

fpr_a, tpr_a, _ = roc_curve(y_u_test, b_u_scores)
ax1.plot([0, 1], [0, 1], "k--", alpha=0.5, label="Random Guessing (AUC = 0.50)")
ax1.plot(
    fpr_a,
    tpr_a,
    color="#1f77b4",
    linewidth=2.8,
    label=f"Autoencoder B(u) (AUC = {auc_anomaly:.3f})",
)
ax1.scatter(
    [fpr_anomaly],
    [tpr_anomaly],
    color="red",
    s=70,
    zorder=5,
    label=f"Operational Threshold (tau = {tau_Anomaly})",
)
ax1.set_title(
    "A. Validator Telemetry Anomaly Detection", fontsize=12, fontweight="bold"
)
ax1.set_xlabel("False Positive Rate (FPR)", fontsize=11)
ax1.set_ylabel("True Positive Rate (TPR / Recall)", fontsize=11)
ax1.legend(loc="lower right", fontsize=10, shadow=True)
ax1.grid(True, linestyle=":", alpha=0.6)

fpr_r, tpr_r, _ = roc_curve(y_r_test, y_r_pred_prob)
ax2.plot([0, 1], [0, 1], "k--", alpha=0.5, label="Random Guessing (AUC = 0.50)")
ax2.plot(
    fpr_r,
    tpr_r,
    color="#2ca02c",
    linewidth=2.8,
    label=f"Venture Risk DNN R(p) (AUC = {auc_risk:.3f})",
)
ax2.set_title(
    "B. Predictive Venture Solvency Classification",
    fontsize=12,
    fontweight="bold",
)
ax2.set_xlabel("False Positive Rate (FPR)", fontsize=11)
ax2.set_ylabel("True Positive Rate (TPR / Recall)", fontsize=11)
ax2.legend(loc="lower right", fontsize=10, shadow=True)
ax2.grid(True, linestyle=":", alpha=0.6)

plt.suptitle(
    "Figure 7 | Empirical Receiver Operating Characteristic (ROC) of Off-Chain"
    " AI Meta-Layer",
    fontsize=13,
    fontweight="bold",
    y=1.02,
)
plt.tight_layout()
plt.savefig("Figure_7_AI_Anomaly_and_Risk_ROC.png", dpi=300, bbox_inches="tight")
print("[+] Figure 7 saved as Figure_7_AI_Anomaly_and_Risk_ROC.png")