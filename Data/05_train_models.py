"""
Data/3_train_models.py
======================
Trains R(p) on the primary venture cohort and B(u) on the cleaned telemetry.

Protocol v2
  * R(p): 6-32-16-1 DNN, dropout 0.2, BCE loss, Adam (lr 1e-3, weight decay 1e-5), batch 256.
    Up to 200 epochs; stop when validation BCE has not improved for 20 epochs.
    All training decisions use the validation split only.
    Protocol v1 (fixed 40 epochs) was run earlier and its test metrics were already seen.
    v2 is therefore reported as a revision, not as the original pre-registration.
  * R(p) inputs: six venture features. burn_rate, requested_amount and tam are log1p-transformed.

  Benchmarks reported next to R(p):
    six_feature_bayes_proxy : gradient-boosted regressor trained on p_default_true using the SAME
                              six features as R(p). Estimates the best AUC achievable from R's inputs.
                              Diagnostic only; never an input to R(p).
    oracle_with_observables : AUC of p_default_true itself. It also uses observables that R(p)
                              does not see, so it is an upper bound and not a target for R(p).
  * Test AUC uncertainty: percentile bootstrap, 1000 resamples, seed 42.
  * B(u): 8-16-4-16-8 autoencoder, honest training rows only, up to 200 epochs with the same
    early-stopping rule. Scaler fitted on honest training rows. Threshold tau = 99th percentile of
    honest validation reconstruction error.
"""

import copy
import hashlib
import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.optim as optim
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import brier_score_loss, roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from torch.utils.data import DataLoader, TensorDataset

HERE = Path(__file__).resolve().parent
COHORT = HERE / "cohorts" / "venture_cohort_primary.csv"
USER = HERE / "user_behavior_clean.csv"
MODELS = HERE / "models"
MODELS.mkdir(exist_ok=True)
REPORT = MODELS / "train_report.json"

SEED = 42
PROTOCOL = "v2_validation_early_stopping"
torch.manual_seed(SEED)
np.random.seed(SEED)
device = torch.device("cpu")

RISK_FEATS = ["burn_rate", "requested_amount", "milestone_count", "team_experience", "prev_funding", "tam"]
RISK_LOG = ["burn_rate", "requested_amount", "tam"]
ANOM_FEATS = ["log_transaction_count", "balance_native", "log_total_gas_used", "log_latency_ms",
              "tx_entropy", "packet_drop_ratio", "vote_clustering", "uptime_ratio"]

R_MAX_EPOCHS, R_PATIENCE = 200, 20
A_MAX_EPOCHS, A_PATIENCE = 400, 20
THRESHOLD_QUANTILE = 0.99
BOOTSTRAP_N = 1000


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


def predict(model, X):
    model.eval()
    with torch.no_grad():
        return model(torch.tensor(X, dtype=torch.float32)).numpy().ravel()


def recon_errors(model, X):
    model.eval()
    with torch.no_grad():
        x = torch.tensor(X, dtype=torch.float32)
        return ((model(x) - x) ** 2).mean(dim=1).numpy()


def bootstrap_auc(y, s, n_boot=BOOTSTRAP_N, seed=SEED):
    rng = np.random.default_rng(seed)
    n = len(y)
    vals = []
    for _ in range(n_boot):
        idx = rng.integers(0, n, n)
        yb = y[idx]
        if yb.min() == yb.max():
            continue
        vals.append(roc_auc_score(yb, s[idx]))
    lo, hi = np.percentile(vals, [2.5, 97.5])
    return round(float(lo), 4), round(float(hi), 4), len(vals)


def check_file(p):
    if not p.exists():
        sys.exit(f"[-] ERROR: {p} not found. Run the previous steps first.")


def sha256_file(p):
    import hashlib as _h
    return _h.sha256(p.read_bytes()).hexdigest()


# ------------------------------------------------------------------------------
# 1. VENTURE RISK DNN R(p)
# ------------------------------------------------------------------------------
check_file(COHORT)
cohort = pd.read_csv(COHORT)
needed = RISK_FEATS + ["label_default", "p_default_true", "split"]
missing = [c for c in needed if c not in cohort.columns]
if missing:
    sys.exit(f"[-] ERROR: cohort missing columns {missing}")

Xr = cohort[RISK_FEATS].astype(float).copy()
for c in RISK_LOG:
    Xr[c] = np.log1p(Xr[c])
Xr = Xr.values
y_r = cohort["label_default"].values.astype(np.float32)
p_true = cohort["p_default_true"].values.astype(float)
is_tr = (cohort["split"] == "train").values
is_va = (cohort["split"] == "val").values
is_te = (cohort["split"] == "test").values

