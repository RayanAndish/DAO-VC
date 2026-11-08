"""
Data/fig2_roc.py
================
Builds Figure 2 of the manuscript: held-out ROC curves of the telemetry
autoencoder B(u) and the venture risk network R(p).

It reads the artifacts written by Data/3_train_models.py (protocol v2) and
reproduces the test split exactly as that script does:
  * R(p): the cohort file has a 'split' column (train / val / test). The test
    rows are used. Features burn_rate, requested_amount, tam are log1p-transformed
    before the scaler saved in models/scalers.joblib (key 'scaler_risk').
  * B(u): user_behavior_clean.csv is split 70/15/15, stratified, random_state 42,
    exactly as in 3_train_models.py. The score is the mean squared reconstruction
    error on the 8 standardised features (key 'scaler_user').
  * The cutoff tau is read from models/threshold.json and is re-derived as the
    99th percentile of honest validation errors. The two values must agree.

The script writes the figure only if the recomputed metrics agree with
models/train_report.json. Nothing is drawn from memory.

Run from the folder that contains 3_train_models.py:
    python fig2_roc.py
"""

import json
import sys
from pathlib import Path

import joblib
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import torch  # noqa: E402
import torch.nn as nn  # noqa: E402
from sklearn.metrics import confusion_matrix, roc_auc_score, roc_curve  # noqa: E402
from sklearn.model_selection import train_test_split  # noqa: E402

HERE = Path(__file__).resolve().parent
COHORT = HERE / "cohorts" / "venture_cohort_primary.csv"
USER = HERE / "user_behavior_clean.csv"
MODELS = HERE / "models"
OUT = HERE / "figures" / "Figure_2_ROC_AI_Meta_Layer.png"

SEED = 42
RISK_FEATS = ["burn_rate", "requested_amount", "milestone_count", "team_experience", "prev_funding", "tam"]
RISK_LOG = ["burn_rate", "requested_amount", "tam"]
ANOM_FEATS = ["log_transaction_count", "balance_native", "log_total_gas_used", "log_latency_ms",
              "tx_entropy", "packet_drop_ratio", "vote_clustering", "uptime_ratio"]
THRESHOLD_QUANTILE = 0.99


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


def require(p):
    if not p.exists():
        sys.exit(f"[-] missing: {p}. Run 3_train_models.py first.")
    return p


def recon_errors(model, X):
    model.eval()
    with torch.no_grad():
        x = torch.tensor(X, dtype=torch.float32)
        return ((model(x) - x) ** 2).mean(dim=1).numpy()