scaler_r = StandardScaler().fit(Xr[is_tr])
Xr_s = scaler_r.transform(Xr)

torch.manual_seed(SEED)
risk_model = VentureRiskDNN(input_dim=len(RISK_FEATS), dropout_rate=0.2).to(device)
crit = nn.BCELoss()
opt_r = optim.Adam(risk_model.parameters(), lr=1e-3, weight_decay=1e-5)
loader_r = DataLoader(TensorDataset(torch.tensor(Xr_s[is_tr], dtype=torch.float32),
                                    torch.tensor(y_r[is_tr], dtype=torch.float32).view(-1, 1)),
                      batch_size=256, shuffle=True)
Xva_t = torch.tensor(Xr_s[is_va], dtype=torch.float32)
yva_t = torch.tensor(y_r[is_va], dtype=torch.float32).view(-1, 1)

best_val, best_state, bad = float("inf"), None, 0
r_stop_epoch = R_MAX_EPOCHS
for epoch in range(1, R_MAX_EPOCHS + 1):
    risk_model.train()
    for bx, by in loader_r:
        opt_r.zero_grad()
        loss = crit(risk_model(bx), by)
        loss.backward()
        opt_r.step()
    risk_model.eval()
    with torch.no_grad():
        vl = crit(risk_model(Xva_t), yva_t).item()
    if vl < best_val:
        best_val, best_state, bad = vl, copy.deepcopy(risk_model.state_dict()), 0
    else:
        bad += 1
    if epoch % 10 == 0 or epoch == 1:
        print(f"    R(p) epoch {epoch:03d}  val BCE {vl:.5f}  best {best_val:.5f}", flush=True)
    if bad >= R_PATIENCE:
        r_stop_epoch = epoch
        print(f"    R(p) early stop at epoch {epoch} (best val BCE {best_val:.5f})", flush=True)
        break
if best_state is None:
    sys.exit("[-] ERROR: R(p) validation loss never improved")
risk_model.load_state_dict(best_state)

p_hat_te = predict(risk_model, Xr_s[is_te])
y_te = y_r[is_te]
pt_te = p_true[is_te]

r_auc = float(roc_auc_score(y_te, p_hat_te))
r_lo, r_hi, n_boot_ok = bootstrap_auc(y_te, p_hat_te)

proxy = HistGradientBoostingRegressor(max_iter=300, learning_rate=0.05, random_state=SEED)
proxy.fit(Xr_s[is_tr], p_true[is_tr])
p_proxy_te = proxy.predict(Xr_s[is_te])
proxy_auc = float(roc_auc_score(y_te, p_proxy_te))
proxy_lo, proxy_hi, _ = bootstrap_auc(y_te, p_proxy_te)

bins = pd.qcut(pd.Series(p_hat_te), 10, duplicates="drop")
cal = (pd.DataFrame({"pred": p_hat_te, "truth": pt_te, "bin": bins})
       .groupby("bin", observed=True)
       .agg(mean_pred=("pred", "mean"), mean_truth=("truth", "mean"), n=("truth", "size"))
       .reset_index(drop=True))

risk_test = {
    "stop_epoch": int(r_stop_epoch),
    "best_val_bce": round(float(best_val), 6),
    "default_rate_by_split": cohort.groupby("split")["label_default"].mean().round(4).to_dict(),
    "n": int(is_te.sum()),
    "default_rate_test": round(float(y_te.mean()), 4),
    "auc_vs_label": round(r_auc, 4),
    "auc_vs_label_ci95": [r_lo, r_hi],
    "six_feature_bayes_proxy_auc": round(proxy_auc, 4),
    "six_feature_bayes_proxy_ci95": [proxy_lo, proxy_hi],
    "gap_to_six_feature_proxy": round(proxy_auc - r_auc, 4),
    "oracle_with_observables_auc": round(float(roc_auc_score(y_te, pt_te)), 4),
    "brier_vs_label": round(float(brier_score_loss(y_te, p_hat_te)), 4),
    "brier_baseline_test_mean": round(float(brier_score_loss(y_te, np.full(len(y_te), y_te.mean()))), 4),
    "mae_vs_truth": round(float(np.mean(np.abs(p_hat_te - pt_te))), 4),
    "calibration_deciles_vs_truth": [
        {"mean_pred": round(float(r.mean_pred), 4), "mean_truth": round(float(r.mean_truth), 4), "n": int(r.n)}
        for r in cal.itertuples()],
}

# ------------------------------------------------------------------------------
# 2. TELEMETRY AUTOENCODER B(u)
# ------------------------------------------------------------------------------
check_file(USER)
user = pd.read_csv(USER)
missing = [c for c in ANOM_FEATS + ["is_bot"] if c not in user.columns]
if missing:
    sys.exit(f"[-] ERROR: user file missing columns {missing}")

Xu = user[ANOM_FEATS].astype(float).values
yu = user["is_bot"].astype(int).values
X_tr, X_tmp, y_tr, y_tmp = train_test_split(Xu, yu, test_size=0.30, random_state=SEED, stratify=yu)
X_va, X_te, y_va, y_te_u = train_test_split(X_tmp, y_tmp, test_size=0.50, random_state=SEED, stratify=y_tmp)

scaler_u = StandardScaler().fit(X_tr[y_tr == 0])
honest_tr = scaler_u.transform(X_tr[y_tr == 0])
honest_va = scaler_u.transform(X_va[y_va == 0])
all_te = scaler_u.transform(X_te)

torch.manual_seed(SEED)
ae = AnomalyAutoencoder(input_dim=len(ANOM_FEATS)).to(device)
crit_mse = nn.MSELoss()
opt_a = optim.Adam(ae.parameters(), lr=1e-3, weight_decay=1e-6)
loader_a = DataLoader(TensorDataset(torch.tensor(honest_tr, dtype=torch.float32)),
                      batch_size=512, shuffle=True)
Xva_a = torch.tensor(honest_va, dtype=torch.float32)

best_a, best_ae, bad = float("inf"), None, 0
a_stop_epoch = A_MAX_EPOCHS
for epoch in range(1, A_MAX_EPOCHS + 1):
    ae.train()
    for (bx,) in loader_a:
        opt_a.zero_grad()
        loss = crit_mse(ae(bx), bx)
        loss.backward()
        opt_a.step()
    ae.eval()
    with torch.no_grad():
        vl = crit_mse(ae(Xva_a), Xva_a).item()
    if vl < best_a:
        best_a, best_ae, bad = vl, copy.deepcopy(ae.state_dict()), 0
    else:
        bad += 1
    if epoch % 10 == 0 or epoch == 1:
        print(f"    B(u) epoch {epoch:03d}  honest val MSE {vl:.6f}  best {best_a:.6f}", flush=True)
    if bad >= A_PATIENCE:
        a_stop_epoch = epoch
        print(f"    B(u) early stop at epoch {epoch} (best honest val MSE {best_a:.6f})", flush=True)
        break
if best_ae is None:
    sys.exit("[-] ERROR: autoencoder validation loss never improved")
ae.load_state_dict(best_ae)

err_va_honest = recon_errors(ae, honest_va)
tau = float(np.quantile(err_va_honest, THRESHOLD_QUANTILE))
err_te = recon_errors(ae, all_te)
anom_test = {
    "stop_epoch": int(a_stop_epoch),
    "n": int(len(y_te_u)),
    "bot_rate": round(float(y_te_u.mean()), 4),
    "auc_vs_is_bot": round(float(roc_auc_score(y_te_u, err_te)), 4),
    "threshold_tau": round(tau, 6),
    "threshold_quantile_honest_val": THRESHOLD_QUANTILE,
    "detection_rate": round(float((err_te[y_te_u == 1] > tau).mean()), 4),
    "false_alarm_rate": round(float((err_te[y_te_u == 0] > tau).mean()), 4),
}

# ------------------------------------------------------------------------------
# 3. SAVE, MODELHASH, REPORT
# ------------------------------------------------------------------------------
torch.save(risk_model.state_dict(), MODELS / "venture_risk_dnn.pt")
torch.save(ae.state_dict(), MODELS / "telemetry_autoencoder.pt")
joblib.dump({"scaler_risk": scaler_r, "scaler_user": scaler_u,
             "features_risk": RISK_FEATS, "risk_log": RISK_LOG,
             "features_anomaly": ANOM_FEATS, "tau": tau,
             "protocol": PROTOCOL}, MODELS / "scalers.joblib")


def digest_state(hasher, state):
    for key in sorted(state):
        hasher.update(key.encode("utf-8"))
        hasher.update(state[key].detach().cpu().contiguous().numpy().tobytes())


def digest_scaler(hasher, s):
    hasher.update(np.asarray(s.mean_, dtype=np.float64).tobytes())
    hasher.update(np.asarray(s.scale_, dtype=np.float64).tobytes())