def main():
    thr = json.loads(require(MODELS / "threshold.json").read_text(encoding="utf-8"))
    report = json.loads(require(MODELS / "train_report.json").read_text(encoding="utf-8"))
    tau = float(thr["tau"])
    scalers = joblib.load(require(MODELS / "scalers.joblib"))

    # ---- R(p): test rows as stored in the cohort -----------------------------
    cohort = pd.read_csv(require(COHORT))
    Xr = cohort[RISK_FEATS].astype(float).copy()
    for c in RISK_LOG:
        Xr[c] = np.log1p(Xr[c])
    is_te = (cohort["split"] == "test").values
    y_te_r = cohort["label_default"].values[is_te].astype(int)
    Xr_te = scalers["scaler_risk"].transform(Xr.values[is_te])

    risk = VentureRiskDNN(input_dim=len(RISK_FEATS))
    risk.load_state_dict(torch.load(require(MODELS / "venture_risk_dnn.pt"), map_location="cpu"))
    risk.eval()
    with torch.no_grad():
        p_te = risk(torch.tensor(Xr_te, dtype=torch.float32)).numpy().ravel()
    auc_r = roc_auc_score(y_te_r, p_te)
    fpr_r, tpr_r, _ = roc_curve(y_te_r, p_te)

    # ---- B(u): same split as 3_train_models.py ----------------------------
    user = pd.read_csv(require(USER))
    Xu = user[ANOM_FEATS].astype(float).values
    yu = user["is_bot"].astype(int).values
    X_tr, X_tmp, y_tr, y_tmp = train_test_split(Xu, yu, test_size=0.30, random_state=SEED, stratify=yu)
    X_va, X_te, y_va, y_te = train_test_split(X_tmp, y_tmp, test_size=0.50, random_state=SEED, stratify=y_tmp)

    ae = AnomalyAutoencoder(input_dim=len(ANOM_FEATS))
    ae.load_state_dict(torch.load(require(MODELS / "telemetry_autoencoder.pt"), map_location="cpu"))
    ae.eval()

    su = scalers["scaler_user"]
    err_va_honest = recon_errors(ae, su.transform(X_va[y_va == 0]))
    tau_check = float(np.quantile(err_va_honest, THRESHOLD_QUANTILE))
    if abs(tau_check - tau) > 1e-6:
        sys.exit(f"[-] tau from threshold.json ({tau:.8f}) differs from the honest validation "
                 f"99th percentile ({tau_check:.8f}). Figure not written.")

    err_te = recon_errors(ae, su.transform(X_te))
    auc_b = roc_auc_score(y_te, err_te)
    fpr_b, tpr_b, _ = roc_curve(y_te, err_te)
    flag = err_te >= tau
    tn, fp, fn, tp = confusion_matrix(y_te, flag.astype(int), labels=[0, 1]).ravel()
    tpr_tau, fpr_tau = tp / (tp + fn), fp / (fp + tn)

    # ---- verify against the training report --------------------------------
    rt = report["risk_model_test"]
    at = report["anomaly_model_test"]
    checks = [
        ("R(p) test AUC", round(auc_r, 4), rt["auc_vs_label"]),
        ("R(p) test n", int(is_te.sum()), rt["n"]),
        ("B(u) test AUC", round(auc_b, 4), at["auc_vs_is_bot"]),
        ("B(u) test n", int(len(y_te)), at["n"]),
        ("B(u) TPR at tau", round(tpr_tau, 4), at["detection_rate"]),
        ("B(u) FPR at tau", round(fpr_tau, 4), at["false_alarm_rate"]),
    ]
    bad = False
    print(f"{'metric':22s} {'recomputed':>12s} {'report':>12s}")
    for name, got, ref in checks:
        ok = abs(float(got) - float(ref)) < 5e-5
        bad |= not ok
        print(f"{name:22s} {got:12} {ref:12}  {'OK' if ok else 'MISMATCH'}")
    if bad:
        sys.exit("[-] recomputed metrics differ from train_report.json. Figure not written.")

    # ---- figure ----------------------------------------------------------
    plt.rcParams["font.family"] = "sans-serif"
    plt.rcParams["font.sans-serif"] = ["DejaVu Sans", "Arial"]
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4.8))

    ax1.plot([0, 1], [0, 1], "k--", alpha=0.5, label="Random guessing (AUC = 0.5000)")
    ax1.plot(fpr_b, tpr_b, color="#1f77b4", linewidth=2.4,
             label=f"Autoencoder B(u) (AUC = {auc_b:.4f})")
    ax1.scatter([fpr_tau], [tpr_tau], color="red", s=70, zorder=5, edgecolor="black",
                label=f"Cutoff τ = {tau:.6f} (FPR = {fpr_tau * 100:.2f}%, TPR = {tpr_tau * 100:.1f}%)")
    ax1.set_title("A. Telemetry anomaly score B(u)\n(simulated bot traffic, n = 90,000)")

    ax2.plot([0, 1], [0, 1], "k--", alpha=0.5, label="Random guessing (AUC = 0.5000)")
    ax2.plot(fpr_r, tpr_r, color="#2ca02c", linewidth=2.4,
             label=f"Venture risk R(p) (AUC = {auc_r:.4f})")
    ax2.set_title(f"B. Venture risk score R(p)\n(synthetic cohort, n = {int(is_te.sum()):,})")

    for ax in (ax1, ax2):
        ax.set_xlabel("False positive rate (FPR)")
        ax.set_ylabel("True positive rate (TPR)")
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1.02)
        ax.grid(True, linestyle=":", alpha=0.5)
        ax.legend(loc="lower right", fontsize=8.5, frameon=False)

    fig.tight_layout()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT, dpi=300)
    plt.close(fig)
    print(f"[+] wrote {OUT}")


if __name__ == "__main__":
    main()