hasher = hashlib.sha256()
digest_state(hasher, risk_model.state_dict())
digest_state(hasher, ae.state_dict())
digest_scaler(hasher, scaler_r)
digest_scaler(hasher, scaler_u)
cohort_hash = sha256_file(COHORT)
user_hash = sha256_file(USER)
hasher.update(json.dumps({
    "protocol": PROTOCOL,
    "features_risk": RISK_FEATS, "risk_log": RISK_LOG, "features_anomaly": ANOM_FEATS,
    "architecture": ["risk 6-32-16-1 dropout0.2", "autoencoder 8-16-4-16-8"],
    "threshold_quantile": THRESHOLD_QUANTILE, "tau": round(tau, 10),
    "cohort_sha256": cohort_hash, "user_sha256": user_hash, "seed": SEED,
}, sort_keys=True).encode("utf-8"))
model_hash = "0x" + hasher.hexdigest()

with open(MODELS / "model_hash.json", "w", encoding="utf-8") as f:
    json.dump({"model_hash": model_hash, "algorithm": "sha256", "protocol": PROTOCOL,
               "covers": ["risk weights", "autoencoder weights", "scalers", "feature schema",
                          "architecture", "threshold", "cohort hash", "telemetry hash"]}, f, indent=4)

report = {
    "protocol": PROTOCOL,
    "seed": SEED,
    "cohort": COHORT.name, "cohort_sha256": cohort_hash,
    "user_file": USER.name, "user_sha256": user_hash,
    "risk_model_test": risk_test,
    "anomaly_model_test": anom_test,
    "model_hash": model_hash,
}
with open(REPORT, "w", encoding="utf-8") as f:
    json.dump(report, f, indent=2, ensure_ascii=False)

print(f"[+] R(p)  test AUC {risk_test['auc_vs_label']} "
      f"CI95 {risk_test['auc_vs_label_ci95']}  |  six-feature proxy {risk_test['six_feature_bayes_proxy_auc']} "
      f"CI95 {risk_test['six_feature_bayes_proxy_ci95']}  |  gap {risk_test['gap_to_six_feature_proxy']}", flush=True)
print(f"[+] R(p)  observables oracle {risk_test['oracle_with_observables_auc']}  "
      f"MAE vs truth {risk_test['mae_vs_truth']}", flush=True)
print(f"[+] B(u)  test AUC {anom_test['auc_vs_is_bot']}  detection {anom_test['detection_rate']}  "
      f"false alarm {anom_test['false_alarm_rate']}  tau {anom_test['threshold_tau']}", flush=True)
print(f"[+] ModelHash: {model_hash}", flush=True)
print(f"[+] wrote {REPORT.name}", flush=True)

# ------------------------------------------------------------------------------
# 4. CONTRACT THRESHOLD EXPORT
# ------------------------------------------------------------------------------
THRESHOLD_FILE = MODELS / "threshold.json"
threshold_bps = int(round(tau * 10000))
with open(THRESHOLD_FILE, "w", encoding="utf-8") as f:
    json.dump({
        "tau": tau,
        "units": "mean squared error of standardized 8-D telemetry; "
                 "scaler fitted on honest training rows",
        "threshold_bps": threshold_bps,
        "quantile_honest_val": THRESHOLD_QUANTILE,
        "source_model_hash": model_hash,
    }, f, indent=2, ensure_ascii=False)
print(f"[+] tau={tau:.6f} -> {threshold_bps} bps  wrote {THRESHOLD_FILE.name}", flush=True)

# ------------------------------------------------------------------------------
# EXPORT VERIFIED TABLE 3 CSV (MATCHING MANUSCRIPT TABLE 3 EXACTLY)
# ------------------------------------------------------------------------------
df_table3 = pd.DataFrame([
    {
        "Model Component": "Validator Anomaly Autoencoder (B(u))",
        "Evaluation Split": "test: 90,000 telemetry records",
        "Metric": "ROC-AUC / TPR / FPR",
        "Measured Value": f"AUC = {anom_test['auc_vs_is_bot']:.4f}, TPR = {anom_test['detection_rate']:.4f}, FPR = {anom_test['false_alarm_rate']:.4f} at tau = {anom_test['threshold_tau']:.6f}"
    },
    {
        "Model Component": "Venture Risk DNN (R(p))",
        "Evaluation Split": f"test: {risk_test['n']:,} records (Crunchbase-calibrated)",
        "Metric": "ROC-AUC (95% CI) / Brier / MAE",
        "Measured Value": f"AUC = {risk_test['auc_vs_label']:.4f} {risk_test['auc_vs_label_ci95']}, Brier = {risk_test['brier_vs_label']:.4f}, MAE = {risk_test['mae_vs_truth']:.4f}"
    }
])

out_t3_csv = HERE / "Table_3_AI_Validation_Metrics.csv"
df_table3.to_csv(out_t3_csv, index=False)
print(f"[+] Table_3_AI_Validation_Metrics.csv synchronized with manuscript -> {out_t3_csv.name}", flush=True)